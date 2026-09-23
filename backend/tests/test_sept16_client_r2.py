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

LF = chr(10)
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
    body = _method_body(api, "private static IEnumerator PostRequestWithRetryAnswered")
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

def fallback(outcome, gone):
    """What the WATCHING seat does.

    `outcome` is the last cr_dcr value it latched for this series: "" (the
    elected seat has said nothing), "send", "ok", "no" or "unk".  `gone` is
    whether that seat has left the room.

    Returns "nothing", "stand-down", or "post" -- and "post" always means the
    zero-total form.

    There is NO server_status parameter any more, and its removal is this
    round's first fix.  The previous model asked GET /team/series/{id}/state
    before posting, on the assumption that a GET cannot change anything.  That
    endpoint CANCELS series: its first arm writes status='canceled',
    invalidation_reason='assembly_timeout' and reconciles bets whenever the row
    reads 'active' with fewer than four spawn-confirms, past the 180 s deadline,
    with no in-process live-game evidence -- all three of which a healthy,
    partly-played 2v2 reaches (a lost spawn-confirm POST, or the bug-245 relock
    that writes spawn_confirmations=0 and room_issued_at=NULL; and the live-game
    dict is empty for minutes after every api restart).  The pre-check meant to
    make the post safe was the most destructive call on the path.

    ONE signal posts now.  `unk` and a departed seat are both NOT terminal --
    see the tests below for what each of them used to cost.
    """
    if outcome == "ok":
        return "stand-down"                       # terminal: the server answered
    if gone:
        # BEFORE the "no" arm, and the ordering is the rule rather than a
        # detail.  A seat that published "no" and then left is observed in ONE
        # callback, and that departure is itself a disconnect in this same
        # series: the election runs again for it and a REAL-TOTALS prompt report
        # is composed in a process this watch holds no property from.  Whatever
        # the seat had said, its absence is the more recent fact.
        return "stand-down"
    if outcome == "no":
        # TERMINAL the other way, and the only trigger there is.  Every attempt
        # of that seat's report was answered and refused, or nothing ever left
        # its process: nothing landed and nothing is still running.  No
        # pre-check -- the report endpoint re-reads the row FOR NO KEY UPDATE
        # and answers {"ignored": true} on a settled series without writing.
        return "post"
    if outcome == "unk":
        # An attempt went UNANSWERED, so a handler may still be running and may
        # still commit.  The client's own timeout abandoned the connection; it
        # did not cancel the transaction.
        return "nothing"
    # still in the room, silent or with a request in flight: not terminal.
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
        return bool(b) and "WaitForSeconds" not in b and "PostRequestWithRetryAnswered(url" in b

    _assert_discriminating(
        claim, api,
        _mutate(api,
                "            yield return Plugin.Instance.StartCoroutine(PostRequestWithRetryAnswered(url",
                "            yield return new WaitForSecondsRealtime(45f);\n"
                "            yield return Plugin.Instance.StartCoroutine(PostRequestWithRetryAnswered(url",
                "H1 elapsed-time net"),
        "H1 no elapsed-time arming")


def test_h1_the_fallback_fires_only_on_a_terminal_outcome():
    """Every state the watching seat can be in, and what it does there.

    EXACTLY ONE cell posts.  `no` is the only signal that means both "nothing
    landed" and "nothing is still running"; every other cell leaves a
    transaction this seat cannot see, so it posts nothing at all."""
    for gone in (False, True):
        # terminal: the server answered the prompt report
        assert fallback("ok", gone) == "stand-down"
        # NOT terminal: an attempt went unanswered and a handler may still run.
        # Present, that is "nothing"; gone, the departure arm answers first and
        # calls it "stand-down" -- different words, and neither one posts, which
        # is the only distinction that reaches the server.
        assert fallback("unk", gone) != "post"
    assert fallback("unk", False) == "nothing"
    # the ONE trigger
    assert fallback("no", False) == "post"
    # still here and not terminal, in both shapes
    assert fallback("", False) == "nothing"          # silent so far
    assert fallback("send", False) == "nothing"      # in flight
    # gone: never a trigger, WHATEVER it had said -- including a latched "no",
    # because NoteActorLeft reports the last value and the departure together
    # and the departure is itself a new disconnect in this same series
    for said in ("", "send", "no"):
        assert fallback(said, True) == "stand-down"
    # exactly one cell of the whole table posts
    posts = [(o, g) for o in ("", "send", "ok", "no", "unk") for g in (False, True)
             if fallback(o, g) == "post"]
    assert posts == [("no", False)], posts

    # and the source runs the same table
    ra = _src("RoomActors.cs")
    body = ra[ra.index("private static void Evaluate(string why)"):]
    body = body[:body.index("/// <summary>Post the fallback. NO PRE-CHECK.")]
    assert "_watchOutcome == OutcomeAnswered" in body
    assert "_watchOutcome == OutcomeFailed" in body
    assert "_watchOutcome == OutcomeUnknown" in body
    # the two arms that used to fire and no longer exist in any form
    assert "_watchGone && _watchOutcome.Length == 0" not in body
    assert "_watchGone && _watchOutcome == OutcomeSent" not in body
    # Fire() is reachable from the OutcomeFailed arm and from nowhere else...
    assert body.count("Fire(") == 1
    assert body.index("_watchOutcome == OutcomeFailed") < body.index("Fire(")
    # ...and the departure arm is checked BEFORE it, so a latched "no" observed
    # together with the departure stands down instead of firing
    assert body.index("if (_watchGone)") < body.index("_watchOutcome == OutcomeFailed")

    def claim(s):
        if "private static void Evaluate(string why)" not in s:
            return False
        b = s[s.index("private static void Evaluate(string why)"):]
        cut = "/// <summary>Post the fallback. NO PRE-CHECK."
        b = b[:b.index(cut)] if cut in b else b
        return b.count("Fire(") == 1 and "_watchOutcome == OutcomeUnknown" in b

    # the mutation that reopens the closed defect: make the departure fire again
    _assert_discriminating(
        claim, ra,
        _mutate(ra, "                _watchSettled = true;\n"
                    '                Plugin.Log.LogInfo("[2v2-DC] fallback STOOD DOWN (" + why + ") — the elected seat "',
                    "                _watchSettled = true;\n"
                    '                Fire("the elected seat left");\n'
                    '                Plugin.Log.LogInfo("[2v2-DC] fallback STOOD DOWN (" + why + ") — the elected seat "',
                    "H1 terminal table"),
        "H1 terminal-outcome table")

    # NEGATIVE CONTROL: a mutation that does NOT touch the table must leave the
    # claim true, or the claim is just detecting that the file changed (#391).
    assert claim(_mutate(ra, "[2v2-DC] fallback WAITING (", "[2v2-DC] fallback HOLDING (",
                         "H1 table negative control"))


def test_h1_an_unanswered_attempt_is_not_a_terminal_outcome():
    """`request.timeout` is a CLIENT-side deadline.  It abandons our end of the
    connection; it never reaches the server and it does not cancel the handler,
    which runs to completion and commits.

    So publishing `no` on a client-observed timeout announced a terminal outcome
    of a transaction that was still live, and the watching seat posted its
    zero-total fallback beside it.  If the fallback took the row lock first it
    wrote dc_incomplete, and the real report behind it was answered
    {"ignored": true} -- a rated lead-forfeit lost.  The failure boolean had to
    be split before the table above could mean anything (#430: one boolean must
    not mean both "the server said no" and "we never heard back")."""
    api = _src("ApiClient.cs")

    # the retry helper MEASURES it rather than inferring it from the error text,
    # and accumulates it across attempts: attempt 1 timing out and attempt 3
    # receiving a 400 still leaves attempt 1's handler running.
    body = _method_body(api, "private static IEnumerator PostRequestWithRetryAnswered")
    assert body, "the retry helper's own text could not be delimited"
    assert "if (request.responseCode <= 0) allAnswered = false;" in body
    assert body.count("bool allAnswered = true;") == 1
    # accumulated, not recomputed per attempt: the reset would have to be inside
    # the loop, and there is no second assignment anywhere in the method.
    assert body.count("allAnswered =") == 2     # the declaration and the one clear

    # ...and the dispatch turns it into the third property value
    dispatch = _method_body(api, "private static IEnumerator SendTeamSeriesDcReport")
    assert dispatch, "the dispatch method's own text could not be delimited"
    assert "answered ? DcReportSync.OutcomeFailed" in dispatch
    assert ": DcReportSync.OutcomeUnknown" in dispatch

    # the model: only the answered failure is terminal
    assert fallback("no", False) == "post"
    assert fallback("unk", False) == "nothing"

    def claim(s):
        b = _method_body(s, "private static IEnumerator PostRequestWithRetryAnswered")
        d = _method_body(s, "private static IEnumerator SendTeamSeriesDcReport")
        return (bool(b) and bool(d)
                and "if (request.responseCode <= 0) allAnswered = false;" in b
                and "DcReportSync.OutcomeUnknown" in d)

    # the mutation that restores the defect: call every failure terminal again
    _assert_discriminating(
        claim, api,
        _mutate(api, "                           : answered ? DcReportSync.OutcomeFailed\n"
                     "                                      : DcReportSync.OutcomeUnknown);",
                "                           : DcReportSync.OutcomeFailed);",
                "H1 unanswered attempt"),
        "H1 unanswered is not terminal")

    # NEGATIVE CONTROL
    assert claim(_mutate(api, "(every attempt answered=", "(all answered=",
                         "H1 unanswered negative control"))


def test_h1_the_elected_seats_departure_is_itself_a_disconnect():
    """The arm that fired on "it left having dispatched nothing" was reasoning
    about ONE transaction: the one this watch was armed on.  The departure it
    fires on opens a SECOND one.

    A (team 2) disconnects; C is elected; D arms the watch on C.  C crashes
    before publishing anything.  Photon delivers OnPlayerLeftRoom(C) to B and D.
    DcReportSync.NoteActorLeft runs FIRST in that callback -- before the DC
    classification below it -- so on the old rule D fired a zero-total fallback,
    while the very same callback elected a reporter for C's departure who posts
    REAL totals against the SAME series.  Arrival order then chose between
    dc_incomplete and the rated completion, which is the defect statement the
    census arm exists to close."""
    plug = _src("Plugin.cs")
    left = plug[plug.index("public void OnPlayerLeftRoom(Photon.Realtime.Player p)"):]
    left = left[:left.index('Plugin.Log.LogWarning($"[2v2-DC] report error')]
    # the ordering the failure scenario rests on, asserted rather than assumed
    assert "DcReportSync.NoteActorLeft(p)" in left
    assert left.index("DcReportSync.NoteActorLeft(p)") < left.index("ApiClient.ReportTeamSeriesDc(")
    # ...and the elected seat's departure does reach the same prompt path
    assert "ApiClient.ReportTeamSeriesDc(seriesId, myId, dcSteamId, t1Points, t2Points," in left

    # so the watch stands down there instead of firing
    assert fallback("", True) == "stand-down"
    assert fallback("send", True) == "stand-down"

    ra = _src("RoomActors.cs")

    def claim(s):
        if "private static void Evaluate(string why)" not in s:
            return False
        b = s[s.index("private static void Evaluate(string why)"):]
        cut = "/// <summary>Post the fallback. NO PRE-CHECK."
        b = b[:b.index(cut)] if cut in b else b
        if "if (_watchGone)" not in b:
            return False
        # the arm's OWN span, not everything after it: the OutcomeFailed arm
        # below it legitimately calls Fire, and a slice that swallowed it would
        # be a claim that cannot hold rather than a claim that cannot fail.
        gone_arm = b[b.index("if (_watchGone)"):]
        end = "if (_watchOutcome == OutcomeFailed)"
        gone_arm = gone_arm[:gone_arm.index(end)] if end in gone_arm else gone_arm
        return "Fire(" not in gone_arm

    _assert_discriminating(
        claim, ra,
        _mutate(ra, '                Plugin.Log.LogInfo("[2v2-DC] fallback STOOD DOWN (" + why + ") — the elected seat "',
                '                Fire("the elected seat left having dispatched nothing");\n'
                '                Plugin.Log.LogInfo("[2v2-DC] fallback STOOD DOWN (" + why + ") — the elected seat "',
                "H1 departure arm"),
        "H1 departure is a new disconnect")

    # NEGATIVE CONTROL
    assert claim(_mutate(ra, "a zero-total post beside it would decide the outcome by arrival order",
                         "a zero-total post beside it would decide the series by arrival order",
                         "H1 departure negative control"))


def test_h1_a_fallback_can_never_be_the_report_that_rates_a_series():
    """The claim this round actually establishes, stated at the width it holds.

    THE BROADER CLAIM IS FALSE AND THE PREVIOUS VERSION OF THIS TEST ASSERTED
    IT.  "No ordering can select rated completion versus dc_incomplete" is not
    true of the pair and cannot be made true from inside one client.  The old
    body computed `after_fallback = endpoint("active", wins, 0)`, asserted it was
    "dc_incomplete", and then asserted the prompt report behind it stayed
    "dc_incomplete" for prompt_points up to 5 -- which IS an ordering selecting
    dc_incomplete over the rated completion, written down as though it were the
    proof of the opposite.

    What is true, and is proved here:
      * a fallback can never BE the report that rates a series.  Its form is
        zero totals and the endpoint's lead-forfeit branch needs >= 2, so the
        only row state it can reach is dc_incomplete, under every ordering.
      * a fallback arriving BEHIND a settled series changes nothing: the
        FOR NO KEY UPDATE reread answers {"ignored": true} without writing.

    What is NOT proved here, and is not claimed anywhere in the tree: that the
    two can never be in flight together.  The client-side table removes every
    schedule a seat can observe; a SECOND disconnect in the same series is a
    different seat's transaction and is closed by the server-lane rule recorded
    with this round, not by this test.  The test that used to carry the broader
    claim is directly below, reduced to what it can support."""
    for other_team_wins in (0, 1, 2):
        for prompt_points in (0, 1, 2, 5):
            # a fallback is never the rating report, whatever the lead
            assert endpoint("active", other_team_wins, 0) == "dc_incomplete"
            assert endpoint("dc_paused", other_team_wins, 0) == "dc_incomplete"
            # behind a settled series it writes nothing at all
            after_prompt = endpoint("active", other_team_wins, prompt_points)
            assert endpoint(after_prompt, other_team_wins, 0) == after_prompt

    # the negative control: a fallback carrying the prompt seat's real totals
    # DOES select the rated completion, which is what the zero form removes
    assert endpoint("active", 1, 3) == "completed"


def test_h1_the_displacement_the_client_half_cannot_close_is_recorded_not_hidden():
    """The residual, asserted as a residual.

    A zero-total fallback that takes the row lock FIRST writes dc_incomplete,
    and a real-totals report arriving behind it is answered {"ignored": true}.
    That is a rated lead-forfeit lost to a fallback -- displacement, in the
    direction the acceptance bar asked be proved impossible, and it is NOT
    impossible.  It is unreachable from any schedule one client can observe, and
    reachable in principle from a concurrent second disconnect.

    Direction check (#283): both seats that can emit the fallback are on the
    WINNING team, so the party that loses by the displacement is the party that
    caused it.  Nobody gains by withholding anything.  That is why the residual
    is survivable while the server rule is not yet written -- not why it is
    acceptable to leave unstated."""
    # the displacement is REAL against the deployed endpoint
    displaced = endpoint(endpoint("active", 1, 0), 1, 3)
    assert displaced == "dc_incomplete"
    # ...and the same pair in the other order does rate the series
    assert endpoint(endpoint("active", 1, 3), 1, 0) == "completed"
    # so arrival order does decide, and only the client-side table keeps the two
    # apart.  Exactly one cell of that table posts, and it is the cell in which
    # the elected seat's transaction is over.
    posts = [(o, g) for o in ("", "send", "ok", "no", "unk") for g in (False, True)
             if fallback(o, g) == "post"]
    assert posts == [("no", False)], posts

    # and the tree says so in both halves rather than claiming the closure
    ra = _src("RoomActors.cs")
    api = _src("ApiClient.cs")
    note = ra[ra.index("WHAT THE CLIENT HALF STILL CANNOT CLOSE"):]
    note = note[:note.index("internal const string OutcomeProp")]
    assert "SECOND disconnect" in note
    assert "server-lane note" in note
    assert "is NOT" in note and "claimed here" in note
    # the ApiClient paragraph that used to overclaim now states both halves
    doc = api[api.index("WHAT THE ZERO FORM DOES AND DOES NOT BUY"):]
    doc = doc[:doc.index("OUTCOME PUBLICATION")]
    assert "does NOT buy immunity from" in doc
    assert '{"ignored": true}' in doc

    def claim(s):
        if "WHAT THE CLIENT HALF STILL CANNOT CLOSE" not in s:
            return False
        n = s[s.index("WHAT THE CLIENT HALF STILL CANNOT CLOSE"):]
        n = n[:n.index("internal const string OutcomeProp")]
        return "SECOND disconnect" in n and "server-lane note" in n

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "        // WHAT THE CLIENT HALF STILL CANNOT CLOSE",
                "        // EVERY ORDERING IS CLOSED CLIENT-SIDE", "H1 residual"),
        "H1 residual is recorded")


def test_h1_the_form_holds_under_every_ordering_the_endpoint_distinguishes():
    """The FORM half, over every series state and every lead, both orders."""
    for other_team_wins in (0, 1, 2):
        for prompt_points in (0, 1, 2, 5):
            # prompt first, then a fallback that the endpoint sees second
            after_prompt = endpoint("active", other_team_wins, prompt_points)
            after_both = endpoint(after_prompt, other_team_wins, 0)
            assert after_both == after_prompt, (other_team_wins, prompt_points)
            # in NEITHER order is the fallback the report that rates the series
            assert endpoint("active", other_team_wins, 0) != "completed"

    # and the client forces the form rather than trusting its caller
    api = _src("ApiClient.cs")

    def claim(s):
        # STRUCTURAL, not a line literal.  The round-4 lens pass gave this
        # normalisation a warning beside it, which a one-line anchor could not
        # survive -- and a predicate that has to be rewritten every time the
        # statement is reformatted measures the formatting, not the rule.
        if "if (fallback)" not in s:
            return False
        blk = s[s.index("if (fallback)"):]
        blk = blk[:blk.index("\n            }") + 14] if "\n            }" in blk else ""
        return ("t1PointsTotal = 0;" in blk and "t2PointsTotal = 0;" in blk)

    _assert_discriminating(
        claim, api,
        _mutate(api, "                t1PointsTotal = 0;\n                t2PointsTotal = 0;",
                "                // the caller is trusted to zero them",
                "H1 fallback form"),
        "H1 fallback form")


def test_h1_the_fallback_never_probes_the_series_state_endpoint():
    """GET /team/series/{id}/state IS A WRITE, and the previous round put it on
    the fallback path as a safety pre-check.

    Its first arm UPDATEs status='canceled', invalidation_reason=
    'assembly_timeout', runs _reconcile_team_series_bets and COMMITS whenever
    the row reads 'active' with fewer than four spawn-confirms, more than
    _ASSEMBLY_DEADLINE_SECONDS past room_issued_at, and no positive live-game
    evidence.  Each of those is ordinary for a healthy, partly-played 2v2:

      * <4 confirms -- production's own comments name a lost spawn-confirm POST
        leaving a LIVE series at 3/4 "forever", and the bug-245 relock writes
        spawn_confirmations=0 AND room_issued_at=NULL, after which the age falls
        back to created_at and is past the deadline on the first read;
      * the live-game veto reads an in-process dict that every api restart
        empties -- "for minutes after every deploy EVERY group looks idle".

    The only shipped caller (PollAssemblyStateLoop) runs ~22 s from 3 s after a
    join and exits the moment the seat leaves the room, so it can never reach
    the arm.  The pre-check would have been its first reachable caller, on a
    series that had been PLAYED: voided as never-assembled, never reaching
    dc_incomplete, so never in the admin panel, bets settled on the wrong
    reason, and the real report afterwards answered {"ignored": true}.

    Nothing replaces it: the report endpoint answers the same question under the
    FOR NO KEY UPDATE reread it already takes."""
    ra = _src("RoomActors.cs")
    api = _src("ApiClient.cs")

    # the probe is gone from the tree, helper and call site alike
    assert "ReadTeamSeriesStatusOnce" not in api
    assert "ReadTeamSeriesStatusOnce" not in ra

    # Fire posts, directly, and nothing else reaches the network from it
    fire = ra[ra.index("private static void Fire(string reason)"):]
    assert "ApiClient.ReportTeamSeriesDc(series, reporter, dc, 0, 0, room, true);" in fire
    assert "/state" not in fire
    assert fire.count("ApiClient.") == 1

    # THIS LINE USED TO COUNT THE URL LITERAL, AND THAT IS WHY IT PASSED ON A
    # TREE WITH TWO LIVE CALLERS.  A route has one literal whether one method
    # calls it or five (#432).  Round 4 replaced the measurement in two places:
    # the count here and the CALLER count in its own test.  Round 5 makes the
    # count here simple again -- the route that writes is built once, full
    # stop, because the read the banner needs is a different PATH and not a
    # mode of this one.
    writing_mode = [ln for ln in api.split("\n")
                    if "/api/v1/team/series/{seriesId}/state" in ln]
    assert len(writing_mode) == 1, writing_mode
    loop = _method_body(_src("Plugin.cs"),
                        "private static System.Collections.IEnumerator PollAssemblyStateLoop")
    assert loop, "the assembly loop's own text could not be delimited"
    assert "if (Plugin.Pending2v2Slot < 0) yield break;" in loop
    assert "if (!PhotonNetwork.InRoom) yield break;" in loop
    deadline = float(re.search(r"Time\.realtimeSinceStartup \+ (\d+)f", loop).group(1))
    start = float(re.search(r"WaitForSeconds\((\d+)f\)", loop).group(1))
    # DERIVED, not written down: the loop's whole life is inside the 180 s
    # deadline, so raising either term here reddens this rather than passing.
    assert start + deadline < 180.0, (start, deadline)

    def claim(s):
        if "private static void Fire(string reason)" not in s:
            return False
        f = s[s.index("private static void Fire(string reason)"):]
        return "ReadTeamSeriesStatusOnce" not in f and "/state" not in f

    # the mutation that reopens it: put the probe back on the fallback path
    _assert_discriminating(
        claim, ra,
        _mutate(ra, "                ApiClient.ReportTeamSeriesDc(series, reporter, dc, 0, 0, room, true);",
                "                ApiClient.ReadTeamSeriesStatusOnce(series, (ok, status) => {\n"
                "                    ApiClient.ReportTeamSeriesDc(series, reporter, dc, 0, 0, room, true); });",
                "H1 destructive pre-check"),
        "H1 no state-endpoint probe")

    # NEGATIVE CONTROL: an unrelated edit in the same method leaves it true
    assert claim(_mutate(ra, "[2v2-DC] fallback POSTING — ", "[2v2-DC] fallback SENDING — ",
                         "H1 probe negative control"))


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
    assert "PostRequestWithRetryAnswered(url" in body
    # the lock mode is the DEPLOYED one, read off production 0cc7f75 rather than
    # remembered: the row re-read takes FOR NO KEY UPDATE; FOR UPDATE is what the
    # completion helper beneath it takes, and the doc used to name the wrong one.
    assert "FOR NO KEY UPDATE" in src
    doc = src[src.index("/// <para>DELIVERY."):src.index("public static void ReportTeamSeriesDc")]
    assert "FOR NO KEY UPDATE" in doc and "re-reads the row under FOR UPDATE" not in doc

    def claim(s):
        b = _method_body(s, "private static IEnumerator SendTeamSeriesDcReport")
        return bool(b) and "PostRequestWithRetryAnswered(url" in b

    _assert_discriminating(
        claim, src,
        _mutate(src, "PostRequestWithRetryAnswered(url, \"\", (ok, resp, answered) =>",
                "PostRequestAnswered(url, \"\", (ok, resp, answered) =>",
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
    # every(empty) must not apply.  The rule now lives on the key-parameterised
    # AllCapableOf, which is what BOTH capabilities of this class go through, so
    # one reading of "capable" cannot apply to one key and miss the other (#432).
    assert "if (seats == null || seats.Count == 0) return false;" in body
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


def test_every_capability_stage_admits_the_states_the_verdict_lands_in():
    """The verdict gate above and the NETWORK-STATE gate below it have to agree,
    and in PoisonSync they did not.

    Moving the stage behind the compatibility verdict moves it about three
    seconds into the process -- by which time ROUNDS is normally sitting on the
    master server or in the lobby, not Disconnected or PeerCreated.  PoisonSync
    kept the narrower pair that was correct when it staged at Awake, so from the
    first post-verdict tick onwards every call returned at the state gate, the
    deferral line had already been spent, and cr_pois2 never staged for the whole
    session with nothing in the log saying so.  The advertisement is the whole
    protocol: without it every peer reads this seat as poison-incapable, the
    sticky incapability latches room-wide and the authoritative-poison path ships
    100% inert behind a healthy-looking bundle (#438).

    A guard is judged by what its refusal costs (#430), and the cost here was the
    feature.  The idle set is the same four states in all four protocols: the
    first two provably precede any connect, and in the other two no join is in
    flight, so a local merge rides the next join op's own snapshot.

    The repo's own comment in VanillaFixes asserted the contradiction in as many
    words -- "PoisonSync stages at Awake where Disconnected/PeerCreated suffices"
    -- while the tree had already moved that stage behind the verdict (#302, and
    #432: the flag named cr_grow2's line, the defect was the operation)."""
    idle = ("Disconnected", "PeerCreated", "ConnectedToMasterServer", "JoinedLobby")
    protocols = [
        ("VanillaFixes.cs", "GrowNormalize"),
        ("VanillaFixes.cs", "SawTargetSync"),
        ("RoomActors.cs", "DcReportSync"),
        ("PoisonSync.cs", "PoisonSync"),
    ]
    for fname, cls in protocols:
        src = _src(fname)
        cut = src[src.index("class " + cls):] if ("class " + cls) in src else src
        stage = cut[cut.index("internal static void StageCapability(string source)"):]
        stage = stage[:stage.index("internal static void RevokeCapability()")]
        # the gate may be inlined or named; a named one is resolved to its body
        gate = stage
        if "InIdleClientState()" in stage:
            gate = _method_body(src, "private static bool InIdleClientState")
            assert gate, cls
        for st in idle:
            assert st in gate, (cls, st)

    # ...and PoisonSync's refusal is no longer silent: the state it refuses from
    # is printed, and it does not share the deferral flag that is already spent
    ps = _src("PoisonSync.cs")
    stage = ps[ps.index("internal static void StageCapability(string source)"):]
    stage = stage[:stage.index("internal static void RevokeCapability()")]
    assert "[POISON-CAP] holding" in stage
    assert "_stateWaitLines" in stage
    assert "_deferLogged" in stage
    # the two counters are separate flags, which is the point of the line: the
    # deferral flag is already SPENT by the time this gate is reached, so a gate
    # sharing it would refuse in silence.  Over the CODE with comment lines
    # removed -- the comment above the gate names _deferLogged to explain exactly
    # that, and deleting the explanation to satisfy a text search would delete
    # the record of the fix.
    hold = stage[stage.index("ClientState st = PhotonNetwork.NetworkClientState;"):]
    hold_code = "\n".join(l for l in hold.splitlines() if not l.strip().startswith("//"))
    assert "_deferLogged" not in hold_code

    def claim(s):
        anchors = ("internal static void StageCapability(string source)",
                   "internal static void RevokeCapability()",
                   "ClientState st = PhotonNetwork.NetworkClientState;")
        if not all(a in s for a in anchors):
            return False
        b = s[s.index(anchors[0]):s.index(anchors[1])]
        if anchors[2] not in b:
            return False
        g = b[b.index(anchors[2]):]
        return all(st in g for st in idle) and "[POISON-CAP] holding" in g

    # the mutation that restores the defect: the narrow pair, silently
    _assert_discriminating(
        claim, ps,
        _mutate(ps,
                "                if (st != ClientState.Disconnected && st != ClientState.PeerCreated\n"
                "                    && st != ClientState.ConnectedToMasterServer && st != ClientState.JoinedLobby)",
                "                if (st != ClientState.Disconnected && st != ClientState.PeerCreated)",
                "POISON-CAP idle set"),
        "PoisonSync idle-state set")

    # NEGATIVE CONTROL: an edit elsewhere in the same method leaves it true
    assert claim(_mutate(ps, "[POISON-CAP] staged ", "[POISON-CAP] merged ",
                         "POISON-CAP negative control"))


def test_the_saw_target_witness_line_prints_measured_terms():
    """The WITNESS line the next round's evidence rests on printed three of its
    four terms as the string literal "true", under a comment asserting that
    "Every term is MEASURED".

    Only postfix-stand-down was.  The other three were constants whose truth
    rested on the line's POSITION after the sameSet guard, not on anything the
    line reads -- a claim in a comment with no code under it (#302) and a check
    that cannot fail (#342).  If a later edit relaxes or reorders that guard --
    dropping the ReferenceEquals identity term is the one its own comment warns
    about -- the line would still print "same-list=true" on every masked frame
    while the restore wrote into a list the window never masked, and no capture
    could tell the working case from the broken one.

    The previous round's deviation note applied exactly this reasoning to the
    fourth term ("a count can come back 0, an asserted true cannot") and stopped
    one term short."""
    vf = _src("VanillaFixes.cs")
    body = _method_body(vf, "internal static void RestoreOrder")
    if not body:
        body = vf[vf.index("[SAW-TARGET] masked/restored") - 4000:]
        body = body[:body.index("[HarmonyFinalizer]")]
    # no term is a literal any more
    assert '"[SAW-TARGET] masked/restored same-list=true' not in vf
    assert "same-count=true" not in vf
    assert "same-members=true" not in vf
    # every term is printed from the variable that decided it
    for term, var in (("same-list=", "sameList"), ("same-count=", "sameCount"),
                      ("same-members=", "sameMembers")):
        assert term in body, term
        seg = body[body.index(term):body.index(term) + 120]
        assert var in seg, (term, var)
        assert '? "true" : "false"' in seg, term

    def claim(s):
        head, tail = "[SAW-TARGET] masked/restored same-list=", "/3 this room)"
        if head not in s or tail not in s:
            return False
        line = s[s.index(head):]
        line = line[:line.index(tail)]
        # all three, inside the witness line's OWN span
        return all('(%s ? "true" : "false")' % v in line
                   for v in ("sameList", "sameCount", "sameMembers"))

    # The mutation anchor carries the WITNESS line's own head.  The bare ternary
    # is not unique in this file -- the !sameSet diagnostic a few lines above
    # prints the same expression, and a first-occurrence replace lands there
    # instead, mutating a line this test does not measure and leaving the claim
    # green (#432: a flag names a LINE; anchor on the one you mean).
    _assert_discriminating(
        claim, vf,
        _mutate(vf,
                'Plugin.Log.LogInfo("[SAW-TARGET] masked/restored same-list="\n'
                '                        + (sameList ? "true" : "false")',
                'Plugin.Log.LogInfo("[SAW-TARGET] masked/restored same-list="\n'
                '                        + "true"',
                "SAW-TARGET witness literal"),
        "SAW-TARGET witness terms measured")

    # NEGATIVE CONTROL
    assert claim(_mutate(vf, "postfix-stand-down=", "postfix-standdown=",
                         "SAW-TARGET witness negative control"))


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
    assert "OutcomeSent || o == OutcomeAnswered" in body
    assert "o == OutcomeFailed || o == OutcomeUnknown" in body

    # the model of the same rule, including the three ways it must answer ""
    def outcome_of(prop, series):
        tag = series[:8].lower()
        if not prop or ":" not in prop:
            return ""
        head, _, rest = prop.partition(":")
        if head != tag or rest not in ("send", "ok", "no", "unk"):
            return ""
        return rest

    assert outcome_of("abcdef12:ok", "ABCDEF12-1111") == "ok"
    assert outcome_of("99999999:ok", "abcdef12-1111") == ""      # a previous series
    assert outcome_of("abcdef12:maybe", "abcdef12-1111") == ""   # unrecognised
    assert outcome_of("", "abcdef12-1111") == ""
    # and the watch treats "" as NOT terminal while the seat is still present
    assert fallback(outcome_of("99999999:no", "abcdef12"), False) == "nothing"

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
    # MEASURED, not asserted: this used to read "same-list=true same-count=true"
    # as string literals, under a comment claiming every term was measured.  See
    # test_the_saw_target_witness_line_prints_measured_terms for why that made
    # the witness line incapable of ever reporting the failure it witnesses.
    assert "[SAW-TARGET] masked/restored same-list=" in restore
    assert "same-list=true same-count=true" not in restore
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


# ══════════════════════════════════════════════════════════════════════════
# ROUND 4 -- the two-lane close, and the GET that writes
# ══════════════════════════════════════════════════════════════════════════
#
# Five of the round-3 review's HIGHs landed INSIDE the round-3 closure.  That is
# the signal that the METHOD was wrong and not one implementation of it
# (#252/#405), so the closing rule changed shape:
#
#   * it is no longer "a client-only guard plus a server NOTE".  It is a
#     two-lane change.  The SERVER defers a fallback settlement so a real-totals
#     report always wins the race; the CLIENT says which of its reports is a
#     fallback (is_fallback) and advances its own capability so a mixed-version
#     room never arms the new protocol at all.
#   * the sixth was a plain sweep miss -- a second caller of the mutating state
#     route -- and the control that should have caught it counted a URL literal.
#
# Every test below is the CLIENT half.  Each one that needs the server lane says
# so, and says what this client does against a server without it.


_CS_MEMBER = re.compile(
    r"^ {8}(?:internal|private|public|protected)\s+[^;{}]*?\b([A-Za-z_0-9]+)\s*\(")


def _all_sources():
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(PLUGIN.glob("*.cs"))}


def _call_sites(method_name, sources=None):
    """Every CALL SITE of a method across the whole client, as a set of
    (file, enclosing member) pairs.

    THIS IS THE CHECK THE PREVIOUS ROUND DID NOT HAVE.  Its H1 control counted
    the mutating route's URL literal and asserted the count was 1 -- but a route
    has ONE literal whether one method calls it or five, so that assertion was
    true on a tree that had a second live caller in the team tab, and could
    never have gone red for the defect it was named after.  A flag names a LINE;
    the defect is a CLASS (#432).  The operation here is "a caller of a GET that
    writes", so the thing to count is callers.

    Declaration lines and comment lines are excluded; any other line mentioning
    `name(` is a call site.  Reading the ENCLOSING member rather than the line
    number is deliberate: it survives line drift, and the identity of the caller
    is what the rule is about."""
    if sources is None:
        sources = _all_sources()
    found = set()
    for fname in sorted(sources):
        member = "<file scope>"
        for line in sources[fname].split("\n"):
            m = _CS_MEMBER.match(line)
            if m:
                member = m.group(1)
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if method_name + "(" not in line:
                continue
            if m is not None and m.group(1) == method_name:
                continue                       # the declaration itself
            found.add((fname, member))
    return found


def _member_owning(source, fragment):
    """The member whose text contains `fragment`, by the same walk-back rule."""
    member = "<file scope>"
    for line in source.split("\n"):
        m = _CS_MEMBER.match(line)
        if m:
            member = m.group(1)
        if fragment in line:
            return member
    return None


# The client-reachable GET routes whose PRODUCTION handler writes a lifecycle or
# economy row.  Swept out of backend/api/main.py on the production pin by taking
# every @app.get handler, delimiting it at the next top-level construct, and
# keeping the ones that UPDATE a series/lobby/player table or call a bet
# reconciler -- then intersecting that with the routes this client actually
# builds.  Six survive:
#
#   /api/v1/presence/ping           UPDATE players            (last-seen stamp)
#   /api/v1/queue/poll/{id}         UPDATE/DELETE ranked_queue, queue_blocks
#   /api/v1/team/queue/poll/{id}    UPDATE team_series + reconcile bets
#   /api/v1/ovt/queue/poll/{id}     UPDATE ovt_series
#   /api/v1/ffa/queue/poll/{id}     UPDATE ffa_lobbies + reconcile bets
#   /api/v1/team/series/{id}/state  UPDATE team_series + reconcile bets
#
# FIVE OF THE SIX ARE QUEUE TICKS, and their write is the thing the poll exists
# to do: it is keyed on the CALLER'S OWN pre-start queue row, and its cancel
# reasons are ready_timeout, member_banned, sitting_abandoned and a dead-lock
# reset -- a sitting that has not begun.  A client that is polling its own queue
# row is inside the window that write is designed for by construction.
#
# THE SIXTH IS DIFFERENT.  Its arm cancels a series that HAS begun
# (status='active') on three conditions a healthy played 2v2 satisfies, and it
# reconciles that series' bets.  It was the only one of the six with a caller
# outside the window its write is designed for, and that caller was a menu tab.
_MUTATING_GET_OWNERS = {
    "/api/v1/presence/ping": "PresenceLoop",
    "/api/v1/queue/poll/{steamId}": "UpdateQueuePoll",
    "/api/v1/team/queue/poll/{steamId}": "UpdateTeamQueuePoll",
    "/api/v1/ovt/queue/poll/{sid}": "UpdateOvtQueuePoll",
    "/api/v1/ffa/queue/poll/{sid}": "UpdateFfaQueuePoll",
}

# THE SIXTH ROUTE IS BUILT ONCE AS OF ROUND 5, and the read the banner needs is
# a DIFFERENT PATH.  Round 4 built this path twice -- one route in two "modes",
# separated by a query parameter -- and that is the design round 5 deletes.  A
# box that does not know a query parameter drops it and runs the mutating arms
# anyway (#266), and the advertisement that was supposed to keep the first such
# request off such a box was read from whichever box answered /mod-version,
# which is not the box that answers this request.  A PATH cannot be dropped: a
# box without the route registers no handler for it.
_STATE_ROUTE = "/api/v1/team/series/{seriesId}/state"
_STATUS_ROUTE = "/api/v1/team/series/{seriesId}/status"
# Neither literal contains the other, so counting them is two independent
# measurements and not one literal counted twice (#342).
assert _STATE_ROUTE not in _STATUS_ROUTE and _STATUS_ROUTE not in _STATE_ROUTE


def test_r5_h1_every_mutating_get_is_built_in_exactly_one_method():
    """The sweep, as an OPERATION over the whole class rather than one route.

    Each queue route above is constructed in exactly ONE client method, so each
    has a single choke point where its rule can be stated.  Round 4 made the
    sixth an exception -- one path built twice, in two modes -- and this round
    removes the exception: the mutating path is built ONCE, by the assembly
    poll, and the read the banner needs is a different path built once by the
    read-only poller.  The distinction that used to live in a query parameter
    now lives in the URL, where no box can drop it."""
    api = _src("ApiClient.cs")
    for route, owner in sorted(_MUTATING_GET_OWNERS.items()):
        assert api.count(route) == 1, (route, api.count(route))
        assert _member_owning(api, route) == owner, (route, _member_owning(api, route))

    # the sixth: one construction, in the writing method, and no query mode
    state_lines = [ln for ln in api.split("\n") if _STATE_ROUTE in ln]
    assert len(state_lines) == 1, state_lines
    assert _member_owning(api, state_lines[0].strip()) == "PollTeamSeriesStateAssemblyOnly"
    assert "?lifecycle" not in api

    # and the read is its own path, built once, by the read-only poller
    status_lines = [ln for ln in api.split("\n") if _STATUS_ROUTE in ln]
    assert len(status_lines) == 1, status_lines
    assert _member_owning(api, status_lines[0].strip()) == "PollTeamSeriesStatusReadOnly"

    # and no OTHER file builds any of them
    for name, src in _all_sources().items():
        if name == "ApiClient.cs":
            continue
        for route in list(_MUTATING_GET_OWNERS) + [_STATE_ROUTE, _STATUS_ROUTE]:
            assert route not in src, (name, route)

    def claim(s):
        if not all(s.count(r) == 1 and _member_owning(s, r) == o
                   for r, o in _MUTATING_GET_OWNERS.items()):
            return False
        st = [ln for ln in s.split("\n") if _STATE_ROUTE in ln]
        ro = [ln for ln in s.split("\n") if _STATUS_ROUTE in ln]
        return (len(st) == 1 and len(ro) == 1
                and _member_owning(s, st[0].strip()) == "PollTeamSeriesStateAssemblyOnly"
                and _member_owning(s, ro[0].strip()) == "PollTeamSeriesStatusReadOnly")

    # THE MUTATION: the banner's read goes back to the mutating path, which is
    # the round-4 shape and the defect its H1 named -- a second construction of
    # the route that writes
    _assert_discriminating(
        claim, api,
        _mutate(api,
                'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/status";',
                'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/state";',
                "R5 the read goes back to the mutating path"),
        "R5 H1 one construction site for the mutating route")

    # NEGATIVE CONTROL: an unrelated edit in the same method leaves it true
    assert claim(_mutate(api, "[2v2] series status read for series ",
                         "[2v2] series-status read for series ",
                         "R5 H1 sweep negative control"))


def test_r4_h1_the_mutating_state_route_has_exactly_one_caller_in_the_whole_client():
    """COUNTING CALLERS, NOT LITERALS -- the finding this round closes.

    The round-3 tree had two: Plugin.PollAssemblyStateLoop, which is the
    assembly window the cancel arm was written for and whose whole life (3 s of
    delay plus a 22 s loop, exited the moment the seat is out of the room) sits
    inside the server's 180 s deadline; and ApiClient.UpdateTeamSeriesStatePoll,
    the team tab's DC-grace banner, running from the MENU against whatever
    series id was cached for as long as the tab was open.

    The second one could reach the arm.  A played series reads fewer than four
    spawn-confirms after a lost confirm POST or a bug-245 resume relock, the
    relock also NULLs room_issued_at so the endpoint's COALESCE measures age
    from created_at, and the live-game veto reads an in-process map that every
    api restart empties.  The arm then sets status='canceled' with
    invalidation_reason='assembly_timeout', reconciles the series' bets and
    commits -- a played match voided as never assembled, its bets settled on the
    wrong reason, and the real report afterwards answered {"ignored": true}.

    The method's NAME now carries the rule, so a call site cannot be written
    without reading it."""
    sites = _call_sites("PollTeamSeriesStateAssemblyOnly")
    assert sites == {("Plugin.cs", "PollAssemblyStateLoop")}, sites

    # the read-only twin is the one the rest of the client uses
    ro = _call_sites("PollTeamSeriesStatusReadOnly")
    assert ("ApiClient.cs", "UpdateTeamSeriesStatePoll") in ro
    assert ("Plugin.cs", "PollAssemblyStateLoop") not in ro

    srcs = _all_sources()

    def claim(api_text):
        if "public static void PollTeamSeriesStateAssemblyOnly(" not in api_text:
            return False
        s = dict(srcs)
        s["ApiClient.cs"] = api_text
        return _call_sites("PollTeamSeriesStateAssemblyOnly", s) == {
            ("Plugin.cs", "PollAssemblyStateLoop")}

    # the mutation that reopens it: the banner calls the mutating route again
    _assert_discriminating(
        claim, srcs["ApiClient.cs"],
        _mutate(srcs["ApiClient.cs"],
                "            PollTeamSeriesStatusReadOnly(sid, null);",
                "            PollTeamSeriesStateAssemblyOnly(sid, null);",
                "R4 second caller of the mutating route"),
        "R4 H1 one caller of the mutating GET")

    # NEGATIVE CONTROL: renaming a log string does not move the caller set
    assert claim(_mutate(srcs["ApiClient.cs"], "[2v2] DC-grace banner NOT polling series ",
                         "[2v2] DC-grace banner is not polling series ",
                         "R4 H1 caller-count negative control"))


def status_read_outcome(box, fallback_to_state=False):
    """ONE status read, transliterated from PollTeamSeriesStatusReadOnly.

    `box` is what the box that ANSWERS THIS REQUEST does with the path -- not
    what any other box does, and not what /mod-version said:

      "final"        200 carrying readonly=true
      "old"          404: production registers no handler on that path
      "rolled-back"  404: it had one and does not now
      "gate"         426 from the version gate, which never reaches routing
      "torn"         200 whose body does not carry readonly
      "down"         no answer at all -- a transport failure or the 20 s timeout

    Returns (routes_dispatched, latched, status_logged).

    `fallback_to_state` is the MODEL'S OWN NEGATIVE CONTROL (#391): a model that
    cannot express the defect cannot measure its absence.  With it True the
    model degrades to the lifecycle route when the read did not come back as a
    read, which is the shape this round exists to make impossible."""
    answered = {"final": 200, "torn": 200, "old": 404, "rolled-back": 404,
                "gate": 426, "down": 0}[box]
    routes = [_STATUS_ROUTE]
    if box == "final":
        return routes, False, answered
    if fallback_to_state:
        routes.append(_STATE_ROUTE)
        return routes, False, answered
    return routes, True, answered


def test_r5_h1_no_cell_of_the_box_matrix_dispatches_the_lifecycle_route():
    """THE ROUND-4 H1, ANSWERED BY ENUMERATION.

    Round 4 claimed this path "may not reach the mutating route, in any server
    state" and that "no UI poll can void a played series".  Both were false in
    one cell: /mod-version answered by a final box set the capability, and the
    state read was then answered by an old or rolled-back box, which DROPPED
    the query parameter, answered 200 and ran the cancel arm -- one write
    before the echo check could latch anything off.

    The matrix is (which box answered /mod-version) x (which box answered the
    status read).  The first dimension is now inert BY CONSTRUCTION, and that
    is asserted rather than assumed: neither method reads any field the
    mod-version answer writes.  The second dimension decides only whether this
    series latches dark.

    In every cell, the routes this path dispatches are exactly one: the status
    route.  The lifecycle route appears in no cell."""
    boxes = ("final", "torn", "old", "rolled-back", "gate", "down")
    for mod_version_box in ("final", "old"):
        for box in boxes:
            routes, latched, status = status_read_outcome(box)
            assert routes == [_STATUS_ROUTE], (mod_version_box, box, routes)
            assert _STATE_ROUTE not in routes, (mod_version_box, box)
            assert latched == (box != "final"), (mod_version_box, box, latched)
            if box != "final":
                assert isinstance(status, int)

    # THE MODEL'S OWN NEGATIVE CONTROL: it can express the defect, so the
    # absence above is a measurement
    routes, latched, _ = status_read_outcome("old", fallback_to_state=True)
    assert _STATE_ROUTE in routes and latched is False

    srcs = _all_sources()
    api = srcs["ApiClient.cs"]

    # WHAT THE MOD-VERSION DIMENSION IS INERT BY: neither method reads anything
    # the mod-version answer sets.  If a gate on one of these ever returns, the
    # first dimension is live again and this goes red.
    _MOD_VERSION_FIELDS = ("LatestModVersion", "MinModVersion", "ForceUpdateRequired")

    def claim(api_text):
        ro = _method_body(api_text, "public static void PollTeamSeriesStatusReadOnly")
        ui = _method_body(api_text, "public static void UpdateTeamSeriesStatePoll")
        if not ro or not ui:
            return False
        for body in (ro, ui):
            if "PollTeamSeriesStateAssemblyOnly" in body:
                return False
            if _STATE_ROUTE in body:
                return False
            if any(f in body for f in _MOD_VERSION_FIELDS):
                return False
        s = dict(srcs)
        s["ApiClient.cs"] = api_text
        return _call_sites("PollTeamSeriesStateAssemblyOnly", s) == {
            ("Plugin.cs", "PollAssemblyStateLoop")}

    # THE MUTATION: a fallback to the lifecycle route on the answer that did not
    # prove itself -- the cell round 4 lost
    _assert_discriminating(
        claim, api,
        _mutate(api,
                '                        RequestBannerRepaintIfChanged(bannerBefore);\n'
                '                        return;',
                '                        RequestBannerRepaintIfChanged(bannerBefore);\n'
                '                        PollTeamSeriesStateAssemblyOnly(seriesId, onResponse);\n'
                '                        return;',
                "R5 H1 a fallback to the lifecycle route"),
        "R5 H1 no cell reaches the lifecycle route")

    # NEGATIVE CONTROL: rewording the refusal line moves no dispatch
    assert claim(_mutate(api, "was not answered as a read: HTTP ",
                         "was not answered as a read -- HTTP ",
                         "R5 H1 matrix negative control"))


def test_r5_h1_the_banner_polls_the_status_route_and_proves_it_per_response():
    """THE PREDICATE, asserted as the code applies it.

    The banner polls GET .../status -- a route with no mutating arm on any box
    -- and nothing else.  There is no advertisement to consult, no mode to
    request and no fallback: the method composes one URL, and any answer that
    is not a 200 carrying readonly=true latches THIS SERIES dark instead of
    trying something else.

    WHY THE ADVERTISEMENT WENT.  It was read from /mod-version and spent as
    permission for a later, separately routed request.  Two requests are two
    routing decisions: the edge routes reads to the standby and keeps the
    primary as a fallback upstream, and a rollback moves a box under a flag
    already held.  A capability read out of one response is not a property of
    the box that answers the next one, so the proof now rides IN the answer it
    is about.

    WHY THERE IS NO LOCAL PLAYED-YET TEST.  The three terms that select the
    cancel arm are the row's confirm count, its age from room_issued_at, and the
    api process's live-game map.  A client can see none of them, so wins-seen, a
    game entered, or a cached status of dc_paused are all guesses about a
    different quantity -- and each is wrong exactly in the resume case, where
    the relock zeroes the confirms and NULLs the room stamp.  A check that
    cannot fail on the state it exists to catch is worse than no check (#342).

    THE GATE IS STILL TAKEN TWICE, and that is still the point (#432): once at
    the call site so the refusal can SPEAK and name the series, and once inside
    the poller, so the rule belongs to the operation and not to one caller's
    discipline."""
    api = _src("ApiClient.cs")

    ui = _method_body(api, "public static void UpdateTeamSeriesStatePoll")
    assert ui, "the banner poll's own text could not be delimited"
    assert "if (_statusPollDarkSeries.Contains(sid))" in ui
    assert "PollTeamSeriesStatusReadOnly(sid, null);" in ui
    assert "PollTeamSeriesStateAssemblyOnly" not in ui
    # the refusal speaks, once per series, and names why
    assert "DC-grace banner NOT polling series" in ui
    assert "_statusPollRefusedForSeries" in ui
    # and it returns BEFORE the throttle, so no poll is dispatched at all
    assert (ui.index("if (_statusPollDarkSeries.Contains(sid))")
            < ui.index("if (!force && Time.unscaledTime < teamSeriesStateNextAt) return;"))

    ro = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    assert ro, "the read-only poller's own text could not be delimited"
    assert "if (_statusPollDarkSeries.Contains(seriesId)) return;" in ro
    assert _STATUS_ROUTE in ro and _STATE_ROUTE not in ro
    # GATE 2: presence tracked separately from value, because a bool extractor
    # answers False for "absent" and for "false" alike and absent is the
    # dangerous one (#604)
    assert 'resp.IndexOf("\\"readonly\\"", StringComparison.Ordinal) >= 0' in ro
    assert 'affirmed = ExtractJsonBool(resp, "readonly");' in ro
    # the latch is taken on the answer, before anything could be parsed out of
    # it, and the non-conforming answer is not parsed at all
    assert "_statusPollDarkSeries.Add(seriesId);" in ro
    assert ro.index("_statusPollDarkSeries.Add(seriesId);") < ro.index("ApplySeriesStateResponse")
    # ONE LINE, NAMING THE STATUS AND THE SERIES (the contract's words)
    assert "was not answered as a read: HTTP " in ro
    # ...and the POSITIVE line, once per series, so a bundle can tell a banner
    # that works from one that never ran (#438)
    assert "series status read PROVEN for series " in ro
    assert "_statusPollProvenForSeries" in ro
    assert '+ seriesId' in ro and '+ answeredWith' in ro
    # the status is this request's own, captured per dispatch rather than in a
    # field shared with every other request in flight
    assert "long answeredWith = 0;" in ro
    assert "onResponseCode: code => answeredWith = code" in ro

    def claim(s):
        u = _method_body(s, "public static void UpdateTeamSeriesStatePoll")
        r = _method_body(s, "public static void PollTeamSeriesStatusReadOnly")
        if not u or not r:
            return False
        return ("if (_statusPollDarkSeries.Contains(sid))" in u
                and "if (_statusPollDarkSeries.Contains(seriesId)) return;" in r
                and _STATUS_ROUTE in r
                and 'affirmed = ExtractJsonBool(resp, "readonly");' in r
                and "_statusPollDarkSeries.Add(seriesId);" in r
                and "series status read PROVEN for series " in r
                and "PollTeamSeriesStateAssemblyOnly" not in u)

    # mutation 1: the call-site gate goes, so a series already refused is
    # polled again at the tab's tick and the refusal never speaks
    _assert_discriminating(
        claim, api,
        _mutate(api, "            if (_statusPollDarkSeries.Contains(sid))\n            {",
                "            if (false)\n            {",
                "R5 banner gate removed"),
        "R5 H1 banner gated on the per-series latch")

    # mutation 2: the choke-point gate inside the poller goes
    _assert_discriminating(
        claim, api,
        _mutate(api, "            if (_statusPollDarkSeries.Contains(seriesId)) return;   // GATE 1\n",
                "", "R5 read-only poller gate removed"),
        "R5 H1 read-only poller gated at the operation")

    # mutation 3: the answer is trusted on a 2xx alone, which is exactly what an
    # old box returns for a route it does not have only by accident -- and what
    # a torn or proxied 200 returns always
    _assert_discriminating(
        claim, api,
        _mutate(api, '                        try { affirmed = ExtractJsonBool(resp, "readonly"); } '
                     'catch { affirmed = false; }',
                '                        affirmed = true;',
                "R5 the answer is trusted on a 2xx alone"),
        "R5 H1 the answer proves itself or it is refused")

    # NEGATIVE CONTROL: rewording the refusal leaves every claim true
    assert claim(_mutate(api, "there is no second route to fall back to",
                         "there is no second route to fall back on",
                         "R5 H1 predicate negative control"))


def test_r5_the_advertised_capability_is_absent_from_every_source():
    """THE DELETION, swept over the whole tree rather than one method (#432).

    A mechanism that is deleted in one file and left in another is not deleted;
    the round-4 notes claimed an absence that the server tree contradicted, and
    the cost of that was a rollout validated against the wrong literal.  So the
    check is over every plugin source, for every spelling of the removed
    mechanism: the capability field, its parse, the query parameter and the
    echoed key it used to read.

    No shipped client depends on any of it -- the round-4 client is unreleased
    (#310, #389: deleted mechanisms beat patched ones)."""
    dead = ("ServerHasReadOnlySeriesStatus", "series_status_readonly",
            "lifecycle=false", '"lifecycle"')
    srcs = _all_sources()
    for name, src in sorted(srcs.items()):
        for token in dead:
            assert token not in src, (name, token)

    def claim(api_text):
        # An absence claim alone holds on a stub, which is a claim that cannot
        # fail (#342) -- so it is conjoined with the presence of what REPLACED
        # the mechanism.  The pair can only hold on a tree that deleted the one
        # and built the other.
        if any(t in api_text for t in dead):
            return False
        return ('affirmed = ExtractJsonBool(resp, "readonly");' in api_text
                and "_statusPollDarkSeries" in api_text)

    # THE MUTATION: the parse comes back, which is how the capability returns
    _assert_discriminating(
        claim, srcs["ApiClient.cs"],
        _mutate(srcs["ApiClient.cs"],
                "                // NOTHING IS READ OUT OF THIS ANSWER BUT THE TWO VERSION NUMBERS.",
                "                bool roStatus = ExtractJsonBool(req.downloadHandler.text, "
                '"series_status_readonly");',
                "R5 the advertisement parse returns"),
        "R5 the advertised capability is gone")

    # NEGATIVE CONTROL: the word "lifecycle" still describes the route that
    # mutates, which is what the server's own handler is called -- the claim is
    # about the deleted MECHANISM, not about a word
    assert claim(_mutate(srcs["ApiClient.cs"], "is a lifecycle WRITE",
                         "is a lifecycle write", "R5 deletion negative control"))
    assert "lifecycle" in srcs["ApiClient.cs"]


def test_r5_the_bound_sentence_is_carried_verbatim_from_the_contract():
    """ONE SENTENCE, ONE WORDING, BOTH LANES (#341, #444).

    The round-4 comment promised that a real-totals report arriving "at any
    later time" still reaches the rated branches.  It does not: the deferral is
    a window.  The cross-lane contract fixes the wording so the two lanes and
    the migration cannot drift into three descriptions of one rule, and the
    client carries it character for character -- once in the comment at the
    is_fallback site, once in the line the deferred answer logs.

    The claim this test makes is about TEXT, and that is the point: a comment
    asserting a guarantee is a claim about the whole state space (#351), and
    the way this one stays true is that it is copied rather than restated."""
    api = _src("ApiClient.cs")

    # the sentence, as the contract writes it, reflowed across comment lines and
    # across string concatenation -- so the comparison is on the words, not on
    # the line breaks
    sentence = ("A real-totals report wins while the deferred marker is younger than 420 "
                "seconds, and after that only until a sweep tick finds no live-game evidence "
                "for the series and settles the row; once a row is settled, a later report is "
                "refused at the settled-row exit and is not rated.")

    def flatten(s):
        out = []
        for line in s.split("\n"):
            t = line.strip()
            if t.startswith("//"):
                t = t[2:]
            t = t.replace('+ "', " ").replace('"', " ")
            out.append(t)
        return " ".join(" ".join(out).split())

    flat = flatten(api)
    assert flat.count(" ".join(sentence.split())) == 2, flat.count(" ".join(sentence.split()))

    # the withdrawn promise is gone, and so is the wording the contract retired
    assert "arriving at any later time" not in api
    assert "second refusal" not in api
    assert "room quiet" not in api and "room-quiet" not in api

    def claim(s):
        return (flatten(s).count(" ".join(sentence.split())) == 2
                and "arriving at any later time" not in s)

    # THE MUTATION: one copy is paraphrased, which is exactly the drift the
    # single wording exists to prevent
    _assert_discriminating(
        claim, api,
        _mutate(api, "            //   A real-totals report wins while the deferred marker is "
                     "younger than\n",
                "            //   A real-totals report wins whenever the deferred marker is "
                "younger than\n",
                "R5 the bound sentence is paraphrased"),
        "R5 the bound sentence is carried verbatim, twice")

    # NEGATIVE CONTROL: an unrelated comment edit leaves both copies intact
    assert claim(_mutate(api, "THE BOUND ON THAT, in the cross-lane contract's words",
                         "THE BOUND ON IT, in the cross-lane contract's words",
                         "R5 bound-sentence negative control"))


# ── H2: the outcome protocol's own capability, and the mixed-room refusal ────


def outcome_quorum(seats):
    """AllOutcomeCapable, transliterated.  `seats` is one bool per fighter seat
    present: True when that seat advertises cr_dc3.

    every(empty) must NOT apply -- an empty seat list is the state in which
    nothing is known about the room, and arming there is arming on no evidence
    (#430: the refusal costs a late close, the arm costs a match result)."""
    if not seats:
        return False
    return all(seats)


def test_r4_h2_a_mixed_room_arms_nothing_over_the_whole_seat_space():
    """The quorum, exercised over every room this arm can see.

    The outcome protocol changed incompatibly while the property that advertises
    it did not, so two generations could read each other's cr_dcr values as
    their own.  The generation before this one published `no` for a report whose
    attempts went UNANSWERED -- a transaction that may still be running
    server-side -- and this generation treats `no` as terminal and fires on it.
    The generation before THAT published nothing on this property at all and ran
    an independent elapsed-time post this build cannot observe or stand down.

    cr_dc3 is what makes "every cr_dcr value this watch acts on was written by a
    process running these rules" a property of the ROOM rather than of this
    seat's code (#286/#301: whole-room capability with quorum, never a room-name
    prefix and never a version string)."""
    # exactly one room in each size arms: the one where every seat advertises
    for n in (0, 1, 2, 3, 4):
        rooms = list(itertools.product([False, True], repeat=n))
        armed = [r for r in rooms if outcome_quorum(list(r))]
        assert armed == ([] if n == 0 else [tuple([True] * n)]), (n, armed)

    # the negative control for the model itself: a rule that ignored the seats
    # would arm the mixed rooms, which is the behaviour being removed
    assert any(not outcome_quorum(list(r))
               for r in itertools.product([False, True], repeat=3))


def test_r4_h2_the_outcome_protocol_has_its_own_key_and_the_watch_takes_its_quorum():
    """The key is new, the election key is untouched, and the gate is at the one
    place a watch can come into existence.

    TWO KEYS, NOT ONE RE-KEYED CONSTANT.  cr_dc2 is the ELECTION generation and
    did not change this round; cr_dc3 is the OUTCOME-PROTOCOL generation and is
    what changed.  Folding a wire generation and a capability into one constant
    breaks compatibility in both directions (#604).

    WHAT THIS TEST DOES NOT SAY, corrected after the lens pass ratified a claim
    it had not earned.  The docstring here used to justify the split with "re-
    keying cr_dc2 would drop rooms to the floor election for no reason" and to
    certify that old builds tolerate an unknown cr_dcr token.  Neither key nor
    cr_dcr is on ANY released tree, so both sentences were statements about
    builds that do not exist, and a harness repeating a source comment ratifies
    it rather than testing it (#342).  What is asserted below is only what the
    text can carry: the two constants exist, they ride one merge and one revoke,
    the gate sits inside ArmFallback before any watch state, and publication is
    ungated.  The REACHABILITY of the refusal -- it is dominated by the election
    quorum on the only path that reaches it -- is asserted separately, in
    test_r4lens_f3_*, together with the corrected comments."""
    ra = _src("RoomActors.cs")
    body = ra[ra.index("internal static class DcReportSync"):]

    assert 'internal const string CapabilityProp = "cr_dc2";' in body        # unchanged
    assert 'internal const string OutcomeCapabilityProp = "cr_dc3";' in body  # new

    # both keys ride ONE pre-join merge, so a seat is never capable of one rule
    # and unknown on the other in the same join snapshot
    stage = body[body.index("internal static void StageCapability(string source)"):]
    stage = stage[:stage.index("internal static void RevokeCapability()")]
    assert "{ CapabilityProp, CapabilityValue }," in stage
    assert "{ OutcomeCapabilityProp, OutcomeCapabilityValue }" in stage
    assert stage.count("SetCustomProperties") == 1
    # and both are withdrawn together on compat-disable
    revoke = body[body.index("internal static void RevokeCapability()"):]
    revoke = revoke[:revoke.index("internal static bool CapableOf")]
    assert "{ CapabilityProp, 0 }," in revoke
    assert "{ OutcomeCapabilityProp, 0 }" in revoke

    # THE GATE: inside ArmFallback, before any watch state is written
    arm = body[body.index("internal static void ArmFallback(string seriesId"):]
    arm = arm[:arm.index("internal static void NoteActorProps")]
    assert "AllOutcomeCapable(fighterSeats, out missingOutcome)" in arm
    assert arm.index("AllOutcomeCapable(") < arm.index("_watchSeries = seriesId;")
    assert "does not advertise " in arm            # the refusal names the key
    assert "actor " in arm                         # ...and the seat
    assert "fallback NOT armed" in arm

    # publication is NOT gated: an older peer must keep getting what it always got
    pub = _method_body(ra, "internal static void PublishOutcome(string seriesId, string outcome)")
    assert pub, "PublishOutcome's own text could not be delimited"
    assert "OutcomeCapabilityProp" not in pub

    # the call site hands the census list, not a fresh guess at the roster
    plug = _src("Plugin.cs")
    assert "observedRoom, survivors);" in plug

    def claim(s):
        if "internal static class DcReportSync" not in s:
            return False
        b = s[s.index("internal static class DcReportSync"):]
        if 'internal const string OutcomeCapabilityProp = "cr_dc3";' not in b:
            return False
        if "internal static void ArmFallback(string seriesId" not in b:
            return False
        a = b[b.index("internal static void ArmFallback(string seriesId"):]
        a = a[:a.index("internal static void NoteActorProps")]
        return ("AllOutcomeCapable(fighterSeats, out missingOutcome)" in a
                and a.index("AllOutcomeCapable(") < a.index("_watchSeries = seriesId;"))

    # the mutation: the quorum stops being consulted, which is the round-3 tree
    _assert_discriminating(
        claim, ra,
        _mutate(ra,
                "                int missingOutcome;\n"
                "                if (!AllOutcomeCapable(fighterSeats, out missingOutcome))",
                "                int missingOutcome = -1;\n"
                "                if (false)",
                "R4 mixed-room arm restored"),
        "R4 H2 the watch takes the outcome quorum")

    # NEGATIVE CONTROL: rewording the refusal line leaves the gate in place
    assert claim(_mutate(ra, "so this room is running", "so this room runs",
                         "R4 H2 quorum negative control"))


# ── H3: the client half of the deferral, and what an older server does ───────


def dc_report_query(fallback):
    """The report-dc query string this client builds, transliterated.  Returns
    the parameter names in order."""
    names = ["reporter_steam_id", "dc_player_steam_id",
             "t1_points_total", "t2_points_total", "photon_room_id"]
    if fallback:
        names.append("is_fallback")
    names.append("hmac_sig")
    return names


def test_r4_h3_a_fallback_report_carries_is_fallback_and_a_prompt_report_does_not():
    """The client half of the two-lane close.

    A server carrying the deferral rule does not settle on a zero-total fallback:
    it records that a survivor believes the series abandoned, answers
    {"deferred": true}, and leaves the row active so a real-totals prompt report
    can still reach its normal branches -- WITHIN THE BOUND, which is the
    contract's sentence and not "at any later time":

    A real-totals report wins while the deferred marker is younger than 420
    seconds, and after that only until a sweep tick finds no live-game evidence
    for the series and settles the row; once a row is settled, a later report is
    refused at the settled-row exit and is not rated.  The round-3 note claimed "client coupling: none
    required" while the reviewed URL sent no such flag -- which would have left
    every fallback on the immediate-settlement path with a complete server half
    deployed (#635: a field on one side of a wire contract and not the other
    ships the feature inert).

    UNSIGNED, like photon_room_id, which already rides outside the frozen DC
    canonical; extending the canonical would fail every current client's
    signature.

    DIRECTION (#283): setting it moves the server away from settling and toward
    deferral, and the deferral branch sits before the lead-forfeit block, so it
    reaches no rating, gold or team_matches write.  It is NOT free, and the
    round-4 lens pass corrected this docstring along with the comment it
    mirrored: the server checks only the FLAG, so a real-totals report sent with
    it would be deferred rather than settled and lose the rated lead-forfeit it
    earned.  The zero form is held in exactly one place across both lanes --
    ReportTeamSeriesDc's own normalisation -- and test_r4lens_f1_* is what pins
    that.

    AGAINST AN OLDER SERVER (#266): an unknown query parameter is IGNORED and
    the request is answered 200.  THAT 200 PROVES ONLY THAT THE BOX WHICH
    ANSWERED PREDATES THE FIELD -- it is not proof that the report settled, and
    this docstring said it was until the round-7 review found the claim here,
    inside the harness that checks the same claim in the product (#351: the
    highest-risk claim is the one your own fix authored).  Contract item 6 is
    what the client may state: `deferred` says only whether THIS call parked
    the report, and an ABSENT `deferred` says only that the answering box
    predates the field, never what that box did with the report.  The flag
    costs nothing against such a box, and nothing in the client reads that 200
    as proof the parameter was understood."""
    assert dc_report_query(True) == ["reporter_steam_id", "dc_player_steam_id",
                                     "t1_points_total", "t2_points_total",
                                     "photon_room_id", "is_fallback", "hmac_sig"]
    assert "is_fallback" not in dc_report_query(False)

    api = _src("ApiClient.cs")
    body = _method_body(api, "public static void ReportTeamSeriesDc")
    assert body, "the report composer's own text could not be delimited"
    assert '(fallback ? "&is_fallback=true" : "") +' in body
    # exactly one emission, inside THIS method -- an occurrence count scoped to
    # the function span, never file-wide (#432)
    assert body.count('"&is_fallback=true"') == 1
    # and the signature stays last, so the unsigned hint rides outside it
    assert body.index('"&is_fallback=true"') < body.index("hmac_sig=")

    def claim(s):
        b = _method_body(s, "public static void ReportTeamSeriesDc")
        return (bool(b) and '(fallback ? "&is_fallback=true" : "") +' in b
                and b.count('"&is_fallback=true"') == 1)

    _assert_discriminating(
        claim, api,
        _mutate(api, '                         (fallback ? "&is_fallback=true" : "") +\n', "",
                "R4 is_fallback dropped"),
        "R4 H3 the fallback names itself")

    # the OTHER mutation this needs: the flag sent unconditionally, which would
    # ask the server to defer a real-totals prompt report as well
    _assert_discriminating(
        claim, api,
        _mutate(api, '(fallback ? "&is_fallback=true" : "") +', '"&is_fallback=true" +',
                "R4 is_fallback sent on every report"),
        "R4 H3 only a fallback names itself")

    # NEGATIVE CONTROL
    assert claim(_mutate(api, "// DIRECTION (#283). Setting it moves the server away",
                         "// DIRECTION (#283): setting it moves the server away",
                         "R4 H3 is_fallback negative control"))


def test_r5_h3_the_deferred_answer_is_a_three_value_measurement():
    """A 200 alone does not distinguish a box that deferred this fallback from
    one that dropped the unknown parameter and settled on it (#266).  Round 4
    read `deferred` as a bool and called its absence "this server does not
    carry the deferral rule" -- but a bool extractor answers False for "absent"
    and for "false" alike (#604), and that endpoint's own validation exits
    emitted no `deferred` either, so the line was an inference about a box from
    a field several of its own answers withheld.

    THE CROSS-LANE CONTRACT CLOSES IT at the source: `deferred` is now PRESENT
    on every 200 that endpoint returns.  So the client reads three values, not
    two, and each line says exactly what its value proves:

      present and true   this box deferred this report
      present and false  this box carries the deferral build and did NOT park
       + ignored=true    this report -- and wrote nothing either: the status in
                         the answer is the one the row already held
      present and false  this box carries the build and took an exit this client
       + no ignored      does not model; the line claims nothing about the write
      absent from a 200  the box that answered PREDATES the field, and that is
                         the whole of what the absence proves

    THE ABSENT BRANCH IS THE ROUND-6 CORRECTION.  It used to read a missing key
    as a SETTLEMENT and name the status it assumed had been written.  A box that
    predates the field still carries the three exits that write nothing and
    answer {"ignored": true} -- the settled-row exit and the two room fences,
    which the production pin has at its report-dc as well -- so "no deferred
    key" covers a settle and a no-write refusal alike.  The branch now reads the
    "ignored" key that generation DOES emit, says which of the two facts it
    holds, and claims no write it cannot see.

    THE FOURTH VALUE IS THE LENS FINDING.  The line used to say "settled this
    report at one of its other exits ... still bounds the row to dc_incomplete".
    On a box carrying the rule the deferral branch PRECEDES every settling
    write, so a report with is_fallback set reaches no settling exit at all --
    the three exits it can reach answer {"ignored": true}, write nothing, and
    echo the status the row already had, which may be `completed` and rated.

    A NON-200 proves nothing about any box, which is why the read is taken only
    on `ok`."""
    api = _src("ApiClient.cs")
    send = _method_body(api, "private static IEnumerator SendTeamSeriesDcReport")
    assert send, "the dispatch half's own text could not be delimited"

    # presence is measured separately from value -- the #604 shape
    assert 'resp.IndexOf("\\"deferred\\"", StringComparison.Ordinal) >= 0' in send
    assert 'ExtractJsonBool(resp, "deferred")' in send
    # three lines, one per value
    assert "fallback DEFERRED by the server" in send
    assert "fallback NOT PARKED AND NOT APPLIED " in send
    assert 'ExtractJsonBool(resp, "ignored")' in send
    assert "fallback answered by a box that PREDATES the deferral" in send
    # and the absent branch claims NO disposition: no settle, no status named
    assert "That is all the absence proves" in send
    assert "a settle and a no-write refusal are not distinguishable from" in send
    assert "still bounds the row to dc_incomplete" not in send
    # it reads the key that generation does emit rather than inferring
    assert "bool oldIgnored = false;" in send
    # exactly two readers of `ignored` in this method, one per branch that has a
    # body to read it from -- counted within the FUNCTION span, never file-wide
    # (#330, #279)
    assert send.count('ExtractJsonBool(resp, "ignored")') == 2
    # the whole read sits inside `if (ok)`, so a non-200 says nothing
    assert send.index("if (ok)") < send.index('resp.IndexOf("\\"deferred\\"')
    # the deferred read happens on the FALLBACK path and before its return
    assert send.index("if (fallback)") < send.index('ExtractJsonBool(resp, "deferred")')
    # the prompt path is untouched: it still publishes the three-way outcome
    assert "DcReportSync.OutcomeUnknown" in send

    def claim(s):
        b = _method_body(s, "private static IEnumerator SendTeamSeriesDcReport")
        if not b:
            return False
        return ('resp.IndexOf("\\"deferred\\"", StringComparison.Ordinal) >= 0' in b
                and 'ExtractJsonBool(resp, "deferred")' in b
                and "fallback DEFERRED by the server" in b
                and "fallback NOT PARKED AND NOT APPLIED " in b
                and "fallback answered by a box that PREDATES the deferral" in b
                and "That is all the absence proves" in b
                and "still bounds the row to dc_incomplete" not in b
                and "bool oldIgnored = false;" in b)

    # MUTATION 1: the field is never read at all
    _assert_discriminating(
        claim, api,
        _mutate(api, 'try { deferred = ExtractJsonBool(resp, "deferred"); } catch { deferred = false; }',
                "deferred = false;",
                "R5 deferred status never read"),
        "R5 H3 the deferred answer is read and named")

    # MUTATION 2: presence collapses back into value, which is the round-4
    # reading -- absent and false become one fact again
    _assert_discriminating(
        claim, api,
        _mutate(api,
                '                        bool present = !string.IsNullOrEmpty(resp)\n'
                '                                       && resp.IndexOf("\\"deferred\\"", '
                'StringComparison.Ordinal) >= 0;',
                "                        bool present = true;",
                "R5 deferred presence collapsed into value"),
        "R5 H3 absence and false are two facts")

    # NEGATIVE CONTROL: rewording the prose of one line leaves all three claims
    assert claim(_mutate(api, "left open so a real-totals report can still take",
                         "left open so a real-totals report may still take",
                         "R5 H3 deferred negative control"))

# ── H5 / M1 / L1: comments that asserted what the tree does not keep ─────────


def test_r4_h5_the_election_note_states_the_departure_rule_and_the_open_residual():
    """A comment asserting a guarantee is a claim about the whole state space
    (#302/#351), and these two were claims the tree stopped keeping rounds ago.

    (a) "plus that seat leaving the room having dispatched nothing" named
        DEPARTURE as a terminal signal that FIRES the fallback.  The tree stands
        the watch DOWN on a departure, and has since the round that wrote the
        rule: the elected seat's departure is itself a disconnect in this same
        series, the election runs again for it in the very next statements, and
        a real-totals report about it is composed in a process this watch holds
        no property from.

    (b) "so no ordering of the two can select the rated completion" was
        withdrawn by the round before this one and left standing here.  A
        zero-total fallback that takes the row lock first writes dc_incomplete
        and a real-totals report behind it is answered {"ignored": true}.

    What replaces (b) is the narrow claim plus the SERVER-LANE residual named as
    a residual: the client sends is_fallback, and against a server without the
    deferral rule the parameter is ignored and the displacement stands."""
    plug = _src("Plugin.cs")

    # the withdrawn claims are gone
    assert "so no ordering of the two can select the rated" not in plug
    assert "seat leaving the room having dispatched nothing" not in plug
    # the rule the tree actually keeps is stated
    assert "DEPARTURE IS NOT A TRIGGER" in plug
    assert "stands the watch DOWN" in plug or "STANDS THE WATCH DOWN" in plug
    # the residual is named as a residual, with its server dependency and #266
    assert "is_fallback=true" in plug
    assert "(#266)" in plug
    assert "THAT IS THE WHOLE CLAIM" in plug
    # the lying-client enumeration no longer lists departure as the trigger
    assert "Leaving the room is" in plug

    def claim(s):
        return ("so no ordering of the two can select the rated" not in s
                and "seat leaving the room having dispatched nothing" not in s
                and "DEPARTURE IS NOT A TRIGGER" in s)

    _assert_discriminating(
        claim, plug,
        _mutate(plug, "                //      DEPARTURE IS NOT A TRIGGER",
                "                //      so no ordering of the two can select the rated\n"
                "                //      completion. DEPARTURE IS NOT A TRIGGER",
                "R4 withdrawn ordering claim restored"),
        "R4 H5 the election note keeps only claims the tree keeps")

    # NEGATIVE CONTROL: an unrelated wording change leaves it true
    assert claim(_mutate(plug, "elapsed-time guess about another seat's transaction",
                         "elapsed-time guess at another seat's transaction",
                         "R4 H5 comment negative control"))


def test_r4_m1_the_capability_note_documents_the_four_idle_states():
    """The staging gate admits four idle client states; this note named two.

    Narrowing the gate to the pair it named is not hypothetical: it is what
    stopped the sibling capability staging at all once staging moved behind the
    compatibility verdict, because the pair excluded every state the verdict
    lands in.  The capability was then inert for the session with nothing in the
    log saying so, which was the fifth HIGH of an earlier round (#342)."""
    vf = _src("VanillaFixes.cs")
    doc = vf[vf.index("/// <summary>Identical state rules to PoisonSync.StageCapability"):]
    doc = doc[:doc.index("internal static void StageCapability(string source)")]

    assert "merge only while Disconnected/PeerCreated" not in doc
    for st in ("Disconnected", "PeerCreated", "ConnectedToMasterServer", "JoinedLobby"):
        assert st in doc, st
    assert "FOUR states" in doc or "four states" in doc
    assert "InIdleClientState" in doc
    # and the implementation really is that helper.  Sliced from the NOTE, not
    # from the file's FIRST StageCapability: VanillaFixes carries more than one
    # capability class, and a window that opens on the wrong one reads a
    # neighbour's statements as this fix's (#342, the same defect _method_body
    # exists to refuse).
    impl = vf[vf.index("/// <summary>Identical state rules to PoisonSync.StageCapability"):]
    impl = impl[:impl.index("internal static void RevokeCapability")]
    assert "if (!InIdleClientState())" in impl

    def claim(s):
        if "/// <summary>Identical state rules to PoisonSync.StageCapability" not in s:
            return False
        d = s[s.index("/// <summary>Identical state rules to PoisonSync.StageCapability"):]
        d = d[:d.index("internal static void StageCapability(string source)")]
        return ("merge only while Disconnected/PeerCreated" not in d
                and all(x in d for x in ("ConnectedToMasterServer", "JoinedLobby")))

    _assert_discriminating(
        claim, vf,
        _mutate(vf, "        /// refuse in-room, merge only from an IDLE client state, one-shot, retried",
                "        /// refuse in-room, merge only while Disconnected/PeerCreated, one-shot, retried",
                "R4 two-state capability note restored"),
        "R4 M1 the capability note names the gate it has")

    # NEGATIVE CONTROL
    assert claim(_mutate(vf, "which is what <c>InIdleClientState()</c> is",
                         "which is what <c>InIdleClientState()</c> means",
                         "R4 M1 note negative control"))


def test_r4_l1_the_assembly_loop_comment_names_the_deployed_deadline():
    """The note said the server cancels after 15 s; production defines 180.

    The number matters beyond being wrong.  At 15 s the loop looks like the
    thing that OUTLIVES the deadline, which would make its own duration the
    reason it is safe.  At 180 s the opposite is true and the real reason is
    visible: 3 s of delay plus a 22 s loop is entirely inside the deadline.  And
    the loop's duration bounds only the loop -- the ROW's age is measured from
    room_issued_at on the server and can already be hours old on the first read
    after a resume relock.

    The assertion below is DERIVED from the loop's own terms rather than
    written down twice, so raising either term reddens this instead of passing
    (#342)."""
    plug = _src("Plugin.cs")
    doc = plug[plug.index("/// <summary>Poll /team/series/{id}/state every 2s"):]
    doc = doc[:doc.index("private static System.Collections.IEnumerator PollAssemblyStateLoop")]

    assert "cancels the series after 15s" not in doc
    assert "180 SECONDS" in doc
    assert "_ASSEMBLY_DEADLINE_SECONDS" in doc
    assert "0cc7f75" in doc                       # which server the number is from

    documented = float(re.search(r"(\d+) SECONDS", doc).group(1))
    loop = _method_body(plug,
                        "private static System.Collections.IEnumerator PollAssemblyStateLoop")
    assert loop, "the assembly loop's own text could not be delimited"
    deadline = float(re.search(r"Time\.realtimeSinceStartup \+ (\d+)f", loop).group(1))
    start = float(re.search(r"WaitForSeconds\((\d+)f\)", loop).group(1))
    assert start + deadline < documented, (start, deadline, documented)

    def claim(s):
        if "/// <summary>Poll /team/series/{id}/state every 2s" not in s:
            return False
        d = s[s.index("/// <summary>Poll /team/series/{id}/state every 2s"):]
        d = d[:d.index("private static System.Collections.IEnumerator PollAssemblyStateLoop")]
        m = re.search(r"(\d+) SECONDS", d)
        if not m or "cancels the series after 15s" in d:
            return False
        lp = _method_body(s, "private static System.Collections.IEnumerator PollAssemblyStateLoop")
        if not lp:
            return False
        dl = float(re.search(r"Time\.realtimeSinceStartup \+ (\d+)f", lp).group(1))
        st = float(re.search(r"WaitForSeconds\((\d+)f\)", lp).group(1))
        return st + dl < float(m.group(1))

    _assert_discriminating(
        claim, plug,
        _mutate(plug, "more than 180 SECONDS", "more than 15 SECONDS",
                "R4 stale deadline restored"),
        "R4 L1 the loop comment names the deployed deadline")

    # NEGATIVE CONTROL
    assert claim(_mutate(plug, "which is exactly why this caller",
                         "which is precisely why this caller",
                         "R4 L1 deadline negative control"))


# ══════════════════════════════════════════════════════════════════════════
# ROUND 4 LENS PASS -- four findings against the round-4 tree itself
# ══════════════════════════════════════════════════════════════════════════
#
# All four are claim defects plus one enforcement gap, and all four have the
# shape #351 names: the highest-risk claim is the one the previous round's own
# fix authored.  Three of them were reporting a PASS neither lane had earned --
# two halves of one contract written in the same round, each citing the other
# (#341/#635).


def _flat_comment(text):
    """Comment text with its line wrapping removed.

    A predicate over a SENTENCE must not depend on where that sentence happened
    to wrap: a reflow of the comment would turn the check red for nothing, and
    writing the predicate to match one wrap point is how a check ends up
    measuring the formatter instead of the claim (#342)."""
    return re.sub(r"\s+", " ", re.sub(r"\n\s*(?:///|//)\s?", "\n", text)).strip()


def test_r4lens_f1_the_zero_form_is_enforced_only_here_and_the_comment_says_so():
    """F1.  The is_fallback note claimed a server-side predicate that does not
    exist.

    The server lane's deferral branch reads is_fallback and nothing else -- its
    own note states the placement before the lead-forfeit block is structural
    and does NOT rest on a fallback carrying zero points, "a property of today's
    client and not a check this endpoint could fail on".  The client's DIRECTION
    paragraph nonetheless closed with "the server's predicate requires zero
    totals anyway", which would license a later caller to drop the client-side
    normalisation as redundant.  Nothing anywhere would then hold the two
    consistent: a real-totals report flagged as a fallback is DEFERRED instead
    of settled, and the rated lead-forfeit it earned is lost to the sweep.

    Three properties are asserted: the false sentence is gone, the normalisation
    is still there and is named as the only enforcement in EITHER lane, and it
    emits a positive signal when it has to act (#438) so a bundle can tell a
    caller that passed real totals from one that passed zeros."""
    api = _src("ApiClient.cs")

    def window(s):
        if "public static void ReportTeamSeriesDc(" not in s:
            return ""
        b = s[s.index("public static void ReportTeamSeriesDc("):]
        if "StartCoroutine(SendTeamSeriesDcReport(" not in b:
            return ""
        return b[:b.index("StartCoroutine(SendTeamSeriesDcReport(")]

    def claim(s):
        body = window(s)
        if not body:
            return False
        if "server's predicate requires zero totals" in body:
            return False                       # the retracted claim is back
        if "ENFORCED HERE AND NOWHERE ELSE" not in body:
            return False                       # ...and its replacement is gone
        if "t1PointsTotal = 0;" not in body or "t2PointsTotal = 0;" not in body:
            return False                       # the normalisation itself
        if "non-zero " not in body or "forcing " not in body:
            return False                       # the positive signal beside it
        # the guard on the warning must test BOTH totals, not one
        return "if (t1PointsTotal != 0 || t2PointsTotal != 0)" in body

    # MUTATION: the false server-side claim comes back
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "// with any server-side check and must not be deleted as one.",
                "// with the server's predicate requires zero totals anyway.",
                "R4-lens F1 server-predicate claim restored"),
        "R4-lens F1 the zero form is enforced only here")

    # MUTATION 2: the normalisation is dropped as redundant -- the exact move
    # the false comment licensed
    assert not claim(_mutate(
        api,
        "                t1PointsTotal = 0;\n                t2PointsTotal = 0;\n",
        "                // (the server checks this)\n",
        "R4-lens F1 normalisation dropped"))

    # NEGATIVE CONTROL: rewording the warning's prose leaves the claim true
    assert claim(_mutate(api, "a game it did not watch", "a game it never watched",
                         "R4-lens F1 negative control"))


def readonly_reads_before_the_latch(rtt_seconds, in_flight_rule):
    """How many status reads reach the wire before the first answer latches
    this series dark.

    The dispatcher is a 2 s menu tick; the latch is applied inside a response
    callback.  With no in-flight rule every tick inside the round trip sends.
    With one, a tick whose predecessor has not answered sends nothing, so the
    count is exactly one whatever the latency.

    Transport bound: GetRequest sets request.timeout = 20, so an unanswered
    read cannot outlive 20 s -- the un-guarded count is bounded, not unbounded,
    and the bound is eleven.  That distinction is why this is a model and not a
    rhetorical point: the round-4 lens finding stated there was no timeout, and
    there is one (#327 -- a refutation is recorded, not smoothed over)."""
    rtt = min(rtt_seconds, 20.0)
    if in_flight_rule:
        return 1
    return 1 + int(rtt // 2.0)


def test_r5lens_f2_at_most_one_status_read_is_outstanding():
    """F2, carried forward onto the route that replaced the mode.

    The documented bound was ONE and nothing enforced it:
    UpdateTeamSeriesStatePoll dispatched a fresh coroutine every 2 s, and on a
    6 s answer the real count was four.

    WHAT THE BOUND IS FOR NOW, AND WHY IT IS CHEAPER.  Round 4 needed it
    because each un-honoured read could run the cancel arm on a played active
    series and reconcile its bets -- the reads it limited were WRITES on the
    wrong box.  On this round's route they are reads on every box, so the bound
    no longer stands between a menu tick and a voided series; it stands between
    a menu tick and a queue of reads no answer has closed.  It is kept because
    the refusal it implements is per-series and one-shot: without the rule, ten
    reads can be in flight when the first 404 arrives, and nine of them land
    after the series is already dark (#430 -- a guard is judged by what its
    refusal costs, and this one costs nothing)."""
    # the model: un-guarded, the count grows with latency and tops out at the
    # transport timeout; guarded, it is one everywhere
    for rtt in (0.5, 2.0, 6.0, 19.0, 45.0):
        assert readonly_reads_before_the_latch(rtt, True) == 1, rtt
    # NEGATIVE CONTROL for the model itself: without the rule it is not one
    assert readonly_reads_before_the_latch(6.0, False) == 4
    assert readonly_reads_before_the_latch(45.0, False) == 11

    api = _src("ApiClient.cs")

    def claim(s):
        ro = _method_body(s, "public static void PollTeamSeriesStatusReadOnly")
        if not ro or "StartCoroutine(" not in ro:
            return False
        # the flag is READ before anything is dispatched...
        if "if (_statusReadInFlight) return;" not in ro:
            return False
        if ro.index("if (_statusReadInFlight) return;") > ro.index("StartCoroutine("):
            return False
        # ...set before the dispatch...
        if "_statusReadInFlight = true;" not in ro:
            return False
        if ro.index("_statusReadInFlight = true;") > ro.index("StartCoroutine("):
            return False
        # ...cleared inside the response callback BEFORE the gate that can
        # return early...
        if "_statusReadInFlight = false;" not in ro:
            return False
        after = ro[ro.index("StartCoroutine("):]
        if "if (!affirmed)" not in after:
            return False
        if after.index("_statusReadInFlight = false;") > after.index("if (!affirmed)"):
            return False
        # ...and released when the dispatch itself throws, or one transient
        # failure leaves this route unable to poll at all
        return "catch (Exception ex)" in ro and ro.count("_statusReadInFlight = false;") == 2

    # MUTATION: the in-flight gate is removed -- the round-4 tree
    _assert_discriminating(
        claim, api,
        _mutate(api, "            if (_statusReadInFlight) return;                        // GATE 3",
                "            // no in-flight rule                                    // GATE 3",
                "R5-lens F2 in-flight gate removed"),
        "R5-lens F2 one status read outstanding")

    # MUTATION 2: the flag is cleared only after the early return, so a failed
    # read leaves the route unable to dispatch for the session
    assert not claim(_mutate(
        api,
        "                    _statusReadInFlight = false;\n"
        "                    // The banner's inputs as of this ANSWER.",
        "                    // The banner's inputs as of this ANSWER.",
        "R5-lens F2 clear moved after the early return"))

    # NEGATIVE CONTROL: rewording the dispatch-failure log leaves the claim true
    assert claim(_mutate(api, "series status read could not be dispatched",
                         "series status read was not dispatched",
                         "R5-lens F2 negative control"))

    # the documented bound names the mechanism rather than asserting it, and the
    # transport term the model uses is the one the source actually sets
    assert "GATE 3" in api
    assert "request.timeout = 20;" in api

def test_r4lens_f3_the_outcome_quorum_is_dominated_by_the_election_quorum():
    """F3.  The mixed-room refusal cannot fire, and the comment justifying two
    keys rested on a premise no tree supports.

    cr_dc2, cr_dc3 and cr_dcr are on NO released tree.  Both capability keys are
    written in one SetCustomProperties merge and withdrawn in one, so a seat
    carries both or neither.  ArmFallback has exactly one caller, the census arm
    in Plugin.OnPlayerLeftRoom, which has already taken the cr_dc2 quorum over
    the SAME seat list it then hands on -- so AllOutcomeCapable can only return
    False where AllCapable already did, i.e. never on the path that reaches it.

    The old comment said re-keying cr_dc2 "would drop rooms to the floor
    election for no reason", which is true only of a key that shipped.  The
    guard is KEPT -- the gate belongs to the operation, not to one caller's
    discipline (#432) -- but the text must now say what it can and cannot catch,
    because a reviewer reading it as "mixed-version 2v2 is handled" stops
    looking, and the branch's log line can never appear in a bundle."""
    ra = _src("RoomActors.cs")
    plug = _src("Plugin.cs")

    # STRUCTURE: ArmFallback has exactly one caller, and it is the census arm
    sites = _call_sites("ArmFallback")
    assert sites == {("Plugin.cs", "OnPlayerLeftRoom")}, sites

    # ...and that caller hands on the same list the election quorum ran over
    assert "observedRoom, survivors);" in plug
    assert "DcReportSync.AllCapable(survivors, out missingCap)" in plug
    assert (plug.index("DcReportSync.AllCapable(survivors")
            < plug.index("DcReportSync.ArmFallback(seriesId, elected"))
    # and the call sits under the census arm's own gate
    assert "bool unique = teamsKnown && survivors.Count == 3 && roomWide;" in plug

    # BOTH keys ride one merge and one revoke, so a seat carries both or neither
    body = ra[ra.index("internal static class DcReportSync"):]
    stage = body[body.index("internal static void StageCapability(string source)"):]
    stage = stage[:stage.index("internal static void RevokeCapability()")]
    assert stage.count("SetCustomProperties") == 1
    assert "{ CapabilityProp, CapabilityValue }," in stage
    assert "{ OutcomeCapabilityProp, OutcomeCapabilityValue }" in stage

    def claim(s):
        if "internal static class DcReportSync" not in s:
            return False
        head = _flat_comment(s[:s.index("internal static class DcReportSync")])
        # the retracted premise is quoted as retracted, never asserted
        if "is on no released tree" not in head:
            return False
        if "DOMINATED by the election quorum" not in head:
            return False
        if "cr_dc4" not in head:        # cr_dc3 is spent; the next election key is 4
            return False
        b = s[s.index("internal static class DcReportSync"):]
        if "internal static void ArmFallback(string seriesId" not in b:
            return False
        a = b[b.index("internal static void ArmFallback(string seriesId"):]
        a = a[:a.index("internal static void NoteActorProps")]
        # the guard is still taken, before any watch state is written
        if "AllOutcomeCapable(fighterSeats, out missingOutcome)" not in a:
            return False
        if a.index("AllOutcomeCapable(") > a.index("_watchSeries = seriesId;"):
            return False
        # ...and the comment states the reachability truth rather than implying
        # that a mixed-version room was exercised
        af = _flat_comment(a)
        return ("cannot fire on a room a player can assemble" in af
                and "exactly one caller" in af
                and "proves nothing either way" in af)

    # MUTATION: the reachability sentence is turned back into the reading it
    # replaces -- "this guard covers mixed rooms" -- which is what a reviewer
    # took from the branch before
    _assert_discriminating(
        claim, ra,
        _mutate(ra,
                "So this refusal cannot fire on a room",
                "So this refusal is what protects a room",
                "R4-lens F3 reachability sentence restored to the old reading"),
        "R4-lens F3 the outcome quorum is dominated")

    # MUTATION 2: the head-note premise is restored to the retracted form.  The
    # anchor is the HEAD paragraph's own line, not the bare sentence -- the
    # sentence also occurs in the cr_dcr note further down, and a mutation that
    # lands on the wrong occurrence is a control that cannot fail (#342).
    assert not claim(_mutate(
        ra,
        "<para>AND NO GENERATION OF IT HAS SHIPPED. <c>cr_dc2</c> is on no released",
        "<para>AND IT SHIPPED LONG AGO. <c>cr_dc2</c> is on every released",
        "R4-lens F3 shipped-key premise restored"))

    # MUTATION 3: the guard is deleted.  The claim must still fail: the fix is
    # "keep the gate AND state its reach", not one or the other
    assert not claim(_mutate(
        ra,
        "                if (!AllOutcomeCapable(fighterSeats, out missingOutcome))",
        "                if (false)",
        "R4-lens F3 guard deleted"))

    # NEGATIVE CONTROL: rewording the kept-anyway rationale leaves it true
    assert claim(_mutate(ra, "and not as belt-and-braces", "and not as belt and braces",
                         "R4-lens F3 negative control"))


def test_r4lens_f4_no_comment_certifies_a_deployed_cr_dcr_parser():
    """F4.  Two summaries asserted, in the present tense, how "an older build"
    parses cr_dcr -- a property of an unreleased intermediate tree stated as a
    fact about builds in the field.

    No shipped build parses cr_dcr at all.  The compatibility direction those
    paragraphs certified is real only as BRANCH HISTORY, and the danger is the
    next round: a change to the cr_dcr value set that consults them reads a
    verified statement about deployed parsers and leaves publication
    unconditional without re-deriving it -- by which time cr_dcr may have
    shipped, and the real deployed parser's behaviour on an unknown token was
    never checked, only asserted (#302, #351).

    Publication STAYS unconditional; only its justification changes, and the
    text now carries the condition under which it must be re-derived."""
    ra = _src("RoomActors.cs")

    def claim(s):
        if "internal static class DcReportSync" not in s:
            return False
        b = s[s.index("internal static class DcReportSync"):]
        # neither summary may assert a deployed parser...
        if "three-token parser does not admit" in b:
            return False
        if "A build that predates this value reads it" in b:
            return False
        # ...both must say it as branch history, and name the re-derive trigger
        if "parsed by NO released build" not in b:
            return False
        if "an earlier commit on THIS" not in b:
            return False
        if "must re-derive whether publication may stay" not in b:
            return False
        # publication itself is still ungated
        pub = _method_body(s, "internal static void PublishOutcome(string seriesId, string outcome)")
        if not pub:
            return False
        return "OutcomeCapabilityProp" not in pub

    # MUTATION: the deployed-parser assertion comes back
    _assert_discriminating(
        claim, ra,
        _mutate(ra, "<c>cr_dcr</c> is parsed by NO released build",
                "<c>cr_dcr</c> is parsed by every older build",
                "R4-lens F4 deployed-parser claim restored"),
        "R4-lens F4 no comment certifies a deployed parser")

    # MUTATION 2: the re-derive condition is dropped -- the sentence the next
    # round would have needed
    assert not claim(_mutate(ra, "must re-derive whether publication may stay",
                             "may assume publication stays",
                             "R4-lens F4 re-derive condition dropped"))

    # MUTATION 3: publication becomes gated -- the thing that must NOT change
    assert not claim(_mutate(
        ra,
        "                string tag = Tag(seriesId);",
        "                string tag = Tag(seriesId);\n"
        "                if (OutcomeCapabilityProp == null) return;",
        "R4-lens F4 publication gated"))

    # the refusal's own log line must not claim older builds read cr_dcr either
    assert "read exactly as they always did" not in ra
    assert "released build parses at all" in ra

    # NEGATIVE CONTROL: rewording the branch-history sentence leaves it true
    assert claim(_mutate(ra, "not about a deployed parser",
                         "and not about a deployed parser",
                         "R4-lens F4 negative control"))


# ── R5: the status channel on the shared GET helper ─────────────────────────


def test_r5_the_status_channel_reports_before_every_callback():
    """THE ONE SHARED METHOD THIS ROUND TOUCHES, and the rule that keeps the
    touch honest.

    The status banner has to name the HTTP status its read was answered with --
    that is the whole content of the line the contract requires, and "HTTP 404"
    and "no answer at all" are the two facts a reviewer needs to tell apart
    (#342).  GetRequest knew the code and threw it away.

    IT IS ADDITIVE AND IT IS ORDERED.  The sink defaults to null, so the ~100
    other callers are unchanged and a null sink is never invoked; and on EVERY
    exit it is invoked immediately BEFORE the body callback, so a caller
    reading it from inside that callback always reads this request's own code
    rather than the previous one's.  The insecure-transport refusal invokes the
    callback itself, so it is handed a wrapper rather than the raw callback --
    otherwise the code would arrive after the body it describes.

    The check below is ORDERING, not presence: it merges the report sites and
    the callback sites into one sequence and requires every callback to be
    immediately preceded by a report.  A presence check would pass on a tree
    that reported once and called back four times."""
    api = _src("ApiClient.cs")
    sig = "private static IEnumerator GetRequest(string url, Action<bool, string> callback,"
    body = _method_body(api, sig)
    assert body, "GetRequest's own text could not be delimited"

    def events(text):
        out = []
        for i, ln in enumerate(text.split("\n")):
            if "onResponseCode(" in ln:
                out.append(("report", i))
            elif "callback(" in ln and "Action<bool" not in ln:
                out.append(("call", i))
        return out

    def claim(s):
        b = _method_body(s, sig)
        if not b:
            return False
        if "Action<long> onResponseCode = null)" not in b:
            return False
        ev = events(b)
        calls = [e for e in ev if e[0] == "call"]
        if len(calls) < 4:
            return False                      # the four exits must all be there
        for idx, (kind, _line) in enumerate(ev):
            if kind != "call":
                continue
            if idx == 0 or ev[idx - 1][0] != "report":
                return False
        return True

    assert claim(api)

    # the default keeps every other caller exactly as it was
    assert "Action<long> onResponseCode = null)" in api
    # and exactly one caller passes it
    assert api.count("onResponseCode: ") == 1
    assert _member_owning(api, "onResponseCode: code =>") == "PollTeamSeriesStatusReadOnly"

    # MUTATION: the report on the answered exit goes, so the status the banner
    # prints is whatever the previous request left behind
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "                if (onResponseCode != null) onResponseCode(request.responseCode);\n"
                "                callback(success, success",
                "                callback(success, success",
                "R5 the answered exit stops reporting its code"),
        "R5 every GetRequest exit reports its code before the callback")

    # MUTATION 2: the insecure-transport refusal is handed the raw callback
    # again, so on that exit the code arrives after the body
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "            if (SensitiveTransportBlocked(url, null, (ok0, body0) =>\n"
                "                {\n"
                "                    if (onResponseCode != null) onResponseCode(0);\n"
                "                    callback(ok0, body0);\n"
                "                })) yield break;",
                "            if (SensitiveTransportBlocked(url, null, callback)) yield break;",
                "R5 the transport refusal drops its report"),
        "R5 the pre-wire refusals report before their callback")

    # NEGATIVE CONTROL: rewording the sink's own comment changes no ordering
    assert claim(_mutate(api, "Both pre-wire refusals report 0 before the callback",
                         "Both pre-wire refusals report zero before the callback",
                         "R5 status-channel negative control"))


# ── ROUND-5 COLD LENS ────────────────────────────────────────────────────────
# One test per finding the lens raised against the round-5 client tip
# (f5affa9).  Each pins the behaviour at the NEW tip, each carries a mutation
# that removes the fix, and each carries a negative control that reworders
# prose without touching the claim.


def test_r5lens_the_latch_darkens_what_the_banner_actually_renders_from():
    """LATCHING STOPS THE POLL; IT MUST ALSO DARKEN THE BANNER.

    The lens found the two were different facts (#342).  `_statusPollDarkSeries
    .Add(seriesId)` was followed by `return`, and the four fields the banner
    renders from were left holding the last good answer.  Their only other
    writer is the ActiveTeamSeriesId setter, which fires on an id CHANGE, so in
    the one window the banner exists for the banner stayed LIT and frozen --
    rendering a countdown that nothing would ever refresh again, for as long as
    the tab stayed open.

    WHAT DARKENS IT, ROUND 6: the banner's whole input is the three deferral
    fields the status route carries, so clearing those is the whole of it.

    THE CONFINEMENT IS THE ROUND-6 CORRECTION.  The round-5 guard read
    `LastSeriesStateForId == seriesId || seriesId == ActiveTeamSeriesId` under a
    comment promising the clear happened "only while the cache describes THIS
    series" -- and the second arm is exactly the case that breaks it: a late
    answer for series B leaves the cache describing B, and a failed read of the
    active series A then satisfied that arm and blanked B's numbers.  The
    comment stated the rule the code broke (#351).  The clear is now confined to
    the cached series, and the cross-series case it was reaching for is refused
    at the RENDER, where the banner draws only while the cache's ForId names the
    series it is about.

    This is the fix the box-matrix test could not see: that test models
    `latched` and never asks what the UI shows afterwards."""
    api = _src("ApiClient.cs")
    ro = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    assert ro, "the read-only poller's own text could not be delimited"

    # the clear sits in the SAME branch as the latch, before its return
    assert "_statusPollDarkSeries.Add(seriesId);" in ro
    assert "LastSeriesDcDeferred = false;" in ro
    assert "LastSeriesDcDeferredSecondsRemaining = 0;" in ro
    assert "LastSeriesDcDeferredBoundSeconds = 0;" in ro
    assert (ro.index("_statusPollDarkSeries.Add(seriesId);")
            < ro.index("LastSeriesDcDeferred = false;"))
    # and it is confined to the series the cache describes -- one arm, no OR.
    # The retired arm survives in the comment that explains WHY it went, which is
    # how the next reader learns not to re-add it; what must not survive is the
    # arm as CODE.
    assert "if (LastSeriesStateForId == seriesId)" in ro
    for line in ro.split("\n"):
        if "seriesId == ActiveTeamSeriesId" in line:
            assert line.strip().startswith("//"), line
    # the retired statics are gone from the whole client, not merely unread
    assert "LastSeriesDcGraceSeconds" not in api
    assert "LastSeriesDcTeamRemaining" not in api
    assert "LastSeriesDcGraceSeconds" not in _src("NativeUI.cs")

    def claim(s):
        b = _method_body(s, "public static void PollTeamSeriesStatusReadOnly")
        if not b:
            return False
        return ("LastSeriesDcDeferred = false;" in b
                and "LastSeriesDcDeferredSecondsRemaining = 0;" in b
                and "LastSeriesDcDeferredBoundSeconds = 0;" in b
                and "if (LastSeriesStateForId == seriesId)" in b
                and all(ln.strip().startswith("//")
                        for ln in b.split("\n") if "seriesId == ActiveTeamSeriesId" in ln)
                and b.index("_statusPollDarkSeries.Add(seriesId);")
                    < b.index("LastSeriesDcDeferred = false;"))

    # MUTATION 1: the latch goes back to stopping the poll and nothing else
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "                            LastSeriesDcDeferred = false;\n"
                "                            LastSeriesDcDeferredSecondsRemaining = 0;\n"
                "                            LastSeriesDcDeferredBoundSeconds = 0;\n",
                "",
                "R6 the latch leaves the banner lit"),
        "R6 a latched series renders dark")

    # MUTATION 2: the confinement goes, so latching one series blanks whatever
    # the cache currently describes
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "if (LastSeriesStateForId == seriesId)",
                "if (true)",
                "R6 the clear is unconfined"),
        "R6 the clear names the series it is about")

    # MUTATION 3: THE ROUND-5 SHAPE ITSELF.  The second OR arm is the defect the
    # lens found, and putting it back must redden this test -- a late answer for
    # B followed by a failed read of the active A would clear B again.
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "if (LastSeriesStateForId == seriesId)",
                "if (LastSeriesStateForId == seriesId || seriesId == ActiveTeamSeriesId)",
                "R6 the round-5 second arm returns"),
        "R6 the clear is confined to the cached series")

    # NEGATIVE CONTROL: rewording the comment above the clear changes nothing
    assert claim(_mutate(api, "DARK HAS TO MEAN DARK,", "DARK MUST MEAN DARK,",
                         "R6 latch negative control"))


def test_r5lens_the_refusal_line_splits_on_whether_a_box_answered():
    """THE TRIAGE LINE MUST NOT NAME A CAUSE IT DOES NOT HAVE.

    The latch is taken on any answer that is not a 200 carrying readonly=true,
    and that includes every cell where NOTHING answered: a refusal before the
    wire (consent, sensitive transport), a transport failure, the 20 s timeout
    -- all reported as HTTP 0.  The latch-site line already split on
    `answeredWith > 0`.  The TICK's line, which is the one a triage grep for
    "NOT polling" lands on, stated the box cause unconditionally: "a box
    answering for this seat has no read-only status route for it".  In an
    HTTP-0 cell that sentence is false and points an investigation at a
    deployment that may be entirely correct.

    The cause is carried to the tick in its own set, so the line can say which
    of the two facts it holds."""
    api = _src("ApiClient.cs")
    ui = _method_body(api, "public static void UpdateTeamSeriesStatePoll")
    assert ui, "the tick's own text could not be delimited"

    assert "_statusPollDarkNoAnswer.Contains(sid)" in ui
    assert "never reached a box" in ui
    assert "This line says nothing about any box's routes" in ui
    assert "did not answer that read AS a read" in ui
    # the unconditional box claim is gone
    assert "a box answering for this seat has no read-only status route" not in api

    # the cause is RECORDED where the latch is taken, from this request's code
    ro = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    assert "if (answeredWith <= 0) _statusPollDarkNoAnswer.Add(seriesId);" in ro

    def claim(s):
        b = _method_body(s, "public static void UpdateTeamSeriesStatePoll")
        p = _method_body(s, "public static void PollTeamSeriesStatusReadOnly")
        if not b or not p:
            return False
        return ("_statusPollDarkNoAnswer.Contains(sid)" in b
                and "never reached a box" in b
                and "did not answer that read AS a read" in b
                and "if (answeredWith <= 0) _statusPollDarkNoAnswer.Add(seriesId);" in p
                and "a box answering for this seat has no read-only status route" not in s)

    # MUTATION 1: the line goes back to naming the box cause for every cell
    _assert_discriminating(
        claim, api,
        _mutate(api,
                '                        + (_statusPollDarkNoAnswer.Contains(sid)',
                '                        + (false',
                "R5lens the refusal line stops measuring"),
        "R5lens the refusal line reads the cause it recorded")

    # MUTATION 2: nothing records the cause, so the tick can only guess
    _assert_discriminating(
        claim, api,
        _mutate(api, "if (answeredWith <= 0) _statusPollDarkNoAnswer.Add(seriesId);",
                "",
                "R5lens the cause is never recorded"),
        "R5lens the cause is recorded at the latch")

    # NEGATIVE CONTROL: rewording the no-answer half keeps both facts
    assert claim(_mutate(api,
                         "transport failure, or the 20 s timeout, recorded as HTTP 0 when ",
                         "transport fault, or the 20 s timeout, recorded as HTTP 0 when ",
                         "R5lens refusal negative control"))


def test_r5lens_a_deferred_false_answer_claims_no_write():
    """AN IGNORED REPORT WROTE NOTHING, AND THE LINE MUST SAY SO.

    The three exits a fallback report can reach on a rule-carrying box answer
    {"status": <the row's EXISTING status>, "ignored": true, "deferred": false}
    and write nothing at all -- the deferral branch precedes every settling
    write, so no settling exit is reachable with is_fallback set.  The client
    line said the box "settled this report at one of its other exits" and that
    "the zero-total form still bounds the row to dc_incomplete": two claims
    about a write that did not happen, on a row whose real status may be
    `completed` and rated from the other seat's prompt report.

    The `ignored` key was in the body all along and was never read."""
    api = _src("ApiClient.cs")
    send = _method_body(api, "private static IEnumerator SendTeamSeriesDcReport")
    assert send, "the dispatch half's own text could not be delimited"

    # presence measured separately from value, the #604 shape, as for `deferred`.
    # ROUND 6: the absent-field branch reads `ignored` too, into its OWN variable,
    # so a bare search for the extractor is no longer specific to THIS branch -- a
    # predicate that a neighbouring reader can satisfy is a check that cannot fail
    # where it matters (#342, #432).  The claim names the false branch's reader.
    assert 'resp.IndexOf("\\"ignored\\"", StringComparison.Ordinal) >= 0' in send
    assert 'try { ignored = ExtractJsonBool(resp, "ignored"); } catch { ignored = false; }' in send
    assert "fallback NOT PARKED AND NOT APPLIED " in send
    assert "this report changed nothing and bounds nothing" in send
    # the two false claims are gone from the whole file
    assert "settled this report at one of its other exits" not in api
    assert "The zero-total form still bounds the row to dc_incomplete" not in api

    def claim(s):
        b = _method_body(s, "private static IEnumerator SendTeamSeriesDcReport")
        if not b:
            return False
        return ('try { ignored = ExtractJsonBool(resp, "ignored"); } catch { ignored = false; }' in b
                and "fallback NOT PARKED AND NOT APPLIED " in b
                and "this report changed nothing and bounds nothing" in b
                and "settled this report at one of its other exits" not in s)

    # MUTATION 1: the ignored key stops being read, so both values collapse
    # back into one line that claims a write
    _assert_discriminating(
        claim, api,
        _mutate(api, 'try { ignored = ExtractJsonBool(resp, "ignored"); } catch { ignored = false; }',
                "ignored = false;",
                "R5lens the ignored key is never read"),
        "R5lens deferred=false reads the ignored key")

    # MUTATION 2: the honest line is replaced by the round-5 wording
    _assert_discriminating(
        claim, api,
        _mutate(api, "fallback NOT PARKED AND NOT APPLIED ",
                "fallback settled this report at one of its other exits ",
                "R5lens the line claims a write again"),
        "R5lens the line claims no write")

    # NEGATIVE CONTROL: rewording the comment above it keeps the claim
    assert claim(_mutate(api, "DOES NOT MEAN THIS REPORT SETTLED ANYTHING",
                         "DOES NOT MEAN THIS REPORT SETTLED ANY ROW",
                         "R5lens ignored negative control"))


def _dc_banner_block(ui):
    """The DC banner's render block, and "" when its bounds cannot be
    established.  A predicate read off the whole 30 000-line file would be
    satisfied by any other method's text; the claim is about THIS block."""
    a = "// DC BANNER — WHAT IT RENDERS FROM."
    b = "// In Queue panel"
    if a not in ui or b not in ui:
        return ""
    start = ui.index(a)
    end = ui.index(b, start)
    return ui[start:end]


def test_r6_item7_the_dead_banner_predicate_is_deleted_not_preserved():
    """THE ROUND-5 TEST REQUIRED THE DEAD PREDICATE.  THIS ONE REJECTS IT.

    The banner rendered behind `status == "dc_paused" && remaining > 0`, and no
    box could satisfy it: no statement in the api sets that status, the flow
    that did was retired in v1.30.0, dc_grace_until is only ever written NULL,
    and the primary holds no row in it.  Round 5 MEASURED that and kept the
    predicate, with a test asserting it was still in the file -- so the check
    that existed guarded the defect.  A dead mechanism is deleted, not
    preserved (#310, #389), and the check that used to preserve it now fails if
    it comes back.

    WHAT REPLACES IT is the cross-lane contract's three fields, and the client
    reads those names and no others.  The show predicate is `dc_deferred`
    ALONE: a marker past its bound that no sweep tick has settled answers
    dc_deferred=true with zero seconds remaining, and gating on a positive
    remaining time would hide the banner in exactly the state it exists for --
    the deleted defect in a new spelling.

    TWO GATES BESIDE IT, both failing to OFF: the cache must describe this
    series (the ForId discipline), and the series must not be latched dark."""
    api = _src("ApiClient.cs")
    ui = _src("NativeUI.cs")
    block = _dc_banner_block(ui)
    assert block, "the DC banner block's own bounds could not be established"

    # THE DELETION.  The predicate is gone, and `dc_paused` survives in this
    # block only as PROSE explaining why it was removed -- never as code.
    assert 'dcStatus == "dc_paused" && dcRemaining > 0' not in ui
    assert "ApiClient.LastSeriesStateStatus" not in block
    for line in block.split("\n"):
        if "dc_paused" in line:
            assert line.strip().startswith("//"), line

    # WHAT IT READS INSTEAD: the contract's three names, and nothing of its own
    assert "ApiClient.LastSeriesDcDeferred" in block
    assert "ApiClient.LastSeriesDcDeferredSecondsRemaining" in block
    assert "ApiClient.LastSeriesDcDeferredBoundSeconds" in block
    # NO LOCAL COPY OF THE BOUND, AND ROUND 7 BINDS THE CONTENT.  Round 6 read
    # this as "420 may sit in prose, never in code", and the prose then carried
    # "a 420 s deferral window" -- a restatement of the server's constant in a
    # file whose whole claim is that it keeps no copy of it, and a check that
    # accepted exactly the wording B3 asks it to reject.  The rule is now about
    # CONTENT: the constant appears in this block only inside the contract's
    # bound sentence, verbatim, or it does not appear at all.
    for line in block.split("\n"):
        if "420" in line:
            assert line.strip().startswith("//"), line
    assert _bound_sentence_or_no_constant(block), (
        "the DC banner block restates 420 outside the contract's bound sentence")
    # and the specific superseded wording is rejected by name
    assert "420 s deferral window" not in block

    # THE SHOW PREDICATE IS dc_deferred ALONE
    assert "&& ApiClient.LastSeriesDcDeferred;" in block
    assert "dcRemaining > 0 &&" not in block
    assert "bool dcShow = dcCacheIsThisSeries && !dcLatchedDark" in block
    # the two gates
    assert "ApiClient.LastSeriesStateForId == dcSeries" in block
    assert "ApiClient.SeriesStatusLatchedDark(dcSeries)" in block
    # and the banner's own witness, which the read's positive line is not
    assert "LogDcBannerWitness(dcSeries, dcShow, dcCacheIsThisSeries, dcLatchedDark);" in block
    assert "DC banner SHOWN for series" in ui
    assert "DC banner OFF for series" in ui

    # the retired pricing is gone from the tick's own comment, and the round-6
    # price is stated there instead
    assert "costs is one countdown in one banner" not in api
    assert "AND THE PRICE CHANGED THIS ROUND" in api

    def claim(s_ui):
        b = _dc_banner_block(s_ui)
        if not b:
            return False
        return ('dcStatus == "dc_paused" && dcRemaining > 0' not in s_ui
                # `dc_paused` may survive as PROSE and never as code
                and all(ln.strip().startswith("//")
                        for ln in b.split("\n") if "dc_paused" in ln)
                and "ApiClient.LastSeriesStateStatus" not in b
                and "ApiClient.LastSeriesDcDeferred" in b
                and "ApiClient.LastSeriesDcDeferredSecondsRemaining" in b
                and "ApiClient.LastSeriesDcDeferredBoundSeconds" in b
                and "&& ApiClient.LastSeriesDcDeferred;" in b
                and "ApiClient.LastSeriesStateForId == dcSeries" in b
                and "ApiClient.SeriesStatusLatchedDark(dcSeries)" in b
                and "LogDcBannerWitness(dcSeries, dcShow, dcCacheIsThisSeries, dcLatchedDark);" in b)

    # MUTATION 1: THE DEAD PREDICATE COMES BACK.  This is the mutation the
    # round-5 test could not have: there, this shape was the requirement.
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "if (dcShow)",
                'if (ApiClient.LastSeriesStateStatus == "dc_paused" && dcRemaining > 0)',
                "R6 the dead dc_paused predicate returns"),
        "R6 the dead banner predicate is deleted")

    # MUTATION 2: the show predicate becomes a positive remaining time, which
    # hides the banner in the state it exists for
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "&& ApiClient.LastSeriesDcDeferred;",
                "&& ApiClient.LastSeriesDcDeferredSecondsRemaining > 0;",
                "R6 the banner gates on remaining > 0"),
        "R6 the show predicate is dc_deferred alone")

    # MUTATION 3: the latch stops being a gate, so a dark series keeps drawing
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "bool dcLatchedDark = ApiClient.SeriesStatusLatchedDark(dcSeries);",
                "bool dcLatchedDark = false;",
                "R6 a latched series still renders"),
        "R6 a latched series draws nothing")

    # MUTATION 4: the ForId gate goes, so another series' cache paints this one
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "&& ApiClient.LastSeriesStateForId == dcSeries;",
                "&& true;",
                "R6 the banner renders another series' cache"),
        "R6 the banner renders only the cached series")

    # NEGATIVE CONTROL: rewording the prose above the block keeps every claim
    assert claim(_mutate(ui, "A deleted mechanism beats a patched one",
                         "A deleted mechanism is better than a patched one",
                         "R6 banner-derivation negative control"))


# ── ROUND 6: the cross-lane binding, and the two sentences the contract fixes ─
# One lane cannot verify a contract by reading its own half.  These read BOTH
# trees and grep them for the SAME literals (#341, #444).


def _server_lane_candidates(root, env, worktree_lines):
    """The ordered (path, how, exclusive) candidates for the server lane, as a
    PURE function of its three inputs -- so the RULE can be tested rather than
    only the tree this machine happens to have.

    NEVER A HARDCODED PATH.  A hardcoded target is a check that cannot fail
    where it matters (#342), and a workstation path written into the repository
    is a privacy defect besides.

    $SCR_SERVER_LANE IS EXCLUSIVE.  When something names the tree to read, a
    tree it did not name is never read in its place.  The mutation-control
    runner points that variable at a mutated COPY; falling through to the real
    lane when the copy is missing or half-written would report the control
    GREEN while reading an unmutated tree, which is the control that cannot
    fail.  A named tree that does not carry the route FAILS, and says so.

    WITHOUT IT, THIS REPOSITORY IS ITSELF A CANDIDATE.  The two halves of this
    contract are two branches today and ONE tree once they merge.  On merged
    main -- or in a fresh clone, on another machine, or on CI, where no review
    pin and no sibling worktree ever existed -- the route lives in this very
    repository; a resolver that cannot see that goes red for a reason that has
    nothing to do with the field list it exists to compare, and a red-on-main
    test is deleted or turned into a skip by the next reader.  That would lose
    the binding at exactly the moment the two halves become one artifact.

    NO CANDIDATE IS EVER ANOTHER LANE'S WORKING TREE -- the round-7 cold-lens
    correction, and the reason `worktree_lines` is still a parameter while
    nothing reads it.  Rounds 6 and 7 kept a candidate built from `git worktree
    list`, matched on the lane's exact branch bracket.  The intent was a
    fallback; the effect, in THIS worktree, was the primary resolution: there
    is no `REVIEW-INPUT` beside this branch, and its own `backend/api/main.py`
    carries no status route, so the worktree candidate was the only one that
    could fire.  A plain `python -m pytest` -- the invocation the bundle itself
    publishes -- therefore opened the other lane's LIVE tree, while that lane
    carried a round in flight.  Two things were wrong with that at once: the
    contract requires this equality be proven against the frozen server
    representation and against nothing else, and a tree being written to is not
    a tree a difference can be read from (#304; `_stable_text`'s own docstring
    records the run where that happened).

    A binding whose only real anchor is an environment variable is a binding no
    reader can re-derive.  ROUND 8 TOOK THE WHOLE QUESTION OFF THIS FUNCTION:
    the contract's server half is the hash-verified extract that ships with this
    lane, resolved by `_server_lane_main` through `_frozen_route_text`, and NO
    CANDIDATE THIS FUNCTION RETURNS IS EVER READ BY A CONTRACT ASSERTION.  The
    round-7 arrangement had the extract as a terminal fallback behind these
    candidates, and the delivered review pin carries the route in its own
    `REVIEW-INPUT/server-lane` copy, so from inside the pin a candidate answered
    first and the equality was proven against an unhashed text.

    WHAT THIS FUNCTION IS FOR NOW.  It is the rule, and only its own cases and
    `_named_tree_route_text` call it: a worktree listing contributes NO
    candidate however exactly its branch bracket matches, and a tree that is
    NAMED in $SCR_SERVER_LANE is exclusive -- never silently replaced by
    another.  Both are properties something asserts rather than absences nobody
    checks (#342), which is why the list and the parameter are still here."""
    if env:
        return [(pathlib.Path(env), "the tree $SCR_SERVER_LANE names", True)]
    return [
        (root / "REVIEW-INPUT" / "server-lane",
         "the review pin's server-lane copy", False),
        (root, "this repository itself -- the merged tree", False),
    ]


# The frozen server-lane extract this lane carries, beside this file.  Not a
# module: it is read as TEXT and never imported.
_FROZEN_SERVER_EXTRACT = pathlib.Path(__file__).resolve().parent / \
    "sept16_dc_server_status_route.frozen.txt"
_ROUTE_ANCHOR = '@app.get("/api/v1/team/series/{series_id}/status"'

# THE RECORDED DIGEST OF THE WHOLE EXTRACT FILE.  The extract carries a sha256
# of its own BODY in its provenance header, which is a self-consistent pair: an
# editor that rewrites the body and the header together produces a file that
# still passes that check.  So the digest the contract resolves against is
# recorded HERE, in the harness, over the whole file, and it is repeated in the
# round-8 notes -- two places outside the file itself.  A check whose reference
# value travels inside the thing it checks is a check that cannot fail (#342).
_FROZEN_SERVER_EXTRACT_SHA256 = (
    "69ac1970c409c232bd41396d7d767ee567e8bdf7832bf3423ff193b92663c98d")

# The path a refusal prints, repository-relative on purpose: a refusal has to
# NAME the file it refused, and a workstation path in a delivered log is a
# privacy defect.
_FROZEN_SERVER_EXTRACT_REL = (
    "backend/tests/sept16_dc_server_status_route.frozen.txt")

# ── THE PROVENANCE RECORD BESIDE THE EXTRACT ────────────────────────────────
#
# WHY THERE IS A SECOND FILE.  The extract's own header records a source line
# range and a source digest that do not reproduce: the range is printed with a
# 1-indexed start beside a 0-INDEXED EXCLUSIVE end, so it names one element
# more than the body has, and the digest under the name `source-sha256` is the
# pin's digest AFTER universal-newline translation rather than the digest of
# its bytes, without saying so.  A reader who byte-hashes the pin, or who cuts
# the stated range, gets a mismatch -- and a mismatch of that shape is exactly
# what a drifted or fabricated extract would produce, so the header cannot be
# used to establish what the body is a slice of.
#
# WHY THE HEADER IS NOT SIMPLY CORRECTED.  The round-6 contract names the
# WHOLE-FILE sha256 of the extract, and that digest is recorded in the contract
# text and in the round-8 build brief, both of which live in read-only pins.
# Editing one header byte changes it.  Curing a provenance mismatch by breaking
# the contract's own seal would put the same failure on a bigger surface, so
# the extract is left sealed and the correction lives HERE, in a file delivered
# in the same tree, which this harness REQUIRES before it will answer.
#
# WHAT THIS BUYS.  The record is not commentary: `_frozen_route_text` refuses
# while it is missing, unreadable or no longer binding, so the correction
# cannot be dropped without the cross-lane equality going dark.
_FROZEN_PROVENANCE = pathlib.Path(__file__).resolve().parent / \
    "sept16_dc_server_status_route.provenance.txt"
_FROZEN_PROVENANCE_REL = (
    "backend/tests/sept16_dc_server_status_route.provenance.txt")

# The four measured facts the record must carry, recorded HERE as well so the
# record cannot certify itself (#342): a reference value that travels only
# inside the thing it checks is a check that cannot fail.
_FROZEN_BODY_SHA256 = (
    "397e4fc4200365415fc8e5ec3128f3fdf54e38b111deb415bc403a1c211313a6")
_FROZEN_SOURCE_SHA256_BYTES = (
    "f8a640c8ec5a641966ee8de5795e882061dfe43d21fc199af8be1eb69bed15c8")
_FROZEN_SOURCE_SHA256_LF = (
    "f025a8b4e21d33768737c740443253f2441ca18094cad1514b33f4b5e67dc1ad")
_FROZEN_SOURCE_LINES = "38671-40545 of 56062"

# THE PASSAGES OF THE SEALED EXTRACT THAT NO LONGER HOLD.  Each is quoted here
# character for character.  The rule the record is held to is a PAIRING in both
# directions: while a passage is still in the extract the record must quote it
# under a supersession heading, and while the record quotes it the passage must
# still be in the extract -- a supersession that outlives its text is a claim
# about nothing, and a passage that outlives its supersession is the round-7
# finding walking back in through the documentation.
_FROZEN_SUPERSEDED = (
    "# source-lines    : 38671-40546 of 56062",
    "# source-sha256   : f025a8b4e21d33768737c740443253f2441ca18094cad1514b3"
    "3f4b5e67dc1ad",
    "# IF THE LANES MERGE this file stops being the binding: the resolver "
    "prefers a" + LF
    + "# real tree that carries the route -- the merged repository itself -- "
    "and falls" + LF
    + "# back here only when no such tree is present.",
)

# The sentences the record must STATE, not merely imply.  An absence alone
# holds on an empty file, which is the check that cannot fail (#342).
_FROZEN_PROVENANCE_REQUIRED = (
    "1-INDEXED and INCLUSIVE",
    "no tree can answer for the server representation",
    "at merge this file is DELETED and the harness is re-run against the",
)


def _frozen_provenance_binds(extract_text, record=None):
    """(True, None) when the record beside the extract re-derives it.

    WHAT THIS REJECTS, each on its own: a missing or unreadable record; a
    record that does not name the extract or carries a different whole-file or
    body digest; a record whose stated source range is the superseded one, or
    whose element count disagrees with the body actually present; a record that
    names one source digest without distinguishing the bytes from the
    translation; a record that stops superseding a passage the extract still
    carries; and a supersession left standing over text the extract no longer
    has.  `record` is a test hook so every one of those can be exercised
    without editing the delivered file."""
    if record is None:
        try:
            record = _FROZEN_PROVENANCE.read_text(encoding="utf-8")
        except OSError as exc:
            return False, ("the frozen extract's provenance record could not "
                           "be read at " + _FROZEN_PROVENANCE_REL + " ("
                           + exc.__class__.__name__ + "), so nothing "
                           "re-derives the extract")

    def fld(name):
        m = re.search(r"^" + re.escape(name) + r"\s*:\s*(.+?)\s*$", record, re.M)
        return m.group(1) if m else None

    for name, want in (("extract-path", _FROZEN_SERVER_EXTRACT_REL),
                       ("extract-sha256", _FROZEN_SERVER_EXTRACT_SHA256),
                       ("body-sha256", _FROZEN_BODY_SHA256),
                       ("source-sha256-bytes", _FROZEN_SOURCE_SHA256_BYTES),
                       ("source-sha256-lf", _FROZEN_SOURCE_SHA256_LF),
                       ("source-lines", _FROZEN_SOURCE_LINES)):
        got = fld(name)
        if got != want:
            return False, ("the provenance record at " + _FROZEN_PROVENANCE_REL
                           + " records " + name + " as " + repr(got)
                           + " where this harness records " + repr(want))

    # THE ELEMENT COUNT IS RE-DERIVED FROM THE BODY IN HAND, not copied: this
    # is the assertion the extract's own header fails.
    body = extract_text[extract_text.find(_ROUTE_ANCHOR):]
    elements = len(body.split(LF))
    stated = fld("body-split-elements")
    if stated != str(elements):
        return False, ("the provenance record says the body is " + repr(stated)
                       + " newline-split elements while the extract's body is "
                       + str(elements))
    lo, hi = _FROZEN_SOURCE_LINES.split(" of ")[0].split("-")
    if int(hi) - int(lo) + 1 != elements:
        return False, ("the recorded source range " + _FROZEN_SOURCE_LINES
                       + " spans " + str(int(hi) - int(lo) + 1)
                       + " elements, not the " + str(elements) + " the body has")

    for sentence in _FROZEN_PROVENANCE_REQUIRED:
        if sentence not in record:
            return False, ("the provenance record does not state: " + sentence)

    for passage in _FROZEN_SUPERSEDED:
        in_extract = passage in extract_text
        at = record.find(passage)
        if in_extract and at < 0:
            return False, ("the extract still carries a passage the provenance "
                           "record no longer supersedes: "
                           + passage.split(LF)[0][:60])
        if at >= 0 and not in_extract:
            return False, ("the provenance record supersedes a passage the "
                           "extract no longer carries: "
                           + passage.split(LF)[0][:60])
        if at >= 0 and "SUPERSEDED" not in record[max(0, at - 400):at]:
            return False, ("a superseded passage is quoted in the provenance "
                           "record outside a supersession heading: "
                           + passage.split(LF)[0][:60])
    return True, None


# THE ANSWER SENTENCE IDENTIFIES THE REPRESENTATION.  `how` is not commentary
# printed beside the equality: every caller asserts that this sentence names
# the extract and carries the recorded digest, so a resolution that came from
# anywhere else cannot be mistaken for this one.
_FROZEN_SERVER_HOW = (
    "the hash-verified frozen server-lane extract this lane carries beside this "
    "harness, " + _FROZEN_SERVER_EXTRACT.name + " (" + _FROZEN_SERVER_EXTRACT_REL
    + ", sha256 " + _FROZEN_SERVER_EXTRACT_SHA256 + ") -- resolved from that file "
    "and from no tree")


# THE MARKS THAT MAKE THE ANSWER SENTENCE AN IDENTIFICATION.  Each one is here
# because it can fail ON ITS OWN: the relative path is the only place the
# extract is located -- and it ends in the file's own name, so a separate name
# clause could never fail independently of it (#441) -- the digest is the only
# place its bytes are pinned, and the closing clause is the one thing a REFUSAL
# sentence does not carry, which is how an answer is told from a refusal
# without depending on a module global that a test may have repointed.
_FROZEN_IDENTITY_MARKS = (
    _FROZEN_SERVER_EXTRACT_REL,
    _FROZEN_SERVER_EXTRACT_SHA256,
    "resolved from that file and from no tree",
)


def _frozen_identity_holds(how):
    """True only when `how` IDENTIFIES the hash-verified extract.

    The round-7 cross-lane assertion compared FIELDS and let `how` say whatever
    it liked, so a resolution that had opened a tree read exactly like one that
    had read the extract.  Identity is therefore part of what is CHECKED: the
    sentence must LOCATE the file, carry the digest this harness records, and
    close with the clause only an answer carries.
    """
    return all(mark in how for mark in _FROZEN_IDENTITY_MARKS)


def _frozen_route_text(raw=None):
    """(text, None) for the frozen server-lane extract, or (None, why).

    THE CONTRACT NAMES ONE SERVER REPRESENTATION and says the field-name
    equality is proven against it and against nothing else.  That representation
    is the round-6 client review pin's immutable `server-lane/main.py`, which
    lives outside this repository; writing its path into this file would put a
    workstation path in the tree and would still leave the binding unverifiable
    from the bundle.  So the region of it the harness reads travels WITH the
    lane, cut by `886bed8-r7-freeze-server-route.py`, which records the source
    line range, the sha256 of the whole pin file, and a sha256 of the extract's
    own body.

    THE HASH IS RECOMPUTED HERE, on every run.  An extract nobody re-hashes is a
    frozen copy only by assertion: a truncation, a stray edit or a line-ending
    rewrite would hand the harness a text that still parses and still yields a
    key set, and a partial key set reads at the assertion as the two lanes
    disagreeing.  A mismatch refuses instead, with both hashes named.

    The body is everything from the status route's own decorator onward; the
    provenance header above it is deliberately outside the hash, so a reader may
    annotate the provenance without invalidating the bytes.

    THE WHOLE-FILE DIGEST IS THE IDENTITY, and it is checked on the read of
    the real file, before the body hash below: the body hash proves the extract
    is internally consistent, the recorded digest proves it is THE extract.  A
    missing file, an unreadable file or a digest mismatch REFUSES with the
    repository-relative path and BOTH digests named.

    `raw` is a test hook, the same one `_stable_text` takes for the same reason:
    a refusal rule that can only be exercised by corrupting the shipped file is
    a rule nobody exercises.  Text handed in through it is exercising the BODY
    rule, so the whole-file identity above is not applied to it -- which is what
    lets the annotated-provenance twin stay green."""
    if raw is None:
        import hashlib as _hashlib
        try:
            data = _FROZEN_SERVER_EXTRACT.read_bytes()
        except OSError as exc:
            # A MISSING OR UNREADABLE EXTRACT FAILS.  It does not skip, and it
            # does not fall through to a tree: there is no tree to fall through
            # to any more, and a cross-lane claim that quietly stops being
            # checked is the check that cannot fail (#342).
            return None, (
                "the frozen server-lane extract could not be read at "
                + _FROZEN_SERVER_EXTRACT_REL + " (" + exc.__class__.__name__
                + "): expected sha256 " + _FROZEN_SERVER_EXTRACT_SHA256
                + ", got sha256 none -- no file was read")
        got_file = _hashlib.sha256(data).hexdigest()
        if got_file != _FROZEN_SERVER_EXTRACT_SHA256:
            return None, (
                "the frozen server-lane extract at " + _FROZEN_SERVER_EXTRACT_REL
                + " is not the representation this harness records: expected "
                  "sha256 " + _FROZEN_SERVER_EXTRACT_SHA256
                + ", got sha256 " + got_file)
        raw = data.decode("utf-8")
        # THE PROVENANCE RECORD IS PART OF THE READ.  The digest above proves
        # these are THE bytes; it says nothing about what they are a slice OF,
        # and the extract's own header answers that question with a range and a
        # digest that do not reproduce.  The record beside it is what does
        # reproduce, so a resolution is refused while it is missing or no
        # longer binding rather than answered from a file whose provenance
        # nobody can establish.
        bound, why_prov = _frozen_provenance_binds(raw)
        if not bound:
            return None, (
                "the frozen server-lane extract at " + _FROZEN_SERVER_EXTRACT_REL
                + " is sealed at sha256 " + got_file + " but its provenance no "
                "longer re-derives: " + why_prov)
    m = re.search(r"^# sha256-of-body\s*:\s*([0-9a-f]{64})\s*$", raw, re.M)
    if not m:
        return None, "the frozen extract records no sha256 of its own body"
    i = raw.find(_ROUTE_ANCHOR)
    if i < 0:
        return None, "the frozen extract carries no status route decorator"
    body = raw[i:]
    import hashlib
    got = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if got != m.group(1):
        return None, ("the frozen extract's body does not match the sha256 it "
                      "records (" + got[:16] + "... vs " + m.group(1)[:16]
                      + "...), so it is not the frozen representation any more")
    return body, None


def _stable_text(read, attempts=3, complete=None):
    """The text of a file nothing is writing to, or None.

    THIS CHECK READS ANOTHER LANE'S WORKING TREE, and that lane's builder edits
    it while this one runs.  A read that lands mid-write returns a file whose
    route is half a dict -- which is indistinguishable, at the assertion, from
    the two lanes genuinely disagreeing about a field name.  It happened: a
    controls run reported this test RED with `dc_deferred_bound_seconds`
    missing while the file re-read minutes later carried it and the contract
    named it throughout.

    A difference is evidence only when the thing read was COMPLETE (#304), so
    two conditions must hold before a text is used, both cheap: two consecutive
    reads are identical, and `complete` -- when one is given -- says the part
    this check actually uses is whole.  Neither proves anything about behaviour
    (#340); they are about the READ.  Parsing the whole 40 000-line file was
    the first cut and cost about fifteen seconds per process, which is the
    controls runner's whole budget; the completeness claim belongs to the text
    this check reads, not to the file around it.

    `read` and `complete` are callables so the rule can be exercised without a
    concurrent writer: hand it a reader that answers differently each time, or
    a completeness predicate that refuses, and it must refuse both."""
    prev = None
    for _ in range(attempts):
        cur = read()
        if cur is None:
            return None
        if cur == prev:
            if complete is not None and not complete(cur):
                return None
            return cur
        prev = cur
    return None


def _route_dict_is_complete(text):
    """True when the status route's own return dict is BALANCED in `text`.

    A text with no such route is not judged here: a candidate tree that does
    not carry the route is SKIPPED by the resolver, and answering False for it
    would turn every unrelated tree into a failure."""
    a = '@app.get("/api/v1/team/series/{series_id}/status"'
    if a not in text:
        return True
    i = text.index(a)
    j = text.find("@app.get(", i + len(a))
    region = text[i:j if j > 0 else len(text)]
    if "return {" not in region:
        return False
    depth = 0
    for ch in region[region.rindex("return {"):]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return True
    return False


def _server_lane_main():
    """(text, how) for THE server representation the contract assertions read:
    the hash-verified frozen extract this lane carries, and nothing else.

    WHAT WAS WRONG.  Rounds 6 and 7 resolved this through an ordered list of
    candidate TREES -- a tree named in $SCR_SERVER_LANE as an exclusive
    candidate, then the review pin's own `REVIEW-INPUT/server-lane` copy, then
    this repository -- and reached the extract only as the caller's terminal
    fallback.  The delivered review pin CARRIES the route in that copy, so from
    inside the pin a candidate answered before the extract was ever read, and
    an inherited variable could redirect the equality to any tree at all.  The
    assertion then compared field names without ever requiring the answer to
    say WHICH representation it had compared, so drift could receive a green
    cross-lane certificate from a text nobody had hashed.

    WHAT THIS DOES INSTEAD.  There is no candidate list on this path.  The
    contract's server half is the extract beside this file, read through
    `_frozen_route_text()`, which verifies the whole file against the digest
    this harness records before returning a byte of it.  `how` is
    `_FROZEN_SERVER_HOW`, which NAMES the file and carries that digest, and
    every caller asserts `_frozen_identity_holds(how)` -- the representation is
    part of what is checked.

    FAILURE DIRECTION IS A REFUSAL.  A missing file, an unreadable file or a
    digest mismatch returns an empty text with the reason, the path and both
    digests; the callers fail on it.  Nothing here skips, and nothing falls
    through to a tree, because no tree can answer this question any more.

    The tree-reading machinery is not deleted -- `_server_lane_candidates` and
    `_named_tree_route_text` keep the rule that a worktree listing contributes
    no candidate, and that a named tree is never silently replaced -- but it is
    off this path and only its own cases call it (#342: a property worth
    keeping keeps its own test over its own function)."""
    frozen, why = _frozen_route_text()
    if frozen is None:
        return "", why
    return frozen, _FROZEN_SERVER_HOW


def _named_tree_route_text(root, env, listing=()):
    """(text, how) for a CANDIDATE TREE, or ("", why) -- NOT the contract path.

    This is the round-7 resolver body, kept because two of its properties are
    worth keeping and a property nobody can exercise is not a property (#342):
    a tree that is NAMED is exclusive and is never silently replaced by another
    one, and a candidate read mid-write is refused rather than reported as a
    disagreement between the lanes.  Its own cases call it; the contract
    assertions do not, and `test_r8_c5_the_named_tree_machinery_is_off_the_
    contract_path` is what holds that separation."""
    route = _ROUTE_ANCHOR
    for cand, how, exclusive in _server_lane_candidates(root, env, list(listing)):
        for rel in ("backend/api/main.py", "main.py"):
            p = cand / rel

            def _read(path=p):
                try:
                    if not path.exists():
                        return None
                    return path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None

            text = _stable_text(_read, complete=_route_dict_is_complete)
            if text is None:
                if p.exists():
                    # It is there and it would not read twice alike, or would
                    # not parse: something is writing it.  That is NOT a
                    # disagreement between the lanes and must not be reported
                    # as one -- the caller fails with the reason, and the
                    # answer is to re-read, never to weaken the assertion.
                    return "", ("a candidate main.py could not be read in a stable, "
                                "complete state -- that tree is being written; "
                                "re-read before treating any difference as a "
                                "disagreement")
                continue
            if route in text:
                return text, how
        if exclusive:
            return "", ("the tree $SCR_SERVER_LANE names carries no status route, "
                        "and a named tree is never silently replaced by another")
    return "", "no candidate tree carried the status route"


def _status_route_keys(server_main):
    """The response keys the read-only status route EMITS, read out of that
    route's own return statement -- not off the whole file, where any other
    handler's dict would answer for it."""
    a = '@app.get("/api/v1/team/series/{series_id}/status"'
    if a not in server_main:
        return set()
    i = server_main.index(a)
    j = server_main.find("@app.get(", i + len(a))
    route = server_main[i:j if j > 0 else len(server_main)]
    if "return {" not in route:
        return set()
    body = route[route.rindex("return {"):]
    return set(re.findall(r'"([a-z0-9_]+)"\s*:', body))


def _banner_parsed_keys(api):
    """Every JSON key the client reads to feed the banner: the shared parse plus
    the deferral-presence helper.  Scoped to those two methods, because a
    file-wide sweep would collect report-dc's keys as well (#330: count the
    operation inside the FUNCTION span)."""
    parse = _method_body(api, "private static void ApplySeriesStateResponse")
    helper = _method_body(api, "private static bool HasDeferralFields")
    assert parse and helper, "the parse or the deferral helper could not be delimited"
    pat = r'(?:HasJsonKey|ExtractJsonBool|ExtractJsonInt|ExtractJsonString)\(resp, "([a-z0-9_]+)"\)'
    return set(re.findall(pat, parse + helper))


def test_r6_item7_every_field_the_banner_reads_is_emitted_by_the_status_route():
    """THE CROSS-LANE BINDING, AND IT MUST BE ABLE TO GO RED.

    A name that exists on one lane and not the other is the defect this test
    exists for, and it is invisible to either lane reading its own half: the
    client would parse a key nobody sends and read a silent 0, the server would
    ship a field nobody reads, and the feature would be inert with healthy logs
    at both ends (#635: two halves of one contract need a test that reads BOTH
    sides' literals, not two careful readings; #341, #444).  So the assertion
    resolves the SERVER tree and compares its emitted key set against the keys
    the client parse actually reads.

    THE MUTATION IS THE POINT.  Removing one field from the route's response
    reddens this; the inert twin -- the client-only deletion test above -- stays
    green, because it never reads the server tree."""
    api = _src("ApiClient.cs")
    server, how = _server_lane_main()
    assert server, (
        "the server representation could not be resolved, so this cross-lane claim "
        "was not checked: " + how)
    assert _frozen_identity_holds(how), (
        "the cross-lane equality was resolved from something other than "
        "the hash-verified extract: " + how)
    keys = _status_route_keys(server)
    assert keys, "the status route's own return keys could not be read"

    CONTRACT = ["dc_deferred", "dc_deferred_seconds_remaining",
                "dc_deferred_bound_seconds"]
    for n in CONTRACT:
        assert n in keys, (n, sorted(keys))

    parsed = _banner_parsed_keys(api)
    for n in CONTRACT:
        assert n in parsed, (n, sorted(parsed))
    # and EVERY key the parse reads is one this route emits -- not only the
    # three, because a fourth invented name is the same defect
    missing = sorted(parsed - keys)
    assert not missing, ("client parses keys the status route does not emit", missing)

    def claim(s_server):
        k = _status_route_keys(s_server)
        if not k:
            return False
        return (all(n in k for n in CONTRACT)
                and not (parsed - k))

    # MUTATION: one field leaves the route's response
    _assert_discriminating(
        claim, server,
        _mutate(server, '"dc_deferred_bound_seconds":',
                '"zz_not_a_contract_name":',
                "R6 a contract field leaves the route"),
        "R6 every banner field is emitted by the route")

    # MUTATION 2: the field survives under a paraphrased name, which is the
    # drift the single field list exists to prevent
    _assert_discriminating(
        claim, server,
        _mutate(server, '"dc_deferred_seconds_remaining":',
                '"dc_deferred_remaining_seconds":',
                "R6 a contract field is renamed on one lane"),
        "R6 the two lanes spell the field the same")

    # NEGATIVE CONTROL, and a MEANINGFUL one: a key the route emits that the
    # banner does not read may change without reddening this test.  The claim is
    # about the banner's fields, not about the route's whole surface.
    assert "deadline_seconds" not in parsed
    assert claim(_mutate(server, '"deadline_seconds":', '"deadline_seconds_v2":',
                         "R6 cross-lane negative control"))


def test_r6_the_deferred_meaning_is_carried_from_the_contract_word_for_word():
    """ONE DEFINITION, TWO TREES (#341, #444).

    Round 5's client said a false `deferred` meant the call had settled the
    report and that an absent one proved an old box settled it.  Both exceed
    what the field carries, and the contract fixes the exact sentences each
    lane may state.  They are COPIED rather than restated, which is the only
    way a sentence this long stays true on two trees (#351)."""
    api = _src("ApiClient.cs")

    definition = ('"deferred" says only whether THIS call parked the report: true when it '
                  'did, false on the five exits that do not park one -- two of which settle '
                  'the series while the other three, the settled-row exit and the two room '
                  'fences, decide nothing and say so with "ignored": true -- and absent only '
                  'from a box that predates the flag.')
    false_sentence = ('A FALSE "deferred" proves only that this call parked nothing. It is '
                      'never proof of settlement: three of the five exits that answer false '
                      'decide nothing and say so with "ignored": true.')
    absent_sentence = ('An ABSENT "deferred" proves only that the box that answered predates '
                       'the field. It says nothing about whether that box settled, ignored or '
                       'fenced this report; the disposition, if the body carries one, is in '
                       '"status" and "ignored".')

    def flatten(s):
        out = []
        for line in s.split("\n"):
            t = line.strip()
            if t.startswith("///"):
                t = t[3:]
            elif t.startswith("//"):
                t = t[2:]
            out.append(t)
        return " ".join(" ".join(out).split())

    flat = flatten(api)
    for sentence in (definition, false_sentence, absent_sentence):
        assert flat.count(" ".join(sentence.split())) == 1, sentence[:48]

    # and the two claims the round-5 lens rejected are gone from the file
    assert "SETTLED by a box that predates the deferral" not in api
    assert "settled this report at one of its other exits" not in api

    def claim(s):
        f = flatten(s)
        return (all(f.count(" ".join(x.split())) == 1
                    for x in (definition, false_sentence, absent_sentence))
                and "SETTLED by a box that predates the deferral" not in s)

    # MUTATION 1: the definition is paraphrased
    _assert_discriminating(
        claim, api,
        _mutate(api, "says only whether THIS call parked the report",
                "says whether THIS call parked the report",
                "R6 the definition is paraphrased"),
        "R6 the contract definition is carried word for word")

    # MUTATION 2: the absent-field sentence goes back to claiming a settlement
    _assert_discriminating(
        claim, api,
        _mutate(api, "An ABSENT \"deferred\" proves only that the box that",
                "An ABSENT \"deferred\" proves that the box that",
                "R6 the absent sentence overclaims again"),
        "R6 the absent-field sentence is the contract's")

    # NEGATIVE CONTROL: an unrelated comment edit leaves all three intact
    assert claim(_mutate(api, "AN ABSENT FIELD IS A FACT ABOUT THE BOX",
                         "AN ABSENT FIELD IS A FACT ABOUT THAT BOX",
                         "R6 contract-sentence negative control"))


def test_r6_the_read_witness_claims_the_answer_and_not_the_ui():
    """W28 PROVES A READ ANSWER.  IT DOES NOT PROVE A BANNER.

    The line said "the DC-grace banner is live for this series" while the
    banner could not render at all, and its comment described one line per
    series when the marker is a single remembered id -- a tab moving A to B and
    back emits it twice for A, and a later refused answer emits the negative
    line for a series that already emitted this one.  Three claims about
    subsystems this line cannot see (#342).

    The banner now reports ITSELF, which is what makes the split checkable."""
    api = _src("ApiClient.cs")
    ui = _src("NativeUI.cs")
    ro = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    assert ro, "the read-only poller's own text could not be delimited"

    assert "series status read PROVEN for series" in ro
    assert "the DC-grace banner is live for this series" not in api
    assert "nothing about what the banner renders" in ro
    assert "This line can repeat for a series the tab returns to" in ro
    assert "it is PER RESPONSE" in ro
    # the banner's own witness lives in the UI, not here
    assert "DC banner SHOWN for series" in ui
    assert "DC banner SHOWN for series" not in api
    # and the missing-field line, which is the other item-7 witness
    assert "carried no complete deferral state" in ro
    assert "Absence is never read as presence" in ro

    def claim(s_api, s_ui):
        b = _method_body(s_api, "public static void PollTeamSeriesStatusReadOnly")
        if not b:
            return False
        return ("the DC-grace banner is live for this series" not in s_api
                and "nothing about what the banner renders" in b
                and "This line can repeat for a series the tab returns to" in b
                and "carried no complete deferral state" in b
                and "DC banner SHOWN for series" in s_ui)

    assert claim(api, ui)
    # MUTATION 1: the read line certifies the UI again
    m = _mutate(api, "nothing about what the banner renders",
                "the DC-grace banner is live for this series",
                "R6 the read witness certifies the UI")
    assert not claim(m, ui), "the claim survives its own mutation (api)"
    # MUTATION 2: the banner stops reporting itself
    m_ui = _mutate(ui, "DC banner SHOWN for series", "DC banner drawn for series",
                   "R6 the banner stops witnessing")
    assert not claim(api, m_ui), "the claim survives its own mutation (ui)"
    # MUTATION 3: the missing-field line goes, so an absent field is silent
    m2 = _mutate(api, "carried no complete deferral state", "carried a deferral state",
                 "R6 the missing-field line goes silent")
    assert not claim(m2, ui), "the claim survives its own mutation (absence line)"
    assert not claim("// nothing here\n", "// nothing here\n")

    # NEGATIVE CONTROL: rewording an adjacent sentence keeps every claim
    assert claim(_mutate(api, "it is about the ANSWER, not about the UI",
                         "it is about the ANSWER and not about the UI",
                         "R6 read-witness negative control"), ui)


def test_r6_item7_an_incomplete_deferral_state_is_read_as_not_deferred():
    """ABSENCE IS NEVER READ AS PRESENCE.

    A bool extractor answers False for "absent" and for "false" alike (#604),
    so a body missing one of the three fields would otherwise parse to a silent
    "not deferred" that looks exactly like a measured one -- and a partial body
    (say the flag but no remaining time) would render a banner with a zero
    countdown it never measured.  The presence of ALL THREE is measured first,
    the else-branch zeroes all three, and the answer says so in the log.

    The direction matters: the unhandled case leaves the banner OFF, which is
    the direction an unknown costs least in (#276, #430)."""
    api = _src("ApiClient.cs")
    helper = _method_body(api, "private static bool HasDeferralFields")
    parse = _method_body(api, "private static void ApplySeriesStateResponse")
    assert helper and parse, "the helper or the parse could not be delimited"

    # ALL three, never any: one HasJsonKey per contract field, joined by &&
    assert helper.count("HasJsonKey(resp,") == 3
    assert "||" not in helper
    for n in ("dc_deferred", "dc_deferred_seconds_remaining",
              "dc_deferred_bound_seconds"):
        assert '"%s"' % n in helper
    # the parse gates on it and the else-branch zeroes all three
    assert "if (HasDeferralFields(resp))" in parse
    tail = parse[parse.index("if (HasDeferralFields(resp))"):]
    assert "else" in tail
    els = tail[tail.index("else"):]
    assert "LastSeriesDcDeferred = false;" in els
    assert "LastSeriesDcDeferredSecondsRemaining = 0;" in els
    assert "LastSeriesDcDeferredBoundSeconds = 0;" in els
    # the remaining seconds can never render negative
    assert "Math.Max(0, ExtractJsonInt(resp, \"dc_deferred_seconds_remaining\"))" in parse

    def claim(s):
        h = _method_body(s, "private static bool HasDeferralFields")
        p = _method_body(s, "private static void ApplySeriesStateResponse")
        if not h or not p or "if (HasDeferralFields(resp))" not in p:
            return False
        t = p[p.index("if (HasDeferralFields(resp))"):]
        if "else" not in t:
            return False
        e = t[t.index("else"):]
        return (h.count("HasJsonKey(resp,") == 3
                and "||" not in h
                and "LastSeriesDcDeferred = false;" in e
                and "LastSeriesDcDeferredSecondsRemaining = 0;" in e
                and "LastSeriesDcDeferredBoundSeconds = 0;" in e
                and "Math.Max(0, ExtractJsonInt(resp, \"dc_deferred_seconds_remaining\"))" in p)

    # MUTATION 1: any one field is enough, so a partial body parses as complete
    _assert_discriminating(
        claim, api,
        _mutate(api,
                '            return HasJsonKey(resp, "dc_deferred")\n'
                '                   && HasJsonKey(resp, "dc_deferred_seconds_remaining")\n'
                '                   && HasJsonKey(resp, "dc_deferred_bound_seconds");',
                '            return HasJsonKey(resp, "dc_deferred")\n'
                '                   || HasJsonKey(resp, "dc_deferred_seconds_remaining")\n'
                '                   || HasJsonKey(resp, "dc_deferred_bound_seconds");',
                "R6 a partial deferral state is accepted"),
        "R6 all three fields or none")

    # MUTATION 2: the else-branch stops zeroing, so a body without the fields
    # leaves the previous answer's deferral state standing
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "                LastSeriesDcDeferred = false;\n"
                "                LastSeriesDcDeferredSecondsRemaining = 0;\n"
                "                LastSeriesDcDeferredBoundSeconds = 0;\n",
                "",
                "R6 an absent deferral state leaves the last one standing"),
        "R6 absence zeroes the banner's input")

    # MUTATION 3: the floor goes, so a negative remaining time can reach the UI
    _assert_discriminating(
        claim, api,
        _mutate(api,
                '                    Math.Max(0, ExtractJsonInt(resp, "dc_deferred_seconds_remaining"));',
                '                    ExtractJsonInt(resp, "dc_deferred_seconds_remaining");',
                "R6 the remaining seconds are unfloored"),
        "R6 the countdown cannot render negative")

    # NEGATIVE CONTROL: rewording the comment above the gate changes nothing
    assert claim(_mutate(api, "ABSENCE IS NEVER READ AS PRESENCE.",
                         "ABSENCE IS NOT READ AS PRESENCE.",
                         "R6 absence-rule negative control"))


def test_r6_an_id_change_clears_the_banners_three_inputs():
    """THE CACHE IS SCOPED TO THE SERIES IT DESCRIBED (Codex r2 f8).

    The setter is the banner inputs' only other writer.  Without the three in
    its reset, moving the tab from series A to series B would leave A's deferral
    state under B's banner until B's first answer arrived -- a banner that is
    correct about a series nobody is looking at."""
    api = _src("ApiClient.cs")
    a = "if (!string.Equals(value, activeTeamSeriesId, StringComparison.Ordinal))"
    assert a in api
    setter = api[api.index(a):api.index("activeTeamSeriesId = value;", api.index(a))]

    # ROUND 7 adds the fourth: the PRESENCE bit is a banner input too -- it is in
    # the render key and the off-witness reads it -- so leaving it set said the
    # previous series' answer carried the deferral state, about a series whose
    # numbers had just been cleared.
    for f in ("LastSeriesDcDeferred = false;",
              "LastSeriesDcDeferredSecondsRemaining = 0;",
              "LastSeriesDcDeferredBoundSeconds = 0;",
              "LastSeriesDcDeferredFieldsPresent = false;"):
        assert f in setter, f

    def claim(s):
        if a not in s or "activeTeamSeriesId = value;" not in s:
            return False
        b = s[s.index(a):s.index("activeTeamSeriesId = value;", s.index(a))]
        return all(f in b for f in ("LastSeriesDcDeferred = false;",
                                    "LastSeriesDcDeferredSecondsRemaining = 0;",
                                    "LastSeriesDcDeferredBoundSeconds = 0;",
                                    "LastSeriesDcDeferredFieldsPresent = false;"))

    # MUTATION: the id change stops clearing the deferral state
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "                    LastSeriesDcDeferred = false;\n"
                "                    LastSeriesDcDeferredSecondsRemaining = 0;\n"
                "                    LastSeriesDcDeferredBoundSeconds = 0;\n",
                "",
                "R6 an id change leaves the previous series' deferral state"),
        "R6 an id change clears the banner's inputs")

    # NEGATIVE CONTROL: rewording the comment beside the reset changes nothing
    assert claim(_mutate(api, "The banner's three inputs are part of that scope",
                         "The banner's three inputs belong to that scope",
                         "R6 id-change negative control"))


# ── ROUND 6, THE COLD LENS: the cadence, the repaint, and three claims ───────
# Every case below closes one lens finding on the round-6 tree.


def _no_frame_time_code(body):
    """True when no LINE OF CODE in `body` reads Time.deltaTime.  The name may
    appear in the comment that explains why the accumulator went -- a claim
    about an operation is checked against the operation, not against the file's
    vocabulary (#432)."""
    return all(ln.strip().startswith("//")
               for ln in body.split(chr(10)) if "Time.deltaTime" in ln)


def _witness_body(ui):
    return _method_body(ui, "private static void LogDcBannerWitness")


def _team_ticker_body(ui):
    return _method_body(ui, "public static void MaybeRefreshTeamTab")


def test_r6lens_h2_the_banner_read_runs_on_a_wall_clock_from_a_per_frame_path():
    """THE CADENCE WAS MEASURED IN REPAINTS, NOT IN SECONDS.

    The banner's only data source was polled on a `Time.deltaTime` accumulator
    whose one caller sat inside RefreshTeamTab -- a path that runs when
    something flips the dirty bit, never per frame (#62, which is why the queue
    panels were pulled out of that same method).  So the documented 2 s
    interval was counted in repaint-frames: the wall-clock cadence moved with
    the frame rate and with however much unrelated traffic happened to repaint
    the tab, and a survivor inside a 420 s deferral window could wait tens of
    seconds for the first read and then watch the handed-over seconds jump by
    as much.  Round 6 made this banner the only consumer of a live countdown
    and certified the 2 s cadence in three comments, which is what makes it a
    defect of this round rather than inherited plumbing.

    THE FIX IS THE DOCUMENTED PATTERN, not a second timer: the per-frame
    ticker calls the poll, and the poll gates on an unscaled wall-clock
    deadline."""
    api = _src("ApiClient.cs")
    ui = _src("NativeUI.cs")

    poll = _method_body(api, "public static void UpdateTeamSeriesStatePoll")
    assert poll, "the poll's own text could not be delimited"
    # the gate is a deadline on the unscaled wall clock
    assert "if (!force && Time.unscaledTime < teamSeriesStateNextAt) return;" in poll
    assert "teamSeriesStateNextAt = Time.unscaledTime + TEAM_SERIES_STATE_INTERVAL;" in poll
    # and the accumulator is gone: frame time survives in this method only as
    # the prose explaining why it went, never as a line of code, and the field
    # itself is gone from the whole file
    assert _no_frame_time_code(poll)
    assert "teamSeriesStateTimer" not in api

    # THE CALLER.  One call site in this file, and it is the per-frame ticker.
    assert ui.count("ApiClient.UpdateTeamSeriesStatePoll(") == 1
    ticker = _team_ticker_body(ui)
    assert ticker, "the team tab's ticker could not be delimited"
    assert "ApiClient.UpdateTeamSeriesStatePoll(force: false);" in ticker
    # BEFORE the ticker's own 2 s throttle: the poll owns its cadence, and a
    # second gate in front of it would put that cadence back in a caller's hands
    assert (ticker.index("ApiClient.UpdateTeamSeriesStatePoll(force: false);")
            < ticker.index("if (Time.unscaledTime < teamTabRefreshAt) return;"))
    # and the render block no longer dispatches anything
    block = _dc_banner_block(ui)
    assert block, "the DC banner block's own bounds could not be established"
    assert "UpdateTeamSeriesStatePoll" not in block

    def claim(s_ui):
        t = _team_ticker_body(s_ui)
        b = _dc_banner_block(s_ui)
        if not t or not b:
            return False
        return ("ApiClient.UpdateTeamSeriesStatePoll(force: false);" in t
                and t.index("ApiClient.UpdateTeamSeriesStatePoll(force: false);")
                < t.index("if (Time.unscaledTime < teamTabRefreshAt) return;")
                and "UpdateTeamSeriesStatePoll" not in b
                and s_ui.count("ApiClient.UpdateTeamSeriesStatePoll(") == 1)

    # MUTATION 1: the poll goes back into the repaint path
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "            ApiClient.UpdateTeamSeriesStatePoll(force: false);\n",
                "",
                "R6lens the poll leaves the per-frame ticker")
        .replace("            var dcBanner = (txtTeamDcGrace as Component)?.gameObject;",
                 "            ApiClient.UpdateTeamSeriesStatePoll(force: false);\n"
                 "            var dcBanner = (txtTeamDcGrace as Component)?.gameObject;"),
        "R6lens the poll runs from the per-frame ticker")

    # MUTATION 2: it runs behind the ticker's own 2 s throttle, so the cadence
    # belongs to the caller again
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "            ApiClient.UpdateTeamSeriesStatePoll(force: false);\n"
                "            if (Time.unscaledTime < teamTabRefreshAt) return;",
                "            if (Time.unscaledTime < teamTabRefreshAt) return;\n"
                "            ApiClient.UpdateTeamSeriesStatePoll(force: false);",
                "R6lens the poll moves behind the throttle"),
        "R6lens the poll is called before the ticker's throttle")

    def gate(s_api):
        p = _method_body(s_api, "public static void UpdateTeamSeriesStatePoll")
        if not p:
            return False
        return ("if (!force && Time.unscaledTime < teamSeriesStateNextAt) return;" in p
                and _no_frame_time_code(p)
                and "teamSeriesStateTimer" not in s_api)

    # MUTATION 3: the accumulator returns, so the interval is frame time again
    _assert_discriminating(
        gate, api,
        _mutate(api,
                "            if (!force && Time.unscaledTime < teamSeriesStateNextAt) return;\n"
                "            teamSeriesStateNextAt = Time.unscaledTime + TEAM_SERIES_STATE_INTERVAL;",
                "            teamSeriesStateTimer += Time.deltaTime;\n"
                "            if (!force && teamSeriesStateTimer < TEAM_SERIES_STATE_INTERVAL) return;\n"
                "            teamSeriesStateTimer = 0f;",
                "R6lens the frame-time accumulator returns"),
        "R6lens the poll gates on the unscaled wall clock")

    # NEGATIVE CONTROL: rewording the prose beside the gate keeps every claim
    assert gate(_mutate(api, "WALL-CLOCK CADENCE, AND THE CALLER IS A PER-FRAME TICKER",
                        "WALL-CLOCK CADENCE, AND ITS CALLER IS A PER-FRAME TICKER",
                        "R6lens cadence negative control"))


def test_r6lens_h2_an_answer_that_changes_the_banner_asks_for_the_repaint():
    """THE OTHER HALF OF THE CADENCE.

    A wall-clock poll alone still draws at whatever rate the tab's other
    fetches happen to repaint it, because this tab re-renders on a dirty flip
    (#62).  The answer that changes what the banner reads asks for that
    repaint, which is the shape every other fetch on this tab already uses --
    the ticker polls, the answer marks dirty.  An answer that changes nothing
    asks for nothing, so the countdown does not become a repaint loop."""
    api = _src("ApiClient.cs")
    parse = _method_body(api, "private static void ApplySeriesStateResponse")
    assert parse, "the shared parse could not be delimited"

    assert "string bannerBefore = BannerRenderKey();" in parse
    assert "RequestBannerRepaintIfChanged(bannerBefore);" in parse
    # the key is taken BEFORE the fields are written and compared after
    assert parse.index("string bannerBefore = BannerRenderKey();") < parse.index(
        "RequestBannerRepaintIfChanged(bannerBefore);")

    key = _method_body(api, "private static string BannerRenderKey()")
    assert key, "the render key could not be delimited"
    for field in ("activeTeamSeriesId", "LastSeriesStateForId", "LastSeriesDcDeferred",
                  "LastSeriesDcDeferredSecondsRemaining",
                  "LastSeriesDcDeferredBoundSeconds",
                  "LastSeriesDcDeferredFieldsPresent",
                  "LastSeriesT1Wins", "LastSeriesT2Wins"):
        assert field in key, field
    # AND EACH AS ITS OWN TERM.  The dark latch joined this key in round 7 and
    # spells `activeTeamSeriesId` as its argument, so the loop above went green
    # with the id's own term deleted -- the one input whose absence turns an id
    # CHANGE into no change, read from a name that another term supplied
    # (#342).  Terms, not names.
    for term in _R7_KEY_TERMS:
        assert term in key, "the render key does not carry the term " + term

    def claim(s):
        p = _method_body(s, "private static void ApplySeriesStateResponse")
        k = _method_body(s, "private static string BannerRenderKey()")
        if not p or not k:
            return False
        return ("string bannerBefore = BannerRenderKey();" in p
                and "RequestBannerRepaintIfChanged(bannerBefore);" in p
                and 'return (activeTeamSeriesId ?? "-")' in k
                and "LastSeriesDcDeferredSecondsRemaining" in k
                and "LastSeriesStateForId" in k)

    # MUTATION 1: the repaint request goes, so the banner redraws only when
    # something unrelated flips the dirty bit
    _assert_discriminating(
        claim, api,
        _mutate(api,
                "one before/after key (#432).\n"
                "            RequestBannerRepaintIfChanged(bannerBefore);",
                "one before/after key (#432).\n"
                "            // no repaint",
                "R6lens the repaint request is removed"),
        "R6lens an answer that changes the banner asks for a repaint")

    # MUTATION 2: the countdown leaves the key, so a changing number never
    # reaches the screen
    _assert_discriminating(
        claim, api,
        _mutate(api,
                '                   + "|" + LastSeriesDcDeferredSecondsRemaining',
                '                   + "|"',
                "R6lens the countdown leaves the render key"),
        "R6lens the render key carries the countdown")

    # MUTATION 3: the series id leaves the key as its own term.  The name
    # survives inside the dark latch's argument, so every name-level assertion
    # stays green while an id change reads as no change and the banner keeps
    # the previous series' numbers on screen.
    _assert_discriminating(
        claim, api,
        _mutate(api,
                """            return (activeTeamSeriesId ?? "-")
                   + "|" + (LastSeriesStateForId ?? "-")""",
                '            return (LastSeriesStateForId ?? "-")',
                "R6lens the series id leaves the render key"),
        "R6lens the render key carries the series id as its own term")


def test_r6lens_m3_m5_the_banner_off_line_separates_absent_from_false():
    """A WITNESS MUST NOT STATE A FACT ITS INPUT DID NOT CARRY (#342, #351).

    The OFF line's last branch is reached for THREE different inputs: an answer
    that really carried dc_deferred=false; a status answer that carried no
    complete deferral state; and an answer to the LIFECYCLE state read, which
    carries none of the three keys, zeroes them through the shared parse and
    stamps the cache with this series all the same.  Only the first measured
    the row.  The line said "the last answer carried dc_deferred=false, so this
    series holds no deferral marker" for all three -- a positive denial derived
    from a body that never contained the key, in a bundle whose reader is
    asking exactly that question.

    The parse records WHICH it was, and the line says which it holds."""
    api = _src("ApiClient.cs")
    ui = _src("NativeUI.cs")

    # the parse records presence separately from value, in both branches
    parse = _method_body(api, "private static void ApplySeriesStateResponse")
    assert parse, "the shared parse could not be delimited"
    assert "LastSeriesDcDeferredFieldsPresent = true;" in parse
    assert "LastSeriesDcDeferredFieldsPresent = false;" in parse
    assert parse.index("LastSeriesDcDeferredFieldsPresent = true;") < parse.index(
        "LastSeriesDcDeferredFieldsPresent = false;")
    # and the state GET reaches that same parse, which is why the flag is needed
    state = _method_body(api, "public static void PollTeamSeriesStateAssemblyOnly")
    assert state and "ApplySeriesStateResponse(seriesId, resp, onResponse);" in state

    w = _witness_body(ui)
    assert w, "the banner witness could not be delimited"
    assert "ApiClient.LastSeriesDcDeferredFieldsPresent" in w
    # the change key carries it, so the transition between the two is visible
    assert '+ (ApiClient.LastSeriesDcDeferredFieldsPresent ? "p" : "-");' in w
    # BOTH sentences exist, and the measured one is qualified by the answer
    assert "so as of that answer the series held no deferral marker" in w
    assert "carried no deferral state" in w
    assert "says nothing " in w and "about whether the row holds a marker" in w
    # the unconditional claim is gone from the file
    assert "the last answer carried dc_deferred=false, so this series " not in ui

    def claim(s_ui):
        b = _witness_body(s_ui)
        if not b:
            return False
        return ("ApiClient.LastSeriesDcDeferredFieldsPresent" in b
                and ": ApiClient.LastSeriesDcDeferredFieldsPresent" in b
                and '+ (ApiClient.LastSeriesDcDeferredFieldsPresent ? "p" : "-");' in b
                and "so as of that answer the series held no deferral marker" in b
                and "carried no deferral state" in b
                and "the last answer carried dc_deferred=false, so this series " not in s_ui)

    # MUTATION 1: the branch collapses back to one sentence for all three inputs
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "                            : ApiClient.LastSeriesDcDeferredFieldsPresent\n",
                "                            : true\n",
                "R6lens the OFF line stops measuring what it holds"),
        "R6lens the OFF line splits on what the answer carried")

    # MUTATION 2: the key drops the flag, so the transition from an absent
    # field to a measured false never prints
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                '                         + (ApiClient.LastSeriesDcDeferredFieldsPresent ? "p" : "-");',
                '                         ;',
                "R6lens the witness key drops the presence flag"),
        "R6lens the witness key carries the presence flag")

    def parsed(s_api):
        p = _method_body(s_api, "private static void ApplySeriesStateResponse")
        if not p:
            return False
        return ("LastSeriesDcDeferredFieldsPresent = true;" in p
                and "LastSeriesDcDeferredFieldsPresent = false;" in p)

    # MUTATION 3: an answer with no deferral state records presence anyway, so
    # the line's "false" case becomes the lie it used to be
    _assert_discriminating(
        parsed, api,
        _mutate(api,
                "                LastSeriesDcDeferredBoundSeconds = 0;\n"
                "                LastSeriesDcDeferredFieldsPresent = false;",
                "                LastSeriesDcDeferredBoundSeconds = 0;\n"
                "                LastSeriesDcDeferredFieldsPresent = true;",
                "R6lens absence is recorded as presence"),
        "R6lens the parse records absence as absence")


def _dc_banner_construction(ui):
    """The banner ELEMENT's construction site -- the comment that introduces it
    and the lines that build it.  The round-6 stale-comment case scoped itself
    to the RENDER block, which is a different span; the comment a maintainer
    reads first is this one."""
    a = "// DC DEFERRAL BANNER."
    b = "(txtTeamDcGrace as Component)?.gameObject?.SetActive(false);"
    if a not in ui or b not in ui:
        return ""
    start = ui.index(a)
    end = ui.index(b, start)
    return ui[start:end]


def test_r6lens_m4_the_banner_construction_site_names_no_dead_mechanism():
    """THE COMMENT THAT INTRODUCES THE ELEMENT THIS ROUND REVIVED.

    It asserted two mechanisms this same branch documents as dead: a "5-minute
    window where the same 4 can re-queue and resume", and "the remaining team
    takes the series win by forfeit at the deadline".  The file says the
    opposite in both halves -- there is no 5-minute grace on this path (it
    belonged to the legacy dc_paused flow, retired in v1.30.0) and the window
    that exists is bug 245's resume at roughly thirty minutes; and the
    lead-forfeit completion needs an existing series win AND >= 2 total points,
    so a parked report's ordinary outcome is dc_incomplete, which is a win for
    nobody.

    This is the #432 / #459 class -- a comment naming a mechanism a numbered
    learning already killed -- and it sat three lines above the element the
    round made live, outside the span the round's own stale-comment case
    checked."""
    ui = _src("NativeUI.cs")
    block = _dc_banner_construction(ui)
    assert block, "the banner's construction site could not be delimited"

    # the two dead claims are gone from the WHOLE file, not only from here
    assert "5-minute window where the same 4 can re-queue" not in ui
    assert "takes the series win by forfeit at the deadline" not in ui
    # and this site states the live mechanisms instead
    assert "bug 245" in block
    assert "thirty minutes" in block
    assert "dc_incomplete" in block
    assert "v1.30.0" in block
    # every line of the span that names the dead flow is prose, never code
    for line in block.split("\n"):
        if "dc_paused" in line:
            assert line.strip().startswith("//"), line

    def claim(s_ui):
        b = _dc_banner_construction(s_ui)
        if not b:
            return False
        return ("5-minute window where the same 4 can re-queue" not in s_ui
                and "takes the series win by forfeit at the deadline" not in s_ui
                and "bug 245" in b and "thirty minutes" in b
                and "dc_incomplete" in b)

    # MUTATION 1: the dead grace window comes back
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "            // are dead on this branch: there is no 5-minute window in which the same",
                "            // server enters a 5-minute window where the same 4 can re-queue and",
                "R6lens the dead grace window returns"),
        "R6lens the construction site names no 5-minute window")

    # MUTATION 2: the forfeit-at-deadline rule comes back
    _assert_discriminating(
        claim, ui,
        _mutate(ui,
                "            // series completes to the other team only where that team had already",
                "            // remaining team takes the series win by forfeit at the deadline, and",
                "R6lens the forfeit rule returns"),
        "R6lens the construction site names no forfeit deadline")


def test_r6lens_m1_l6_the_cross_lane_resolver_finds_a_merged_tree():
    """THE CHECK MUST NOT GO RED FOR THE WRONG REASON, AND MUST NOT GUESS.

    (M1) The resolver knew three places, and none of them was the repository
    itself.  On main after the two branches merge -- or in a fresh clone, on
    another machine, on CI -- the route is in THIS tree and no candidate could
    see it, so the cross-lane case would fail with "the server lane's main.py
    could not be located" on the one tree where both halves finally live
    together.  A red-on-main test is deleted or skipped by the next reader,
    which is how the field-list binding would be lost at the moment it starts
    guarding one artifact.

    (L6) And the worktree candidate was a SUBSTRING match against each `git
    worktree list` line, which on this machine also matches read-only review
    pins checked out from that lane at older shas.  Matching the bracketed
    BRANCH was exact -- and the round-7 cold lens then showed that being exact
    about WHICH live tree to open was the wrong repair: no live tree is opened
    at all any more.  That case is `test_r7cl_f5_...` below; what survives here
    is the half this case was really about, that the repository itself is a
    candidate and that a NAMED tree is exclusive."""
    # drive-less on purpose: see the note above about the bundle sweep
    here = pathlib.Path("/lane/root")
    lines = [
        "/pins/scr-codex-sept16-dc-server-1dc473e  1dc473e (detached HEAD)",
        "/lane/scr-wt-sept16-dc-server             deab5c5 [claude/sept16-dc-server]",
        "/lane/scr-wt-sept16-client-r2             baf43e0 [claude/sept16-client-r2]",
    ]

    # M1: without an env override, the repository itself is a candidate
    cands = _server_lane_candidates(here, None, lines)
    assert here in [c for c, _, _ in cands], [str(c) for c, _, _ in cands]

    # neither the pin nor this lane's own worktree is a candidate
    paths = [c for c, _, _ in cands]
    assert not any("1dc473e" in str(p) for p in paths), paths
    assert not any("client-r2" in str(p) for p in paths), paths

    # L6: a named tree is exclusive and is never replaced by another
    named = _server_lane_candidates(here, "/lane/copy", lines)
    assert len(named) == 1 and named[0][2] is True
    assert named[0][0] == pathlib.Path("/lane/copy")

    # ...and the CONTRACT resolver answers from the extract, whatever this
    # rule says about candidate trees: the two are on different paths now.
    text, how = _server_lane_main()
    assert text, how
    assert _frozen_identity_holds(how), (
        "the cross-lane equality was resolved from something other than "
        "the hash-verified extract: " + how)
    assert '@app.get("/api/v1/team/series/{series_id}/status"' in text


def test_r7cl_f5_the_cross_lane_binding_reads_the_frozen_extract_and_no_live_tree():
    """THE EQUALITY IS PROVEN AGAINST THE FROZEN REPRESENTATION AND NOTHING ELSE.

    WHAT WAS WRONG.  Rounds 6 and 7 resolved the server lane through an ordered
    list whose last entry was built from `git worktree list`, matched on the
    lane's exact branch bracket.  Read as a design that is a fallback; read as
    an EXECUTION on this branch it was the only candidate that could ever fire.
    There is no `REVIEW-INPUT` beside this worktree, and its own
    `backend/api/main.py` carries no status route -- so `python -m pytest
    backend/tests/test_sept16_client_r2.py -q`, the invocation the round-7
    bundle publishes in its own log, opened the OTHER lane's live working tree.
    The contract forbids reading that tree, and the round it was read during
    carried a build in flight, which is the condition `_stable_text` exists
    because of.  Everything that made the binding true rested on one environment
    variable a wrapper set and no log recorded.

    WHAT IS ASSERTED, AND WHY EACH PART IS SEPARATE.  That no listing line
    becomes a candidate is about the RULE and is exercised on a synthetic
    listing, so it holds on any machine.  That the resolver does not even ASK
    for a listing is about this body, because a rule whose enforcement is an
    empty argument can be undone by one line that fills the argument.  That the
    frozen extract is WIRED is the #342 lesson the sibling case above already
    learned once: a defined-and-unused guard is a guard nobody runs.  And the
    hash rule is exercised through the same `raw` hook `_stable_text` takes,
    both directions -- a tampered body is refused, an annotated PROVENANCE is
    not, which is the whole reason the header sits outside the hash."""
    import inspect

    here = pathlib.Path("/lane/root")
    listing = [
        "/lane/root                       aaaaaaa [claude/sept16-client-r2]",
        "/lane/scr-wt-sept16-dc-server    bbbbbbb [claude/sept16-dc-server]",
        "/pins/scr-codex-dc-server-1dc473e  1dc473e (detached HEAD)",
    ]

    # 1. NO LISTING LINE BECOMES A CANDIDATE -- not even the exact branch.
    cands = _server_lane_candidates(here, None, listing)
    assert not any("sept16-dc-server" in str(c) for c, _, _ in cands), \
        [str(c) for c, _, _ in cands]
    assert [c for c, _, _ in cands] == [here / "REVIEW-INPUT" / "server-lane", here], \
        [str(c) for c, _, _ in cands]
    # a NAMED tree is still exclusive, and is still the only thing that wins
    named = _server_lane_candidates(here, "/lane/copy", listing)
    assert len(named) == 1 and named[0][2] is True

    # 2. ...AND THE RESOLVER DOES NOT ASK FOR A LISTING.  Read off the body,
    #    with the docstring and the comments removed: both of those TALK about
    #    worktrees, and a check that a word is absent from prose is a check
    #    about prose.
    src = inspect.getsource(_server_lane_main)
    after_doc = src[src.index('"""', src.index('"""') + 3) + 3:]
    code = "\n".join(ln for ln in after_doc.split("\n")
                     if not ln.strip().startswith("#"))
    assert "worktree" not in code, code[:500]
    assert "subprocess" not in code, code[:500]

    # 3. THE FROZEN EXTRACT IS WIRED, not merely present (#342).
    assert "_frozen_route_text()" in code

    # 4. It answers, and it carries the three names the contract fixes.
    frozen, why = _frozen_route_text()
    assert frozen is not None, why
    assert _ROUTE_ANCHOR in frozen
    fkeys = _status_route_keys(frozen)
    for n in ("dc_deferred", "dc_deferred_seconds_remaining",
              "dc_deferred_bound_seconds"):
        assert n in fkeys, (n, sorted(fkeys))

    # 5. THE HASH REFUSES A TAMPERED BODY...
    raw = _FROZEN_SERVER_EXTRACT.read_text(encoding="utf-8")
    i = raw.find(_ROUTE_ANCHOR)
    assert i > 0, "the extract has no provenance header above its body"
    tampered = raw[:i] + raw[i:].replace("dc_deferred_bound_seconds",
                                         "dc_deferred_bound_secs", 1)
    assert tampered != raw, "the tamper changed nothing"
    out, why2 = _frozen_route_text(tampered)
    assert out is None and "sha256" in why2, (out is None, why2)

    # ...AND ACCEPTS AN ANNOTATED PROVENANCE, which is the inert twin of that
    # tamper: the same kind of edit, above the body instead of inside it.
    out2, why3 = _frozen_route_text("# a reader's note" + LF + raw)
    assert out2 is not None, why3
    assert out2 == frozen

    # 6. AND THE LIVE RESOLUTION AGREES.  On this branch only the extract can
    #    answer; on the merged tree the repository answers and this is the
    #    comparison that matters.  Either way the resolved text is the one the
    #    field-list assertions above read.
    server, how = _server_lane_main()
    assert server, how
    assert _frozen_identity_holds(how), (
        "the cross-lane equality was resolved from something other than "
        "the hash-verified extract: " + how)
    assert {"dc_deferred", "dc_deferred_seconds_remaining",
            "dc_deferred_bound_seconds"} <= _status_route_keys(server), how


# ── ROUND 8, C5: the cross-lane equality resolves from the extract ONLY ──────

_R8_STUB_ROUTE = (
    'from fastapi import FastAPI' + LF
    + 'app = FastAPI()' + LF + LF
    + '@app.get("/api/v1/team/series/{series_id}/status")' + LF
    + 'async def team_series_status(series_id: str):' + LF
    + '    return {' + LF
    + '        "readonly": True,' + LF
    + '        "dc_deferred": False,' + LF
    + '        "dc_deferred_seconds_remaining": 0,' + LF
    + '        "zz_stub_only_name": 1,' + LF
    + '    }' + LF)


def _r8_write_tree(root, rel, text):
    p = pathlib.Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_r8_c5_the_cross_lane_equality_resolves_from_the_hash_verified_extract_only():
    """C5: THE REPRESENTATION IS PART OF WHAT IS CHECKED.

    WHAT WAS WRONG.  `_server_lane_main` returned the first CANDIDATE TREE that
    carried the route -- a tree named in $SCR_SERVER_LANE as an exclusive
    candidate, then the review pin's own `REVIEW-INPUT/server-lane` copy, then
    this repository -- and read the frozen extract only when none of them
    answered.  The delivered pin carries that copy, so a run from inside the
    pin proved the equality against a text nobody had hashed; an inherited
    variable could point it at any tree at all.  And the live assertion
    compared field NAMES while letting `how` say whatever it liked, so a
    resolution that had opened a tree was indistinguishable from one that had
    read the extract.

    THE FOUR NAMED CHECKS.  (a) the answer IDENTIFIES the extract by name and
    by digest; (b) the resolved text hashes to the digest this harness records;
    (c) with $SCR_SERVER_LANE pointed at a throwaway tree that carries a
    COMPLETE status route, the resolution is UNCHANGED; (d) with a directory
    shaped like the review pin as the working root, the resolution is still the
    extract.

    AND THE FAILURE DIRECTION IS A REFUSAL: a missing file, an unreadable file
    and a digest mismatch each fail with the repository-relative path and BOTH
    digests, rather than skipping or falling through to a tree."""
    import hashlib
    import os
    import tempfile

    # (a) THE ANSWER IDENTIFIES THE EXTRACT.
    text, how = _server_lane_main()
    assert text, how
    assert _frozen_identity_holds(how), how
    #     ...and EVERY mark is load-bearing: drop any one of them from the
    #     sentence and the identity must stop holding.  Without this the marks
    #     could be decorative and the rule would still read as if it checked
    #     them (#441).
    for mark in _FROZEN_IDENTITY_MARKS:
        assert mark in how, (mark, how)
        assert not _frozen_identity_holds(how.replace(mark, "(removed)")), mark
    assert _ROUTE_ANCHOR in text
    print("SERVER REPRESENTATION: " + how)

    # (b) THE RESOLVED TEXT HASHES TO THE RECORDED DIGEST.  The digest is over
    #     the whole file the text came out of, which is the thing the notes
    #     repeat; the body the resolver returns is a suffix of it.
    data = _FROZEN_SERVER_EXTRACT.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    assert got == _FROZEN_SERVER_EXTRACT_SHA256, (
        _FROZEN_SERVER_EXTRACT_REL, _FROZEN_SERVER_EXTRACT_SHA256, got)
    assert data.decode("utf-8").endswith(text), (
        "the resolved text is not the tail of the hashed file")
    print("SERVER REPRESENTATION SHA256: " + got)
    print("SERVER REPRESENTATION FILE: " + _FROZEN_SERVER_EXTRACT_REL)

    keys = _status_route_keys(text)
    for n in ("dc_deferred", "dc_deferred_seconds_remaining",
              "dc_deferred_bound_seconds"):
        assert n in keys, (n, sorted(keys))

    prev = os.environ.get("SCR_SERVER_LANE")
    cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as td:
            # (c) A NAMED THROWAWAY TREE CARRYING A COMPLETE ROUTE CHANGES
            #     NOTHING.  The stub emits a name the contract does not carry,
            #     so if anything read it the key set would say so.
            _r8_write_tree(td, "backend/api/main.py", _R8_STUB_ROUTE)
            os.environ["SCR_SERVER_LANE"] = td
            t2, how2 = _server_lane_main()
            assert t2 == text, "a named tree changed the contract resolution"
            assert how2 == how, how2
            assert _frozen_identity_holds(how2), how2
            assert "zz_stub_only_name" not in t2
            assert "zz_stub_only_name" not in _status_route_keys(t2)

            # and the stub really was a complete, readable route -- otherwise
            # this control proves only that the stub was broken (#342)
            stub = (pathlib.Path(td) / "backend/api/main.py").read_text(
                encoding="utf-8")
            assert _route_dict_is_complete(stub) is True
            assert "zz_stub_only_name" in _status_route_keys(stub)

            # (d) A DIRECTORY SHAPED LIKE THE REVIEW PIN, AS THE WORKING ROOT.
            _r8_write_tree(td, "REVIEW-INPUT/server-lane/backend/api/main.py",
                           _R8_STUB_ROUTE)
            del os.environ["SCR_SERVER_LANE"]
            try:
                # the working root is left before the directory is removed:
                # on this platform a directory that is the process's cwd
                # cannot be deleted, and a teardown error would read as a
                # failure of the check rather than of the fixture
                os.chdir(td)
                t3, how3 = _server_lane_main()
            finally:
                os.chdir(cwd)
            assert t3 == text, "a pin-shaped working root changed the resolution"
            assert how3 == how, how3
            assert "zz_stub_only_name" not in t3
    finally:
        os.chdir(cwd)
        if prev is None:
            os.environ.pop("SCR_SERVER_LANE", None)
        else:
            os.environ["SCR_SERVER_LANE"] = prev

    # THE RESOLVER READS NO TREE AT ALL.  A behavioural check on this machine
    # passes for a body that would still open a tree somewhere else, so the
    # body itself is asserted -- comments and docstring removed, because both
    # TALK about trees and a check that a word is absent from prose is a check
    # about prose.
    import inspect
    body = inspect.getsource(_server_lane_main)
    code = body[body.index('"""', body.index('"""') + 3) + 3:]
    code = LF.join(ln for ln in code.split(LF) if not ln.strip().startswith("#"))
    for banned in ("_server_lane_candidates", "_named_tree_route_text",
                   "SCR_SERVER_LANE", "REVIEW-INPUT", "worktree", "subprocess",
                   "ROOT"):
        assert banned not in code, (banned, code)
    assert "_frozen_route_text()" in code
    assert "_FROZEN_SERVER_HOW" in code

    # THE REFUSAL DIRECTION, all three ways, each naming the path and BOTH
    # digests.  The module constant is repointed rather than the file touched:
    # a rule that can only be exercised by damaging the shipped extract is a
    # rule nobody exercises.
    g = globals()
    real = g["_FROZEN_SERVER_EXTRACT"]
    try:
        with tempfile.TemporaryDirectory() as td:
            missing = pathlib.Path(td) / "not-here.frozen.txt"
            g["_FROZEN_SERVER_EXTRACT"] = missing
            out, why = _frozen_route_text()
            assert out is None
            assert _FROZEN_SERVER_EXTRACT_REL in why, why
            assert _FROZEN_SERVER_EXTRACT_SHA256 in why, why
            assert "got sha256 none" in why, why
            t, h = _server_lane_main()
            assert t == "", "a missing extract resolved to something"
            assert not _frozen_identity_holds(h), h

            flipped = pathlib.Path(td) / "flipped.frozen.txt"
            b = bytearray(real.read_bytes())
            b[-1] = b[-1] ^ 0x20
            flipped.write_bytes(bytes(b))
            g["_FROZEN_SERVER_EXTRACT"] = flipped
            out2, why2 = _frozen_route_text()
            assert out2 is None
            assert _FROZEN_SERVER_EXTRACT_REL in why2, why2
            assert _FROZEN_SERVER_EXTRACT_SHA256 in why2, why2
            got2 = hashlib.sha256(bytes(b)).hexdigest()
            assert got2 in why2, why2
            assert got2 != _FROZEN_SERVER_EXTRACT_SHA256
            t2, h2 = _server_lane_main()
            assert t2 == "", "a digest mismatch resolved to something"
            assert not _frozen_identity_holds(h2), h2

            # an unreadable file is the directory case: read_bytes raises
            g["_FROZEN_SERVER_EXTRACT"] = pathlib.Path(td)
            out3, why3 = _frozen_route_text()
            assert out3 is None
            assert _FROZEN_SERVER_EXTRACT_REL in why3, why3
            assert _FROZEN_SERVER_EXTRACT_SHA256 in why3, why3
    finally:
        g["_FROZEN_SERVER_EXTRACT"] = real

    # restored, and still the representation
    t4, how4 = _server_lane_main()
    assert t4 == text and how4 == how


def test_r8_c5_the_named_tree_machinery_is_off_the_contract_path():
    """C5's other half: the tree-reading rule KEEPS ITS OWN TEST.

    The brief's instruction is that if the property "a worktree listing
    contributes no candidate" is worth keeping, it keeps its own test over its
    own function and the contract path does not call that machinery.  So the
    round-7 resolver body survives as `_named_tree_route_text`, exercised here
    on trees this case builds, and the contract resolver does not name it.

    THE NAMED-TREE MISS STILL FAILS RATHER THAN SKIPS -- the half the round-7
    report ruled met, re-executed at this tip: a named tree that carries no
    status route returns an EMPTY text with the reason, and a caller that
    rejects an empty result is what turns that into a failure."""
    import inspect
    import tempfile

    contract = inspect.getsource(_server_lane_main)
    assert "_named_tree_route_text" not in contract.split('"""')[2], contract

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)

        # a NAMED tree that carries no status route: empty text, stated reason
        empty = root / "named-no-route"
        _r8_write_tree(empty, "backend/api/main.py", "x = 1" + LF)
        text, why = _named_tree_route_text(root, str(empty))
        assert text == "", text[:120]
        assert "carries no status route" in why, why
        assert "never silently replaced" in why, why

        # ...and the caller shape that makes that a failure rather than a skip
        assert not text, ("an empty result is rejected by the caller: " + why)

        # a NAMED tree that DOES carry the route answers, so the check above is
        # not passing because the machinery is broken (#342)
        full = root / "named-with-route"
        _r8_write_tree(full, "backend/api/main.py", _R8_STUB_ROUTE)
        text2, how2 = _named_tree_route_text(root, str(full))
        assert _ROUTE_ANCHOR in text2
        assert "$SCR_SERVER_LANE names" in how2, how2

        # a NAMED tree is EXCLUSIVE: a repository that carries the route beside
        # it is never read in its place
        _r8_write_tree(root, "backend/api/main.py", _R8_STUB_ROUTE)
        text3, why3 = _named_tree_route_text(root, str(empty))
        assert text3 == "", "the named tree was silently replaced"

        # with nothing named, the listing contributes no candidate however
        # exactly its branch bracket matches
        listing = [
            str(root / "other-lane") + "  bbbbbbb [claude/sept16-dc-server]",
        ]
        _r8_write_tree(root / "other-lane", "backend/api/main.py",
                       _R8_STUB_ROUTE.replace("zz_stub_only_name",
                                              "zz_listing_only_name"))
        text4, how4 = _named_tree_route_text(root, None, listing)
        assert "zz_listing_only_name" not in text4, how4


def test_r8cl_cl1_the_frozen_extracts_provenance_re_derives_from_the_record():
    """CL1 (B2, B6, B11, B18): THE PROVENANCE IS A MEASUREMENT, NOT A HEADER.

    WHAT WAS WRONG.  The extract's header records `source-lines` with a
    1-indexed start beside the 0-indexed EXCLUSIVE end the freeze held in a
    variable, so the stated range names 1876 newline-split elements where the
    body has 1875, and the text that range cuts hashes to b9573ad2... rather
    than to the body digest the same header records.  The header's
    `source-sha256` is the pin's digest after universal-newline translation --
    the mode the freeze read it in -- while the pin's own bytes hash to
    f8a640c8...; nothing in the header says which of the two it is.  Both
    mismatches have the shape of a drifted or fabricated extract, and neither
    can be told from one.

    WHY THE HEADER IS STILL THERE.  The contract froze the extract's whole-file
    digest and repeats it in a read-only pin, so the bytes are sealed.  The
    correction is delivered beside the file and this harness REQUIRES it: the
    resolver refuses while it is missing or no longer binding.

    WHAT THIS REJECTS.  Each defect on its own, through the record hook: a
    missing record, a wrong extract digest, a wrong body digest, the superseded
    RANGE restored, a body-element count that disagrees with the body in hand,
    one source digest offered without the two read modes distinguished, and a
    required sentence removed."""
    raw = _FROZEN_SERVER_EXTRACT.read_bytes().decode("utf-8")
    record = _FROZEN_PROVENANCE.read_text(encoding="utf-8")

    ok, why = _frozen_provenance_binds(raw)
    assert ok, why
    print("CL1 PROVENANCE RECORD : " + _FROZEN_PROVENANCE_REL
          + " binds the extract at sha256 " + _FROZEN_SERVER_EXTRACT_SHA256)

    # THE RANGE IS THE ONE THAT REPRODUCES, and the arithmetic is done here
    # rather than trusted: this is the assertion the extract's header fails.
    body = raw[raw.find(_ROUTE_ANCHOR):]
    lo, hi = _FROZEN_SOURCE_LINES.split(" of ")[0].split("-")
    assert int(hi) - int(lo) + 1 == len(body.split(LF)), (
        "the recorded range does not span the body")
    assert "38671-40546" not in _FROZEN_SOURCE_LINES
    import hashlib
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == \
        _FROZEN_BODY_SHA256
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == \
        _FROZEN_SERVER_EXTRACT_SHA256

    # THE TWO SOURCE DIGESTS ARE DIFFERENT VALUES UNDER DIFFERENT NAMES.  One
    # digest under one name is what produced the finding.
    assert _FROZEN_SOURCE_SHA256_BYTES != _FROZEN_SOURCE_SHA256_LF
    assert "CRLF throughout" in record
    assert "universal-newline translation" in record

    # ONE REJECTION PER DEFECT CLASS, planted through the hook.
    for label, edit in (
            ("the extract digest", lambda r: r.replace(
                "extract-sha256        : " + _FROZEN_SERVER_EXTRACT_SHA256,
                "extract-sha256        : " + "0" * 64)),
            ("the body digest", lambda r: r.replace(
                "body-sha256           : " + _FROZEN_BODY_SHA256,
                "body-sha256           : " + "1" * 64)),
            ("the superseded range restored", lambda r: r.replace(
                "source-lines          : 38671-40545 of 56062",
                "source-lines          : 38671-40546 of 56062")),
            ("the body element count", lambda r: r.replace(
                "body-split-elements   : 1875",
                "body-split-elements   : 1874")),
            ("the byte digest replaced by the translated one",
             lambda r: r.replace(
                 "source-sha256-bytes   : " + _FROZEN_SOURCE_SHA256_BYTES,
                 "source-sha256-bytes   : " + _FROZEN_SOURCE_SHA256_LF)),
            ("the index convention sentence", lambda r: r.replace(
                "1-INDEXED and INCLUSIVE", "somewhere in that region")),
            ("the no-tree sentence", lambda r: r.replace(
                "no tree can answer for the server representation",
                "a tree may answer when one is present")),
    ):
        bad, why_bad = _frozen_provenance_binds(raw, record=edit(record))
        assert not bad, "the record check accepted " + label
        assert why_bad, label

    # AN EMPTY RECORD FAILS.  It does not skip and it does not fall through:
    # a cross-lane claim that quietly stops being checked is the check that
    # cannot fail (#342).
    bad, why_bad = _frozen_provenance_binds(raw, record="")
    assert not bad, "an empty provenance record was accepted"
    assert _FROZEN_PROVENANCE_REL in (why_bad or ""), why_bad

    # INERT TWIN: prose that binds nothing, reworded at the same site.
    twin = record.replace("It is not a fallback behind a tree",
                          "It is not a tree's fallback")
    assert twin != record
    ok2, why2 = _frozen_provenance_binds(raw, record=twin)
    assert ok2, why2


def test_r8cl_cl2_the_stale_header_passages_are_superseded_in_both_directions():
    """CL2 (B2, B11, B18): THE FALSE MERGE PARAGRAPH IS BOUND, NOT LEFT LOOSE.

    WHAT WAS WRONG.  The sealed extract's header says, in the present tense,
    that if the lanes merge the resolver prefers a real tree carrying the route
    and falls back to the extract only when no such tree is present.  That is
    the mechanism the round-7 finding was raised about and this round removed:
    `_server_lane_main` calls `_frozen_route_text` and nothing else, no tree can
    answer merged or not, and the merge disposition is to DELETE this file and
    re-run the harness against the merged `backend/api/main.py`.  Read at merge
    time the paragraph is an instruction to restore the candidate ordering.

    WHY IT IS STILL IN THE FILE.  The extract's bytes are sealed by the
    contract digest.  The paragraph is therefore SUPERSEDED in a delivered file
    beside it, and the pairing is checked BOTH WAYS so neither half can rot:
    while the passage is in the extract the record must quote it under a
    supersession heading, and while the record quotes it the passage must still
    be there.

    WHAT THIS REJECTS.  The supersession removed; the quotation moved out from
    under its heading; the quotation altered so it no longer matches the sealed
    text; and a supersession left standing over text the extract does not
    carry."""
    raw = _FROZEN_SERVER_EXTRACT.read_bytes().decode("utf-8")
    record = _FROZEN_PROVENANCE.read_text(encoding="utf-8")

    merge = _FROZEN_SUPERSEDED[2]
    assert merge in raw, "the sealed extract no longer carries the passage"
    assert merge in record, "the record no longer supersedes it"
    print("CL2 SUPERSEDED PASSAGES : %d, each quoted under a heading"
          % len(_FROZEN_SUPERSEDED))

    # THE RESOLVER THE RECORD DESCRIBES IS THE ONE THIS FILE HAS.  The record
    # is prose; this is the tree.  Docstring and comments are stripped first,
    # because both TALK about trees and a word-absence check over prose is a
    # check about prose.
    import inspect
    src = inspect.getsource(_server_lane_main)
    code = src[src.index('"""', src.index('"""') + 3) + 3:]
    code = LF.join(l for l in code.split(LF) if not l.strip().startswith("#"))
    assert "_frozen_route_text()" in code
    for banned in ("_server_lane_candidates", "_named_tree_route_text",
                   "SCR_SERVER_LANE", "REVIEW-INPUT"):
        assert banned not in code, (
            "the record says no tree can answer while the resolver names "
            + banned)

    for label, edit in (
            ("the supersession deleted",
             lambda r: r.replace(merge, "(the merge paragraph)")),
            ("the heading removed", lambda r: r.replace(
                "SUPERSEDED -- the extract's merge paragraph, verbatim:",
                "A note on the merge paragraph:")),
            ("the quotation altered", lambda r: r.replace(
                "# back here only when no such tree is present.",
                "# back here only when no such tree exists.")),
    ):
        bad, why_bad = _frozen_provenance_binds(raw, record=edit(record))
        assert not bad, "the pairing accepted " + label
        assert why_bad, label

    # THE OTHER DIRECTION: a supersession over text the extract does not carry
    # is refused too, so the record cannot accumulate claims about nothing.
    ghost = record + LF + "SUPERSEDED -- a passage nobody has, verbatim:" + LF
    stale = _FROZEN_SUPERSEDED + ("# a line the extract has never carried",)
    saved = globals()["_FROZEN_SUPERSEDED"]
    try:
        globals()["_FROZEN_SUPERSEDED"] = stale
        bad, why_bad = _frozen_provenance_binds(
            raw, record=ghost + "# a line the extract has never carried" + LF)
        assert not bad, "a supersession over absent text was accepted"
        assert "no longer carries" in (why_bad or ""), why_bad
    finally:
        globals()["_FROZEN_SUPERSEDED"] = saved

    # INERT TWIN: the correction reworded where it explains rather than binds.
    twin = record.replace("Read at merge time as an",
                          "Read at merge time it would be an")
    assert twin != record
    ok2, why2 = _frozen_provenance_binds(raw, record=twin)
    assert ok2, why2


def test_r8cl_cl1b_the_sealed_extract_is_exempt_from_line_ending_conversion():
    """CL1 (B2): THE CONTRACT'S SEAL IS OVER BYTES, SO THE BYTES ARE PINNED.

    WHAT WAS FOUND WHILE RE-DERIVING THE PROVENANCE.  This repository is
    checked out with end-of-line conversion ON.  The extract is stored with
    line feeds and had never been re-checked-out since it was added, so the
    copy on disk still hashed to the sealed digest -- but a FRESH checkout
    rewrites it with carriage returns, 106143 bytes hashing to 7b8bd630..., and
    every cross-lane assertion then refuses with a digest mismatch.  The
    integrator's merge checkout is exactly that case.

    THE FIX IS AT THE ROOT: `backend/tests/.gitattributes` marks the extract and
    its provenance record as NOT text, so no checkout may rewrite them and the
    working-tree bytes are the blob's bytes on every seat.

    WHAT THIS REJECTS.  The attribute dropped for either file, and a carriage
    return in either file on disk."""
    attrs = (pathlib.Path(__file__).resolve().parent / ".gitattributes")
    assert attrs.exists(), (
        "backend/tests/.gitattributes is gone: a fresh checkout would rewrite "
        "the sealed extract's line endings and the contract digest would fail")
    text = attrs.read_text(encoding="utf-8")
    print("CL1b EOL EXEMPTION : " + " / ".join(
        l.strip() for l in text.split(LF) if l.strip()))
    for name in (_FROZEN_SERVER_EXTRACT.name, _FROZEN_PROVENANCE.name):
        assert re.search(r"^" + re.escape(name) + r"\s+-text\s*$", text, re.M), (
            name + " is not marked -text; a checkout may rewrite its bytes")
    for p in (_FROZEN_SERVER_EXTRACT, _FROZEN_PROVENANCE):
        assert b"\r" not in p.read_bytes(), (
            p.name + " carries a carriage return, so this working tree is "
            "already the converted copy")


def test_r6lens_l6_a_tree_being_written_is_not_read_as_a_disagreement():
    """A RED HERE MUST MEAN THE LANES DISAGREE, NOT THAT ONE WAS MID-SAVE.

    This was observed rather than imagined: a controls run read the other
    lane's `main.py` while its builder was saving it, and the route's key set
    came back without `dc_deferred_bound_seconds` -- a field the contract names
    throughout and which the same file carried on the next read.  A check whose
    RED can mean "I read a half-written file" sends a round looking for a
    defect that is not there, and the natural remedy for a test that cries wolf
    is to stop believing it.

    The rule is exercised through a reader callable, so it is tested without a
    concurrent writer."""
    seq = iter(["a = 1", "a = 2", "a = 3"])
    assert _stable_text(lambda: next(seq)) is None, "a changing file was accepted"
    assert _stable_text(lambda: "a = 1") == "a = 1", "a stable file was refused"
    assert _stable_text(lambda: None) is None, "a missing file was accepted"
    # the completeness hook is HONOURED, not decorative
    assert _stable_text(lambda: "a = 1", complete=lambda t: False) is None

    # a file that settles part-way through the attempts is accepted, because
    # the writer finished: the rule refuses instability, not slowness
    settling = iter(["a = 1", "a = 2", "a = 2"])
    assert _stable_text(lambda: next(settling), attempts=3) == "a = 2"

    # and the completeness predicate is about the DICT this check reads
    head = 'x = 1' + LF + '@app.get("/api/v1/team/series/{series_id}/status")' + LF
    whole = head + '    return {' + LF + '        "readonly": True,' + LF + '    }' + LF
    cut = head + '    return {' + LF + '        "readonly": True,' + LF
    assert _route_dict_is_complete(whole) is True
    assert _route_dict_is_complete(cut) is False
    # a tree that carries no such route is not judged here: the resolver skips
    # it, and failing it would make every unrelated tree an error
    assert _route_dict_is_complete("nothing of ours here") is True

    # THE RULE IS WIRED, not merely defined.  A defined-and-unused guard is a
    # check that cannot fail (#342), and nothing else here would notice: the
    # live resolver answers the same either way on a tree nobody is writing.
    #
    # THE FIRST CUT OF THIS ASSERTION READ THE WHOLE FILE, and the line below
    # would have satisfied it by containing the text it searched for -- which
    # its own control caught: R6L-12 unwired the resolver and the case stayed
    # green.  The claim is about the RESOLVER's body, so it reads that body.
    import inspect
    # THE RULE LIVES WITH THE MACHINERY IT GUARDS.  The contract resolver no
    # longer reads any tree (C5), so the claim "a tree being written is not
    # read as a disagreement" is about `_named_tree_route_text`, which is the
    # function that still reads one.  Asserting it against the contract
    # resolver after C5 would be a check that cannot fail.
    resolver = inspect.getsource(_named_tree_route_text)
    assert "_stable_text(_read, complete=_route_dict_is_complete)" in resolver

    # and the contract resolver answers from the hash-verified extract
    text, how = _server_lane_main()
    assert text, how
    assert _frozen_identity_holds(how), (
        "the cross-lane equality was resolved from something other than "
        "the hash-verified extract: " + how)


# ── ROUND 7: the repaint rule at the class, and eleven claims ────────────────
# The round-6 review raised one MEDIUM and eleven LOWs.  The MEDIUM was an
# implementation error inside round 6's own closure of H -- the repaint request
# was added at ONE exit while the defect was the CLASS -- so nothing below
# replaces a mechanism.  Each case closes one finding by number.


# The contract's bound sentence, reflowed-tolerant, shared by the round-7 cases
# that bind it.  One copy in this file, because a rule described twice is a rule
# that drifts (#341, #444).
_R7_BOUND_SENTENCE = (
    "A real-totals report wins while the deferred marker is younger than 420 "
    "seconds, and after that only until a sweep tick finds no live-game evidence "
    "for the series and settles the row; once a row is settled, a later report is "
    "refused at the settled-row exit and is not rated.")


def _r7_flatten(s):
    """Comment/string text as WORDS, so a sentence can be compared across line
    breaks, comment markers and C# string concatenation."""
    out = []
    for line in s.split("\n"):
        t = line.strip()
        if t.startswith("///"):
            t = t[3:]
        elif t.startswith("//"):
            t = t[2:]
        elif t.startswith("#"):
            t = t[1:]
        t = t.replace('+ "', " ").replace('"', " ")
        out.append(t)
    return " ".join(" ".join(out).split())


def _bound_sentence_or_no_constant(block):
    """The CONTENT rule B3 asks for: the bound constant appears in this text only
    inside the contract's sentence, verbatim, or it does not appear at all.

    A rewording that keeps the meaning and drops the number stays true; restating
    "420" in prose of this file's own does not."""
    if "420" not in block:
        return True
    return " ".join(_R7_BOUND_SENTENCE.split()) in _r7_flatten(block)


# ── M1 / B3 / B19: every path that changes a banner input asks for a repaint ──

# The banner's inputs, as the render key spells them.  A WRITER is anything that
# changes one of them; the census below is a grep of that OPERATION rather than
# of the one line the review flagged (#432, #330, #279).
_R7_BANNER_INPUTS = (
    "LastSeriesDcDeferred",
    "LastSeriesDcDeferredSecondsRemaining",
    "LastSeriesDcDeferredBoundSeconds",
    "LastSeriesDcDeferredFieldsPresent",
    "LastSeriesStateForId",
    "LastSeriesT1Wins",
    "LastSeriesT2Wins",
    "activeTeamSeriesId",
)

# EACH INPUT'S OWN TERM IN THE KEY, because a name is not a term.  The dark
# latch's term SPELLS `activeTeamSeriesId` as its argument, so from the moment
# the latch joined the key `"activeTeamSeriesId" in key` was satisfied by the
# latch alone: the id could leave the key as its own term with every
# name-level assertion still green, and an id change would then read as no
# change.  These are the TERMS; the names above are what the census greps for,
# which is a different question (#342, #431).
_R7_KEY_TERMS = (
    'return (activeTeamSeriesId ?? "-")',
    '+ "|" + (LastSeriesStateForId ?? "-")',
    '+ "|" + (LastSeriesDcDeferred ? "1" : "0")',
    '+ "|" + LastSeriesDcDeferredSecondsRemaining',
    '+ "|" + LastSeriesDcDeferredBoundSeconds',
    '+ "|" + (LastSeriesDcDeferredFieldsPresent ? "p" : "-")',
    '+ "|" + (SeriesStatusLatchedDark(activeTeamSeriesId) ? "d" : "-")',
    '+ "|" + LastSeriesT1Wins',
    '+ "|" + LastSeriesT2Wins',
)

# THE NINTH INPUT IS NOT A FIELD.  The render predicate is
# `cacheIsThisSeries && !latchedDark && dc_deferred`, and the latch is a SET.
# It was missed by the first census for exactly that reason: a grep for
# assignments cannot see a set, which is written by a method call.  So the
# census asks about the OPERATION in both of its spellings (#432).
_R7_BANNER_LATCH = "_statusPollDarkSeries"

# Every way C# changes a value, not just `=`: compound assignment and
# increment/decrement are writes, and the round-7 census matched neither.  `=`
# is guarded against `==` and, because the name must sit immediately before the
# operator, `<=`, `>=` and `!=` cannot reach it.
_R7_ASSIGN = re.compile(
    r"(?:ApiClient\.)?(?:" + "|".join(_R7_BANNER_INPUTS) + r")\s*"
    r"(?:(?:\+|-|\*|/|%|\||&|\^|<<|>>|\?\?)?=(?!=)|\+\+|--)")
_R7_PRE_INCDEC = re.compile(
    r"(?:\+\+|--)\s*(?:ApiClient\.)?(?:" + "|".join(_R7_BANNER_INPUTS) + r")\b")
_R7_SET_WRITE = re.compile(
    r"(?:ApiClient\.)?" + _R7_BANNER_LATCH +
    r"\s*\.\s*(?:Add|Remove|Clear|UnionWith|IntersectWith|ExceptWith|"
    r"SymmetricExceptWith|RemoveWhere)\s*\(")

# A FIELD PASSED BY REFERENCE IS A WRITER, and it was the form the round-7
# census could not see at all.  `Interlocked.Increment(ref ApiClient.LastSeriesT1Wins)`
# changes the value without the name ever sitting beside an assignment
# operator, so every regex above misses it; the fields were `public static`,
# which made it a writer anything in the assembly could use.  Round 8 narrows
# that at the root as well -- the inputs are now `{ get; private set; }`, and a
# property cannot be passed by reference -- but the census stays wide, because
# a check that stopped looking for a form is a check that certifies a class it
# cannot see (#342), and the narrowing is one edit away from being undone.
#
# The name must follow `ref`/`out` IMMEDIATELY, so a line that passes some
# other variable by reference while merely READING a banner input is not a
# writer here -- that is this rule's own inert twin.
_R8_REF_OUT_WRITE = re.compile(
    r"\b(?:ref|out)\s+(?:ApiClient\.)?(?:" + "|".join(_R7_BANNER_INPUTS) + r")\b")

# The API-mediated writers, named as their own class so the rejection is
# greppable rather than implied by the rule above.  Every one of them reaches
# the value through `ref`, which is why the two overlap; a census may recognise
# a form twice, and naming the class is what makes its absence checkable.
_R8_API_WRITE = re.compile(
    r"\b(?:Interlocked|Volatile)\s*\.\s*\w+\s*\(\s*ref\s+"
    r"(?:ApiClient\.)?(?:" + "|".join(_R7_BANNER_INPUTS) + r")\b")


def _r7_plugin_sources():
    """{name: text} for EVERY C# source in the plugin, resolved at run time.

    The round-7 census read ApiClient.cs alone while the banner's inputs are
    `public static`, so a writer in NativeUI.cs, Plugin.cs or any file added
    later was outside the scan and the check would have stayed green on the
    case it exists to catch.  Globbing rather than listing the files means a
    NEW file joins the census by existing (#330: sweep the siblings)."""
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(PLUGIN.glob("*.cs"))}


_R8_DECL_HEAD = re.compile(
    r"^\s*(?:(?:public|private|internal|protected|static|readonly|const|"
    r"volatile|new|partial)\s+)+[A-Za-z_][A-Za-z0-9_<>\[\],.?]*\s+$")


def _r8_declared_name_at(line):
    """Where a banner-input identifier first appears on this line, or None."""
    best = None
    low = line.lower()
    for tok in ("lastseries", "activeteamseriesid", _R7_BANNER_LATCH.lower()):
        i = low.find(tok)
        if i >= 0 and (best is None or i < best):
            best = i
    return best


def _r8_is_declaration(line):
    """True when this line DECLARES a banner input rather than WRITING one.

    THE EXCLUSION THIS REPLACES DISCARDED THE LINE IT WAS MEASURING.  It
    dropped any line containing the word `static`, which is true of a
    declaration and equally true of a one-line static method, a static
    constructor and a static initialiser -- so a write placed on such a line
    was invisible to the census, and the control that plants exactly that
    (R8-L11a) stayed GREEN.  A filter that throws away the line it is supposed
    to judge is the defect class #441 names, and this is the second time this
    round that a probe could not fire.

    A declaration is recognised by SHAPE instead: modifiers, then a type, then
    the name, with no call between the start of the line and the name.  An
    auto-property declaration ends in an accessor block and an initialiser and
    still matches, because everything before the NAME is still modifiers and a
    type."""
    at = _r8_declared_name_at(line)
    if at is None:
        return False
    head = line[:at]
    if "(" in head:
        return False
    return bool(_R8_DECL_HEAD.match(head))


def _r7_writer_lines(sources):
    """Every (file, line, text) in `sources` that CHANGES a banner input.

    Declarations are excluded -- a field's own declaration is not a writer, and
    it is recognised by the `static` that every one of these carries.  `sources`
    is a {name: text} map so a control can put a writer in another file without
    touching the tree."""
    if not isinstance(sources, dict):
        sources = {"ApiClient.cs": sources}
    out = []
    for fname in sorted(sources):
        for i, line in enumerate(sources[fname].split("\n"), 1):
            # cheap pre-filter: three substring tests over ~100 000 lines, so
            # the three regexes below run on the handful that could match
            if ("LastSeries" not in line and "activeTeamSeriesId" not in line
                    and _R7_BANNER_LATCH not in line):
                continue
            if not (_R7_ASSIGN.search(line) or _R7_PRE_INCDEC.search(line)
                    or _R7_SET_WRITE.search(line)
                    or _R8_REF_OUT_WRITE.search(line)
                    or _R8_API_WRITE.search(line)):
                continue
            s = line.strip()
            if _r8_is_declaration(line) or s.startswith("///") \
                    or s.startswith("//"):
                continue
            out.append((fname, i, s))
    return out


def _r7_setter_span(api):
    a = api.find("        public static string ActiveTeamSeriesId")
    b = api.find("        public static bool IsTeamQueuePolling", a)
    if a < 0 or b < 0:
        return ""
    return api[a:b]


def _r7_refusal_span(poller):
    """The refusal path inside the read-only poller: from the `!affirmed` gate to
    the `return;` that ends it.  This is also the TIMEOUT path and the
    transport-refusal path -- GetRequest invokes this one callback on every exit,
    and the three are distinguished only by the code in `answeredWith`."""
    a = poller.find("if (!affirmed)")
    if a < 0:
        return ""
    b = poller.find("return;", a)
    if b < 0:
        return ""
    return poller[a:b + len("return;")]


def _r7_dispatch_throw_span(poller):
    a = poller.find("catch (Exception ex)")
    return poller[a:] if a >= 0 else ""


def _r7_repaint_paths(src):
    """{name: span} for every path that must hold the repaint rule."""
    poller = _method_body(src, "public static void PollTeamSeriesStatusReadOnly")
    return {
        "the id setter": _r7_setter_span(src),
        "the refusal path (and the timeout)": _r7_refusal_span(poller),
        "the dispatch-throw path": _r7_dispatch_throw_span(poller),
        "the shared parse": _method_body(
            src, "private static void ApplySeriesStateResponse"),
    }


def test_r7_m1_b19_every_path_that_changes_a_banner_input_asks_for_the_repaint():
    """THE RULE BELONGS TO THE OPERATION, NOT TO ONE EXIT (#432, #330, #279).

    Round 6 closed H by adding the repaint request at the end of the affirmative
    parse.  The refusal branch clears the same three fields and returns without
    it, so once the banner had rendered, a later 404, 500 or unanswered read
    changed the state the banner reads while the visible object stayed active
    until something unrelated marked the tab dirty -- during an outage, for as
    long as the tab stayed open.  A flag names a LINE; the defect was a CLASS.

    WHAT IS ASSERTED HERE.  First the CENSUS: every write of a banner input
    ANYWHERE IN THE PLUGIN, found by grepping the operation in all of its
    spellings, falls inside one of the paths below -- so a new writer somewhere
    else reddens this rather than slipping in beside it.  Then, for each path,
    the request is present EXACTLY ONCE within that path's own span, never
    counted file-wide, where four copies would let any one of them go missing
    unnoticed.

    THE CENSUS IS WIDER THAN IT WAS, TWICE OVER.  Its first cut anchored on
    `^\\s*Name =` in ApiClient.cs alone, so a compound write (`+=`, `??=`, `++`)
    matched nothing and a writer in any other file -- the fields are
    `public static` -- was outside the scan entirely.  Neither existed on the
    tree, which is precisely the shape of a check that certifies a class while
    being unable to see it (#342).  And the latch is now one of the inputs, so
    the census asks about a SET as well as about fields.

    The dispatch-throw path writes none of the inputs and therefore asks for
    nothing at run time.  It carries the call all the same: a rule with an
    exempt path is a rule nobody can check, and a path that gains a write later
    gains the request with it."""
    api = _src("ApiClient.cs")

    paths = _r7_repaint_paths(api)
    for name, span in paths.items():
        assert span, "the span for " + name + " could not be delimited"

    # THE RENDER KEY IS THE WHOLE INPUT SET.  The census is a census OF a list,
    # so the list has to be the render's own; a name that the render reads and
    # the key omits is the defect the latch was (#342).
    keyfn = _method_body(api, "private static string BannerRenderKey")
    assert keyfn, "the render key could not be delimited"
    for name in _R7_BANNER_INPUTS:
        assert name in keyfn, "the render key does not read " + name
    # AND EACH AS ITS OWN TERM.  The loop above stays green with the id's
    # own term deleted, because the latch term spells the id (#342).
    for term in _R7_KEY_TERMS:
        assert term in keyfn, "the render key does not carry the term " + term
    assert "SeriesStatusLatchedDark(activeTeamSeriesId)" in keyfn, (
        "the render key does not ask the dark latch about the ACTIVE series, "
        "which is the one term the render predicate reads beside the fields")
    ui = _src("NativeUI.cs")
    assert "ApiClient.SeriesStatusLatchedDark(dcSeries)" in ui, (
        "the render predicate no longer reads the latch -- the key's term and "
        "the render's term must be the same question")

    # THE CENSUS -- the sweep of siblings, recorded.  Every writer of a banner
    # input, in EVERY plugin source, is inside one of the paths above.
    sources = _r7_plugin_sources()
    assert "ApiClient.cs" in sources and len(sources) > 3, sorted(sources)
    writers = _r7_writer_lines(sources)
    assert writers, "the writer grep found nothing -- the census cannot be empty"
    outside = []
    for fname, lineno, text in writers:
        if fname != "ApiClient.cs" or not any(text in span
                                              for span in paths.values()):
            outside.append((fname, lineno, text))
    assert not outside, (
        "these writers of a banner input sit outside every repaint path: "
        + repr(outside))

    # THAT THE CENSUS CAN SEE each write form and each source file is its own
    # named case: test_r7cl_c4_... below.  A census is only as wide as its grep,
    # and the grep's reach is a separate claim from this one's result.

    # THE OCCURRENCE ASSERTION, WITHIN EACH PATH'S SPAN.
    for name, span in paths.items():
        n = span.count("RequestBannerRepaintIfChanged(")
        assert n == 1, "%s carries %d repaint requests, not 1" % (name, n)

    # the callback takes ONE key for every answer, so the refusal, the transport
    # failure and the 20 s timeout are one path and are covered together
    poller = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    assert "_statusReadInFlight = false;" in poller
    assert "string bannerBefore = BannerRenderKey();" in poller
    assert poller.index("_statusReadInFlight = false;") < poller.index(
        "string bannerBefore = BannerRenderKey();")
    assert poller.index("string bannerBefore = BannerRenderKey();") < poller.index(
        "if (!affirmed)")

    # the helper exists and is the only thing that marks the tab dirty for this
    # banner -- one rule, one implementation (#330)
    helper = _method_body(api, "private static void RequestBannerRepaintIfChanged")
    assert helper, "the repaint helper could not be delimited"
    assert "if (BannerRenderKey() != keyBefore) NativeUI.MarkDirty();" in helper

    def claim(s):
        try:
            ps = _r7_repaint_paths(s)
        except Exception:
            return False
        if not all(ps.values()):
            return False
        return all(span.count("RequestBannerRepaintIfChanged(") == 1
                   for span in ps.values())

    # ONE MUTATION PER PATH, each removing that path's own request.  Each anchor
    # is unique in the file -- by indentation, or by the argument name -- so a
    # first-occurrence replace removes exactly the one named.
    # EACH ANCHOR CARRIES THE UNIQUE LINE ABOVE ITS CALL.  The call text at one
    # indentation is a SUBSTRING of the same call at a deeper one, so a bare
    # call line would mutate whichever copy came first -- a control that reports
    # on a path it never touched (#342).
    removals = (
        ("the id setter",
         "                activeTeamSeriesId = value;\n"
         "                RequestBannerRepaintIfChanged(bannerBefore);",
         "R7-M1-a the id setter stops asking for the repaint"),
        ("the refusal path",
         "// OPERATION's rather than one exit's (#432, #330).\n"
         "                        RequestBannerRepaintIfChanged(bannerBefore);",
         "R7-M1-b the refusal path stops asking for the repaint"),
        ("the dispatch-throw path",
         "RequestBannerRepaintIfChanged(dispatchBannerBefore);",
         "R7-M1-c the dispatch-throw path stops asking for the repaint"),
        ("the shared parse",
         "one before/after key (#432).\n"
         "            RequestBannerRepaintIfChanged(bannerBefore);",
         "R7-M1-d the shared parse stops asking for the repaint"),
    )
    for _name, anchor, label in removals:
        assert api.count(anchor) == 1, "ambiguous anchor: " + label
        _assert_discriminating(
            claim, api, _mutate(api, anchor, "// no repaint", label), label)

    # AND ONE INERT TWIN PER PATH: a change of the SAME SHAPE at the SAME SITE
    # that leaves the request in place.  A check that reddens on any edit at all
    # proves nothing about this one (#391).
    twins = (
        ("the id setter",
         "// RequestBannerRepaintIfChanged for the repaint after — the same rule",
         "// RequestBannerRepaintIfChanged for the redraw after — the same rule"),
        ("the refusal path",
         "// THE REPAINT RULE ON THE REFUSAL PATH. The branch above may",
         "// THE REPAINT RULE ON THE REFUSAL PATH. That branch above may"),
        ("the dispatch-throw path",
         "// THE REPAINT RULE ON THE DISPATCH-THROW PATH, and it is inert on",
         "// THE REPAINT RULE ON THE DISPATCH-THROW PATH, and it stays inert on"),
        ("the shared parse",
         "// IT IS THE SHARED CALL AND NOT A LOCAL COMPARISON, because round 6's",
         "// IT IS THE SHARED CALL AND NOT A LOCAL COMPARISON, since round 6's"),
    )
    for name, old, new in twins:
        twin = _mutate(api, old, new, "R7-M1 inert twin at " + name)
        assert twin != api, "the inert twin for " + name + " changed nothing"
        assert claim(twin), "the inert twin at " + name + " reddened the check"


def test_r7_b16_the_refusal_branch_says_what_it_now_does_to_the_screen():
    """B16: THE AUTHORED CLAIM AT THE LATCH.

    The round-6 comment said latching stops the poll and, on its own, does not
    change what the banner renders FROM -- two facts.  There is a third: changing
    what it renders from does not repaint it.  The off-witness's own wording,
    "the last one is not kept", is a claim about the SCREEN, and the clear alone
    made it true only of the STATE."""
    api = _src("ApiClient.cs")
    poller = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    assert poller
    assert "DARK HAS TO MEAN DARK, AND THAT IS THREE FACTS, NOT TWO." in poller
    assert "changing what it renders from" in poller
    assert "does not repaint it" in poller
    # the superseded two-fact wording is gone
    assert "are two different facts (#342). These three fields are the" not in poller

    def claim(s):
        b = _method_body(s, "public static void PollTeamSeriesStatusReadOnly")
        return bool(b) and "DARK HAS TO MEAN DARK, AND THAT IS THREE FACTS, NOT TWO." in b \
            and "does not repaint it" in b

    _assert_discriminating(
        claim, api,
        _mutate(api, "DARK HAS TO MEAN DARK, AND THAT IS THREE FACTS, NOT TWO.",
                "DARK HAS TO MEAN DARK. Latching stops the POLL; on its own",
                "R7-B16 the latch comment returns to two facts"),
        "R7-B16 the latch comment states the third fact")
    # inert twin: the sentence around it is reworded, the claim stands
    assert claim(_mutate(api, "Latching stops the POLL; on its own it does not change what",
                         "Latching stops the POLL; by itself it does not change what",
                         "R7-B16 inert twin"))


# ── L2: the bound constant is not restated in the banner block ───────────────


def test_r7_l2_the_banner_block_restates_no_bound_constant():
    """L2, carrying B3.

    A local "420 s deferral window" sat in the prose of the one file whose whole
    claim is that it keeps no copy of the bound, and `test:4124` explicitly
    accepted it -- the check admitted exactly the wording B3 asks it to reject.
    The rule is now about CONTENT: the constant appears in that block only inside
    the contract's bound sentence, verbatim, or not at all."""
    ui = _src("NativeUI.cs")
    block = _dc_banner_block(ui)
    assert block, "the DC banner block could not be delimited"

    assert _bound_sentence_or_no_constant(block)
    assert "420 s deferral window" not in block
    assert "THE BOUND IS NOT RESTATED HERE AS" in block

    def claim(s):
        b = _dc_banner_block(s)
        return bool(b) and _bound_sentence_or_no_constant(b) \
            and "420 s deferral window" not in b

    # MUTATION: the superseded prose comes back
    _assert_discriminating(
        claim, ui,
        _mutate(ui, "sat inside the deferral window the status\n            // route reports",
                "sat inside a 420 s deferral window\n            // and was told",
                "R7-L2 the banner block restates the bound as a number"),
        "R7-L2 the banner block restates no bound constant")

    # INERT TWIN: a rewording that keeps the meaning and names no number
    assert claim(_mutate(
        ui, "sat inside the deferral window the status",
        "sat inside the deferral window that the status",
        "R7-L2 inert twin"))


# ── L3 / B11: the ABSENT branch says only what an absent key proves ──────────


def test_r7_l3_b11_the_absent_branch_says_only_what_absence_proves():
    """L3, carrying B11.

    The branch carried the contract's sentence and then added that "nothing
    parked this report" -- an event-level conclusion an absent key did not
    measure.  Under contract item 6 an absent `deferred` proves only that the
    answering box predates the field, and says nothing about whether that box
    settled, ignored or fenced the report."""
    api = _src("ApiClient.cs")
    assert "That the answering box predates the field is the whole of " in api
    assert "what this absence proves; it says nothing about whether that " in api
    assert "box settled, ignored or fenced this report" in api
    # THE SUPERSEDED WORDING IS REJECTED BY NAME
    assert "What is certain is that nothing parked this report" not in api

    def claim(s):
        return ("That the answering box predates the field is the whole of " in s
                and "box settled, ignored or fenced this report" in s
                and "What is certain is that nothing parked this report" not in s)

    _assert_discriminating(
        claim, api,
        _mutate(api,
                '                                + ". That the answering box predates the field '
                'is the whole of "',
                '                                + ". What is certain is that nothing parked '
                'this report, so the "',
                "R7-L3 the absent branch reclaims that nothing parked the report"),
        "R7-L3 the absent branch says only what absence proves")

    # INERT TWIN: the explanatory comment above the line is reworded
    assert claim(_mutate(api, "AN ABSENT FIELD IS A FACT ABOUT THE BOX, NOT ABOUT THE ROW,",
                         "AN ABSENT FIELD IS A FACT ABOUT THE BOX AND NOT ABOUT THE ROW,",
                         "R7-L3 inert twin"))


# ── L6: the off line splits "no cached series" from "a different series" ─────


def test_r7_l6_the_off_line_splits_no_cached_series_from_a_different_one():
    """L6.

    `ApiClient.cs` produces the cache-mismatch state two ways: a cache whose
    ForId names ANOTHER series, and a cache with no ForId at all, which is what
    the id setter leaves for a newly adopted series before its first answer.
    The witness reported both as "a different series", so the state BEFORE the
    first answer was logged as an answer about another series."""
    ui = _src("NativeUI.cs")
    api = _src("ApiClient.cs")
    body = _witness_body(ui)
    assert body, "the witness body could not be delimited"

    # the state exists on the other side: the setter nulls the cache id
    assert "LastSeriesStateForId = null;" in api

    assert "bool noCachedSeries = string.IsNullOrEmpty(ApiClient.LastSeriesStateForId);" in body
    assert "the status cache describes NO series" in body
    assert "the status cache describes a DIFFERENT series (" in body
    # and the change key holds them apart, or the second suppresses the first
    assert '+ (noCachedSeries ? "0" : "s")' in body

    def claim(s):
        b = _witness_body(s)
        return bool(b) and "the status cache describes NO series" in b \
            and "the status cache describes a DIFFERENT series (" in b \
            and '+ (noCachedSeries ? "0" : "s")' in b

    # MUTATION 1: the two states collapse back into one sentence
    _assert_discriminating(
        claim, ui,
        _mutate(ui, "the status cache describes NO series",
                "the status cache describes a different series",
                "R7-L6 the two cache states collapse into one"),
        "R7-L6 the off line names each cache state")

    # MUTATION 2: the key stops holding them apart, so one suppresses the other
    _assert_discriminating(
        claim, ui,
        _mutate(ui, '                         + (noCachedSeries ? "0" : "s")\n', "",
                "R7-L6 the change key stops separating the two cache states"),
        "R7-L6 the change key separates the two cache states")

    # INERT TWIN: the explanatory comment is reworded
    assert claim(_mutate(
        ui, '// "No cached series at all" and "a cache describing another series" are',
        '// "No cached series at all" and "a cache naming another series" are',
        "R7-L6 inert twin"))


# ── L7: the three suppressors state the cardinality they actually have ───────

_R7_SUPPRESSORS = ("_statusPollRefusedForSeries",
                   "_statusPollProvenForSeries",
                   "_statusPollNoDeferralForSeries")


def test_r7_l7_the_three_suppressors_state_their_real_cardinality():
    """L7.

    Three comments promised "one line per series" while all three suppressors
    are a single remembered string, so an A -> B -> A sequence emits A's line
    again -- which `:14916-14920` already admitted correctly for W28.  Each
    comment now states the cardinality the field has."""
    api = _src("ApiClient.cs")

    # all three ARE single remembered strings, not sets -- the fact the comments
    # have to match
    for f in _R7_SUPPRESSORS:
        assert ("private static string " + f + " = null;") in api, f

    def _decl_comment(src, field):
        """The CONTIGUOUS run of // lines immediately above that declaration.

        Walking back to the nearest blank line is what the first cut did, and it
        swept in the PREVIOUS field's comment -- so a mutation of one field's
        wording was answered by a neighbour's text and the control stayed green
        (#342, and the same shape as this file's own _method_body lesson)."""
        decl = "private static string " + field + " = null;"
        i = src.find(decl)
        if i < 0:
            return ""
        lines = src[:i].split("\n")
        out = []
        for ln in reversed(lines[:-1] if lines and not lines[-1].strip() else lines):
            if ln.strip().startswith("//"):
                out.append(ln)
                continue
            break
        return "\n".join(reversed(out))

    # the wording is reflowed across comment lines, so it is compared as WORDS
    for f in _R7_SUPPRESSORS:
        c = _r7_flatten(_decl_comment(api, f))
        assert c, f
        assert "ONE REMEMBERED SERIES ID" in c, f
        assert "A -> B -> A" in c, f
        # the superseded promise is rejected by name
        assert "One line per series id:" not in c, f

    def claim(s):
        return all("ONE REMEMBERED SERIES ID" in _r7_flatten(_decl_comment(s, f))
                   for f in _R7_SUPPRESSORS)

    # ONE MUTATION PER FIELD: each comment's own opening line is reworded back
    # to the superseded promise, and the claim must go False each time.
    openers = (
        ("_statusPollRefusedForSeries",
         "        // ONE REMEMBERED SERIES ID, NOT A SET, so the cardinality this thins the"),
        ("_statusPollProvenForSeries",
         "        // The other half of the same rule, and the same cardinality: ONE REMEMBERED"),
        ("_statusPollNoDeferralForSeries",
         "        // The third suppressor, and the third of the same shape: ONE REMEMBERED"),
    )
    for f, opener in openers:
        assert api.count(opener) == 1, f
        _assert_discriminating(
            claim, api,
            _mutate(api, opener, opener.replace("ONE REMEMBERED", "One line per series id:"),
                    "R7-L7 " + f + " reclaims one line per series"),
            "R7-L7 the suppressors state their real cardinality")

    # INERT TWIN: rewording a neighbouring sentence keeps every claim
    assert claim(_mutate(api, "and it is not evidence of how many series were refused",
                         "and it is no evidence of how many series were refused",
                         "R7-L7 inert twin"))


# ── L9 + SERVER-L7: the refusal's cost, and who can settle a marked row ──────


def test_r7_l9_serverl7_the_refusal_cost_and_the_rows_settlers_are_stated_as_the_tree_has_them():
    """L9 (client half of server-report L7) and SERVER-L7's first passage.

    Two comments described a tree that has moved.  The refusal-cost paragraph
    said a countdown "cannot appear on current data" -- written when the banner
    hung off a predicate no box satisfied; the banner now renders from the three
    fields this very route carries, so a refusal darkens a live countdown.  And
    the deferral paragraph named the sweep as the only other writer of the row,
    while a later real-totals report settles it at the lead-forfeit completion or
    the dc_incomplete settle inside the bound."""
    api = _src("ApiClient.cs")

    # L9 -- the refusal cost
    assert "the DC-grace banner for that series as" in api
    assert "repaint that takes an already-rendered banner off the screen" in api
    assert "not a countdown, which cannot appear on current data" not in api

    # SERVER-L7 -- who settles a marked row
    assert "the sweep is not the only thing that can close" in api
    assert "the lead-forfeit completion or" in api
    assert "the dc_incomplete settle while the bound still holds" in api
    assert "The only other writer of that row is the server's" not in api

    def claim(s):
        return ("repaint that takes an already-rendered banner off the screen" in s
                and "not a countdown, which cannot appear on current data" not in s
                and "the sweep is not the only thing that can close" in s
                and "The only other writer of that row is the server's" not in s)

    _assert_discriminating(
        claim, api,
        _mutate(api, "repaint that takes an already-rendered banner off the screen",
                "countdown, which cannot appear on current data",
                "R7-L9 the refusal cost reclaims that no countdown can be current"),
        "R7-L9 the refusal cost names the banner it darkens")

    _assert_discriminating(
        claim, api,
        _mutate(api, "the sweep is not the only thing that can close",
                "The only other writer of that row is the server's",
                "R7-SERVER-L7 the sweep is named the only settler again"),
        "R7-SERVER-L7 the row's settlers are named as the tree has them")

    # INERT TWIN, one per corrected passage
    assert claim(_mutate(api, "is the round-7 correction of a sentence",
                         "is the round-7 correction to a sentence",
                         "R7-L9 inert twin"))
    assert claim(_mutate(api, "// the whole point of leaving it open. So a series",
                         "// the entire point of leaving it open. So a series",
                         "R7-SERVER-L7 inert twin"))


# ── L11: W8 states the disposition the reviewed route produces ───────────────


def test_r7_l11_w8_states_the_disposition_the_reviewed_route_produces():
    """L11.

    W8 said a zero-total fallback is one "which the deployed endpoint can only
    record as dc_incomplete".  The route this client is built against marks the
    row and answers `deferred=true` BEFORE any total is read, so the witness
    named a disposition the reviewed server does not produce.  It now reports
    what each generation of box actually answers, and says the disposition is
    read out of the answer rather than assumed.

    THE SERVER SIDE OF THIS CLAIM IS CHECKED ACROSS THE LANES, not asserted from
    here: the resolver reads the other tree's report-dc handler and requires the
    fallback branch to answer `deferred` before it reads totals."""
    ra = _src("RoomActors.cs")
    assert "WHAT THAT FORM IS RECORDED AS depends on the box" in ra
    assert "before any total is read, leaving the series open for a real-totals report" in ra
    assert "the deployed endpoint can only record as" not in ra

    # cross-lane: the reviewed route really does answer deferred before totals
    server, how = _server_lane_main()
    assert server, how
    assert _frozen_identity_holds(how), (
        "the cross-lane equality was resolved from something other than "
        "the hash-verified extract: " + how)
    i = server.find("if is_fallback:")
    assert i > 0, "the fallback branch could not be found on the server lane"
    branch = server[i:i + 4000]
    j = branch.find('"deferred": True')
    assert j > 0, "the fallback branch does not answer deferred=true"
    # and it does so before any total is read in that branch
    for total in ("t1_points_total", "t2_points_total"):
        k = branch.find(total)
        assert k < 0 or k > j, (
            "the fallback branch reads " + total + " before it answers deferred")

    def claim(s):
        return ("WHAT THAT FORM IS RECORDED AS depends on the box" in s
                and "the deployed endpoint can only record as" not in s)

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "WHAT THAT FORM IS RECORDED AS depends on the box",
                "which the deployed endpoint can only record as dc_incomplete, the box",
                "R7-L11 W8 reclaims a single deployed disposition"),
        "R7-L11 W8 states the disposition the reviewed route produces")

    assert claim(_mutate(ra, "and is read out of the answer, never assumed",
                         "and is read out of the answer, never presumed",
                         "R7-L11 inert twin"))


# ── SERVER-L3: no comment reads a pre-field 200 as a settlement ──────────────

# SPLIT ON PURPOSE, and this is L8's mechanism as much as its subject: the
# round-8 scope below covers the HARNESS as well as the plugin sources, so a
# file that spelled a forbidden form contiguously would reject itself forever.
# Each form is assembled from two pieces; the value is identical and the source
# line is not the form.  (`_R7_CLAIMS` already carried one row this way.)
_R7_PRE_FIELD_SETTLEMENT_FORMS = (
    "the report settles " + "immediately exactly",
    "is_fallback parameter " + "and settled the series on it",
)


def test_r7_serverl3_no_comment_reads_a_pre_field_200_as_settlement():
    """SERVER-L3, routed to this lane, and the answer SERVER-B0c takes.

    Two passages described a 200 from a box that predates the field as a
    settlement.  Contract item 6 splits the five false exits two ways -- two
    settle, three decide nothing and say so with `ignored: true` -- and an ABSENT
    key proves only the box's age.  SERVER-B0c's executable handling was already
    correct; it was NOT MET because of these two passages, so this check is that
    row's answer as well."""
    api = _src("ApiClient.cs")

    for form in _R7_PRE_FIELD_SETTLEMENT_FORMS:
        assert form not in api, "a superseded settlement claim survives: " + form

    assert "only that the box which answered" in api
    assert "predates the field. It is not proof that the report settled" in api
    assert "a box that predates the" in api
    assert "it cannot say what that older box DID with the report" in api

    def claim(s):
        return (all(f not in s for f in _R7_PRE_FIELD_SETTLEMENT_FORMS)
                and "predates the field. It is not proof that the report settled" in s
                and "it cannot say what that older box DID with the report" in s)

    _assert_discriminating(
        claim, api,
        _mutate(api, "predates the field. It is not proof that the report settled",
                "the report settles " + "immediately exactly as it does today, so it settled",
                "R7-SERVER-L3a the older-server passage reclaims settlement"),
        "R7-SERVER-L3a a pre-field 200 is not read as settlement")

    _assert_discriminating(
        claim, api,
        _mutate(api, "it cannot say what that older box DID with the report",
                "the is_fallback parameter " + "and settled the series on it is what it says",
                "R7-SERVER-L3b the three-value passage reclaims settlement"),
        "R7-SERVER-L3b the three-value passage names no settlement")

    assert claim(_mutate(api, "AGAINST AN OLDER SERVER (#266). An unknown query parameter",
                         "AGAINST AN OLDER SERVER (#266). Any unknown query parameter",
                         "R7-SERVER-L3 inert twin"))


# ── B16: one claims check over every sentence this round corrected ───────────

# (file, must-be-ABSENT superseded form, must-be-PRESENT corrected form).  One
# table, so a superseded wording cannot return to any of them quietly and a
# corrected one cannot be dropped.  `test` is this harness itself: the L8
# docstring is a claim like any other.
_R7_CLAIMS = (
    ("ApiClient.cs",
     "What is certain is that nothing parked this report",
     "box settled, ignored or fenced this report"),
    ("ApiClient.cs",
     "the report settles " + "immediately exactly",
     "predates the field. It is not proof that the report settled"),
    ("ApiClient.cs",
     "is_fallback parameter " + "and settled the series on it",
     "it cannot say what that older box DID with the report"),
    ("ApiClient.cs",
     "The only other writer of that row is the server's",
     "the sweep is not the only thing that can close"),
    ("ApiClient.cs",
     "not a countdown, which cannot appear on current data",
     "repaint that takes an already-rendered banner off the screen"),
    ("ApiClient.cs",
     "One line per series id:",
     "ONE REMEMBERED SERIES ID"),
    ("NativeUI.cs",
     "420 s deferral window",
     "THE BOUND IS NOT RESTATED HERE AS"),
    ("NativeUI.cs",
     "the status cache describes a different series, so nothing in ",
     "the status cache describes NO series"),
    ("RoomActors.cs",
     "the deployed endpoint can only record as",
     "WHAT THAT FORM IS RECORDED AS depends on the box"),
    # ── the round-7 cold-lens rows ──────────────────────────────────────────
    # W8 said the reviewed route PARKS a zero-total fallback, full stop.  Three
    # exits on that route are reached before any total is read and park nothing
    # (contract item 6), so the arming line named a disposition the route does
    # not guarantee -- the mirror of the three rows this round already closed,
    # written by the same hand in the same pass.
    ("RoomActors.cs",
     "client is built against PARKS it",
     "the park is ONE ANSWER AMONG SEVERAL, not a property "),
    # The latch comment counted the banner's inputs as three while the render
    # predicate beside it read the presence bit and the latch as well.
    ("ApiClient.cs",
     "does not repaint it (#342). These three fields are the",
     "THREE NUMBERS, THE PRESENCE BIT AND THIS LATCH"),
    # SPLIT ON PURPOSE: this row's own source line must not contain the literal
    # it forbids, or the file would always fail its own check.
    ("test",
     "arriving at ANY later time still " + "reaches its normal branches",
     "WITHIN THE BOUND, " + "which is the"),
)


def _r7_claim_source(name):
    if name == "test":
        return pathlib.Path(__file__).read_text(encoding="utf-8")
    return _src(name)


def test_r7_b16_the_claims_check_rejects_every_superseded_form():
    """B16: NO LINE CLAIMS MORE THAN IT MEASURED, held as a SURFACE.

    Every sentence this round corrected is bound here in one table: its
    superseded form must be absent and its corrected form present.  Round 6 fell
    on six separate comments, one at a time; a per-sentence check would have to
    be remembered six more times.  This one reddens if any of them regresses."""
    for name, superseded, corrected in _R7_CLAIMS:
        src = _r7_claim_source(name)
        assert superseded not in src, (
            "%s: the superseded claim returned: %r" % (name, superseded))
        assert corrected in src, (
            "%s: the corrected claim is missing: %r" % (name, corrected))

    # L8 also carries the contract's bound sentence verbatim in that docstring
    harness = _r7_claim_source("test")
    i = harness.find("def test_r4_h3_a_fallback_report_carries_is_fallback")
    doc = harness[i:i + 2400]
    assert " ".join(_R7_BOUND_SENTENCE.split()) in " ".join(doc.split())

    # THE CONTROL: the check must be able to fail on EACH row, not merely exist.
    # Re-running the table against a source with one superseded form reinstated
    # has to reject that row.
    def row_holds(src, superseded, corrected):
        return superseded not in src and corrected in src

    for name, superseded, corrected in _R7_CLAIMS:
        src = _r7_claim_source(name)
        assert row_holds(src, superseded, corrected), name
        # negate: put the superseded form back
        assert not row_holds(src + "\n// " + superseded + "\n", superseded, corrected), (
            "%s: the check accepts the superseded form" % name)
        # negate: drop the corrected form
        # EVERY occurrence: this harness carries the corrected form twice -- once
        # in the claim it makes and once in this table -- and removing only the
        # first leaves the row green for a reason that is not the claim (#342).
        assert not row_holds(src.replace(corrected, ""), superseded, corrected), (
            "%s: the check accepts the corrected form's removal" % name)
        # INERT TWIN: an unrelated edit of the same shape leaves the row green
        assert row_holds(src + "\n// an unrelated comment line\n",
                         superseded, corrected), name


# ── ROUND 7, COLD LENS: four cases the round-7 pass itself introduced ───────
# Three of these are the same defect the round closed elsewhere, reappearing in
# the prose and the checks the round WROTE: a sentence that reads one exit of a
# route as a property of the route, a key that omits the one input that is not
# a field, and a census whose grep cannot match the operation it is quoted for.
# That is the expected place to find them (#351 -- re-read the comments your own
# fix authored), not a sign the method is wrong.


def test_r7cl_c1_w8_names_the_three_exits_that_precede_the_park():
    """C1: the arming line states what the route GUARANTEES, not one of its exits.

    W8's round-7 wording said "the route this client is built against PARKS it
    -- it marks the row and answers deferred=true before any total is read",
    as a flat property of that route.  On the frozen server representation the
    park is reached only past three earlier exits, none of which reads a total
    and none of which parks anything: a row already settled, a report naming a
    room the series does not own, and a roomless report inside the post-resume
    window.  Contract item 6 names exactly those three as exits that decide
    nothing and say so with `ignored` true beside `deferred` false.

    WHY IT MATTERS TO A READER OF A BUNDLE.  A survivor's fallback arms, this
    line is written, and the report then meets the settled-row exit: nothing is
    stamped, no window opens, and the status route answers `dc_deferred=false`
    for the rest of the series' life.  Triage that believes the arming line
    looks for a deferral marker and a sweep tick that never existed and
    attributes the outcome to the sweep.

    THE SERVER HALF IS READ, NOT ASSERTED: the three exits are located in the
    frozen representation and each is required to precede the park."""
    ra = _src("RoomActors.cs")
    assert "the park is ONE ANSWER AMONG SEVERAL, not a property " in ra
    assert "client is built against PARKS it" not in ra
    # the line names all three, and names what they answer
    for phrase in ("a row already settled",
                   "a report naming a room this ",
                   "a roomless report inside the post-resume window",
                   "ignored=true beside deferred=false"):
        assert phrase in ra, phrase

    # CROSS-LANE: the three exits exist on the reviewed route and every one of
    # them is reached BEFORE the park.
    server, how = _server_lane_main()
    assert server, how
    assert _frozen_identity_holds(how), (
        "the cross-lane equality was resolved from something other than "
        "the hash-verified extract: " + how)
    i = server.find("async def report_team_dc")
    if i < 0:
        i = server.find('@app.post("/api/v1/team/series/{series_id}/report-dc"')
    assert i > 0, "the report-dc handler could not be found on the server lane"
    handler = server[i:]
    park = handler.find("if is_fallback:")
    assert park > 0, "the handler carries no is_fallback park"
    for exit_text in ('"ignored": True, "deferred": False',
                      '"reason": "dc_room_mismatch"',
                      '"reason": "dc_after_resume"'):
        k = handler.find(exit_text)
        assert 0 < k < park, (
            exit_text + " is not an exit reached before the park")

    def claim(s):
        return ("the park is ONE ANSWER AMONG SEVERAL, not a property " in s
                and "client is built against PARKS it" not in s)

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "the park is ONE ANSWER AMONG SEVERAL, not a property ",
                "client is built against PARKS it, and that is a property ",
                "R7CL-C1 W8 reclaims the park as a property of the route"),
        "R7CL-C1 W8 names the three exits that precede the park")
    # INERT TWIN: the sentence around it reworded, the claim intact
    assert claim(_mutate(ra, "and is read out of the answer, never assumed",
                         "and is read out of that answer, never assumed",
                         "R7CL-C1 inert twin"))


def test_r7cl_c2_the_render_key_carries_the_dark_latch():
    """C2: the key is the WHOLE input set, and the latch is part of it.

    The render predicate is `cacheIsThisSeries && !latchedDark && dc_deferred`.
    The round-7 key read the fields and not the latch, because the latch is the
    one input that is a SET: a census of assignments cannot see it, so nothing
    put it on the list.  The two halves of the refusal branch then came apart --
    the latch add is unconditional, the clear beneath it is confined to the
    cached series -- so a refusal for a series the cache does not describe
    changed what the banner reads while no keyed field moved, and the repaint
    the same branch asks for was asked for on an unchanged key.

    THE FAILING SEQUENCE IS ORDINARY, not contrived: a slow status answer for a
    previous series stamps the cache with that series' id, the seat adopts a new
    one, and the new series' read is then refused during an outage.  The off
    witness keeps printing the cache-mismatch reason and never records that the
    read was latched -- and the witness line is the acceptance signal this
    feature emits (#438).

    WHAT IS ASSERTED: the key asks the latch about the ACTIVE series, which is
    the same question the render asks; the latch add really is unconditional,
    which is what makes the omission reachable; and the clear really is
    confined, which is what makes the two come apart."""
    api = _src("ApiClient.cs")
    key = _method_body(api, "private static string BannerRenderKey")
    assert key, "the render key could not be delimited"
    assert "SeriesStatusLatchedDark(activeTeamSeriesId)" in key

    poller = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    add = poller.find("_statusPollDarkSeries.Add(seriesId);")
    clear = poller.find("if (LastSeriesStateForId == seriesId)")
    assert 0 < add < clear, (
        "the latch add and the confined clear are not in the order this case "
        "is about")
    # the add is NOT inside the confined block -- that asymmetry is the defect
    assert "if (LastSeriesStateForId == seriesId)" not in poller[:add]

    def claim(s):
        b = _method_body(s, "private static string BannerRenderKey")
        return bool(b) and "SeriesStatusLatchedDark(activeTeamSeriesId)" in b

    _assert_discriminating(
        claim, api,
        _mutate(api,
                '+ "|" + (SeriesStatusLatchedDark(activeTeamSeriesId) ? "d" : "-")',
                '+ "|" + "-"',
                "R7CL-C2 the key drops the latch"),
        "R7CL-C2 the render key carries the dark latch")
    # INERT TWIN: the key's separator prose changes, the latch term stays
    assert claim(_mutate(api,
                         '+ "|" + (LastSeriesDcDeferredFieldsPresent ? "p" : "-")',
                         '+ "|" + (LastSeriesDcDeferredFieldsPresent ? "P" : "-")',
                         "R7CL-C2 inert twin"))


def test_r7cl_c3_the_refusal_clears_the_presence_bit_with_the_numbers():
    """C3: no cache state that no answer can produce.

    The id setter clears the presence bit beside the three numbers, under the
    stated reason that leaving it set says the previous series' answer carried
    the deferral state about a series whose numbers were just cleared.  The
    refusal path cleared the same three numbers for the same series and left the
    bit standing, so after a refusal the cache read deferred=false /
    remaining=0 / bound=0 with present=true -- a combination no answer produces.

    It is masked today, and that is the point: the witness tests its
    latched-dark arm before its presence arm, so the false bit never reaches the
    off text.  Reorder those arms, or give the per-series latch a reset -- the
    tree has no writer that removes from the set -- and the witness prints "the
    last answer for this series carried dc_deferred=false" about a series whose
    last answer was not an answer at all.  That is the denial-nobody-made the L6
    to L11 group exists to remove, so it is closed at the writer rather than
    left standing behind the arm order."""
    api = _src("ApiClient.cs")
    poller = _method_body(api, "public static void PollTeamSeriesStatusReadOnly")
    i = poller.find("if (LastSeriesStateForId == seriesId)")
    assert i > 0
    block = poller[i:poller.index("}", poller.index("{", i)) + 1]
    for name in ("LastSeriesDcDeferred = false;",
                 "LastSeriesDcDeferredSecondsRemaining = 0;",
                 "LastSeriesDcDeferredBoundSeconds = 0;",
                 "LastSeriesDcDeferredFieldsPresent = false;"):
        assert name in block, name

    # the id setter -- the other writer of the same cache -- clears the same
    # four, so the two writers agree about what the cache means
    setter = _r7_setter_span(api)
    for name in ("LastSeriesDcDeferred = false;",
                 "LastSeriesDcDeferredFieldsPresent = false;"):
        assert name in setter, name

    def claim(s):
        b = _method_body(s, "public static void PollTeamSeriesStatusReadOnly")
        j = b.find("if (LastSeriesStateForId == seriesId)")
        if j < 0:
            return False
        blk = b[j:b.index("}", b.index("{", j)) + 1]
        return "LastSeriesDcDeferredFieldsPresent = false;" in blk

    _assert_discriminating(
        claim, api,
        _mutate(api,
                "                            LastSeriesDcDeferredFieldsPresent = false;" + LF
                + "                        }",
                "                        }",
                "R7CL-C3 the refusal leaves the presence bit standing"),
        "R7CL-C3 the refusal clears the presence bit with the numbers")
    # INERT TWIN: the bound field's clear is respelled, the presence clear stays
    assert claim(_mutate(api,
                         "                            LastSeriesDcDeferredBoundSeconds = 0;",
                         "                            LastSeriesDcDeferredBoundSeconds = 0;  // bound",
                         "R7CL-C3 inert twin"))


def test_r7cl_c4_the_banner_input_census_sees_every_write_form_and_every_source():
    """C4: the census is as wide as the claim it is quoted for.

    The round-7 census is described as "a grep census of the OPERATION" and as
    covering "every assignment to a banner input".  Its regex anchored on
    `^\\s*Name =` and it scanned ApiClient.cs alone, so a compound write, a
    null-coalescing write, an increment, and any writer in another plugin source
    -- the fields are `public static` -- all fell outside it.  None existed on
    the tree, which is exactly how a check certifies a class it cannot see
    (#342, #441).

    EACH SHAPE IS PLANTED AND THE CENSUS MUST FIND IT, and four comparisons are
    planted and it must NOT: a grep widened until it matches everything is the
    same failure from the other side."""
    sources = _r7_plugin_sources()
    assert len(sources) > 3, sorted(sources)
    base = len(_r7_writer_lines(sources))
    assert base, "the census cannot be empty"

    for label, fname, line in (
            ("a compound write", "ApiClient.cs",
             "                LastSeriesT1Wins += 1;"),
            ("a null-coalescing write", "ApiClient.cs",
             "                LastSeriesStateForId ??= seriesId;"),
            ("a post-increment", "ApiClient.cs",
             "                LastSeriesT2Wins++;"),
            ("a pre-increment", "ApiClient.cs",
             "                ++LastSeriesT2Wins;"),
            ("a writer in another source", "NativeUI.cs",
             "                ApiClient.LastSeriesT1Wins = 0;"),
            ("a writer in a third source", "Plugin.cs",
             "                ApiClient.LastSeriesDcDeferred = true;"),
            ("a write of the latch set", "ApiClient.cs",
             "                _statusPollDarkSeries.Remove(seriesId);")):
        planted = dict(sources)
        planted[fname] = planted[fname] + LF + line + LF
        assert len(_r7_writer_lines(planted)) == base + 1, (
            "the census did not see " + label)

    for line in ("                if (LastSeriesT1Wins == 0) return;",
                 "                if (LastSeriesT1Wins >= 3) return;",
                 "                if (LastSeriesT2Wins != 0) return;",
                 "                if (LastSeriesT1Wins <= 0) return;",
                 "                int n = LastSeriesT1Wins;",
                 "                bool d = _statusPollDarkSeries.Contains(s);"):
        planted = dict(sources)
        planted["ApiClient.cs"] = planted["ApiClient.cs"] + LF + line + LF
        assert len(_r7_writer_lines(planted)) == base, (
            "the census read a read as a write: " + line.strip())

    # AND THE FILE SET IS RESOLVED, not listed: a new source joins by existing.
    import inspect
    assert 'PLUGIN.glob("*.cs")' in inspect.getsource(_r7_plugin_sources)


# ── B18, RE-EXECUTED RATHER THAN INHERITED (#308) ──────────────────────────
# Round 6 reported B18 MET on prose alone: two canonicals read as identical and
# a configuration read as unchanged.  A row whose evidence is a careful reading
# is the defect L1 named one row over, so the row now has a check that can go
# red, on both lanes and on the build configuration.
_R7_B18_DC_SKELETON = "{}:{}:{}:dc"


def _r7_skeleton(expr):
    """An interpolated string with every placeholder reduced to `{}`.

    The two lanes spell the same four fields with different identifiers --
    `reporterSteamId` here, `steam_id` there -- so comparing the raw strings
    would compare naming conventions.  What the wire contract fixes is the
    ORDER and the COUNT of the parts and the literal tail, and that is what
    survives this reduction."""
    return re.sub(r"\{[^{}]*\}", "{}", expr)


def _r7_b18_client_canonicals(api):
    return [m for m in re.findall(r'ComputeHmacHex\(\$"([^"]*)"\)', api)
            if m.endswith(":dc")]


def _r7_b18_server_canonicals(server):
    return re.findall(r'f"([^"]*:dc)"\.encode\(\)', server)


def test_r7_b18_the_dc_canonical_is_one_contract_on_both_lanes_and_the_build_gate_stands():
    """B18: the frozen DC canonical, and the two csproj properties that keep a
    workstation path out of the shipped assembly.

    THREE CLAIMS, EACH WITH ITS OWN NEGATIVE CONTROL INSIDE THIS TEST:

      * the client signs the DC report over the four-field canonical, in
        EXACTLY ONE place -- a second signing site is how the two ends come to
        disagree one release later;
      * the SERVER LANE's own copy reduces to the same skeleton, read out of
        that tree rather than described from this one (#341, #444, #635: two
        halves of one contract are grepped for the same literals);
      * the csproj still carries `DebugType=none` and `Deterministic`, which
        are what keep the build from embedding a local path in every release
        assembly.  Nothing in the pre-commit privacy guard validates them, so a
        check is the only thing that would notice their removal.

    The three controls below each remove ONE of the three and require the claim
    to go False, so a pass here is a statement about all three rather than
    about whichever one happened to hold."""
    api = _src("ApiClient.cs")
    server, how = _server_lane_main()
    assert server, (
        "the server representation could not be resolved, so the cross-lane half "
        "of this claim was not checked: " + how)
    assert _frozen_identity_holds(how), (
        "the cross-lane equality was resolved from something other than "
        "the hash-verified extract: " + how)
    csproj = (PLUGIN / "CompetitiveRounds.csproj").read_text(encoding="utf-8")

    def claim(api_text, server_text, csproj_text):
        c = _r7_b18_client_canonicals(api_text)
        if len(c) != 1 or _r7_skeleton(c[0]) != _R7_B18_DC_SKELETON:
            return False
        s = _r7_b18_server_canonicals(server_text)
        if len(s) != 1 or _r7_skeleton(s[0]) != _R7_B18_DC_SKELETON:
            return False
        return ("<DebugType>none</DebugType>" in csproj_text
                and "<Deterministic>true</Deterministic>" in csproj_text)

    assert claim(api, server, csproj), (
        "client canonicals: %r; server canonicals: %r"
        % (_r7_b18_client_canonicals(api), _r7_b18_server_canonicals(server)))

    # CONTROL 1 -- a fifth field on the client half
    bad_api = api.replace(
        'ComputeHmacHex($"{reporterSteamId}:{seriesId}:{dcPlayerSteamId}:dc")',
        'ComputeHmacHex($"{reporterSteamId}:{seriesId}:{dcPlayerSteamId}:{roomId}:dc")',
        1)
    assert bad_api != api, "the client signing site's spelling moved"
    assert not claim(bad_api, server, csproj), (
        "the claim survives a fifth field on the client half")

    # CONTROL 2 -- the same fifth field on the SERVER half.  This is the one a
    # lane reading only its own source cannot see.
    bad_server = re.sub(r'f"([^"]*):dc"\.encode\(\)',
                        r'f"\1:{room_id}:dc".encode()', server, count=1)
    assert bad_server != server, "the server signing site's spelling moved"
    assert not claim(api, bad_server, csproj), (
        "the claim survives a fifth field on the server half")

    # CONTROL 3 -- the build gate
    assert not claim(api, server,
                     csproj.replace("<DebugType>none</DebugType>", "", 1)), (
        "the claim survives the removal of DebugType=none")

    # AND THE INERT TWIN: an edit of the same shape that changes none of the
    # three leaves the claim true, so a red above is about the canonical and the
    # gate rather than about any edit at all.
    assert claim(api + LF + "// an unrelated comment line" + LF,
                 server + LF + "# an unrelated comment line" + LF,
                 csproj + LF + "<!-- an unrelated comment -->" + LF)


# ══ ROUND 8: the eleven LOW findings of the round-7 review, by number ════════


# L3: THE FIVE DELETED MECHANISM CLASSES, plus the retired statics and the dead
# predicate, as REJECTION CLASSES over the whole plugin source.  Round 7 swept
# four capability tokens over every source but checked the retired statics in
# two files and the dead predicate in one, so a re-introduction anywhere else
# was not rejected.  Each row is (class name, kind, needles).
_R8_DELETED_CLASSES = (
    ("the lifecycle=false arm", "token", ("lifecycle=false",)),
    ("the advertised capability field", "token",
     ("ServerHasReadOnlySeriesStatus",)),
    ("the client parse of the lifecycle key", "token", ('"lifecycle"',)),
    ("the echoed capability key", "token", ("series_status_readonly",)),
    # The W20/W24 latch is the client-side memory of that advertisement, and it
    # is rejected under every name a re-introduction would carry rather than
    # under the one spelling it happened to have -- a flag names a LINE, the
    # defect is a CLASS (#432).  These are mechanism-specific identifiers, not
    # common words, so the rule can still fail (#342, #431).
    ("the W20/W24 capability latch", "token",
     ("HasReadOnlySeriesStatus", "ReadOnlySeriesStatusAdvertised",
      "SeriesStatusCapability")),
    ("the retired dc-grace statics", "token",
     ("LastSeriesDcGraceSeconds", "LastSeriesDcTeamRemaining")),
    # The dead predicate is rejected as CODE, not as a word: `dc_paused` is a
    # server status value this client still NAMES in prose and in one log line
    # that lists the statuses the route accepts, and a rule that rejected the
    # word would reject those too -- and would then be relaxed by the next
    # reader.  What may not return is the COMPARISON.
    ("the dead dc_paused predicate", "code",
     ('== "dc_paused"', '!= "dc_paused"', '.Equals("dc_paused"',
      '"dc_paused" ==', '"dc_paused".Equals')),
)


def _r8_is_comment(line):
    t = line.strip()
    return t.startswith("//") or t.startswith("/*") or t.startswith("*")


def _r8_deleted_class_hits(sources):
    """[(class, file, line no, text)] for every re-introduction in `sources`.

    `sources` is a {name: text} map so a control can plant a re-introduction in
    a file that does not exist on the tree without touching the tree -- and so
    a control can hand in ONE file, which is what keeps a whole-suite mutation
    run affordable.

    ONE PASS OVER THE LINES, every class at once: the sweep covers every plugin
    source and this suite is re-run once per mutation control."""
    hits = []
    for fname in sorted(sources):
        for i, line in enumerate(sources[fname].split(LF), 1):
            comment = _r8_is_comment(line)
            for cls, kind, needles in _R8_DELETED_CLASSES:
                if kind == "code" and comment:
                    continue
                for needle in needles:
                    if needle in line:
                        hits.append((cls, fname, i, line.strip()))
                        break
    return hits


def test_r8_l3_every_deleted_mechanism_class_is_rejected_across_the_whole_plugin_source():
    """L3 (B10): THE DELETIONS ARE A CLASS, AND THE SWEEP IS THE WHOLE SOURCE.

    WHAT WAS WRONG.  `test_r5_the_advertised_capability_is_absent_from_every_source`
    swept every plugin source, but for four capability/query tokens only; the
    retired statics were checked in ApiClient.cs and NativeUI.cs, and the dead
    `dc_paused` predicate in NativeUI.cs.  A retired static reappearing in
    Plugin.cs, or the predicate reappearing in any third file, was outside every
    check.  A flag names a LINE while the defect is a CLASS (#432, #330).

    WHAT THIS DOES.  Seven named rejection classes -- the five the contract
    deletes, plus the retired statics and the dead predicate -- swept over EVERY
    `.cs` under the plugin, resolved by glob so a new file joins by existing.
    The scanned COUNT and the file list are printed, because a sweep whose
    listing could have been truncated proves nothing about what it did not
    cover (#304, #205).

    The predicate class rejects the COMPARISON rather than the word: this client
    still names `dc_paused` in the prose that records why the predicate went and
    in one log line that lists the statuses the route accepts, and a rule that
    rejected those would be relaxed by the next reader rather than obeyed."""
    sources = _r7_plugin_sources()
    names = sorted(sources)
    print("L3 DELETION SWEEP: %d plugin sources scanned" % len(names))
    print("L3 DELETION SWEEP FILES: " + ", ".join(names))
    print("L3 DELETION SWEEP CLASSES: %d" % len(_R8_DELETED_CLASSES))

    # the file set is the glob's, not a list that could have gone stale
    on_disk = sorted(p.name for p in PLUGIN.glob("*.cs"))
    assert names == on_disk, (names, on_disk)
    assert len(names) > 3, names

    hits = _r8_deleted_class_hits(sources)
    assert not hits, ("a deleted mechanism was found in plugin source: "
                      + repr(hits))

    # EVERY CLASS CAN FIRE, and it fires in a file neither round-7 check read.
    # The scratch source is a THIRD file, handed in through the map rather than
    # written to the tree, so nothing has to be restored afterwards.
    for cls, kind, needles in _R8_DELETED_CLASSES:
        for needle in needles:
            if kind == "code":
                if needle.startswith("==") or needle.startswith("!="):
                    line = "                if (dcStatus " + needle + " true) { }"
                else:
                    line = "                if (dcStatus" + needle + ")) { }"
            else:
                line = "                // reintroduced: " + needle
            # THE SCRATCH SOURCE ALONE.  The rule is a pure function of the map
            # it is handed, and re-sweeping 94 unchanged files once per needle
            # buys nothing the assertion above has not already bought -- while
            # this suite is re-run once per mutation control.
            planted = {"ZzScratchProbe.cs": ("class ZzScratchProbe {" + LF
                                             + line + LF + "}" + LF)}
            got = _r8_deleted_class_hits(planted)
            assert any(h[0] == cls and h[1] == "ZzScratchProbe.cs" for h in got), (
                "the sweep did not reject " + cls + " via " + repr(needle))

    # AND THE PREDICATE CLASS DOES NOT FIRE ON PROSE OR ON THE STATUS LIST --
    # the inert twin, in the same file, of a shape the rule permits.
    for permitted in ('                // the old predicate compared == "dc_paused"',
                      '                /// a cached status of dc_paused is a guess',
                      '                Log("statuses (active, dc_paused) are accepted");'):
        planted = {"ZzScratchProbe.cs": ("class ZzScratchProbe {" + LF
                                         + permitted + LF + "}" + LF)}
        assert not _r8_deleted_class_hits(planted), (
            "the sweep rejected a permitted line: " + permitted.strip())

    # and an identifier of a similar shape that the rule permits
    planted = {"ZzScratchProbe.cs": (
        "class ZzScratchProbe {" + LF
        + "                public static int LastSeriesDcDeferredBoundSeconds2 = 0;" + LF
        + "}" + LF)}
    assert not _r8_deleted_class_hits(planted), "the sweep rejected a permitted identifier"


# L8: the item-6 claim surface, over every source this lane delivers from the
# worktree -- the plugin files AND this harness.  The tool prose the bundle
# delivers is outside the worktree and is covered by the round-8 notes checker,
# which reads the bundle; that split is recorded in the notes.
def _r8_claim_scope():
    """{name: text} for every file this lane delivers from the worktree.

    THE ROUND-8 SCOPE SAID `every source this lane delivers` WHILE MEANING THE
    PLUGIN SOURCES AND THIS FILE.  The two data files beside this harness --
    the sealed server-lane extract and its provenance record -- are tracked,
    are delivered, and carry prose a reader acts on; the extract's own header
    is where the round-7 mechanism survived in words after the code dropped it.
    A scope that names everything and reaches a subset is the gap the claim
    check exists to close, so they are IN, and the docstring now says what the
    dictionary holds."""
    out = dict(_r7_plugin_sources())
    out["test_sept16_client_r2.py"] = pathlib.Path(__file__).read_text(
        encoding="utf-8")
    for p in (_FROZEN_SERVER_EXTRACT, _FROZEN_PROVENANCE):
        out[p.name] = p.read_text(encoding="utf-8")
    return out


def test_r8_l8_no_delivered_source_claims_a_pre_field_200_settles():
    """L8 (B16, B11): THE CHECK'S SOURCE SCOPE IS EVERY SOURCE IT SPEAKS FOR.

    WHAT WAS WRONG.  The SERVER-L3 check scanned `ApiClient.cs`, and the
    `_R7_CLAIMS` row that binds this form scoped it to `ApiClient.cs` as well --
    while the harness's OWN docstring, at the `is_fallback` case, said an older
    box answers 200 and that the report then settles at once.  The product
    rejected the claim and the file checking the product made it.  The
    superseded wording is not spelled out here either: this case's scope covers
    this file, so a source carrying the form would reject itself.  That is the surviving class of SERVER-L3 and SERVER-B0c, and it is
    exactly where #351 says to look: in the prose the fix itself authored.

    WHAT CONTRACT ITEM 6 PERMITS.  `deferred` says only whether THIS call parked
    the report.  A response that carries no `deferred` at all proves only that
    the box which answered predates the field; it never proves settlement.

    WHAT THIS REJECTS.  The superseded FORM, in every source this harness can
    reach -- every plugin `.cs` and this file -- rather than a heading or a file
    name.  The forms are assembled from pieces so this file does not carry them
    contiguously and cannot reject itself."""
    scope = _r8_claim_scope()
    names = sorted(scope)
    print("L8 CLAIM SCOPE: %d sources" % len(names))
    print("L8 CLAIM SCOPE FILES: " + ", ".join(names))
    assert "test_sept16_client_r2.py" in scope
    assert "ApiClient.cs" in scope
    assert len(names) > 3, names

    def offenders(sources):
        out = []
        for fname in sorted(sources):
            for form in _R7_PRE_FIELD_SETTLEMENT_FORMS:
                if form in sources[fname]:
                    out.append((fname, form))
        return out

    assert not offenders(scope), (
        "a superseded item-6 settlement claim survives: " + repr(offenders(scope)))

    # THE CORRECTED FORM IS PRESENT where the claim used to be made -- an
    # absence alone holds on a stub, which is the check that cannot fail (#342).
    assert ("THAT 200 PROVES ONLY THAT THE BOX WHICH" + LF
            + "    ANSWERED PREDATES THE FIELD") in scope["test_sept16_client_r2.py"]
    assert "predates the field. It is not proof that the report settled" in         scope["ApiClient.cs"]

    # ONE RED PER SOURCE KIND, planted through the map so no file is touched:
    # the harness itself, and a plugin file that is NOT ApiClient.cs -- the two
    # places the round-7 scope could not see.
    for fname in ("test_sept16_client_r2.py", "NativeUI.cs", "Plugin.cs"):
        for form in _R7_PRE_FIELD_SETTLEMENT_FORMS:
            planted = dict(scope)
            planted[fname] = planted[fname] + LF + "// " + form + LF
            got = offenders(planted)
            assert (fname, form) in got, (
                "the claim check does not reach " + fname)

    # INERT TWIN: the contract meaning stated in different words, in the same
    # files, leaves the check green.
    twin = dict(scope)
    for fname in ("test_sept16_client_r2.py", "NativeUI.cs", "Plugin.cs"):
        twin[fname] = twin[fname] + LF + (
            "// a 200 from a box with no deferral field tells this client the "
            "box's age and nothing about the row" + LF)
    assert not offenders(twin), "the check rejected a correct restatement"


# L11: the census, and the root narrowing beneath it.
def test_r8_l11_the_census_sees_every_csharp_write_form():
    """L11 (B19, the surviving class of C4): A CENSUS IS AS WIDE AS ITS GREP.

    WHAT WAS WRONG.  The census recognised plain and compound assignment,
    `++`/`--`, `??=` and the latch's HashSet methods.  It did not recognise a
    field passed by REFERENCE, so `Interlocked.Increment(ref ApiClient.LastSeriesT1Wins)`
    -- a valid writer while the field was `public static`, which
    `ApiClient.cs:13945` made it -- changed a banner input invisibly, and the
    round-7 controls planted no such form.

    WHAT THIS ASSERTS.  Every write form is planted at a real site that does NOT
    request the repaint, and the census must see each one; the reads planted
    beside them must not be counted, because a grep widened until it matches
    everything fails the same way from the other side (#441)."""
    sources = _r7_plugin_sources()
    base = len(_r7_writer_lines(sources))
    assert base, "the census cannot be empty"
    print("L11 CENSUS: %d plugin sources, %d writer lines on the tree"
          % (len(sources), base))

    for label, fname, line in (
            ("an API-mediated write through ref", "ApiClient.cs",
             "                Interlocked.Increment(ref ApiClient.LastSeriesT1Wins);"),
            ("a volatile write through ref", "NativeUI.cs",
             "                Volatile.Write(ref ApiClient.LastSeriesT2Wins, 3);"),
            ("a ref argument", "Plugin.cs",
             "                Helper(ref ApiClient.LastSeriesDcDeferredBoundSeconds);"),
            ("an out argument", "ApiClient.cs",
             "                TryRead(out LastSeriesStateForId);"),
            ("a null-coalescing write", "ApiClient.cs",
             "                LastSeriesStateForId ??= seriesId;"),
            ("a compound write", "ApiClient.cs",
             "                LastSeriesT1Wins += 1;"),
            ("a post-increment", "ApiClient.cs",
             "                LastSeriesT2Wins++;"),
            ("a pre-increment", "ApiClient.cs",
             "                ++LastSeriesT2Wins;"),
            ("a write of the latch set", "ApiClient.cs",
             "                _statusPollDarkSeries.Remove(seriesId);")):
        planted = dict(sources)
        planted[fname] = planted[fname] + LF + line + LF
        assert len(_r7_writer_lines(planted)) == base + 1, (
            "the census did not see " + label)

    # THE TWINS: a `ref`/`out` that passes some OTHER variable while reading a
    # banner input is not a writer, and neither is any comparison.
    for line in (
            "                Interlocked.Exchange(ref copy, LastSeriesT1Wins);",
            "                TryParse(s, out local) ; int n = LastSeriesT1Wins;",
            "                if (LastSeriesT1Wins == 0) return;",
            "                if (LastSeriesT1Wins >= 3) return;",
            "                if (LastSeriesT2Wins != 0) return;",
            "                if (LastSeriesT1Wins <= 0) return;",
            "                int n = LastSeriesT1Wins;",
            "                bool d = _statusPollDarkSeries.Contains(s);"):
        planted = dict(sources)
        planted["ApiClient.cs"] = planted["ApiClient.cs"] + LF + line + LF
        assert len(_r7_writer_lines(planted)) == base, (
            "the census read a read as a write: " + line.strip())

    # AND A WRITE INSIDE A PATH THAT DOES REQUEST THE REPAINT is seen by the
    # census and leaves the census RESULT green -- the twin at the level the
    # result is judged on.
    api = _src("ApiClient.cs")
    paths = _r7_repaint_paths(api)
    setter = paths["the ActiveTeamSeriesId setter"] if         "the ActiveTeamSeriesId setter" in paths else list(paths.values())[0]
    anchor = "                    LastSeriesT1Wins = 0;"
    assert anchor in setter, "the setter's own write could not be anchored"
    twinned = dict(sources)
    twinned["ApiClient.cs"] = api.replace(
        anchor, anchor + LF + "                    LastSeriesT2Wins += 0;", 1)
    writers = _r7_writer_lines(twinned)
    assert len(writers) == base + 1
    ps = _r7_repaint_paths(twinned["ApiClient.cs"])
    outside = [w for w in writers
               if w[0] != "ApiClient.cs"
               or not any(w[2] in span for span in ps.values())]
    assert not outside, ("a write inside a repaint path was counted outside it: "
                         + repr(outside))

    # the file set is resolved, not listed
    import inspect
    assert 'PLUGIN.glob("*.cs")' in inspect.getsource(_r7_plugin_sources)


def test_r8_l11_the_banner_inputs_are_not_publicly_writable():
    """L11's ROOT: the writable surface is narrowed, not only watched.

    A `public static` field is writable by every form C# has, from every source
    in the assembly, which is why the census had to be widened twice.  The
    banner's inputs are read from other sources -- NativeUI renders them,
    Plugin.cs gates on the cached id -- and written from none, so each is now
    `{ get; private set; }`.  A property cannot be passed by reference, so the
    `ref`/`out` and `Interlocked` forms stop COMPILING on these names rather
    than stopping being visible, and a writer added in another source is a
    compile error rather than a census miss.

    The census stays as wide as it was made: this narrows what it has to find
    and does not replace it, and one edit would undo the narrowing."""
    api = _src("ApiClient.cs")
    for name in ("LastSeriesT1Wins", "LastSeriesT2Wins", "LastSeriesDcDeferred",
                 "LastSeriesDcDeferredSecondsRemaining",
                 "LastSeriesDcDeferredBoundSeconds",
                 "LastSeriesDcDeferredFieldsPresent", "LastSeriesStateForId"):
        decl = [ln for ln in api.split(LF)
                if ln.strip().startswith("public static") and (" " + name + " ") in ln]
        assert len(decl) == 1, (name, decl)
        assert "{ get; private set; }" in decl[0], (name, decl[0])
    # the backing field of the id is private already
    assert "private static string activeTeamSeriesId;" in api

    # AND NO OTHER SOURCE WRITES ONE.  The census is the instrument; this is the
    # claim the narrowing makes, held over every plugin source.
    sources = _r7_plugin_sources()
    foreign = [w for w in _r7_writer_lines(sources) if w[0] != "ApiClient.cs"]
    assert not foreign, ("a banner input is written outside ApiClient.cs: "
                         + repr(foreign))
    print("L11 ROOT: 7 banner inputs declared with a private setter")

