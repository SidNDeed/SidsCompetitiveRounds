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
import bisect
import functools
import itertools
import os
import pathlib
import re
import unicodedata
import xml.etree.ElementTree as ET

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

        # arm (2): the floor election as the merged tree runs it,
        # DcReporterElection.ShouldReport (floor_rule below), with this seat's
        # own snapshot. This lane's own floor (the room-wide lowest id, plus the
        # L3 stand-down of a seat advertising the leaver's team) met the
        # v1.41.0 client lane's two-lowest floor in merge pass 1; see
        # test_l3_dc_team_seat_stands_down_when_another_is_eligible.
        peers = [(pp["uid"], _team(pp["team"])) for pp in seats if pp is not me]
        if floor_rule(my_val, _team(my_team), _team(dc_team), peers):
            posts.append((my_val, "REAL", "prompt"))
    return posts


def _team(t):
    return -1 if t is None else t


def floor_rule(my_val, my_team, dc_team, peers):
    """DcReporterElection.ShouldReport, transliterated (v1.41.0 merge pass 1,
    follow-up 6). `peers`: (uid or None, team or -1) for every other survivor.

    THE CONSISTENT VIEW first: both teams known, exactly two peers, every peer's
    uid readable and distinct (and not mine) and its team readable, and exactly
    one survivor advertising the leaver's team. There the seat advertising the
    leaver's team reports, and of the two advertising the other team only the
    lower id does. Everywhere else: the two lowest readable ids report (the
    floor) OR the team claim (teams unknown, or I look eligible and no lower
    peer shares my team)."""
    teams_known = dc_team >= 0 and my_team >= 0
    ids = [u for u, _t in peers]
    if (teams_known and len(peers) == 2 and None not in ids and my_val not in ids
            and len(set(ids)) == 2 and all(t >= 0 for _u, t in peers)
            and (my_team == dc_team) + [t for _u, t in peers].count(dc_team) == 1):
        if my_team == dc_team:
            return True
        return not any(u < my_val and t != dc_team for u, t in peers)
    lower = 0
    lowest_on_my_team = (not teams_known) or my_team != dc_team
    for u, t in peers:
        if u is None or u >= my_val:
            continue
        lower += 1
        if teams_known and lowest_on_my_team and t == my_team:
            lowest_on_my_team = False
    return lower < 2 or lowest_on_my_team


def lane_standdown_rule(my_val, my_team, dc_team, peers):
    """The negative control: floor_rule with this lane's first cut of the L3
    stand-down put back -- a seat advertising the leaver's team stands down
    whenever another survivor with a readable id looks eligible."""
    if dc_team >= 0 and my_team >= 0 and my_team == dc_team:
        if any(u is not None and t >= 0 and t != dc_team for u, t in peers):
            return False
    return floor_rule(my_val, my_team, dc_team, peers)


def _floor_sweep(rule):
    """DcReporterElection's sentinel sweep over `rule`: every leaver, every
    order of four ids, every t_id 0, 1 or unreadable, every u_id readable or
    not. Seats 0 and 1 really play on team 0, seats 2 and 3 on team 1; a report
    is ACCEPTED when its seat's real team is not the leaver's (the F6 gate).
    Returns (states, states with no accepted report, true-team states,
    true-team states whose accepted count is not exactly one), where a
    true-team state has every u_id readable and every t_id true or every one
    exchanged."""
    states = misses = true_states = true_not_one = 0
    for order in itertools.permutations((100, 200, 300, 400)):
        for adv in itertools.product((0, 1, None), repeat=4):
            real = (0, 0, 1, 1)
            same = all(adv[i] == real[i] for i in range(4))
            swapped = all(adv[i] == 1 - real[i] for i in range(4))
            for unreadable in range(16):
                uid = [None if (unreadable >> i) & 1 else order[i] for i in range(4)]
                for lv in range(4):
                    accepted = 0
                    for me in range(4):
                        if me == lv:
                            continue
                        peers = [(uid[o], _team(adv[o])) for o in range(4) if o not in (me, lv)]
                        if rule(order[me], _team(adv[me]), _team(adv[lv]), peers) and real[me] != real[lv]:
                            accepted += 1
                    states += 1
                    misses += accepted < 1
                    if unreadable == 0 and (same or swapped):
                        true_states += 1
                        true_not_one += accepted != 1
    return states, misses, true_states, true_not_one


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
    """L3 as the integrator ruled it in v1.41.0 merge pass 1 (follow-up 6).
    The requirement: at least one seat the server accepts always reports a
    2v2 disconnect, and when several seats are eligible exactly one of them
    does, the lowest Steam id (the project's reporter rule). So the stand-down
    belongs to an ELIGIBLE seat that is not the lowest eligible one.

    This test used to pin the lane's first cut, `if (teamsKnown && myTeam ==
    dcTeam && otherEligible) return;` in Plugin.cs: a seat advertising the
    leaver's team stood down whenever another survivor looked eligible. Beside
    the v1.41.0 lane's two-lowest floor that leaves states with NO accepted
    reporter (a wrong t_id makes the seat that stands down one of the two that
    stayed; that lane's round 3 finding 2), so that expectation is gone, and
    the negative control below is exactly that rule put back. The census arm's
    half of L3 is unchanged: with the split intact and every seat running the
    census, the DC-team survivor never posts."""
    src = _src("DcReporterElection.cs")

    def claim(s):
        return ("consistentView = ConsistentView(myVal, myTeam, dcTeam, peers, out lowerLooksEligible);" in s
                and "return myTeam == dcTeam || !lowerLooksEligible;" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "return myTeam == dcTeam || !lowerLooksEligible;",
                "return !lowerLooksEligible;", "L3 two-sided"),
        "L3 stand-down of an eligible seat that is not the lowest eligible one")
    plug = _src("Plugin.cs")
    assert "otherEligible" not in plug, "the unconditional stand-down is back in Plugin.cs"
    assert "out onFloor, out _, out consistentView)) return;" in plug

    # the model, over the sentinel's whole sweep: the ruled rule meets both
    # halves of the requirement ...
    states, misses, true_states, true_not_one = _floor_sweep(floor_rule)
    assert states == 124416 and true_states == 192, (states, true_states)
    assert misses == 0, ("states with no accepted reporter", misses)
    assert true_not_one == 0, ("true-team states without exactly one accepted", true_not_one)
    # ... and the unconditional stand-down put back is red: zero reporters.
    _s, lane_misses, _t, _n = _floor_sweep(lane_standdown_rule)
    assert lane_misses > 0, "the negative control no longer misses: the sweep proves nothing"
    # the named state: real teams {L=400, A=100} and {B=200, C=300}; A and C
    # advertise each other's teams, a clean 2/2 split that is wrong. The seat
    # advertising the leaver's team is C, one of the two that stayed.
    seats = [(100, 1), (200, 1), (300, 0)]              # A, B, C as advertised
    peers_of = lambda i: [(u, t) for j, (u, t) in enumerate(seats) if j != i]
    ruled = [u for i, (u, t) in enumerate(seats) if floor_rule(u, t, 0, peers_of(i))]
    lane = [u for i, (u, t) in enumerate(seats) if lane_standdown_rule(u, t, 0, peers_of(i))]
    assert ruled == [100, 300], ruled                  # A refused, C accepted
    assert lane == [100], lane                         # A alone: refused, zero accepted

    # the census arm: with the split intact the DC-team survivor never posts
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

    # every quorum in VanillaFixes, BY NAME (v1.41.0 merge pass 1, follow-up
    # 7). This lane's sweep moved the two it could see, the saw quorum and the
    # grow quorum. The v1.41.0 client lane had added a third it could not see,
    # the weapon-cooldown reset's AllFightersCapable, which follow-up 2 moved
    # to the replicated read. Each is asserted inside its own method, and the
    # file-wide count must equal the named sites, so a fourth quorum added
    # without a name here fails instead of being absorbed by a bare count.
    quorums = (
        ("internal static class SawTargetSync",
         "private static bool AllFightersCapable(out int fighterCount, out int missingActor)"),
        ("internal static class GrowNormalize",
         "private static bool Quorum(out bool allCap, out bool allRankedIntent,"),
        ("internal static class WeaponCooldownReset",
         "private static bool AllFightersCapable(out int fighterCount, out int missingActor)"),
    )
    for cls, sig in quorums:
        span = vf[vf.index(cls):]
        span = span[:span.index("\n    }\n")]
        assert span.count(sig) == 1, (cls, sig)
        body = span[span.index(sig):]
        body = body[:body.index("\n        }\n")]
        assert body.count("RoomActors.IsSpectatorReplicated(actor)") == 1, (cls, sig)
        assert "RoomActors.IsSpectator(" not in body, (cls, sig)
    assert vf.count("RoomActors.IsSpectatorReplicated(actor)") == len(quorums)
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
            # the rj-drift merge made the gate internal (the pre-join fence
            # applies the same test); exactly one declaration must exist
            sigs = [s + " static bool InIdleClientState" for s in ("private", "internal")
                    if s + " static bool InIdleClientState" in src]
            assert len(sigs) == 1, (cls, sigs)
            gate = _method_body(src, sigs[0])
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

    # the model of the same rule, including the three ways it must answer "".
    # It is DERIVED from the source (_r10_outcome_model), never typed here: the
    # hand-written model this replaced keyed on the first eight characters of
    # the series id and so certified the truncation it should have rejected
    # (per the round-9 review, R9-M1).
    outcome_of, why = _r10_outcome_model(ra)
    assert outcome_of is not None, why
    publish, why = _r10_publish_model(ra)
    assert publish is not None, why
    series = "abcdef12-1111-4111-8111-111111111111"
    previous = "99999999-1111-4111-8111-111111111111"
    assert outcome_of(publish(series, "ok"), series.upper()) == "ok"
    assert outcome_of(publish(previous, "ok"), series) == ""    # a previous series
    assert outcome_of(publish(series, "maybe"), series) == ""   # unrecognised
    assert outcome_of("", series) == ""
    # and the watch treats "" as NOT terminal while the seat is still present
    assert fallback(outcome_of(publish(previous, "no"), series), False) == "nothing"

    def claim(s):
        b = _method_body(s, "internal static string OutcomeOf(PhotonPlayer actor, string seriesId)")
        return bool(b) and "s.Substring(0, i), tag" in b

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "if (!string.Equals(s.Substring(0, i), tag, StringComparison.Ordinal)) return " + '""' + ";",
                "// any series' answer will do", "outcome scope"),
        "DC outcome series scope")


# ── R9-M1 (round 10): the cr_dcr key is the WHOLE series identity ──────────
#
# WHAT WAS WRONG.  Tag() kept the first eight characters of the normalized
# series id and OutcomeOf() compared only that, so two distinct ids sharing
# eight characters had one key: a value retained on the elected seat from the
# earlier series answered for the later one -- an old `ok` stood the watch down
# and an old `no` fired it.  The model in the test above keyed the same way
# (`series[:8].lower()`), so it certified the truncation instead of rejecting
# it.  Nothing on the server lane makes a shared prefix impossible: the frozen
# extract parses the id as a UUID, and parsing says nothing about generation.
#
# THE CHECK.  The key, the read and the publication are MODELLED FROM THE C#
# TEXT at run time.  Tag is walked statement by statement: each form the
# derivation recognises maps to one Python operation, and a form it does not
# recognise REFUSES rather than guessing, so a tag that truncates at a length
# the derivation reads (`.Substring(0, N)`, directly or behind a length test)
# reddens the scenario it breaks.  OutcomeOf and PublishOutcome are walked
# the same way, against the method's KNOWN SEQUENCE of statements (R10CL5,
# below): every statement of each is accounted for, and any statement outside
# that sequence -- a read whose key comparison is not ONE whole-key equality,
# a prefix pre-comparison, a reassignment that shortens the key after Tag --
# is refused, which fails every scenario closed.
_R10_TAG_SIG = "private static string Tag(string seriesId)"
_R10_OUTCOME_SIG = "internal static string OutcomeOf(PhotonPlayer actor, string seriesId)"
_R10_PUBLISH_SIG = "internal static void PublishOutcome(string seriesId, string outcome)"
_R10_OUTCOME_CONSTS = ("OutcomeSent", "OutcomeAnswered", "OutcomeFailed",
                       "OutcomeUnknown")
_R10_CHAIN_STEP = re.compile(
    r"\.(?:(Trim)\(\)|(ToLowerInvariant)\(\)|(ToUpperInvariant)\(\)"
    r"|Substring\(0,\s*(\d+)\)"
    r'|Replace\("((?:[^"\\]|\\.)*)",\s*"((?:[^"\\]|\\.)*)"\))')


def _r10_code_only(body):
    """A method's text with its // comments removed, one statement per `;`."""
    lines = [ln.split("//", 1)[0] for ln in body.split(LF)]
    return " ".join(" ".join(lines).split())


def _r10_chain(expr, env):
    """A Python function for `<name>(.step)*`, or (None, why)."""
    m = re.match(r"^([A-Za-z_]\w*)", expr)
    if m is None or m.group(1) not in env:
        return None, "the chain does not start at a known value: " + expr
    base = env[m.group(1)]
    steps, pos = [], m.end()
    while pos < len(expr):
        s = _R10_CHAIN_STEP.match(expr, pos)
        if s is None:
            return None, "an unrecognised step in: " + expr
        steps.append(s.groups())
        pos = s.end()

    def run(v):
        v = base(v)
        for trim, low, up, n, old, new in steps:
            if trim:
                v = v.strip()
            elif low:
                v = v.lower()
            elif up:
                v = v.upper()
            elif n is not None:
                v = v[:int(n)]
            else:
                v = v.replace(old, new)
        return v
    return run, ""


def _r10_tag_model(ra):
    """(tag function, why) derived from Tag's own text; (None, why) when any
    statement in it is not a form this derivation knows."""
    body = _method_body(ra, _R10_TAG_SIG)
    if not body:
        return None, "Tag's own text could not be delimited"
    code = _r10_code_only(body)
    inner = code[code.find("{") + 1:code.rfind("}")]
    env = {"seriesId": lambda v: v}
    guard = False
    result = None
    for stmt in [x.strip() for x in inner.split(";") if x.strip()]:
        if stmt == 'if (string.IsNullOrEmpty(seriesId)) return ""':
            guard = True
            continue
        m = re.match(r"^string\s+([A-Za-z_]\w*)\s*=\s*(.+)$", stmt)
        if m:
            fn, why = _r10_chain(m.group(2).strip(), env)
            if fn is None:
                return None, why
            env[m.group(1)] = fn
            continue
        m = re.match(r"^return\s+([A-Za-z_]\w*)\.Length\s*<=\s*(\d+)\s*\?\s*"
                     r"([A-Za-z_]\w*)\s*:\s*(.+)$", stmt)
        if m and m.group(1) == m.group(3) and m.group(1) in env:
            fn, why = _r10_chain(m.group(4).strip(), env)
            if fn is None:
                return None, why
            keep, cap, name = env[m.group(1)], int(m.group(2)), m.group(1)
            result = (lambda v, keep=keep, cap=cap, fn=fn:
                      keep(v) if len(keep(v)) <= cap else fn(v))
            continue
        m = re.match(r"^return\s+(.+)$", stmt)
        if m and result is None:
            fn, why = _r10_chain(m.group(1).strip(), env)
            if fn is None:
                return None, why
            result = fn
            continue
        return None, "a statement Tag carries that this derivation does not know: " + stmt
    if not guard or result is None:
        return None, "Tag lacks its empty-id guard or its return"
    return (lambda v, result=result: "" if not v else result(v)), ""


def _r10_outcome_tokens(ra):
    toks = {}
    for name in _R10_OUTCOME_CONSTS:
        m = re.search(r'internal const string ' + name + r' = "([^"]*)";', ra)
        if m is None:
            return None
        toks[name] = m.group(1)
    return toks


# ── R10CL5 (round-10 cold lens): EVERY statement of the read and of the
# publication is accounted for ───────────────────────────────────────────────
#
# WHAT WAS WRONG.  Round 10 walked Tag statement by statement, but judged
# OutcomeOf and PublishOutcome by the PRESENCE of a few known statements.  A
# statement placed after `string tag = Tag(seriesId);` that shortened the key
# again -- in the read, in the publication, or as a prefix pre-comparison
# before the whole-key equality -- left every presence check true, and the
# scenarios, built from the whole-id Tag, stayed green while the C# compared
# eight characters again.
#
# THE CHECK.  Each method's text is cut into statements and block braces by a
# small C# statement reader (comments dropped; string and character literals
# kept whole; a `;` or a brace outside parentheses ends a statement) and the
# sequence must equal the method's KNOWN SEQUENCE below, statement for
# statement, in order.  The freedoms are exactly two: the four outcome tokens
# may be listed in any order (the model reads them), and a LOG CALL may stand
# anywhere -- a `Plugin.Log.Log*` statement with no assignment, no increment,
# no `ref` or `out` argument, and no nested call, object creation or indexer
# in its arguments other than the allow-listed pure ones (R10-L3 and
# R11CL1, below, which also say what that reading does not see).
# Any other statement is REFUSED, and a refusal fails every scenario closed.
#
# R10-L2 (round-10 review) -- THE SPLIT IS AT THE LAST COLON, AND ONLY THERE.
# Round 10 modelled either split as a freedom: `LastIndexOf` or `IndexOf`,
# the model reading which.  The whole series id is the key (R9-M1) and the
# read must recover it exactly as it was published, so the value is split at
# its LAST colon; a first-colon split takes a shorter key whenever the id
# carries a colon, which is the truncation class R9-M1 closed.  The
# first-colon statement is therefore a REFUSED statement, not a modelled one,
# and `test_r11_l2_...` proves it with an identity carrying two colons, where
# the two split points select different keys.
_R10CL_LOG = re.compile(r"^Plugin\.Log\.Log(?:Info|Warning|Error)\((.*)\)$")
_R10CL_SPLIT = {"int i = s.LastIndexOf(':')": "last"}
# The round-10 table, kept ONLY so `test_r11_l2_...` can show that it
# ACCEPTED the first-colon statement; the walk reads it only when that test
# hands it in.
_R10CL_SPLIT_ROUND10 = {"int i = s.LastIndexOf(':')": "last",
                        "int i = s.IndexOf(':')": "first"}
_R10CL_TOKENS = re.compile(
    r'^return \(o == (\w+) \|\| o == (\w+) \|\| o == (\w+) \|\| o == (\w+)\) \? o : ""$')
_R10CL_OUTCOME_SEQ = (
    _R10_OUTCOME_SIG, "{", "try", "{",
    "string tag = Tag(seriesId)",
    'if (actor == null || tag.Length == 0) return ""',
    "var props = actor.CustomProperties",
    'if (props == null) return ""',
    "object v",
    'if (!props.TryGetValue(OutcomeProp, out v)) return ""',
    "string s = v as string",
    'if (string.IsNullOrEmpty(s)) return ""',
    "<split>",
    'if (i <= 0 || i + 1 >= s.Length) return ""',
    'if (!string.Equals(s.Substring(0, i), tag, StringComparison.Ordinal)) return ""',
    "string o = s.Substring(i + 1)",
    "<tokens>",
    "}", "catch", "{", 'return ""', "}", "}")
_R10CL_PUBLISH_SEQ = (
    _R10_PUBLISH_SIG, "{", "try", "{",
    "string tag = Tag(seriesId)",
    "if (tag.Length == 0 || string.IsNullOrEmpty(outcome)) return",
    "var local = PhotonNetwork.LocalPlayer",
    "if (local == null || !PhotonNetwork.InRoom) return",
    'local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable '
    '{ { OutcomeProp, tag + ":" + outcome } })',
    "}", "catch (Exception ex)", "{", "}", "}")


def _r10cl_statements(body):
    """[statement, or "{" / "}"] of one C# method's text: comments dropped,
    string and character literals kept whole, whitespace collapsed, and a `;`
    or a brace outside parentheses ending a statement."""
    out, cur, i, n, paren = [], [], 0, len(body), 0
    while i < n:
        ch = body[i]
        if body.startswith("//", i):
            j = body.find(LF, i)
            i = n if j < 0 else j
            continue
        if body.startswith("/*", i):
            j = body.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch in "\"'":
            j = i + 1
            while j < n and body[j] != ch:
                j += 2 if body[j] == "\\" else 1
            cur.append(body[i:j + 1])
            i = j + 1
            continue
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        if paren == 0 and ch in ";{}":
            s = " ".join("".join(cur).split())
            if s:
                out.append(s)
            if ch != ";":
                out.append(ch)
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    s = " ".join("".join(cur).split())
    if s:
        out.append(s)
    return out


# ── R10-L3 (round-10 review): a log call is exempt only when its ARGUMENTS
# call nothing this derivation cannot prove pure ──────────────────────────────
#
# WHAT WAS WRONG.  The exemption read the log statement's own top-level text:
# no `=`, no `++` or `--`, no `ref` or `out`.  A value-returning helper called
# INSIDE the arguments -- `Plugin.Log.LogInfo("x" + Clear())` -- was invisible
# to it, and a helper can change state (clear or rewrite OutcomeProp) as a
# side effect, so the walk set the whole statement aside.  Its literal
# blanking also blanked the holes of an interpolated string, so a call or an
# assignment written in `$"{...}"` was invisible as well.
#
# THE RULE.  The arguments are read by the C# lexer (`_cs_code_mask`): the
# text of every literal is blanked and every interpolation hole is kept as
# code.  In that code an invocation, an object creation, an indexer and the
# other forms named below disqualify the exemption, unless the invocation is
# one of the allow-listed PURE forms below -- compile-time operators and
# static string predicates whose result depends on their arguments alone.  A
# disqualified log call is not set aside: like any other statement it must be
# the next one the KNOWN SEQUENCE names, and no sequence names a log call, so
# it is REFUSED, naming the call.
#
# ROUND-11 COLD LENS (R11CL1, R11CL3) -- A CALL IS FOUND BY ITS PARENTHESIS,
# NOT BY A NAME.  The first reading of this round found a call only where a
# BARE name chain stood directly before `(`, so a call through `?.` or `!.`,
# a member of a parenthesised or called expression (`(tag).M()`,
# `nameof(a).M()`), a generic method with a nested argument list, and the
# invocation of a parenthesised expression (`(d)()`, `(x => x)(1)`,
# `((Func<string>)F)()`) were not seen, and the log call was set aside.  Now
# EVERY `(` in the code is judged by the character before it, spaces skipped
# (`_r11_opens_call`): after the end of an operand -- a letter, a digit or
# `_`, a `)`, a `]`, a `>`, or a null-forgiving `!` that itself follows one
# of those -- the `(` INVOKES what precedes it; after anything else (an
# operator, a `(`, a `,`, a `?`, or the start) it opens a grouping, a cast or
# a lambda's parameters, and the code inside it is read like the rest.  An
# invocation is pure only when the WHOLE text it invokes (`_r11_callee`:
# names, dots, `?`, `!` and balanced brackets, read back from the `(`) is an
# allow-listed name and no `.` stands before that text; so a member reached
# through any receiver that is not a bare name, the invocation of a
# parenthesised, indexed or generic expression, and an allow-listed NAME
# reached through a receiver (`tag?.Equals(x)`) are never pure.  The reading
# errs toward refusal: a comparison with a parenthesised right operand
# (`a > (b)`) and a cast before a grouping (`(int)(x)`) read as calls and are
# refused, a closed direction.  Besides invocations, every `new`,
# `stackalloc`, `await` and `throw`, every `[` (an indexer, an array or a
# collection) and every `{` (an initializer, a block, a pattern or a `with`)
# disqualifies.
#
# WHAT THIS READING DOES NOT SEE, so no sentence above is read as a promise
# about it: code that a C# expression runs WITHOUT a parenthesis -- a property
# getter (`ex.Message`, `tag?.Length`), a user-defined operator or implicit
# conversion, and the `ToString` that a concatenation or an interpolation hole
# calls on an operand that is not a string.  Those are not invocations here.
# The two walked methods' log calls read a constant, locals, parameters and an
# exception's message; a helper hidden in a getter or an operator is outside
# this check, and the notes carry that as a residual.
#
# The first reading's grammar is kept below, read ONLY by
# `_r11_impure_calls_first_pass`, so the R11CL1 test can show that it set
# aside every form it now refuses.
_R11_CALL = re.compile(
    r"(?<![\w.])(new\s+)?([A-Za-z_@]\w*(?:\s*\.\s*[A-Za-z_@]\w*)*)\s*"
    r"(?:<[^<>()]*>)?\s*\(")
_R11_NEW = re.compile(r"(?<![\w.])new\s*[\[{(]")
_R11_INDEXER = re.compile(r"[\w\])]\s*\??\[")
_R11_PURE_CALLS = frozenset((
    "nameof", "typeof", "sizeof", "default", "checked", "unchecked",
    "string.IsNullOrEmpty", "string.IsNullOrWhiteSpace", "string.Equals",
    "String.IsNullOrEmpty", "String.IsNullOrWhiteSpace", "String.Equals"))

# ROUND 12 (R11-L2, the round-11 review) -- AN UPPERCASE `String` CALL IS
# PURE ONLY WHEN ITS BINDING IS ESTABLISHED.  The allow-list above exempted
# `String.Equals`, `String.IsNullOrEmpty` and `String.IsNullOrWhiteSpace` by
# their SPELLING, but `String` is an ordinary identifier: a type, field,
# property, local, parameter, type parameter, namespace or using alias named
# String in scope makes `String.Equals(...)` invoke THAT, and one with a side
# effect inside a log call's arguments was set aside with the log call.  The
# lowercase `string` is a keyword and always names System.String, so the
# lowercase forms keep their exemption.  An uppercase form is now pure only
# when `_r12_string_binding` finds no reason to doubt the binding, in the
# compilation unit the statement belongs to AND in every delivered plugin
# source (the compile set of R11-L1): the unit imports `System` (in its own
# code, or through a `global using System;` in a delivered source); no
# identifier escape stands in the code of either; every bare occurrence of
# the identifier String in their code is a member access `String.<name>` -- a
# declaration, a type use or any other form is a reason, erring toward
# refusal; no namespace declaration carries a String component; and no using
# directive names String other than as `System.String`.  No MSBuild file the
# project reads may declare a using alias String either (R12CL2, below, reads
# every spelling MSBuild accepts).  A statement judged WITHOUT its unit
# is refused its uppercase forms: the binding is not established.  An
# allow-listed name reached through `::` (`global::String.Equals`) is never
# pure: `global::String` is not System.String.
#
# WHAT THIS DOES NOT SEE, so no sentence above is read as a promise about it:
# a type named String that a REFERENCED assembly (the game's, Unity's,
# Photon's, the loader's) declares in the global namespace or in the
# plugin's own namespace -- C# looks up both before a compilation unit's own
# `using System;` -- and a member named String that a base class from such
# an assembly declares.  None is in any delivered source.  The walked
# methods' classes are static, so their only base class is `object`; the
# notes carry the referenced-assembly case as a residual.
_R12_STRING_UPPER = frozenset(("String.IsNullOrEmpty", "String.IsNullOrWhiteSpace",
                               "String.Equals"))
_R12_STRING_IDENT = re.compile(r"(?<![\w@])@?String\b")
# a using DIRECTIVE: no parenthesis, so a using statement or declaration that
# calls something is read by the identifier rule instead
_R12_USING = re.compile(r"(?m)^[ \t]*(?:global[ \t]+)?using[ \t]+([^;(){}]*);")
_R12_NAMESPACE = re.compile(r"\bnamespace\s+([\w@.\s]+?)\s*[{;]")
_R12_ESCAPE = re.compile(r"\\[uU][0-9A-Fa-f]{4}")
# a character literal -- the code mask keeps it, and an escape inside one
# (`'\u2028'`) names a character, never an identifier
_R12_CHAR_LITERAL = re.compile(r"'(?:\\[^'\n]{1,9}|[^'\\\n])'")
_R12_SYSTEM_STRING = re.compile(r"(?:global\s*::\s*)?System\s*\.\s*String\b")
_R12_IMPORTS_SYSTEM = re.compile(r"(?m)^[ \t]*(?:global[ \t]+)?using[ \t]+System[ \t]*;")
_R12_GLOBAL_SYSTEM = re.compile(r"(?m)^[ \t]*global[ \t]+using[ \t]+System[ \t]*;")
# ROUND-12 COLD LENS (R12CL2): every character of the Unicode category Cf (a
# formatting character).  C# removes one from an identifier before comparing
# it, so `Str<U+200B>ing` written in code is the identifier String.
_R12_FORMAT_CHARS = "".join(chr(c) for c in range(0x110000)
                            if unicodedata.category(chr(c)) == "Cf")
_R12_FORMAT_CHAR = re.compile("[" + re.escape(_R12_FORMAT_CHARS) + "]")
# the raw pre-filter: every reason below needs one of these in the code, so a
# source whose raw text carries none needs no lexing
_R12_RAW_REASON = re.compile(r"(?<![\w@])@?String\b|\\[uU][0-9A-Fa-f]{4}|"
                             + _R12_FORMAT_CHAR.pattern)


def _r12_code_string_problems(code, text, name):
    """[reason] -- why `code` (a source's code mask) could bind `String` to
    something other than System.String; `text` is the source, for line
    numbers, and `name` labels each reason."""
    out = []
    bare = _R12_CHAR_LITERAL.sub(lambda m: " " * len(m.group(0)), code)
    esc = _R12_ESCAPE.search(bare)
    if esc:
        out.append("%s: an identifier escape stands in code at line %d"
                   % (name, _cs_line(text, esc.start())))
    # a byte-order mark at the very start of a file is not code (R12CL2)
    fmt = _R12_FORMAT_CHAR.search(bare, 1 if bare.startswith("\ufeff") else 0)
    if fmt:
        out.append("%s: a formatting character stands in code at line %d"
                   % (name, _cs_line(text, fmt.start())))
    skip = []
    for m in _R12_USING.finditer(code):
        skip.append((m.start(), m.end()))
        rest = _R12_SYSTEM_STRING.sub(" ", m.group(1))
        if _R12_STRING_IDENT.search(rest):
            out.append("%s: a using directive names String at line %d"
                       % (name, _cs_line(text, m.start())))
    for m in _R12_NAMESPACE.finditer(code):
        skip.append((m.start(), m.end()))
        parts = [p.strip().lstrip("@") for p in m.group(1).split(".")]
        if "String" in parts:
            out.append("%s: a namespace with a String component at line %d"
                       % (name, _cs_line(text, m.start())))
    for m in _R12_STRING_IDENT.finditer(code):
        if any(a <= m.start() < b for a, b in skip):
            continue
        q = _r11_prev(code, m.start())
        if q >= 0 and (code[q] == "." or (code[q] == ":" and q > 0
                                          and code[q - 1] == ":")):
            continue                 # a qualified name: System.String, x::String
        k = m.end()
        while k < len(code) and code[k].isspace():
            k += 1
        j = k + 1
        while j < len(code) and code[j].isspace():
            j += 1
        if (k < len(code) and code[k] == "." and j < len(code)
                and (code[j].isalpha() or code[j] in "_@")):
            continue                 # a member access String.<name>
        out.append("%s: the identifier String at line %d is not a member "
                   "access String.<name>" % (name, _cs_line(text, m.start())))
    return out


@functools.lru_cache(maxsize=256)
def _r12_source_string_problems(text, name):
    """The reasons of one C# source, cached by its text."""
    if not _R12_RAW_REASON.search(text):
        return ()
    return tuple(_r12_code_string_problems(_cs_code_mask(text), text, name))


@functools.lru_cache(maxsize=64)
def _r12_imports_system(text, form):
    """Whether `text` carries the using directive `form` in its CODE."""
    rx = _R12_IMPORTS_SYSTEM if form == "any" else _R12_GLOBAL_SYSTEM
    return bool(rx.search(text)) and bool(rx.search(_cs_code_mask(text)))


# ROUND-12 COLD LENS (R12CL2) -- A USING ALIAS IN AN MSBUILD FILE IS READ AS
# MSBUILD READS IT, NOT BY ITS SPELLING.  The first pass looked for a using
# alias String in the project file with one pattern, a double-quoted
# `Alias="String"` attribute.  MSBuild accepts the same Using item with a
# single-quoted attribute, with the alias as a child `<Alias>` element, with
# a character reference in either, with the item and metadata names in any
# letter case, as an Update of an item, and in any file it imports, and the
# SDK writes each into `global using String = ...;` under obj/, which the
# compile set leaves out.  `_r12_msbuild_string_problems` now parses every
# MSBuild file the gate lists (the project file, its .user file and its
# extension files, NuGet's included) as XML, so quoting and character
# references are resolved by the parser; it finds every element named Using,
# in any letter case, wherever it stands, and reads its alias from every
# attribute and every child element named Alias, in any letter case, with
# MSBuild's own `%XX` escapes decoded, as a task reads an item's metadata.  An
# alias is a reason when, compared as C# compares identifiers -- surrounding
# space dropped, a leading `@` dropped, every `\uXXXX` and `\UXXXXXXXX`
# escape decoded, every formatting character removed -- it is `String`, and
# when it carries an MSBuild expansion (`$(`, `@(`, `%(`), which this reading
# does not evaluate.  A Using item whose Include or Update carries an
# expansion is a reason for the same cause -- an Include from another item
# list brings that list's metadata, an alias among it -- and so is a task
# output adding Using items (`<Output ItemName="Using" />`, the item type
# compared in any letter case, or named by an expansion).  A file it cannot
# read, or read as XML, is a reason.
# The same comparison reaches the sources: a formatting character in a
# source's code (a byte-order mark at its very start aside) is a reason, as
# an identifier escape is.
#
# WHAT THIS DOES NOT SEE: a Using item added by a restored package's own
# build files or by MSBuild's machine-wide or per-user extension folders,
# which lie outside plugin/'s tree; the notes carry it with the
# referenced-assembly case as a residual.
_R12_CS_UNICODE_ESCAPE = re.compile(r"\\u([0-9A-Fa-f]{4})|\\U([0-9A-Fa-f]{8})")
_R12_MSBUILD_EXPANSION = ("$(", "@(", "%(")
# MSBuild's own escape: `%` and two hex digits stand for one character, and a
# task reads an item's metadata with every one decoded
_R12_MSBUILD_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")


def _r12_msbuild_unescape(value):
    """`value` as a task reads an item's metadata: every `%XX` decoded."""
    return _R12_MSBUILD_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), value)


def _r12_cs_identifier(value):
    """`value` as C# compares an identifier -- surrounding space dropped, a
    leading `@` dropped, every unicode escape decoded, every formatting
    character removed -- or None when an escape names no character."""
    v = value.strip()
    if v.startswith("@"):
        v = v[1:]
    try:
        v = _R12_CS_UNICODE_ESCAPE.sub(
            lambda m: chr(int(m.group(1) or m.group(2), 16)), v)
    except (ValueError, OverflowError):
        return None
    if v.startswith("@"):
        v = v[1:]
    return _R12_FORMAT_CHAR.sub("", v)


def _r12_msbuild_alias_reason(value):
    """Why a Using item's alias `value` could name String, or None."""
    if any(x in value for x in _R12_MSBUILD_EXPANSION):
        return "an alias carrying an MSBuild expansion this reading does not evaluate"
    value = _r12_msbuild_unescape(value)
    name = _r12_cs_identifier(value)
    if name is None:
        return "an alias whose escape names no character"
    if name == "String":
        return "the alias String"
    return None


def _r12_output_names_using(el):
    """Whether the element `el` adds items of the type Using through an output
    -- a task output's ItemName or an item's OutputItemType, an attribute or
    a child element -- the type compared as `_r13_item_type_is` compares it
    (R12CL2; R12R-L2 on every element, not only one named Output)."""
    return any(_r13_item_type_is(v, ("using",))
               for v in _r13_output_item_types(el))


def _r12_output_names_using_round12(el):
    """THE ROUND-12 READING, the same in behaviour: the ItemName attribute
    only, where the caller had already found an element named Output.  Kept
    ONLY so `test_r12cl2_...` can show the forms it did not see; nothing else
    calls it."""
    for k, v in el.attrib.items():
        if k.lower() == "itemname" and (
                v.strip().lower() == "using"
                or any(x in v for x in _R12_MSBUILD_EXPANSION)):
            return True
    return False


def _r12_msbuild_string_problems(project_dir):
    """[reason] -- every using alias that could name String, in any spelling
    MSBuild accepts, in every MSBuild file the gate lists for the project in
    `project_dir` (R12CL2), and every output adding Using items, on any
    element (R12R-L2)."""
    project_dir = pathlib.Path(project_dir)
    projects = sorted(p for p in project_dir.iterdir()
                      if p.is_file() and p.suffix.lower() == ".csproj")
    files, listing = _r12_msbuild_files(project_dir, projects)
    out = list(listing)
    for role, p, _kind in files:
        try:
            root = ET.fromstring(p.read_bytes())
        except (OSError, ET.ParseError) as exc:
            out.append("%s could not be read as XML (%s)" % (role, type(exc).__name__))
            continue
        for el in root.iter():
            if _r12_output_names_using(el):
                out.append("%s: a using item made by an output -- a task "
                           "output's ItemName or an item's OutputItemType -- "
                           "this reading does not evaluate" % role)
                continue
            if _r12_local(el.tag).lower() != "using":
                continue
            spec = [v for k, v in el.attrib.items()
                    if k.lower() in ("include", "update")]
            if any(x in v for v in spec for x in _R12_MSBUILD_EXPANSION):
                out.append("%s: a using item with its items from an MSBuild "
                           "expansion this reading does not evaluate" % role)
            values = [v for k, v in el.attrib.items() if k.lower() == "alias"]
            values += ["".join(ch.itertext()) for ch in el
                       if _r12_local(ch.tag).lower() == "alias"]
            for v in values:
                why = _r12_msbuild_alias_reason(v)
                if why:
                    out.append("%s: a using item with %s" % (role, why))
    return out


def _r12_project_alias_first_pass(project_dir):
    """THE FIRST-PASS READING of the project file, verbatim in behaviour: one
    pattern over each project file's text.  Kept ONLY so `test_r12cl2_...`
    can show the spellings it did not see; nothing else calls it."""
    out = []
    for p in sorted(pathlib.Path(project_dir).glob("*.csproj")):
        if re.search(r'Alias\s*=\s*"@?String"', p.read_text(encoding="utf-8")):
            out.append(p.name + ": a using item with the alias String")
    return out


def _r12_delivered_string_problems(sources=None, project_dir=None):
    """(reasons, a global using System) over every delivered plugin source
    and every MSBuild file the gate lists (R12CL2)."""
    sources = _r12_compile_sources() if sources is None else sources
    out, global_system = [], False
    for name in sorted(sources):
        out.extend(_r12_source_string_problems(sources[name], name))
        global_system = global_system or _r12_imports_system(sources[name],
                                                             "global")
    out.extend(_r12_msbuild_string_problems(project_dir or PLUGIN))
    return out, global_system


@functools.lru_cache(maxsize=8)
def _r12_tree_string_problems_at(plugin_dir):
    """The delivered-source reasons of the project in `plugin_dir`, read once
    per folder: the folder is the cache KEY, so a test that points PLUGIN
    elsewhere can only add an entry beside the tree's (#744)."""
    probs, glob_sys = _r12_delivered_string_problems(
        _r12_compile_sources(pathlib.Path(plugin_dir)), plugin_dir)
    return tuple(probs), glob_sys


def _r12_tree_string_problems():
    """The delivered-source reasons of the project PLUGIN names."""
    return _r12_tree_string_problems_at(str(PLUGIN))


def _r12_string_binding(unit, sources=None, project_dir=None):
    """(established, reasons) -- whether `String` in the compilation unit
    `unit` binds to System.String as far as the delivered sources show
    (R11-L2).  `unit` None: not established.  `sources` is handed in only by
    the R11-L2 test; otherwise the tree's compile set is read."""
    if unit is None:
        return False, ["the statement was judged without its compilation unit"]
    reasons = list(_r12_source_string_problems(unit, "the unit"))
    if sources is None:
        others, glob_sys = _r12_tree_string_problems()
    else:
        others, glob_sys = _r12_delivered_string_problems(sources, project_dir)
    reasons.extend(others)
    if not _r12_imports_system(unit, "any") and not glob_sys:
        reasons.append("the unit does not import System, so String does not "
                       "bind to System.String")
    return not reasons, reasons


def _r12_pure_refusal(name, code, before, unit):
    """None when the allow-listed invocation `name` is pure here; else the
    reason it is not (R11-L2)."""
    if before >= 0 and code[before] == ":":
        return "(reached through ::, which is not System.String)"
    if name in _R12_STRING_UPPER:
        ok, reasons = _r12_string_binding(unit)
        if not ok:
            return "(its binding to System.String is not established: %s)" % (
                reasons[0])
    return None


def _r11_log_arg_code(stmt):
    """The arguments of a log call as CODE -- literal text blanked, every
    interpolation hole kept -- or None when `stmt` is not a log call."""
    m = _R10CL_LOG.match(stmt)
    if m is None:
        return None
    return _cs_code_mask(m.group(1))


# The characters that END an operand, besides a name: after one of these a
# `(` invokes what precedes it (R11CL1).
_R11_OPERAND_CLOSERS = ")]>"
_R11_KEYWORDS = re.compile(r"\b(new|stackalloc|await|throw)\b")
_R11_BRACKETS = ("[", "{", "}")


def _r11_prev(code, i):
    """The index of the last character before `i` that is not a space, or
    -1."""
    j = i - 1
    while j >= 0 and code[j].isspace():
        j -= 1
    return j


def _r11_is_operand_end(code, q):
    """Whether `code[q]` ends an operand: a name's last character, one of
    `_R11_OPERAND_CLOSERS`, or a null-forgiving `!` after one of those."""
    ch = code[q]
    if ch.isalnum() or ch in "_@":
        return True
    if ch in _R11_OPERAND_CLOSERS:
        return True
    if ch == "!":
        r = _r11_prev(code, q)
        return r >= 0 and (code[r].isalnum() or code[r] in "_@"
                           or code[r] in _R11_OPERAND_CLOSERS)
    return False


def _r11_opens_call(code, p):
    """Whether the `(` at `code[p]` INVOKES what precedes it (R11CL1): the
    character before it, spaces skipped, ends an operand."""
    q = _r11_prev(code, p)
    return q >= 0 and _r11_is_operand_end(code, q)


def _r11_callee(code, p):
    """(start, text): the text the `(` at `code[p]` invokes, read back from
    it over names, dots, `?`, `!` and balanced (), [] and <> groups."""
    pairs = {")": "(", "]": "[", ">": "<"}
    j = _r11_prev(code, p)
    end = j + 1
    while j >= 0:
        ch = code[j]
        if ch.isalnum() or ch in "_@.?!":
            j -= 1
            continue
        if ch in pairs:
            depth, k = 0, j
            while k >= 0:
                if code[k] == ch:
                    depth += 1
                elif code[k] == pairs[ch]:
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            if k < 0:
                break
            j = k - 1
            continue
        break
    return j + 1, code[j + 1:end]


def _r11_impure_calls(stmt, unit=None, refusal=None):
    """[the nested calls, creations and other forms in a log call's arguments
    that this derivation cannot prove pure]; [] for a log call whose
    arguments invoke nothing but the allow-listed forms, and [] for a
    statement that is not a log call.  Every `(` is judged by what precedes
    it (R11CL1, R11CL3), never by a name pattern.

    `unit` is the text of the compilation unit the statement belongs to: an
    allow-listed form is pure only when `refusal` finds no reason against it
    there -- an uppercase `String` form needs its binding to System.String
    established (R11-L2), so a statement judged without its unit is refused
    those forms.  `refusal` defaults to `_r12_pure_refusal`; only
    `_r11_impure_calls_round11` hands in another, to show what the round-11
    reading set aside."""
    refusal = _r12_pure_refusal if refusal is None else refusal
    code = _r11_log_arg_code(stmt)
    if code is None:
        return []
    calls = []
    for p, ch in enumerate(code):
        if ch != "(" or not _r11_opens_call(code, p):
            continue
        start, callee = _r11_callee(code, p)
        name = re.sub(r"\s+", "", callee)
        before = _r11_prev(code, start)
        if name in _R11_PURE_CALLS and (before < 0 or code[before] != "."):
            why = refusal(name, code, before, unit)
            if why is None:
                continue
            calls.append(name + "(...) " + why)
            continue
        calls.append((name or "the expression before it") + "(...)")
    for mm in _R11_KEYWORDS.finditer(code):
        calls.append("`" + mm.group(1) + "`")
    for b in _R11_BRACKETS:
        if b in code:
            calls.append("`" + b + "` (an indexer, a creation, an initializer, "
                         "a block or a pattern)")
    return calls


def _r11_impure_calls_round11(stmt):
    """THE ROUND-11 READING (e5dfd3b), verbatim in behaviour: an allow-listed
    name with no member dot before it is pure by its SPELLING alone.  Kept
    ONLY so `test_r12_l2_...` can show that it set aside every shadowed form;
    nothing else calls it."""
    return _r11_impure_calls(stmt, refusal=lambda name, code, before, unit: None)


def _r11_impure_calls_first_pass(stmt):
    """THE FIRST READING OF THIS ROUND, verbatim in behaviour: a call found
    only where a bare name chain stands directly before `(`.  Kept ONLY so
    `test_r11cl1_...` can show that it set aside every form the reading above
    refuses; nothing else calls it."""
    code = _r11_log_arg_code(stmt)
    if code is None:
        return []
    calls = []
    for mm in _R11_CALL.finditer(code):
        name = re.sub(r"\s+", "", mm.group(2))
        if mm.group(1):
            calls.append("new " + name + "(...)")
        elif name not in _R11_PURE_CALLS:
            calls.append(name + "(...)")
    for mm in _R11_NEW.finditer(code):
        if not _R11_CALL.match(code, mm.start()):
            calls.append("an object or array creation")
    if _R11_INDEXER.search(code):
        calls.append("an indexer")
    return calls


def _r10cl_is_log_call(stmt, unit=None):
    """A log call that cannot change a local: no assignment outside a string
    or a comparison, no increment or decrement, no `ref` or `out` argument --
    each read over the arguments as CODE, interpolation holes included -- and
    no nested call this derivation cannot prove pure (R10-L3, R11CL1), with
    an uppercase `String` form pure only when its binding is established in
    `unit`, the compilation unit the statement belongs to (R11-L2)."""
    code = _r11_log_arg_code(stmt)
    if code is None:
        return False
    bare = re.sub(r"[=!<>]=|=>", " ", code)
    return ("=" not in bare and "++" not in code and "--" not in code
            and not re.search(r"\b(?:ref|out)\s", code)
            and not _r11_impure_calls(stmt, unit))


def _r11_is_log_call_first_pass(stmt):
    """The exemption with the FIRST reading's nested-call grammar -- kept ONLY
    so `test_r11cl1_...` can show what that reading set aside."""
    code = _r11_log_arg_code(stmt)
    if code is None:
        return False
    bare = re.sub(r"[=!<>]=|=>", " ", code)
    return ("=" not in bare and "++" not in code and "--" not in code
            and not re.search(r"\b(?:ref|out)\s", code)
            and not _r11_impure_calls_first_pass(stmt))


def _r10cl_is_log_call_round10(stmt):
    """THE ROUND-10 EXEMPTION, verbatim in behaviour: the statement's own text
    only, with every string literal blanked whole.  Kept ONLY so
    `test_r11_l3_...` can show that it exempted a nested state-changing call;
    nothing else calls it."""
    m = _R10CL_LOG.match(stmt)
    if m is None:
        return False
    code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', m.group(1))
    code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
    bare = re.sub(r"[=!<>]=|=>", " ", code)
    return ("=" not in bare and "++" not in code and "--" not in code
            and not re.search(r"\b(?:ref|out)\s", code))


def _r10cl_walk(name, stmts, sequence, split=None, exempt=None, unit=None):
    """(slots, why): `stmts` walked against the KNOWN SEQUENCE, log calls set
    aside.  Every statement must be the next one the sequence names; one that
    is not is REFUSED, never skipped.  `split` and `exempt` default to this
    round's split table and log-call exemption; only the R10-L2 and R10-L3
    tests hand in the round-10 ones, to show what those accepted.  `unit` is
    the compilation unit the statements belong to, which the default
    exemption needs for the String binding (R11-L2)."""
    split = _R10CL_SPLIT if split is None else split
    default = exempt is None or exempt is _r10cl_is_log_call
    if default:
        exempt = lambda s: _r10cl_is_log_call(s, unit)
    slots, k, logs = {}, 0, 0
    for s in stmts:
        if exempt(s):
            logs += 1
            continue
        nested = _r11_impure_calls(s, unit) if default else []
        if nested:
            return None, ("a log call in %s is not set aside: %s -- its "
                          "arguments call %s, which this derivation cannot "
                          "prove pure (R10-L3)" % (name, s, ", ".join(nested)))
        want = sequence[k] if k < len(sequence) else None
        if want == "<split>" and s in split:
            slots["split"] = split[s]
            k += 1
            continue
        if want == "<tokens>" and _R10CL_TOKENS.match(s):
            slots["tokens"] = _R10CL_TOKENS.match(s).groups()
            k += 1
            continue
        if want is not None and s == want:
            k += 1
            continue
        return None, ("a statement %s carries that this derivation does not "
                      "know: %s" % (name, s))
    if k != len(sequence):
        return None, "%s lacks a statement this derivation requires: %s" % (
            name, sequence[k])
    slots["statements"] = len(stmts) - logs
    slots["logs"] = logs
    return slots, ""


def _r10_outcome_model(ra, split=None):
    """(outcome_of(prop, series), why) derived from OutcomeOf's text and Tag's:
    every statement of OutcomeOf accounted for (R10CL5).  `split` is handed in
    only by `test_r11_l2_...`, to derive what the round-10 table accepted."""
    tag, why = _r10_tag_model(ra)
    if tag is None:
        return None, why
    body = _method_body(ra, _R10_OUTCOME_SIG)
    if not body:
        return None, "OutcomeOf's own text could not be delimited"
    slots, why = _r10cl_walk("OutcomeOf", _r10cl_statements(body), _R10CL_OUTCOME_SEQ,
                             split=split, unit=ra)
    if slots is None:
        return None, why
    toks = _r10_outcome_tokens(ra)
    if toks is None:
        return None, "an outcome token constant could not be read"
    if sorted(slots["tokens"]) != sorted(_R10_OUTCOME_CONSTS):
        return None, "OutcomeOf's token set is not the four known tokens"
    allowed = set(toks.values())
    last = slots["split"] == "last"

    def outcome_of(prop, series):
        t = tag(series)
        if not prop or not t:
            return ""
        i = prop.rfind(":") if last else prop.find(":")
        if i <= 0 or i + 1 >= len(prop):
            return ""
        if prop[:i] != t:
            return ""
        return prop[i + 1:] if prop[i + 1:] in allowed else ""
    return outcome_of, ""


def _r10_publish_model(ra):
    """(publish(series, outcome) -> the value written, why): every statement
    of PublishOutcome accounted for (R10CL5)."""
    tag, why = _r10_tag_model(ra)
    if tag is None:
        return None, why
    body = _method_body(ra, _R10_PUBLISH_SIG)
    if not body:
        return None, "PublishOutcome's own text could not be delimited"
    slots, why = _r10cl_walk("PublishOutcome", _r10cl_statements(body),
                             _R10CL_PUBLISH_SEQ, unit=ra)
    if slots is None:
        return None, why
    return (lambda series, outcome: (tag(series) + ":" + outcome)
            if tag(series) else None), ""


# Two VALID, DISTINCT series ids per pair, sharing a prefix of the stated
# length -- eight is the length the removed truncation kept; the longer ones
# make a truncation at ANY length red, not only at eight.
_R10_PREFIX_PAIRS = (
    ("3f2a9c1e-0b6d-4e5f-8a7b-1c2d3e4f5a60", "3f2a9c1e-9d8c-4b7a-9f6e-5d4c3b2a1f09"),
    ("3f2a9c1e-0b6d-4e5f-8a7b-1c2d3e4f5a60", "3f2a9c1e-0b6d-4e5f-8a7b-1c2d3e4f5a61"),
    ("0000000000000000-aaaa", "0000000000000000-bbbb"),
)


def _r10_m1_models():
    ra = _src("RoomActors.cs")
    tag, why = _r10_tag_model(ra)
    assert tag is not None, why
    outcome_of, why = _r10_outcome_model(ra)
    assert outcome_of is not None, why
    publish, why = _r10_publish_model(ra)
    assert publish is not None, why
    # THE OPERATION, counted inside each FUNCTION span, never file-wide: the
    # key is taken from Tag once in each user.  Tag's own text is judged by
    # the scenarios that run the model derived from it, not by a spelling.
    assert _method_body(ra, _R10_OUTCOME_SIG).count("Tag(seriesId)") == 1
    assert _method_body(ra, _R10_PUBLISH_SIG).count("Tag(seriesId)") == 1
    return tag, outcome_of, publish


def test_r10_m1a_two_series_sharing_a_prefix_keep_distinct_keys():
    """R9-M1, control a: two distinct series ids sharing a prefix, published
    in sequence on the elected seat, stay two keys -- neither series reads the
    other's value, and the later value is read only under its own series."""
    tag, outcome_of, publish = _r10_m1_models()
    for a, b in _R10_PREFIX_PAIRS:
        assert a != b and a[:8] == b[:8]
        assert tag(a) != tag(b), (
            "two distinct series ids sharing a prefix have ONE key: %r" % tag(a))
        prop = publish(a, "ok")                   # series A's answer
        assert outcome_of(prop, a) == "ok"
        assert outcome_of(prop, b) == "", (
            "series B read series A's retained 'ok' as its own answer")
        prop = publish(b, "no")                   # then series B's, in sequence
        assert outcome_of(prop, b) == "no"
        assert outcome_of(prop, a) == "", (
            "series A read series B's 'no' as its own answer")

    # TWIN, in the test: the SAME id in another letter case or with surrounding
    # whitespace is the same series and keeps one key.
    a = _R10_PREFIX_PAIRS[0][0]
    assert tag(a) == tag(a.upper()) == tag("  " + a + " ")
    assert outcome_of(publish(a.upper(), "ok"), a) == "ok"


def test_r10_m1b_a_watch_armed_for_one_series_never_reads_another_series_value():
    """R9-M1, control b: the elected seat still carries the value it published
    for series A when the watch arms for series B, which shares A's prefix.
    Arming latches OutcomeOf(elected, B), so B must read NOTHING -- a stale
    `ok` would stand the watch down and a stale `no` would fire it."""
    tag, outcome_of, publish = _r10_m1_models()
    for a, b in _R10_PREFIX_PAIRS:
        for stale in ("ok", "no", "unk", "send"):
            latched = outcome_of(publish(a, stale), b)   # arm under B
            assert latched == "", (
                "armed for series B, the watch latched series A's %r" % stale)
            assert fallback(latched, False) == "nothing"
        # and read back under A, the value is A's own
        assert outcome_of(publish(a, "no"), a) == "no"
        assert fallback(outcome_of(publish(a, "no"), a), False) == "post"


# The statements the round-10 cold lens planted, each AFTER the whole-id Tag
# and each shortening the key again (R10CL5).  They are planted in memory
# here; the controls runner plants the same forms in the tree.
_R10CL_RETRUNCATE = "tag = tag.Length > 8 ? tag.Substring(0, 8) : tag;"
_R10CL_PRECOMPARE = ("if (string.CompareOrdinal(s, 0, tag, 0, 8) == 0) "
                     "{ s = tag + s.Substring(i); i = tag.Length; }")


def _r10cl_presence_only(ra):
    """The round-10 presence reading this check replaced, kept ONLY to show
    that it accepted every planted form: True when each statement it looked
    for is present and the two spellings it excluded are absent."""
    ob = _r10_code_only(_method_body(ra, _R10_OUTCOME_SIG))
    pb = _r10_code_only(_method_body(ra, _R10_PUBLISH_SIG))
    return (ob.count("string tag = Tag(seriesId);") == 1
            and ob.count("int i = s.LastIndexOf(':');") == 1
            and ob.count('if (!string.Equals(s.Substring(0, i), tag, '
                         'StringComparison.Ordinal)) return "";') == 1
            and "StartsWith" not in ob
            and "Substring(0, i), tag.Substring" not in ob
            and pb.count("string tag = Tag(seriesId);") == 1
            and pb.count('{ OutcomeProp, tag + ":" + outcome }') == 1)


def test_r10cl5_every_statement_of_the_read_and_the_publication_is_accounted_for():
    """R10CL5: the read and the publication are derived statement by
    statement.  A statement that shortens the key after Tag -- in the read, in
    the publication, or as a prefix pre-comparison before the whole-key
    equality -- is REFUSED, and the presence reading it replaced accepted each
    one."""
    ra = _src("RoomActors.cs")
    out_at = ra.index(_R10_OUTCOME_SIG)
    pub_at = ra.index(_R10_PUBLISH_SIG)
    tag_line = "string tag = Tag(seriesId);"
    cmp_line = ('if (!string.Equals(s.Substring(0, i), tag, '
                'StringComparison.Ordinal)) return "";')

    def after(src, at, anchor, planted):
        """`src` with `planted` inserted after the first `anchor` from `at`."""
        j = src.index(anchor, at) + len(anchor)
        return src[:j] + " " + planted + src[j:]

    def before(src, at, anchor, planted):
        j = src.index(anchor, at)
        return src[:j] + planted + " " + src[j:]

    planted = {
        "the key shortened again in the read": after(
            ra, out_at, tag_line, _R10CL_RETRUNCATE),
        "the key shortened again in the publication": after(
            ra, pub_at, tag_line, _R10CL_RETRUNCATE),
        "a prefix pre-comparison before the whole-key equality": before(
            ra, out_at, cmp_line, _R10CL_PRECOMPARE),
    }
    for label, src in planted.items():
        assert src != ra, label + ": the plant did not land"
        o, why_o = _r10_outcome_model(src)
        p, why_p = _r10_publish_model(src)
        refused = [w for w in (why_o, why_p) if w]
        assert (o is None or p is None) and refused, (
            label + ": the derivation ACCEPTED a statement that shortens the key")
        assert all("does not know" in w for w in refused), (label, refused)
        assert _r10cl_presence_only(src), (
            label + ": the removed presence reading was not blind here")

    # TWINS, in the test: a comment and a blank line inside the read, extra
    # whitespace inside the publication's value, and a reworded log message
    # change no statement, and are accepted.
    twins = {
        "a comment beside the key": after(
            ra, out_at, tag_line, "// the key is the whole id" + LF),
        "whitespace inside the published value": ra.replace(
            '{ OutcomeProp, tag + ":" + outcome }',
            '{ OutcomeProp,  tag + ":"  +  outcome }', 1),
        "a reworded log line": ra.replace(
            "read their next move from it", "read their next step from it", 1),
    }
    for label, src in twins.items():
        assert src != ra, label + ": the twin did not land"
        o, why_o = _r10_outcome_model(src)
        p, why_p = _r10_publish_model(src)
        assert o is not None and p is not None, (label, why_o, why_p)

    oslots, _w = _r10cl_walk("OutcomeOf", _r10cl_statements(
        _method_body(ra, _R10_OUTCOME_SIG)), _R10CL_OUTCOME_SEQ, unit=ra)
    pslots, _w = _r10cl_walk("PublishOutcome", _r10cl_statements(
        _method_body(ra, _R10_PUBLISH_SIG)), _R10CL_PUBLISH_SEQ, unit=ra)
    assert oslots is not None and pslots is not None
    print("R10CL5 STATEMENTS: OutcomeOf %d accounted (%d log call(s)), "
          "PublishOutcome %d accounted (%d log call(s)); planted forms refused "
          "%d/%d, and the removed presence reading accepted each; twins "
          "accepted %d/%d" % (oslots["statements"], oslots["logs"],
                              pslots["statements"], pslots["logs"],
                              len(planted), len(planted), len(twins), len(twins)))


# ── R10-L2 and R10-L3 (round-10 review), in memory ─────────────────────────
# An identity carrying colons: the two split points select different keys
# here and nowhere in the prefix pairs above.
_R11_COLON_IDS = ("srv:3f2a9c1e", "srv:3f2a9c1e:2", "a:b")
_R11_SPLIT_LAST = "int i = s.LastIndexOf(':');"
_R11_SPLIT_FIRST = "int i = s.IndexOf(':');"


def test_r11_l2_the_read_is_split_at_the_last_colon_and_only_there():
    """R10-L2 (B9): the walk REQUIRES the last-colon split.  With the
    first-colon statement in its place the round-10 split table accepted the
    read and derived a model that took a shorter key -- for an identity
    carrying a colon, the series' own published answer read as nothing --
    and this round's table refuses the statement, naming it."""
    ra = _src("RoomActors.cs")
    body = _method_body(ra, _R10_OUTCOME_SIG)
    assert body.count(_R11_SPLIT_LAST) == 1, (
        "OutcomeOf does not carry the last-colon split exactly once")
    assert body.count(_R11_SPLIT_FIRST) == 0
    publish, why_p = _r10_publish_model(ra)
    assert publish is not None, why_p
    outcome_of, why = _r10_outcome_model(ra)
    assert outcome_of is not None, why
    for sid in _R11_COLON_IDS:
        prop = publish(sid, "ok")
        assert prop.count(":") >= 2, prop
        assert outcome_of(prop, sid) == "ok", (
            "the series' own answer did not read back under its colon-carrying "
            "id: %r" % prop)
    out_at = ra.index(_R10_OUTCOME_SIG)
    j = ra.index(_R11_SPLIT_LAST, out_at)
    first = ra[:j] + _R11_SPLIT_FIRST + ra[j + len(_R11_SPLIT_LAST):]
    assert first != ra

    # the round-10 table ACCEPTED the first-colon statement, and its model
    # took the shorter key
    old, why_old = _r10_outcome_model(first, split=_R10CL_SPLIT_ROUND10)
    assert old is not None, (
        "the round-10 table did not accept the first-colon split: " + why_old)
    wrong = [(sid, publish(sid, "ok")) for sid in _R11_COLON_IDS
             if old(publish(sid, "ok"), sid) != "ok"]
    assert len(wrong) == len(_R11_COLON_IDS), wrong
    sid, prop = wrong[0]
    print("R10-L2 ROUND-10 TABLE: accepted %r; key taken %r, published under "
          "%r -- the series' own answer read as %r" % (
              _R11_SPLIT_FIRST, prop[:prop.find(":")], prop[:prop.rfind(":")],
              old(prop, sid)))

    # this round's table REFUSES it, naming the statement
    new, why_new = _r10_outcome_model(first)
    assert new is None and "does not know" in why_new, why_new
    assert _R11_SPLIT_FIRST.rstrip(";") in why_new, why_new
    print("R10-L2 REFUSED: " + why_new)

    # TWIN, in the test: a comment after the last-colon statement changes no
    # statement and is accepted
    twin = ra[:j + len(_R11_SPLIT_LAST)] + "  // the last colon" + ra[
        j + len(_R11_SPLIT_LAST):]
    t, why_t = _r10_outcome_model(twin)
    assert t is not None, why_t
    print("R10-L2 LAST-COLON SPLIT: required; %d colon-carrying ids read back "
          "their own answer; the first-colon statement refused" % len(
              _R11_COLON_IDS))


# The planted forms: a log call whose arguments call a helper that could
# rewrite or clear the published value, in every place an argument can call
# one.  `ZzClearOutcome` names no plugin member; the text is judged, never run.
_R11_PLANTED_LOG_CALLS = (
    'Plugin.Log.LogInfo("[2v2-DC] cleared " + ZzClearOutcome(tag));',
    'Plugin.Log.LogInfo($"[2v2-DC] cleared {ZzClearOutcome(tag)}");',
    'Plugin.Log.LogInfo("[2v2-DC] cleared " + new ZzSink(tag).Text);',
    'Plugin.Log.LogInfo("[2v2-DC] cleared " + ZzSinks[OutcomeProp]);',
    'Plugin.Log.LogInfo("[2v2-DC] cleared " + tag.ZzClear());',
)
# The exempt shape: literals, property reads and the allow-listed pure forms.
_R11_PURE_LOG_CALLS = (
    'Plugin.Log.LogInfo("[2v2-DC] cleared");',
    'Plugin.Log.LogInfo("[2v2-DC] key " + nameof(OutcomeProp) + " " + tag.Length);',
    'Plugin.Log.LogInfo($"[2v2-DC] empty {string.IsNullOrEmpty(tag)}");',
    'Plugin.Log.LogInfo("[2v2-DC] a call written in text: ZzClearOutcome(tag)");',
)


def test_r11_l3_a_log_call_whose_arguments_call_a_helper_is_not_set_aside():
    """R10-L3 (B9): a log call is set aside only when its ARGUMENTS call
    nothing this derivation cannot prove pure.  Each planted helper call --
    concatenated, in an interpolation hole, an object creation, an indexer, a
    method on a local -- was exempted by the round-10 reading and is REFUSED
    now, naming the call; a log call of literals, property reads and the
    allow-listed pure forms is still set aside."""
    ra = _src("RoomActors.cs")
    pub_at = ra.index(_R10_PUBLISH_SIG)
    tag_line = "string tag = Tag(seriesId);"
    j = ra.index(tag_line, pub_at) + len(tag_line)

    def plant(line):
        return ra[:j] + " " + line + ra[j:]

    body = _method_body(ra, _R10_PUBLISH_SIG)
    stmts = _r10cl_statements(body)
    logs = [s for s in stmts if _R10CL_LOG.match(s)]
    assert logs and all(_r10cl_is_log_call(s, ra) for s in logs), logs
    slots, why = _r10cl_walk("PublishOutcome", stmts, _R10CL_PUBLISH_SEQ,
                             unit=ra)
    assert slots is not None, why

    refused = 0
    for line in _R11_PLANTED_LOG_CALLS:
        src = plant(line)
        stmt = line.rstrip(";")
        assert _r10cl_is_log_call_round10(stmt), (
            "the round-10 reading did not exempt: " + line)
        pb = _r10cl_statements(_method_body(src, _R10_PUBLISH_SIG))
        old, _w = _r10cl_walk("PublishOutcome", pb, _R10CL_PUBLISH_SEQ,
                              exempt=_r10cl_is_log_call_round10)
        assert old is not None, "the round-10 walk refused: " + line
        assert not _r10cl_is_log_call(stmt, src), "still exempt: " + line
        assert _r11_impure_calls(stmt, src), line
        p, why_p = _r10_publish_model(src)
        assert p is None and "is not set aside" in why_p, (line, why_p)
        refused += 1
        print("R10-L3 REFUSED: " + why_p)

    for line in _R11_PURE_LOG_CALLS:
        stmt = line.rstrip(";")
        src = plant(line)
        assert _r10cl_is_log_call(stmt, src), "no longer exempt: " + line
        p, why_p = _r10_publish_model(src)
        assert p is not None, (line, why_p)
    print("R10-L3 NESTED CALLS: %d planted forms refused, each exempted by the "
          "round-10 reading; %d pure forms still set aside; the tree's %d log "
          "call(s) in PublishOutcome exempt" % (
              refused, len(_R11_PURE_LOG_CALLS), len(logs)))


# ROUND-11 COLD LENS (R11CL1, R11CL3): the forms the first reading of this
# round set aside -- a call through a receiver that is not a bare name, the
# invocation of a parenthesised, generic or null-forgiven expression, an
# allow-listed name reached through a receiver, an indexer after `!`, a
# creation without parentheses and an `await` -- each concatenated and each
# in an interpolation hole.  `Zz*` names no plugin member; the text is judged,
# never run.
_R11CL_FORMS = (
    "tag?.ZzClearOutcome()", "tag!.ZzClearOutcome()", "ZzSink?.Invoke(tag)",
    "((System.Func<string>)ZzClearOutcome)()", "(tag).ZzClearOutcome()",
    "nameof(tag).ZzClearOutcome()", "ZzF<Dictionary<string,int>>()",
    "(ZzDel)()", "(x => x)(1)", "ZzDel!(tag)", "tag?.Equals(OutcomeProp)",
    "ZzSinks![OutcomeProp]", "new ZzSink { }.Text", "await ZzPending")
# Still set aside: property reads through `?.` and a grouping, a grouping
# with a ternary, a negated grouping, a hole, and an allow-listed operator
# followed by a property read.
_R11CL_PURE = (
    '"[2v2-DC] key " + tag?.Length',
    '"[2v2-DC] key " + (tag).Length',
    '"[2v2-DC] key " + (tag == null ? "none" : tag)',
    '"[2v2-DC] set " + !(tag == null)',
    '$"[2v2-DC] key {tag?.Length}"',
    '"[2v2-DC] key " + typeof(string).Name',
)
# Written with spaces around a dot: the first reading refused both, and this
# one must too -- the second is an allow-listed NAME read after a member dot,
# which only the no-`.`-before rule refuses.
_R11CL_SPACED = ("tag ?. ZzClearOutcome ()",
                 "ZzHolder. String.Equals(tag, OutcomeProp)")
_R11CL_PUBLISH_PLANT = ('Plugin.Log.LogInfo("[2v2-DC] cleared " + '
                        'tag?.ZzClearOutcome());')
_R11CL_OUTCOME_PLANT = 'Plugin.Log.LogInfo("r " + s?.ZzRewrite());'


def test_r11cl1_a_call_through_any_receiver_in_a_log_call_is_not_set_aside():
    """R11CL1, R11CL3 (B9): a `(` after the end of an operand is a call,
    whatever stands before it.  Every planted form was set aside by the first
    reading of this round and is REFUSED now, naming the call; end to end, a
    `?.` helper call planted in the publication after Tag and one planted in
    the read after the last-colon split are refused, where the first reading
    walked both methods; property reads, groupings and the allow-listed forms
    are still set aside."""
    ra = _src("RoomActors.cs")
    tree_logs = 0
    for sig in (_R10_PUBLISH_SIG, _R10_OUTCOME_SIG):
        body = _method_body(ra, sig)
        logs = [s for s in _r10cl_statements(body) if _R10CL_LOG.match(s)]
        assert all(_r10cl_is_log_call(s, ra) for s in logs), logs
        tree_logs += len(logs)
    publish, why_p = _r10_publish_model(ra)
    assert publish is not None, why_p
    outcome_of, why_o = _r10_outcome_model(ra)
    assert outcome_of is not None, why_o

    refused = 0
    for form in _R11CL_FORMS:
        found = []
        for stmt in ('Plugin.Log.LogInfo("[2v2-DC] cleared " + %s)' % form,
                     'Plugin.Log.LogInfo($"[2v2-DC] cleared {%s}")' % form):
            assert _r11_is_log_call_first_pass(stmt), (
                "the first reading did not set aside: " + stmt)
            assert not _r10cl_is_log_call(stmt, ra), "still set aside: " + stmt
            calls = _r11_impure_calls(stmt, ra)
            assert calls, stmt
            found.append(calls[0])
            refused += 1
        print("R11CL1 FORM %s : set aside by the first reading, refused now "
              "-- concatenated: %s; in a hole: %s" % (form, found[0], found[1]))
    for form in _R11CL_SPACED:
        stmt = 'Plugin.Log.LogInfo("[2v2-DC] cleared " + %s)' % form
        assert not _r11_is_log_call_first_pass(stmt), stmt
        assert not _r10cl_is_log_call(stmt, ra), "set aside: " + stmt
        print("R11CL1 SPACED %s : refused by both readings -- %s"
              % (form, _r11_impure_calls(stmt, ra)[0]))
    for arg in _R11CL_PURE:
        stmt = "Plugin.Log.LogInfo(%s)" % arg
        assert _r10cl_is_log_call(stmt, ra), "no longer set aside: " + stmt
        print("R11CL1 PURE %s : still set aside" % arg)

    # end to end: in the publication after Tag, and in the read after the
    # last-colon split
    tag_line = "string tag = Tag(seriesId);"
    j = ra.index(tag_line, ra.index(_R10_PUBLISH_SIG)) + len(tag_line)
    pub = ra[:j] + " " + _R11CL_PUBLISH_PLANT + ra[j:]
    k = (ra.index(_R11_SPLIT_LAST, ra.index(_R10_OUTCOME_SIG))
         + len(_R11_SPLIT_LAST))
    out = ra[:k] + " " + _R11CL_OUTCOME_PLANT + ra[k:]
    walked = 0
    for label, src, model, sig, seq in (
            ("PublishOutcome", pub, _r10_publish_model, _R10_PUBLISH_SIG,
             _R10CL_PUBLISH_SEQ),
            ("OutcomeOf", out, _r10_outcome_model, _R10_OUTCOME_SIG,
             _R10CL_OUTCOME_SEQ)):
        stmts = _r10cl_statements(_method_body(src, sig))
        old, why_old = _r10cl_walk(label, stmts, seq,
                                   exempt=_r11_is_log_call_first_pass)
        assert old is not None, "the first reading refused the walk: " + why_old
        got, why = model(src)
        assert got is None and "is not set aside" in why, (label, why)
        walked += 1
        print("R11CL1 REFUSED: " + why)
    print("R11CL1 RECEIVERS: %d planted forms refused (%d shapes, each "
          "concatenated and in a hole), each set aside by the first reading; "
          "%d spaced forms refused by both readings; %d pure forms still set "
          "aside; the tree's %d log call(s) in the two walked methods still "
          "set aside; the ?. helper call refused end to end in %d methods, "
          "each walked by the first reading" % (
              refused, len(_R11CL_FORMS), len(_R11CL_SPACED), len(_R11CL_PURE),
              tree_logs, walked))


# ROUND 12 (R11-L2): the forms in which `String` need not name System.String.
# Each is a compilation unit, or a delivered source beside the unit, built
# from the tree's RoomActors.cs; `Zz*` names no plugin member, and the text is
# judged, never run.  The shadow type's Equals changes a static on every call,
# so a log call invoking it is not pure.
_R12_UPPER_ARG = '"[2v2-DC] same " + String.Equals(tag, OutcomeProp)'
_R12_LOWER_ARG = '"[2v2-DC] same " + string.Equals(tag, OutcomeProp)'
_R12_SHADOW_TYPE = ("    internal static class String" + LF + "    {" + LF
                    + "        internal static int Calls;" + LF
                    + "        internal static bool Equals(string a, string b) "
                    "{ Calls++; return a == b; }" + LF + "    }" + LF)


def _r12_block(body):
    return "namespace CompetitiveRounds" + LF + "{" + LF + body + "}" + LF


def _r12_shadow_units(ra):
    """{label: (unit, other sources or None, project folder or None)}."""
    esc = "Str" + chr(92) + "u0069ng"
    return {
        "a type named String declared in the unit":
            (ra + LF + _r12_block(_R12_SHADOW_TYPE), None, None),
        "a type named String declared in another delivered source":
            (ra, {"Zz/ZzString.cs": _r12_block(_R12_SHADOW_TYPE)}, None),
        "a using alias String in the unit":
            (ra.replace("using System;" + LF, "using System;" + LF
                        + "using String = CompetitiveRounds.ZzShadow;" + LF, 1),
             None, None),
        "a global using alias String in another delivered source":
            (ra, {"Zz/ZzUsings.cs": "global using String = "
                  "CompetitiveRounds.ZzShadow;" + LF}, None),
        "a field named String in the unit":
            (ra + LF + _r12_block("    internal static class ZzHolder" + LF
                                  + "    {" + LF + "        internal static "
                                  "ZzShadow String = null;" + LF + "    }" + LF),
             None, None),
        "a type parameter named String in the unit":
            (ra + LF + _r12_block("    internal static class ZzHolder" + LF
                                  + "    {" + LF + "        internal static void "
                                  "ZzF<String>() { }" + LF + "    }" + LF),
             None, None),
        "a namespace with a String component in another delivered source":
            (ra, {"Zz/ZzNs.cs": "namespace CompetitiveRounds.String" + LF + "{"
                  + LF + "    internal static class ZzShadowNs { }" + LF + "}"
                  + LF}, None),
        "an identifier escape in the unit's code":
            (ra + LF + _r12_block("    internal static class ZzHolder" + LF
                                  + "    {" + LF + "        internal static int "
                                  + esc + ";" + LF + "    }" + LF), None, None),
        "a unit that does not import System":
            (ra.replace("using System;" + LF, "", 1), None, None),
        "a using item with the alias String in the project file":
            (ra, None, "alias"),
    }


def test_r12_l2_an_uppercase_string_call_is_exempt_only_when_its_binding_is_established(
        tmp_path):
    """R11-L2 (B9, and B20 through R10-L3): `String.Equals`,
    `String.IsNullOrEmpty` and `String.IsNullOrWhiteSpace` inside a log call's
    arguments are pure only when `String` is established to bind to
    System.String.  On the tree the binding is established and the walked
    methods' log calls are set aside.  Each shadow form -- a type, field,
    type parameter, using alias or namespace named String in the unit or in
    another delivered source, an identifier escape, a unit without
    `using System;`, an alias in the project file, a call through `::`, and a
    statement judged without its unit -- REFUSES the uppercase call, where the
    round-11 reading set every one of them aside by spelling; the lowercase
    keyword `string` stays exempt in every one of them; and end to end, an
    uppercase call planted in the publication after Tag beside a shadow type
    is refused where the same call with no shadow is still set aside."""
    ra = _src("RoomActors.cs")
    ok, reasons = _r12_string_binding(ra)
    assert ok, reasons
    tree_probs, _glob = _r12_tree_string_problems()
    assert tree_probs == (), tree_probs
    tree_logs = 0
    for sig in (_R10_PUBLISH_SIG, _R10_OUTCOME_SIG):
        logs = [s for s in _r10cl_statements(_method_body(ra, sig))
                if _R10CL_LOG.match(s)]
        assert all(_r10cl_is_log_call(s, ra) for s in logs), logs
        tree_logs += len(logs)
    assert tree_logs, "the walked methods carry no log call to judge"
    publish, why_p = _r10_publish_model(ra)
    assert publish is not None, why_p
    print("R11-L2 TREE: the binding of String is established in RoomActors.cs "
          "and across the %d delivered sources; the tree's %d log call(s) in "
          "the two walked methods set aside" % (len(_r12_compile_sources()),
                                                 tree_logs))

    upper = "Plugin.Log.LogInfo(%s)" % _R12_UPPER_ARG
    lower = "Plugin.Log.LogInfo(%s)" % _R12_LOWER_ARG
    tree = _r12_compile_sources()
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    (alias_dir / "CompetitiveRounds.csproj").write_bytes(
        ('<Project Sdk="Microsoft.NET.Sdk">' + LF + "  <ItemGroup>" + LF
         + '    <Using Include="CompetitiveRounds.ZzShadow" Alias="String" />'
         + LF + "  </ItemGroup>" + LF + "</Project>" + LF).encode("utf-8"))
    refused = 0
    for label, (unit, others, proj) in _r12_shadow_units(ra).items():
        assert _r11_impure_calls_round11(upper) == [], label
        sources = dict(tree)
        sources.update(others or {})
        got, why = _r12_string_binding(
            unit, sources, alias_dir if proj == "alias" else None)
        assert not got and why, label
        if others is None and proj is None:
            # a unit-level form refuses the call itself, through the exemption
            assert not _r10cl_is_log_call(upper, unit), "set aside: " + label
            calls = _r11_impure_calls(upper, unit)
            assert calls and "not established" in calls[0], (label, calls)
            assert _r10cl_is_log_call(lower, unit), "lowercase refused: " + label
        refused += 1
        print("R11-L2 SHADOW %s : set aside by the round-11 reading, refused "
              "now -- %s" % (label, why[0]))

    colons = ('Plugin.Log.LogInfo("[2v2-DC] same " + '
              'global::String.Equals(tag, OutcomeProp))')
    assert _r11_impure_calls_round11(colons) == []
    assert not _r10cl_is_log_call(colons, ra), colons
    print("R11-L2 COLONS : set aside by the round-11 reading, refused now -- "
          + _r11_impure_calls(colons, ra)[0])
    assert not _r10cl_is_log_call(upper), "judged without its unit, set aside"
    print("R11-L2 NO UNIT : refused -- " + _r11_impure_calls(upper)[0])
    for form in ("String.IsNullOrEmpty(tag)", "String.IsNullOrWhiteSpace(tag)"):
        stmt = 'Plugin.Log.LogInfo("[2v2-DC] empty " + %s)' % form
        assert _r10cl_is_log_call(stmt, ra), "established, refused: " + form
        shadow = _r12_shadow_units(ra)["a type named String declared in the unit"][0]
        assert not _r10cl_is_log_call(stmt, shadow), "shadowed, set aside: " + form
    assert _r10cl_is_log_call(upper, ra) and _r10cl_is_log_call(lower, ra)

    # end to end: the publication after Tag, the shadow type in the same file.
    # Each check judges the PLANTED statement in the unit it was planted in;
    # the tree's own log calls are judged by the tree checks above, so a tree
    # whose walked methods already carry an established uppercase call is
    # still a tree this test accepts.
    tag_line = "string tag = Tag(seriesId);"
    j = ra.index(tag_line, ra.index(_R10_PUBLISH_SIG)) + len(tag_line)
    k = ra.index(_R10_PUBLISH_SIG)
    k = ra.rindex(LF, 0, k) + 1
    member = "    " + _R12_SHADOW_TYPE.replace(LF, LF + "    ")[:-4]
    planted_upper = ra[:j] + " " + upper + ";" + ra[j:]
    shadowed = planted_upper[:k] + member + planted_upper[k:]
    assert not _r10cl_is_log_call(upper, shadowed), "set aside beside the shadow"
    calls = _r11_impure_calls(upper, shadowed)
    assert calls and "not established" in calls[0], calls
    p, why_p = _r10_publish_model(shadowed)
    assert p is None and "is not set aside" in why_p, why_p
    assert "not established" in why_p, why_p
    print("R11-L2 REFUSED: " + why_p)
    assert _r10cl_is_log_call(upper, planted_upper), "refused with no shadow"
    p, why_p = _r10_publish_model(planted_upper)
    assert p is not None, why_p
    planted_lower = ra[:j] + " " + lower + ";" + ra[j:]
    lower_shadowed = planted_lower[:k] + member + planted_lower[k:]
    assert _r10cl_is_log_call(lower, lower_shadowed), "lowercase refused"
    # the lowercase plant adds no refusal: the shadowed publication answers
    # the same with and without it
    p0, why0 = _r10_publish_model(ra[:k] + member + ra[k:])
    p, why_p = _r10_publish_model(lower_shadowed)
    assert (p is None) == (p0 is None), (why0, why_p)
    assert p is not None or why_p == why0, (why0, why_p)
    print("R11-L2 BINDING: %d shadow forms refused, each set aside by the "
          "round-11 reading; the call through :: refused; a statement judged "
          "without its unit refused; the lowercase keyword still set aside "
          "beside every unit-level shadow; the uppercase call planted after Tag "
          "refused beside a shadow type and still set aside with none" % refused)


# ROUND 12 (R11-L1): a nested source carrying a second caller of the mutating
# route -- the class B2 forbids.  `Zz*` names no plugin member.
_R12_NESTED_CALLER = (
    "namespace CompetitiveRounds" + LF + "{" + LF
    + "    internal static class ZzNested" + LF + "    {" + LF
    + "        internal static void ZzHidden(string sid)" + LF + "        {" + LF
    + "            ApiClient.PollTeamSeriesStateAssemblyOnly(sid, null);" + LF
    + "        }" + LF + "    }" + LF + "}" + LF)
_R12_NESTED_INERT = _R12_NESTED_CALLER.replace(
    "            ApiClient.PollTeamSeriesStateAssemblyOnly(sid, null);",
    "            int zz = sid.Length;")


def test_r12_l1_the_whole_client_source_map_is_the_compile_set(tmp_path, monkeypatch):
    """R11-L1 (B2, B10, B11, B16, B19): both whole-client source maps are the
    compile set -- every compiled source in any subfolder, keyed by its path
    relative to plugin/.  On the tree: the default compile glob is the
    authority and both maps equal the recursive walk.  On a scratch project:
    a nested source carrying a second caller of the mutating route, and a
    nested source sharing a top-level file's name, are both in both maps and
    the caller census finds the nested caller, where the round-11 map missed
    both; plugin/'s own obj and bin folders and a dot folder at any depth stay
    out, a subfolder's own obj folder stays in; and each override of the
    default glob is REFUSED."""
    assert _r12_compile_authority_problems(PLUGIN) == []
    tree = _r12_compile_sources()
    top = sorted(p.name for p in PLUGIN.glob("*.cs"))
    assert set(top) <= set(tree), sorted(set(top) - set(tree))
    assert all((PLUGIN / k).is_file() for k in tree), sorted(tree)
    assert _all_sources() == tree and _r7_plugin_sources() == tree
    print("R11-L1 TREE: the default compile glob is the authority; %d compiled "
          "sources, %d in a subfolder; both whole-client maps equal the compile "
          "set" % (len(tree), len([k for k in tree if "/" in k])))

    scratch = tmp_path / "plugin"
    files = {
        "CompetitiveRounds.csproj": '<Project Sdk="Microsoft.NET.Sdk">' + LF
                                    + "</Project>" + LF,
        "ApiClient.cs": _src("ApiClient.cs"),
        "Plugin.cs": _src("Plugin.cs"),
        "Zz/ZzNested.cs": _R12_NESTED_CALLER,
        "Zz/ApiClient.cs": _R12_NESTED_INERT,
        "Zz/obj/ZzInner.cs": _R12_NESTED_INERT,
        "Zz/Deeper/.cache/ZzDot.cs": _R12_NESTED_CALLER,
        "obj/ZzObj.cs": _R12_NESTED_CALLER,
        "BIN/ZzBin.cs": _R12_NESTED_CALLER,
        ".hidden/ZzHidden.cs": _R12_NESTED_CALLER,
    }
    for rel, body in files.items():
        f = scratch / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body.encode("utf-8"))
    want = ["ApiClient.cs", "Plugin.cs", "Zz/ApiClient.cs", "Zz/ZzNested.cs",
            "Zz/obj/ZzInner.cs"]
    got = _r12_compile_sources(scratch)
    assert sorted(got) == want, sorted(got)
    assert got["ApiClient.cs"] == files["ApiClient.cs"]
    assert got["Zz/ApiClient.cs"] == files["Zz/ApiClient.cs"]
    old = _r12_round11_map(scratch)
    assert sorted(old) == ["ApiClient.cs", "Plugin.cs"], sorted(old)
    old_sites = _call_sites("PollTeamSeriesStateAssemblyOnly", old)
    assert not any("ZzNested" in f for f, _m in old_sites), old_sites

    monkeypatch.setitem(globals(), "PLUGIN", scratch)
    assert _all_sources() == got, "the caller census's map is not the compile set"
    assert _r7_plugin_sources() == got, "the census map is not the compile set"
    sites = _call_sites("PollTeamSeriesStateAssemblyOnly")
    assert ("Zz/ZzNested.cs", "ZzHidden") in sites, sites
    assert sites != {("Plugin.cs", "PollAssemblyStateLoop")}, sites
    assert not any(f.split("/")[0] in ("obj", "BIN", ".hidden") or "/." in f
                   for f, _m in sites), sites
    print("R11-L1 NESTED: the compile set of a scratch project holds %s; the "
          "round-11 map held %s; the caller census found %s, so the one-caller "
          "rule is REFUSED on it" % (", ".join(sorted(got)), ", ".join(sorted(old)),
                                     ", ".join("%s:%s" % s for s in sorted(sites))))
    monkeypatch.undo()
    assert PLUGIN == ROOT / "plugin"

    refusals = 0
    proj = scratch / "CompetitiveRounds.csproj"
    base = proj.read_bytes()
    for label, body in (
            ("a Compile item", '<Project Sdk="Microsoft.NET.Sdk">' + LF
             + '  <ItemGroup><Compile Remove="Zz/**" /></ItemGroup>' + LF
             + "</Project>" + LF),
            ("a default-items switch", '<Project Sdk="Microsoft.NET.Sdk">' + LF
             + "  <PropertyGroup><EnableDefaultCompileItems>false"
             "</EnableDefaultCompileItems></PropertyGroup>" + LF + "</Project>" + LF),
            ("an Import", '<Project Sdk="Microsoft.NET.Sdk">' + LF
             + '  <Import Project="zz.props" />' + LF + "</Project>" + LF),
            ("not SDK-style", "<Project>" + LF + "</Project>" + LF)):
        proj.write_bytes(body.encode("utf-8"))
        try:
            _r12_compile_sources(scratch)
            raise AssertionError("an override of the default glob was not "
                                 "refused: " + label)
        except AssertionError as exc:
            assert "not the default compile glob" in str(exc), (label, str(exc))
            print("R11-L1 AUTHORITY REFUSED (%s): %s" % (label, exc))
        refusals += 1
    proj.write_bytes(base)
    (scratch / "Directory.Build.props").write_bytes(b"<Project />")
    try:
        _r12_compile_sources(scratch)
        raise AssertionError("a Directory.Build.props was not refused")
    except AssertionError as exc:
        assert "Directory.Build.props stands in the project folder" in str(exc), str(exc)
        print("R11-L1 AUTHORITY REFUSED (a Directory.Build.props): %s" % exc)
    refusals += 1
    print("R11-L1 COMPILE SET: nested and same-named sources enumerated by "
          "their paths, excluded folders left out, %d overrides of the default "
          "glob refused" % refusals)


# ROUND 12 COLD LENS (R12CL1): an MSBuild file that swaps ApiClient.cs for a
# file outside every map, and one that carries only a property.  `Zz*` names
# no plugin member.
_R12CL_SWAP = ("<Project>" + LF + "  <ItemGroup>" + LF
               + '    <Compile Remove="ApiClient.cs" />' + LF
               + '    <Compile Include="..' + chr(92) + "ZzElsewhere" + chr(92)
               + 'ApiClient.cs" />' + LF + "  </ItemGroup>" + LF + "</Project>" + LF)
_R12CL_QUIET = ("<Project>" + LF + "  <PropertyGroup>" + LF
                + "    <ZzDebugProfile>zz</ZzDebugProfile>" + LF
                + "  </PropertyGroup>" + LF + "</Project>" + LF)


def _r12cl_nuget_props(extra=""):
    """A NuGet-generated props file in NuGet's own shape -- one package content
    file as a Compile item, one package build file as an Import -- with
    `extra` before its end."""
    bs = chr(92)
    pkg = "$(NuGetPackageRoot)zz.package" + bs + "1.0.0" + bs
    content = pkg + "contentfiles" + bs + "cs" + bs + "any" + bs + "ZzAttribute.cs"
    build = pkg + "build" + bs + "Zz.Package.props"
    return ('<?xml version="1.0" encoding="utf-8" standalone="no"?>' + LF
            + '<Project ToolsVersion="14.0" '
              'xmlns="http://schemas.microsoft.com/developer/msbuild/2003">' + LF
            + "  <PropertyGroup>" + LF
            + "    <NuGetPackageRoot Condition=\" '$(NuGetPackageRoot)' == '' \">"
              "$(UserProfile)" + bs + ".nuget" + bs + "packages" + bs
            + "</NuGetPackageRoot>" + LF + "  </PropertyGroup>" + LF
            + "  <ItemGroup Condition=\" '$(Language)' == 'C#' \">" + LF
            + '    <Compile Include="' + content + '" Condition="Exists(\''
            + content + '\')">' + LF
            + "      <NuGetPackageId>Zz.Package</NuGetPackageId>" + LF
            + "    </Compile>" + LF + "  </ItemGroup>" + LF
            + "  <ImportGroup>" + LF
            + '    <Import Project="' + build + '" Condition="Exists(\'' + build
            + '\')" />' + LF + "  </ImportGroup>" + LF + extra + "</Project>" + LF)


def test_r12cl1_every_file_msbuild_reads_for_the_project_is_held_by_the_gate(tmp_path):
    """R12CL1 (B2, B10, B11, B16, B19, through R11-L1's compile set): the gate
    that makes the default compile glob the authority reads every file
    MSBuild reads for the project from plugin/ itself -- the project file,
    its .user file and every extension file under obj/ -- and refuses a
    Directory.Packages.props or a Directory.Build.rsp as it refuses the
    Directory.Build files.  On the tree nothing refuses.  On a scratch project
    each case is judged by the gate and by the first-pass gate: a .user file
    or an extension file that swaps ApiClient.cs for a file outside every
    map, an Import in either, a property in the project file naming a file
    MSBuild imports, a Directory.Packages.props, a Directory.Build.rsp,
    NuGet's own props or targets carrying anything but NuGet's shape, and --
    the sibling forms -- a property redefining the default glob, an Analyzer
    item, a task's or a project reference's output into the Compile or
    Analyzer items and an SDK reference each REFUSE the compile set, where
    the first-pass gate gave no reason; NuGet's own shape, a .user or
    extension file carrying only a property, and a task output adding
    another item type are accepted.

    ROUND 13 (R12R-L1): the gate reads each file as the parser reads it.  An
    output into the Compile or Analyzer items spelled with a character
    reference, as a child element with surrounding space, as an
    ItemDefinitionGroup default, through an expansion, an `%XX` escape or an
    entity the parser expands; a default-items switch inside a task's
    properties spelled with a character reference or an escape; and a .user
    file that is not XML each REFUSE the compile set, where the round-12
    reading of the same text -- every pattern over the raw text -- gave no
    reason either; the same constructions decoding to another item type or
    property are accepted."""
    projects = sorted(p for p in PLUGIN.iterdir()
                      if p.is_file() and p.suffix.lower() == ".csproj")
    files, listing = _r12_msbuild_files(PLUGIN, projects)
    assert listing == [], listing
    problems = _r12_compile_authority_problems(PLUGIN)
    assert problems == [], problems
    shaped = 0
    for _role, p, kind in files:
        if kind == "nuget":
            shaped += len([el for el in ET.fromstring(p.read_bytes()).iter()
                           if _r12_local(el.tag).lower() in ("compile", "import")])
    print("R12CL1 TREE: the gate read %d MSBuild file(s) of the project -- %s; "
          "%d Compile item(s) and Import(s) in NuGet's own files, each in NuGet's "
          "shape; no reason" % (len(files), ", ".join(r for r, _p, _k in files),
                                shaped))

    scratch = tmp_path / "plugin"
    (scratch / "obj").mkdir(parents=True)
    proj = scratch / "CompetitiveRounds.csproj"
    proj.write_bytes(('<Project Sdk="Microsoft.NET.Sdk">' + LF + "</Project>"
                      + LF).encode("utf-8"))
    (scratch / "ApiClient.cs").write_bytes(_R12_NESTED_INERT.encode("utf-8"))
    assert _r12_compile_authority_problems(scratch) == []
    bs = chr(92)
    user = "CompetitiveRounds.csproj.user"
    ext_t = "obj/CompetitiveRounds.csproj.zz.targets"
    ext_p = "obj/CompetitiveRounds.csproj.zz.props"
    ng_p = "obj/CompetitiveRounds.csproj.nuget.g.props"
    ng_t = "obj/CompetitiveRounds.csproj.nuget.g.targets"
    imp = ("<Project>" + LF + '  <Import Project="zz.targets" />' + LF
           + "</Project>" + LF)
    hook = ('<Project Sdk="Microsoft.NET.Sdk">' + LF + "  <PropertyGroup>"
            "<CustomAfterMicrosoftCommonTargets>zz.targets"
            "</CustomAfterMicrosoftCommonTargets></PropertyGroup>" + LF
            + "</Project>" + LF)
    def sdk_body(inner):
        return '<Project Sdk="Microsoft.NET.Sdk">' + LF + inner + "</Project>" + LF

    def plain_body(inner):
        return "<Project>" + LF + inner + "</Project>" + LF

    output = ('  <Target Name="ZzTarget" BeforeTargets="CoreCompile"><CreateItem '
              'Include="%s"><Output TaskParameter="Include" ItemName="%s" />'
              "</CreateItem></Target>" + LF)
    elsewhere = ".." + bs + "ZzElsewhere" + bs + "ApiClient.cs"
    cases = (
        ("a .user file that swaps ApiClient.cs for a file outside every map",
         user, _R12CL_SWAP, True),
        ("a .user file carrying an Import", user, imp, True),
        ("a .user file carrying only a property", user, _R12CL_QUIET, False),
        ("an extension targets file under obj/ that swaps ApiClient.cs",
         ext_t, _R12CL_SWAP, True),
        ("an extension props file under obj/ carrying an Import", ext_p, imp,
         True),
        ("an extension props file under obj/ carrying only a property",
         ext_p, _R12CL_QUIET, False),
        ("NuGet's props in NuGet's own shape", ng_p, _r12cl_nuget_props(),
         False),
        ("NuGet's props carrying a Compile Remove of ApiClient.cs", ng_p,
         _r12cl_nuget_props('  <ItemGroup><Compile Remove="ApiClient.cs" />'
                            "</ItemGroup>" + LF), True),
        ("NuGet's props carrying a Compile Include outside the package root",
         ng_p, _r12cl_nuget_props('  <ItemGroup><Compile Include="..' + bs
                                  + "ZzElsewhere" + bs + 'ApiClient.cs" />'
                                  "</ItemGroup>" + LF), True),
        ("NuGet's props naming a package file that climbs out of the package "
         "root", ng_p, _r12cl_nuget_props(
             '  <ItemGroup><Compile Include="$(NuGetPackageRoot)..' + bs + ".."
             + bs + "ZzElsewhere" + bs + 'ApiClient.cs" /></ItemGroup>' + LF),
         True),
        ("NuGet's props naming two files in one Include", ng_p,
         _r12cl_nuget_props('  <ItemGroup><Compile Include="$(NuGetPackageRoot)zz'
                            + bs + "a.cs;.." + bs + 'ApiClient.cs" /></ItemGroup>'
                            + LF), True),
        ("NuGet's targets carrying an Import outside the package root", ng_t,
         "<Project>" + LF + '  <Import Project="..' + bs + 'zz.targets" />' + LF
         + "</Project>" + LF, True),
        ("NuGet's props that is not XML", ng_p, "<Project>" + LF, True),
        ("the project file naming a file MSBuild imports through a property",
         "CompetitiveRounds.csproj", hook, True),
        ("a Directory.Packages.props in the project folder",
         "Directory.Packages.props", "<Project />" + LF, True),
        ("a Directory.Build.rsp in the project folder", "Directory.Build.rsp",
         "-p:EnableDefaultCompileItems=false" + LF, True),
        ("the project file excluding a folder from the default glob",
         "CompetitiveRounds.csproj", sdk_body(
             "  <PropertyGroup><DefaultItemExcludesInProjectFolder>Zz/**"
             "</DefaultItemExcludesInProjectFolder></PropertyGroup>" + LF), True),
        ("a .user file redefining the default glob's extension", user,
         plain_body("  <PropertyGroup><DefaultLanguageSourceExtension>.zz"
                    "</DefaultLanguageSourceExtension></PropertyGroup>" + LF),
         True),
        ("the project file carrying an Analyzer item", "CompetitiveRounds.csproj",
         sdk_body('  <ItemGroup><Analyzer Include="..' + bs + 'ZzGenerator.dll" />'
                  "</ItemGroup>" + LF), True),
        ("a .user file adding a Compile item through a task output", user,
         plain_body(output % (elsewhere, "Compile")), True),
        ("an extension props file under obj/ taking a project reference's "
         "output as an Analyzer", ext_p, plain_body(
             '  <ItemGroup><ProjectReference Include="..' + bs + "ZzGen" + bs
             + 'ZzGen.csproj" OutputItemType="Analyzer" /></ItemGroup>' + LF),
         True),
        ("an extension targets file under obj/ referencing an SDK", ext_t,
         plain_body('  <Sdk Name="Zz.Sdk" />' + LF), True),
        ("a .user file naming an SDK on its Project element", user,
         '<Project Sdk="Zz.Sdk">' + LF + "</Project>" + LF, True),
        ("a .user file whose task output adds another item type", user,
         plain_body(output % ("zz", "ZzItems")), False),
    )
    # ROUND 13 (R12R-L1): each spelling below reads as its literal form once
    # parsed or decoded; the round-12 reading of the raw text gave no reason.
    ref = ('  <ItemGroup><ProjectReference Include="..' + bs + "ZzGen" + bs
           + 'ZzGen.csproj"%s</ItemGroup>' + LF)
    task = ('  <Target Name="ZzTarget" BeforeTargets="CoreCompile"><MSBuild '
            'Projects="$(MSBuildProjectFullPath)" Targets="ZzInner" '
            'Properties="%s" /></Target>' + LF)
    r13_cases = (
        ("a .user file adding a Compile item through a task output whose item "
         "type is spelled with a character reference", user,
         plain_body(output % (elsewhere, "Com&#112;ile")), True),
        ("an extension props file under obj/ taking a project reference's "
         "output as an Analyzer spelled with a character reference", ext_p,
         plain_body(ref % ' OutputItemType="&#x41;nalyzer" />'), True),
        ("a .user file naming a project reference's output type Compile in a "
         "child element with surrounding space", user,
         plain_body(ref % "><OutputItemType> Compile </OutputItemType>"
                    "</ProjectReference>"), True),
        ("an extension targets file under obj/ giving every project reference "
         "the output type Analyzer by default", ext_t, plain_body(
             "  <ItemDefinitionGroup><ProjectReference><OutputItemType>Analyzer"
             "</OutputItemType></ProjectReference></ItemDefinitionGroup>" + LF),
         True),
        ("a .user file naming a task output's item type with an expansion "
         "inside it", user,
         plain_body(output % (elsewhere, "Comp$(ZzEmpty)ile")), True),
        ("a .user file naming a task output's item type with an MSBuild "
         "escape", user, plain_body(output % (elsewhere, "Com%70ile")), True),
        ("a .user file naming a task output's item type through an entity the "
         "parser expands", user,
         '<!DOCTYPE Project [<!ENTITY zz "Compile">]>' + LF
         + plain_body(output % (elsewhere, "&zz;")), True),
        ("an extension targets file under obj/ switching the default items "
         "off inside a task's properties with a character reference", ext_t,
         plain_body(task % "EnableDefault&#67;ompileItems=false"), True),
        ("a .user file switching the default items off inside a task's "
         "properties with an MSBuild escape", user,
         plain_body(task % "EnableDefault%43ompileItems=false"), True),
        ("a .user file that is not XML", user, "<Project>" + LF, True),
        ("a .user file whose task output's item type decodes to another item "
         "type", user, plain_body(output % ("zz", "ZzI&#116;ems")), False),
        ("an extension props file under obj/ naming a project reference's "
         "output type in a child element that decodes to another item type",
         ext_p, plain_body(ref % "><OutputItemType>Zz&#x49;tems"
                                 "</OutputItemType></ProjectReference>"),
         False),
        ("an extension targets file under obj/ whose task properties decode "
         "to another property", ext_t,
         plain_body(task % "ZzDebug&#80;rofile=false"), False),
    )
    refused = accepted = r13_refused = 0
    for label, rel, body, want, r13 in ([c + (False,) for c in cases]
                                        + [c + (True,) for c in r13_cases]):
        f = scratch / rel
        before = f.read_bytes() if f.exists() else None
        f.write_bytes(body.encode("utf-8"))
        try:
            got = _r12_compile_authority_problems(scratch)
            first = _r12_compile_authority_problems_first_pass(scratch)
            if want:
                assert got, "not refused: " + label
                assert first == [], ("the first-pass gate read it", label, first)
                if r13:
                    assert _r12_authority_text_reasons_round12(body) == [], (
                        "the round-12 reading saw it", label)
                    r13_refused += 1
                try:
                    _r12_compile_sources(scratch)
                    raise AssertionError("the compile set was read past: " + label)
                except AssertionError as exc:
                    assert "not the default compile glob" in str(exc), (label,
                                                                        str(exc))
                refused += 1
                print("R12CL1 CASE %s : REFUSED -- %s; the first-pass gate gave "
                      "no reason%s" % (label, got[0], "; the round-12 reading of "
                                       "its raw text gave none either" if r13
                                       else ""))
            else:
                assert got == [], (label, got)
                assert sorted(_r12_compile_sources(scratch)) == ["ApiClient.cs"], label
                accepted += 1
                print("R12CL1 CASE %s : accepted" % label)
        finally:
            if before is None:
                f.unlink()
            else:
                f.write_bytes(before)
    assert (refused, accepted) == (30, 7), (refused, accepted)
    assert r13_refused == 10, r13_refused
    print("R12CL1 GATE: %d case(s) refused where the first-pass gate gave no "
          "reason, %d of them where the round-12 reading gave none either; %d "
          "accepted" % (refused, r13_refused, accepted))


def test_r12cl2_a_using_alias_string_in_any_msbuild_spelling_refuses_the_binding(
        tmp_path):
    """R12CL2 (B9, and B20 through R10-L3): a using alias that could name
    String is read from every MSBuild file the gate lists as MSBuild reads it
    -- parsed as XML, the item and metadata names in any letter case, the
    alias an attribute or a child element with MSBuild's `%XX` escapes
    decoded, compared as C# compares identifiers -- and an alias, an item
    list or a task output the reading cannot evaluate is a reason.  On the
    tree there is none.  Each spelling below REFUSES the binding of String,
    where the first-pass pattern saw only the double-quoted attribute and its
    `@` form; a project file that is not XML refuses it; a formatting
    character inside an identifier in a delivered source's code refuses it,
    and the uppercase call beside it; a different alias, a longer name, a
    Using item with no alias, an Alias on another item type, an escape
    spelling another name, a task output adding another item type and a
    formatting character inside a string literal leave it established.

    ROUND 13 (R12R-L2): an output adding Using items is read on every
    element.  A project reference's OutputItemType of Using -- an attribute
    beside the alias String, a child element, an ItemDefinitionGroup default,
    spelled with a character reference, in any letter case, or with an `%XX`
    escape -- and a task output's ItemName spelled with an escape each REFUSE
    the binding, where the round-12 reading, which looked for the item type
    only on an element named Output and only in its ItemName, had nothing to
    read in any of them; a project reference whose output type is Analyzer,
    beside the same alias, or ZzItems in a child element leaves it
    established."""
    ra = _src("RoomActors.cs")
    assert _r12_msbuild_string_problems(PLUGIN) == []
    tree = _r12_compile_sources()
    bs = chr(92)
    inc = 'Include="CompetitiveRounds.ZzShadow"'
    prop = "  <PropertyGroup><ZzAlias>String</ZzAlias></PropertyGroup>" + LF
    zz_item = ("  <ItemGroup><ZzItem Include='CompetitiveRounds.ZzShadow' "
               "Alias='String' /></ItemGroup>" + LF)
    zz_output = ('  <Target Name="ZzTarget" BeforeTargets="GenerateGlobalUsings">'
                 '<CreateItem Include="CompetitiveRounds.ZzShadow" '
                 'AdditionalMetadata="Alias=String"><Output '
                 'TaskParameter="Include" ItemName="%s" /></CreateItem>'
                 "</Target>" + LF)

    def project(d, kind, item, extra):
        (d / "obj").mkdir(parents=True)
        body = "<ItemGroup>" + LF + "    " + item + LF + "  </ItemGroup>" + LF
        (d / "CompetitiveRounds.csproj").write_bytes((
            '<Project Sdk="Microsoft.NET.Sdk">' + LF + extra
            + ("  " + body if kind == "csproj" else "") + "</Project>"
            + LF).encode("utf-8"))
        other = ("<Project>" + LF + "  " + body + "</Project>" + LF).encode("utf-8")
        if kind == "user":
            (d / "CompetitiveRounds.csproj.user").write_bytes(other)
        if kind == "ext":
            (d / "obj" / "CompetitiveRounds.csproj.zz.props").write_bytes(other)
        return d

    forms = (
        ("a double-quoted attribute", "csproj",
         '<Using %s Alias="String" />' % inc, "", True),
        ("a single-quoted attribute", "csproj",
         "<Using %s Alias='String' />" % inc, "", False),
        ("a child element", "csproj",
         "<Using %s><Alias>String</Alias></Using>" % inc, "", False),
        ("a character reference in the attribute", "csproj",
         '<Using %s Alias="&#83;tring" />' % inc, "", False),
        ("a character reference in the child element", "csproj",
         "<Using %s><Alias>&#x53;tring</Alias></Using>" % inc, "", False),
        ("surrounding space", "csproj", '<Using %s Alias=" String " />' % inc,
         "", False),
        ("a verbatim @ prefix", "csproj", '<Using %s Alias="@String" />' % inc,
         "", True),
        ("a unicode escape", "csproj",
         ('<Using %s Alias="' % inc) + bs + 'u0053tring" />', "", False),
        ("a formatting character", "csproj",
         '<Using %s Alias="Str&#x200B;ing" />' % inc, "", False),
        ("lower-case item and metadata names", "csproj",
         '<using include="CompetitiveRounds.ZzShadow" alias="String" />', "",
         False),
        ("an MSBuild property", "csproj", '<Using %s Alias="$(ZzAlias)" />' % inc,
         prop, False),
        ("an Update of the item", "csproj",
         "<Using Update=\"CompetitiveRounds.ZzShadow\" Alias='String' />", "",
         False),
        ("the project's .user file", "user", "<Using %s Alias='String' />" % inc,
         "", False),
        ("an extension file under obj/", "ext",
         "<Using %s><Alias>String</Alias></Using>" % inc, "", False),
        ("an MSBuild escape", "csproj", '<Using %s Alias="%%53tring" />' % inc,
         "", False),
        ("an MSBuild escape of the verbatim @", "csproj",
         '<Using %s Alias="%%40String" />' % inc, "", False),
        ("items included from another item list", "csproj",
         '<Using Include="@(ZzItem)" />', zz_item, False),
        ("a task output adding Using items", "csproj", '<ZzHolder Include="x" />',
         zz_output % "Using", False),
    )
    refused = seen_first = 0
    for i, (label, kind, item, extra, seen) in enumerate(forms):
        d = project(tmp_path / ("f%02d" % i), kind, item, extra)
        got, why = _r12_string_binding(ra, tree, d)
        alias = [w for w in why if "using item" in w]
        assert not got and alias, (label, why)
        first = _r12_project_alias_first_pass(d)
        assert bool(first) == seen, (label, first)
        refused += 1
        seen_first += 1 if seen else 0
        print("R12CL2 FORM %s : REFUSED -- %s; the first-pass pattern %s" % (
            label, alias[0], "saw it" if seen else "did not see it"))
    d = tmp_path / "notxml"
    (d / "obj").mkdir(parents=True)
    (d / "CompetitiveRounds.csproj").write_bytes(
        ('<Project Sdk="Microsoft.NET.Sdk">' + LF).encode("utf-8"))
    got, why = _r12_string_binding(ra, tree, d)
    assert not got and any("could not be read as XML" in w for w in why), why
    print("R12CL2 NOT XML: a project file that is not XML REFUSED -- " + why[-1])

    twins = (
        ("a different alias", "<Using %s Alias='ZzAlias' />" % inc, ""),
        ("a longer name", "<Using %s><Alias>Strings</Alias></Using>" % inc, ""),
        ("a Using item with no alias", '<Using Include="System" />', ""),
        ("an Alias on another item type", "<ZzItem Include='x' Alias='String' />",
         ""),
        ("an MSBuild escape naming ZzString",
         '<Using %s Alias="Zz%%53tring" />' % inc, ""),
        ("a task output adding another item type", '<ZzHolder Include="x" />',
         zz_output % "ZzItems"),
    )
    for i, (label, item, extra) in enumerate(twins):
        d = project(tmp_path / ("t%02d" % i), "csproj", item, extra)
        got, why = _r12_string_binding(ra, tree, d)
        assert got, (label, why)
        print("R12CL2 TWIN %s : established" % label)

    # ROUND 13 (R12R-L2): an output adding Using items, on any element.
    def round12_saw(d):
        """Whether the round-12 reading had anything to read in `d`: an
        element named Output whose ItemName it read as Using, or an element
        named Using."""
        found, _listing = _r12_msbuild_files(d, sorted(d.glob("*.csproj")))
        for _role, p, _kind in found:
            for el in ET.fromstring(p.read_bytes()).iter():
                name = _r12_local(el.tag).lower()
                if name == "using" or (
                        name == "output" and _r12_output_names_using_round12(el)):
                    return True
        return False

    shadow = ".." + bs + "ZzShadow" + bs + "ZzShadow.csproj"
    r13_forms = (
        ("a project reference's output type Using beside the alias String",
         "csproj", '<ProjectReference Include="%s" OutputItemType="Using" '
         'Alias="String" />' % shadow, ""),
        ("a project reference's output type Using in a child element", "user",
         '<ProjectReference Include="%s"><OutputItemType>Using'
         "</OutputItemType></ProjectReference>" % shadow, ""),
        ("every project reference's output type Using by an "
         "ItemDefinitionGroup default", "ext",
         '<ProjectReference Include="%s" />' % shadow,
         "  <ItemDefinitionGroup><ProjectReference><OutputItemType>Using"
         "</OutputItemType></ProjectReference></ItemDefinitionGroup>" + LF),
        ("a character reference in a project reference's output type",
         "csproj", '<ProjectReference Include="%s" '
         'OutputItemType="Usin&#103;" />' % shadow, ""),
        ("a lower-case metadata name and an upper-case output type", "csproj",
         '<ProjectReference Include="%s" outputitemtype="USING" />' % shadow,
         ""),
        ("an MSBuild escape in a project reference's output type", "csproj",
         '<ProjectReference Include="%s" OutputItemType="Us%%69ng" />' % shadow,
         ""),
        ("an MSBuild escape in a task output's item type", "csproj",
         '<ZzHolder Include="x" />', zz_output % "Us%69ng"),
    )
    r13_refused = 0
    for i, (label, kind, item, extra) in enumerate(r13_forms):
        d = project(tmp_path / ("r%02d" % i), kind, item, extra)
        got, why = _r12_string_binding(ra, tree, d)
        using = [w for w in why if "using item" in w]
        assert not got and using, (label, why)
        assert not round12_saw(d), ("the round-12 reading had it to read", label)
        r13_refused += 1
        print("R12CL2 FORM %s : REFUSED -- %s; the round-12 reading had nothing "
              "to read in it" % (label, using[0]))
    assert r13_refused == 7, r13_refused
    r13_twins = (
        ("a project reference's output type Analyzer beside the alias String",
         '<ProjectReference Include="%s" OutputItemType="Analyzer" '
         'Alias="String" />' % shadow),
        ("a project reference's output type ZzItems in a child element",
         '<ProjectReference Include="%s"><OutputItemType>ZzItems'
         "</OutputItemType></ProjectReference>" % shadow),
    )
    for i, (label, item) in enumerate(r13_twins):
        d = project(tmp_path / ("s%02d" % i), "csproj", item, "")
        got, why = _r12_string_binding(ra, tree, d)
        assert got, (label, why)
        print("R12CL2 TWIN %s : established" % label)

    zw = chr(0x200B)
    cf_ident = _r12_block("    internal static class ZzHolder" + LF + "    {" + LF
                          + "        internal static int Str" + zw + "ing;" + LF
                          + "    }" + LF)
    cf_text = cf_ident.replace("int Str" + zw + "ing;",
                               'string ZzText = "a' + zw + 'b";')
    assert not _R12_STRING_IDENT.search(cf_ident)
    got, why = _r12_string_binding(ra, dict(tree, **{"Zz/ZzCf.cs": cf_ident}))
    fmt = [w for w in why if "formatting character" in w]
    assert not got and fmt, why
    upper = "Plugin.Log.LogInfo(%s)" % _R12_UPPER_ARG
    assert _r10cl_is_log_call(upper, ra)
    assert not _r10cl_is_log_call(upper, ra + LF + cf_ident), "set aside"
    print("R12CL2 SOURCE: a formatting character inside an identifier in a "
          "delivered source's code REFUSED -- %s; the identifier pattern alone "
          "does not match it, and the uppercase call beside it in the unit is "
          "not set aside" % fmt[0])
    got, why = _r12_string_binding(ra, dict(tree, **{"Zz/ZzCf.cs": cf_text}))
    assert got, why
    print("R12CL2 SOURCE TWIN: the same character inside a string literal : "
          "established")
    print("R12CL2 BINDING: %d MSBuild spelling(s) refused, %d of them seen by "
          "the first-pass pattern; %d output form(s) refused that the round-12 "
          "reading had nothing to read in; a project file that is not XML "
          "refused; a formatting character in code refused; %d twin(s) "
          "established" % (refused, seen_first, r13_refused,
                           len(twins) + len(r13_twins) + 1))


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


# ROUND 12 (R11-L1, the round-11 review) -- THE WHOLE-CLIENT SOURCE MAP IS
# THE COMPILE SET.  The project file is SDK-style with no Compile item and no
# switch that turns the default items off, so what it compiles is the SDK's
# default compile glob: every `**/*.cs` under plugin/, minus plugin/'s own
# output and intermediate folders (bin, obj) and any folder whose name starts
# with a dot, at any depth.  Both whole-client maps -- `_all_sources`, which
# feeds the caller census, and `_r7_plugin_sources`, which feeds the
# dead-status sweep, the ignored-read census, the claimed-prose scope and the
# writer census -- used to glob plugin/'s TOP LEVEL only and key each entry
# by its file NAME, so a source in a subfolder, compiled into the DLL, was
# outside every one of those checks, and two sources sharing a name in
# different folders could not both have been keys.  Both now return
# `_r12_compile_sources()`: a recursive walk applying exactly those
# exclusions, keyed by the path relative to plugin/ with forward slashes (a
# top-level file's key is its name, as before).
#
# THE GLOB IS THE AUTHORITY ONLY WHILE NOTHING OVERRIDES IT, so the walk
# REFUSES -- raises, and every check built on it goes red -- when the project
# folder holds other than one project file, the project is not SDK-style,
# the project file carries a Compile item, a default-items switch, a
# DefaultItemExcludes or output/intermediate path override, an Import or a
# property naming a file MSBuild imports, or a Directory.Build.props/.targets
# stands in plugin/ or any folder above it; the R12CL1 paragraphs below add
# the files and the forms of the round-12 second pass.  A folder the walk
# cannot list raises too.  Each refusal names the file by its role, never by
# its path.
#
# ROUND-12 COLD LENS (R12CL1) -- EVERY FILE MSBUILD READS FOR THIS PROJECT
# FROM plugin/ ITSELF IS HELD BY THE GATE, NOT THE PROJECT FILE ALONE.  The
# SDK's own files import, besides the project file, `<project file>.user`
# beside it (Microsoft.Common.CurrentVersion.targets) and every
# `obj/<project file>.*.props` and `.*.targets` (Microsoft.Common.props and
# Microsoft.Common.targets, through MSBuildProjectExtensionsPath, which is
# obj/ while no override stands); NuGet.props imports a
# Directory.Packages.props found in the project folder or above, and
# MSBuild's command line reads a Directory.Build.rsp found there.
# `_r12_msbuild_files` lists the .user file and the extension files beside
# the project file, and the gate holds each to the same forms as the project
# file, with one exception: NuGet's own `<project file>.nuget.g.props` and
# `.nuget.g.targets` name the restored packages' content files as Compile
# items and their build files as Imports, so there each Compile item must be
# an Include of ONE file named under $(NuGetPackageRoot) -- no parent
# segment, wildcard, list separator or further expansion -- and each Import
# must name one .props or .targets file there the same way; any other
# Compile item there, a Remove or an Update among them, refuses.  A
# Directory.Packages.props or a Directory.Build.rsp in plugin/ or above
# refuses by its presence, like the Directory.Build files.  A file the gate
# cannot read, or cannot read as XML where it has to, refuses.
#
# THE SIBLING FORMS (R12CL1, the same pass): the forms themselves were swept
# for other ways a file can move the compile off the default glob, and four
# more refuse wherever the gate reads them -- a property redefining the
# glob, its extension (DefaultLanguageSourceExtension) or its project-folder
# exclude (DefaultItemExcludesInProjectFolder, DefaultExcludesInProjectFolder,
# which the DefaultItemExcludes pattern never matched); an Analyzer item,
# which can add generated code to the compile; a task's or a project
# reference's output into the Compile or Analyzer items, or into an item
# type named by an expansion; and an SDK reference other than the project's
# own Microsoft.NET.Sdk, which imports that SDK's files.
#
# WHAT THIS DOES NOT SEE, so no sentence above is read as a promise about
# it: a source the build adds from outside plugin/'s own tree -- a restored
# package's content file (NuGet's props in this tree names one today), a
# file the SDK generates under obj/ (the assembly-info file), the code a
# restored package's analyzers generate -- is compiled but is not delivered
# plugin source; a target that runs the compiler on inputs of its own,
# rather than through the Compile items, is not modelled; and a restored
# package's own build files, the package root NuGet's files name, and
# MSBuild's machine-wide and per-user extension folders (the ImportBefore
# and ImportAfter wildcards) lie outside plugin/'s tree and are not read.
# The notes carry these as a residual.
_R12_AUTHORITY_FORMS = (
    ("a Compile item", re.compile(r"<\s*Compile\b", re.I)),
    ("a default-items switch",
     re.compile(r"\bEnableDefault(?:Compile)?Items\b", re.I)),
    ("a DefaultItemExcludes override", re.compile(r"\bDefaultItemExcludes\b", re.I)),
    ("an output or intermediate path override",
     re.compile(r"\bBase(?:Output|IntermediateOutput)Path\b", re.I)),
    ("an Import", re.compile(r"<\s*Import\b", re.I)),
    ("a property naming a file MSBuild imports", re.compile(
        r"<\s*(?:Custom(?:Before|After)\w+|DirectoryBuild(?:Props|Targets)Path"
        r"|DirectoryPackagesPropsPath|MSBuildProjectExtensionsPath"
        r"|Import(?:DirectoryBuild|DirectoryPackages|ProjectExtension"
        r"|UserLocationsByWildcard|ByWildcard)\w*)\b", re.I)),
    # the sibling forms of the second pass (R12CL1)
    ("a property redefining the default compile glob", re.compile(
        r"\bDefault(?:LanguageSourceExtension|(?:Item)?ExcludesInProjectFolder)\b",
        re.I)),
    ("an Analyzer item", re.compile(r"<\s*Analyzer\b", re.I)),
    # an output into the Compile or Analyzer items is read from the parsed
    # file by `_r13_output_item_types`, not by a pattern (R12R-L1)
    ("an SDK reference", re.compile(
        r"<\s*Sdk\b|\bSdk\s*=\s*([\"'])(?!Microsoft\.NET\.Sdk\1)", re.I)),
)
# THE ROUND-12 PATTERN for an output into the Compile or Analyzer items, over
# the raw text -- the same pattern, its literal split differently.  Kept ONLY
# so `test_r12cl1_...` can show the spellings it did not see; the gate reads
# the parsed item type instead (R12R-L1).
_R12_OUTPUT_FORM_ROUND12 = ("an output into the Compile or Analyzer items",
                            re.compile(r"\b(?:ItemName|OutputItemType)\s*=\s*"
                                       r"([\"'])\s*(?:(?:Compile|Analyzer)\s*\1"
                                       r"|[$@%]\()", re.I))
# the item types an output may not name, because they decide what the
# project compiles (R12R-L1)
_R13_AUTHORITY_ITEM_TYPES = ("compile", "analyzer")
# the two forms NuGet's own generated files carry, held to NuGet's shape
_R12_NUGET_SHAPED = ("a Compile item", "an Import")
_R12_PACKAGE_FILE = re.compile(r"\$\(NuGetPackageRoot\)(?!.*\.\.)[A-Za-z0-9_.+\-\\/]+")
_R12_SDK_PROJECT = re.compile(r'<\s*Project\s+Sdk\s*=\s*"Microsoft\.NET\.Sdk"')
_R12_EXCLUDED_TOP = ("bin", "obj")
_R12_BUILD_FILES = ("Directory.Build.props", "Directory.Build.targets",
                    "Directory.Packages.props", "Directory.Build.rsp")


def _r12_local(tag):
    """An element's name without its XML namespace."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _r12_msbuild_files(plugin_dir, projects):
    """([(role, path, kind)], [problem]) -- every file MSBuild reads for the
    project in `plugin_dir` from plugin/ itself, the Directory files aside:
    each project file, the `.user` file beside it, and every extension file
    under plugin/'s own obj/ folder (R12CL1).  `kind` is `project`, `user`,
    `nuget` (NuGet's own generated props or targets) or `extension`."""
    files, problems = [], []
    for p in projects:
        files.append(("the project file", p, "project"))
        user = p.with_name(p.name + ".user")
        if user.exists():
            files.append(("the project's .user file", user, "user"))
    try:
        ext_dirs = sorted(d for d in pathlib.Path(plugin_dir).iterdir()
                          if d.name.lower() == "obj" and d.is_dir())
    except OSError as exc:
        return files, ["the project folder could not be listed (%s)"
                       % type(exc).__name__]
    for d in ext_dirs:
        try:
            entries = sorted(d.iterdir())
        except OSError as exc:
            problems.append("the project's obj/ folder could not be listed (%s)"
                            % type(exc).__name__)
            continue
        for f in entries:
            low = f.name.lower()
            for p in projects:
                stem = p.name.lower() + "."
                if not (low.startswith(stem) and low.endswith((".props", ".targets"))):
                    continue
                ext = low.rsplit(".", 1)[1]
                if low in (stem + "nuget.g.props", stem + "nuget.g.targets"):
                    files.append(("NuGet's generated " + ext + " file", f, "nuget"))
                else:
                    files.append(("a project extension file (." + ext
                                  + ") under obj/", f, "extension"))
                break
    return files, problems


def _r12_nuget_shape_problems(role, path):
    """[reason] -- each Compile item or Import in NuGet's generated file at
    `path` that is not in NuGet's shape (R12CL1)."""
    try:
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError) as exc:
        return ["%s could not be read as XML (%s)" % (role, type(exc).__name__)]
    out = []
    for el in root.iter():
        name = _r12_local(el.tag).lower()
        attrs = dict((k.lower(), v.strip()) for k, v in el.attrib.items())
        if name == "compile":
            if (set(attrs) - {"include", "condition"}
                    or not _R12_PACKAGE_FILE.fullmatch(attrs.get("include", ""))):
                out.append("%s carries a Compile item that is not one package "
                           "content file" % role)
        elif name == "import":
            proj = attrs.get("project", "")
            if (set(attrs) - {"project", "condition"}
                    or not _R12_PACKAGE_FILE.fullmatch(proj)
                    or not proj.lower().endswith((".props", ".targets"))):
                out.append("%s carries an Import that is not one package build "
                           "file" % role)
    return out


# ROUND 13 (R12R-L1, R12R-L2) -- THE ITEM TYPE AN OUTPUT NAMES, READ AS
# MSBUILD READS IT, ON ANY ELEMENT.  MSBuild names an output's item type in
# two places: a task's `<Output ItemName="..." />`, and an item's
# OutputItemType metadata -- a ProjectReference with OutputItemType adds what
# the referenced project returns to the items of that type, and an
# ItemDefinitionGroup can give every such reference that metadata by default.
# Either can be an attribute or a child element, and either is parsed, so a
# character reference in it is decoded.  `_r13_output_item_types` reads, from
# any element, every attribute named ItemName or OutputItemType and the text
# of an element so named, in any letter case and without its namespace;
# `_r13_item_type_is` compares a value with its surrounding space dropped, in
# any letter case, after every `%XX` escape is decoded -- so the comparison
# does not depend on whether MSBuild decodes one there -- and a value carrying
# an expansion (`$(`, `@(`, `%(`), before or after that decoding, is taken to
# name the type, as this reading does not evaluate it.
_R13_OUTPUT_TYPE_NAMES = ("itemname", "outputitemtype")


def _r13_output_item_types(el):
    """Every item type the element `el` names for an output: its ItemName and
    OutputItemType attributes, and its own text when it is an element so
    named (R12R-L1, R12R-L2)."""
    out = [v for k, v in el.attrib.items()
           if _r12_local(k).lower() in _R13_OUTPUT_TYPE_NAMES]
    if _r12_local(el.tag).lower() in _R13_OUTPUT_TYPE_NAMES:
        out.append("".join(el.itertext()))
    return out


def _r13_item_type_is(value, wanted):
    """Whether the item type `value` is one of `wanted` (lower case) as this
    reading compares it, or carries an expansion it does not evaluate."""
    decoded = _r12_msbuild_unescape(value)
    if any(x in v for v in (value, decoded) for x in _R12_MSBUILD_EXPANSION):
        return True
    return decoded.strip().lower() in wanted


# ROUND 13 (R12R-L1) -- THE GATE READS EACH FILE AS THE PARSER READS IT.  Round
# 12 ran every form's pattern over each file's raw text, so a form spelled
# with an XML character reference -- `ItemName="Com&#112;ile"`, which the
# parser, and so MSBuild, reads as Compile -- or with MSBuild's own `%XX`
# escape matched no pattern.  Each form is now also searched in two views of
# the parsed file: every element, attribute and text rendered as the parser
# reads it (references and entities decoded, comments gone, namespaces
# dropped), and that rendering with every `%XX` decoded.  A file that cannot
# be read as XML is a reason.  An output's item type is read from the parsed
# file by `_r13_output_item_types`, on any element, and is a reason when
# `_r13_item_type_is` finds it names the Compile or Analyzer items or carries
# an expansion.
def _r13_msbuild_views(role, path):
    """((the file as parsed, the same with every %XX decoded), root, []) for
    the MSBuild file at `path`; ((), None, [reason]) when it cannot be read
    as XML (R12R-L1)."""
    try:
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError) as exc:
        return (), None, ["%s could not be read as XML (%s)"
                          % (role, type(exc).__name__)]
    said = []
    for el in root.iter():
        said.append("<" + _r12_local(el.tag) + "".join(
            ' %s="%s"' % (_r12_local(k), v) for k, v in el.attrib.items()) + ">")
        said.append(el.text or "")
        said.append(el.tail or "")
    said = LF.join(said)
    return (said, _r12_msbuild_unescape(said)), root, []


def _r12_authority_text_reasons_round12(text):
    """THE ROUND-12 READING of one file, the same in behaviour: every form's
    pattern over the raw text, the output pattern among them.  Kept ONLY so
    `test_r12cl1_...` can show the spellings it did not see; nothing else
    calls it."""
    return [label for label, rx in _R12_AUTHORITY_FORMS + (_R12_OUTPUT_FORM_ROUND12,)
            if rx.search(text)]


def _r12_compile_authority_problems(plugin_dir):
    """[reason] -- why the SDK default compile glob is NOT the authority for
    what the project in `plugin_dir` compiles; [] when it is (R11-L1; R12CL1
    for the files MSBuild reads besides the project file; R12R-L1 for each
    file read as the parser reads it, not only as its raw text)."""
    plugin_dir = pathlib.Path(plugin_dir)
    projects = sorted(p for p in plugin_dir.iterdir()
                      if p.is_file() and p.suffix.lower() == ".csproj")
    out = []
    if len(projects) != 1:
        out.append("the project folder holds %d project files, not one"
                   % len(projects))
    files, listing = _r12_msbuild_files(plugin_dir, projects)
    out.extend(listing)
    for role, p, kind in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            out.append("%s could not be read (%s)" % (role, type(exc).__name__))
            continue
        if kind == "project" and not _R12_SDK_PROJECT.search(text):
            out.append("the project file is not SDK-style")
        views, root, unread = _r13_msbuild_views(role, p)
        out.extend(unread)
        for label, rx in _R12_AUTHORITY_FORMS:
            if kind == "nuget" and label in _R12_NUGET_SHAPED:
                continue
            if any(rx.search(v) for v in (text,) + views):
                out.append("%s carries %s" % (role, label))
        if root is not None and any(
                _r13_item_type_is(v, _R13_AUTHORITY_ITEM_TYPES)
                for el in root.iter() for v in _r13_output_item_types(el)):
            out.append("%s carries an output into the Compile or Analyzer items"
                       % role)
        if kind == "nuget":
            out.extend(_r12_nuget_shape_problems(role, p))
    here = plugin_dir.resolve()
    for level, folder in enumerate([here] + list(here.parents)):
        for name in _R12_BUILD_FILES:
            if (folder / name).exists():
                out.append("a %s stands %s" % (
                    name, "in the project folder" if level == 0 else
                    "%d folder(s) above the project folder" % level))
    return out


def _r12_compile_authority_problems_first_pass(plugin_dir):
    """THE FIRST-PASS GATE, verbatim in behaviour: the project file and the
    two Directory.Build files only.  Kept ONLY so `test_r12cl1_...` can show
    what it did not read; nothing else calls it."""
    plugin_dir = pathlib.Path(plugin_dir)
    projects = sorted(p for p in plugin_dir.iterdir()
                      if p.is_file() and p.suffix.lower() == ".csproj")
    out = []
    if len(projects) != 1:
        out.append("the project folder holds %d project files, not one"
                   % len(projects))
    for p in projects:
        text = p.read_text(encoding="utf-8")
        if not _R12_SDK_PROJECT.search(text):
            out.append("the project file is not SDK-style")
        for label, rx in _R12_AUTHORITY_FORMS[:5]:
            if rx.search(text):
                out.append("the project file carries " + label)
    here = plugin_dir.resolve()
    for level, folder in enumerate([here] + list(here.parents)):
        for name in _R12_BUILD_FILES[:2]:
            if (folder / name).exists():
                out.append("a %s stands %s" % (
                    name, "in the project folder" if level == 0 else
                    "%d folder(s) above the project folder" % level))
    return out


def _r12_excluded_dir(rel_base, name):
    """Whether the folder `name`, inside `rel_base` (relative to plugin/), is
    outside the default compile glob: a dot folder at any depth, or plugin/'s
    own bin or obj folder (this file system ignores letter case)."""
    return name.startswith(".") or (
        rel_base == pathlib.Path(".") and name.lower() in _R12_EXCLUDED_TOP)


def _r12_walk_error(exc):
    raise exc


def _r12_compile_sources(plugin_dir=None):
    """{path relative to plugin/: text} for EVERY source the project
    compiles, walked recursively under the SDK default compile glob; raises
    when the glob is not the authority or a folder cannot be listed (R11-L1).
    `plugin_dir` is handed in only by the R11-L1 test; otherwise plugin/."""
    plugin_dir = pathlib.Path(PLUGIN if plugin_dir is None else plugin_dir)
    problems = _r12_compile_authority_problems(plugin_dir)
    if problems:
        raise AssertionError("the plugin's compile set is not the default "
                             "compile glob: " + "; ".join(problems))
    out = {}
    for base, dirs, files in os.walk(plugin_dir, onerror=_r12_walk_error):
        rel_base = pathlib.Path(base).relative_to(plugin_dir)
        dirs[:] = sorted(d for d in dirs if not _r12_excluded_dir(rel_base, d))
        for f in sorted(files):
            if f.lower().endswith(".cs"):
                rel = (rel_base / f).as_posix()
                out[rel] = (pathlib.Path(base) / f).read_text(encoding="utf-8")
    return dict(sorted(out.items()))


def _r12_round11_map(plugin_dir):
    """THE ROUND-11 MAP, verbatim in behaviour: plugin/'s top level only,
    keyed by file name.  Kept ONLY so `test_r12_l1_...` can show what it
    missed; nothing else calls it."""
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(pathlib.Path(plugin_dir).glob("*.cs"))}


def _all_sources():
    """{path relative to plugin/: text} for every compiled plugin source: the
    caller census reads the compile set, never a listing (R11-L1)."""
    return _r12_compile_sources()


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
        # L3 (round 9): the domination rests on today's single merge, and the
        # comment names the three changes that would end it.  Each one is its
        # own requirement, so deleting any one of them reddens this.
        for clause in _R9_DOMINATION_ENDERS:
            if clause not in head:
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

    # L3 (round 9): each domination-ending clause, deleted on its own, reddens
    # the claim; rewording the sentence that joins them does not.
    flat = _flat_comment(ra[:ra.index("internal static class DcReportSync")])
    for clause in _R9_DOMINATION_ENDERS:
        assert flat.count(clause) == 1, clause
        assert not claim(_r9_drop_clause(ra, clause)), (
            "the claim survives the deletion of: " + clause)
    assert claim(_mutate(ra, "and on nothing stronger", "and on nothing firmer",
                         "L3 twin: the joining sentence reworded"))


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

    # L9 (round 9): THE COVERAGE IS ASSERTED, NOT DESCRIBED.  The record's own
    # field set must equal the set this function verifies; an extra, missing or
    # repeated field is a refusal naming it.
    uncovered = _r9_provenance_coverage(record)
    if uncovered:
        return False, uncovered
    if not _FROZEN_SOURCE_LINES.endswith(" of " + _FROZEN_SOURCE_SPLIT_ELEMENTS):
        return False, "the recorded range and element count disagree"

    for name, want in (("extract-path", _FROZEN_SERVER_EXTRACT_REL),
                       ("extract-sha256", _FROZEN_SERVER_EXTRACT_SHA256),
                       ("body-sha256", _FROZEN_BODY_SHA256),
                       ("source", _FROZEN_SOURCE),
                       ("source-bytes", _FROZEN_SOURCE_BYTES),
                       ("source-sha256-bytes", _FROZEN_SOURCE_SHA256_BYTES),
                       ("source-sha256-lf", _FROZEN_SOURCE_SHA256_LF),
                       ("source-split-elements", _FROZEN_SOURCE_SPLIT_ELEMENTS),
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

    # 6. AND THE LIVE RESOLUTION AGREES.  On this branch, and on any tree it is
    #    merged into, only the hash-verified extract answers: the resolver reads
    #    that one file.  At merge the integrator deletes the extract and its
    #    digest constant and re-points this harness at the merged
    #    backend/api/main.py by hand -- an open item for the integrator, not
    #    something this resolver does.  The resolved text is the one the
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

    WHAT WAS WRONG.  The sealed extract's header carries a merge paragraph,
    quoted under its supersession heading in the provenance record, that
    describes, in the present tense, the candidate ordering the round-7 finding
    was raised about and this round removed:
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

# R9-L4 (round 10): THE QUALIFIER IS PART OF THE LAYOUT.  A form that puts a
# keyword before the name (`++`, `ref`, `out`, `Interlocked.X(ref`) used to
# admit only the literal `ApiClient.` between them, so the same write spelled
# `ref ApiClient` + line break + `.LastSeriesT1Wins`, or with the namespace in
# front, was not a write.  The qualifier is now any chain of identifiers and
# dots, with any whitespace around each dot and an optional `global::`, so a
# write is recognised however its qualified name is spelled or wrapped.  It is
# deliberately wide: another object's member with the same name is counted too,
# which can only add to the census, never hide a writer from it.
_R10_QUALIFIER = r"(?:global\s*::\s*)?(?:[A-Za-z_][A-Za-z0-9_]*\s*\.\s*)*"

# Every way C# changes a value, not just `=`: compound assignment and
# increment/decrement are writes, and the round-7 census matched neither.  `=`
# is guarded against `==` and, because the name must sit immediately before the
# operator, `<=`, `>=` and `!=` cannot reach it.
_R7_ASSIGN = re.compile(
    r"(?:ApiClient\.)?(?:" + "|".join(_R7_BANNER_INPUTS) + r")\s*"
    r"(?:(?:\+|-|\*|/|%|\||&|\^|<<|>>|\?\?)?=(?!=)|\+\+|--)")
_R7_PRE_INCDEC = re.compile(
    r"(?:\+\+|--)\s*" + _R10_QUALIFIER
    + r"(?:" + "|".join(_R7_BANNER_INPUTS) + r")\b")
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
    r"\b(?:ref|out)\s+" + _R10_QUALIFIER
    + r"(?:" + "|".join(_R7_BANNER_INPUTS) + r")\b")

# The API-mediated writers, named as their own class so the rejection is
# greppable rather than implied by the rule above.  Every one of them reaches
# the value through `ref`, which is why the two overlap; a census may recognise
# a form twice, and naming the class is what makes its absence checkable.
_R8_API_WRITE = re.compile(
    r"\b(?:Interlocked|Volatile)\s*\.\s*\w+\s*\(\s*ref\s+"
    + _R10_QUALIFIER + r"(?:" + "|".join(_R7_BANNER_INPUTS) + r")\b")


def _r7_plugin_sources():
    """{key: text} for EVERY C# source in the plugin, resolved at run time.

    The round-7 census read ApiClient.cs alone while the banner's inputs are
    `public static`, so a writer in NativeUI.cs, Plugin.cs or any file added
    later was outside the scan and the check would have stayed green on the
    case it exists to catch.  Globbing rather than listing the files means a
    NEW file joins the census by existing (#330: sweep the siblings).

    Round 12 (R11-L1): that glob read plugin/'s top level only and keyed each
    source by its name; the census now reads the compile set -- every
    compiled source, in any subfolder, keyed by its path relative to
    plugin/."""
    return dict(_r12_compile_sources())


_R8_DECL_HEAD = re.compile(
    r"^\s*(?:(?:public|private|internal|protected|static|readonly|const|"
    r"volatile|new|partial)\s+)+[A-Za-z_][A-Za-z0-9_<>\[\],.?]*\s+$")


# R9-L4 (round 10): A WRITE IS A STATEMENT, NOT A PHYSICAL LINE.  The round-9
# census applied the write grammar to each physical line on its own, so a name,
# its operator and its value split across a line break were never one write.
# Every form above lets the gap between its parts be any whitespace -- the
# qualifier's dots included, since this round -- and what kept a split write
# invisible was the per-line loop.  The same forms now
# run over the WHOLE text of each source with its comments blanked (offsets and
# line numbers kept), so the gap may cross any number of line breaks and a
# comment inside it is blank space.  String literals are NOT blanked, exactly
# as before: an interpolation hole can hold a write, so the census stays as
# wide over literals as it was.
#
# A declaration is recognised on its whole STATEMENT head -- back to the
# previous `;`, `{` or `}` -- rather than on its physical line.  The shape rule
# is round 8's (modifiers, then a type, then the name, with no call before the
# name), which replaced an exclusion that dropped every line carrying the word
# `static` and so discarded the one-line static method a write can sit in
# (R8-L11a, #441).  On the statement head, a declaration wrapped after its type
# is still a declaration, and a write that follows a declaration's own
# initialiser on the same line is still a write.
_R10_WRITE_FORMS = (
    _R7_ASSIGN, _R7_PRE_INCDEC, _R7_SET_WRITE,
    _R8_REF_OUT_WRITE,
    _R8_API_WRITE)
_R10_ANY_NAME = re.compile(
    "(?:" + "|".join(_R7_BANNER_INPUTS) + ")|" + _R7_BANNER_LATCH)


def _r10_blank_comments(text):
    """`text` with every comment replaced by spaces, line breaks kept."""
    comments, _literals = _cs_lex(text)
    if not comments:
        return text
    parts, pos = [], 0
    for s, e in comments:
        parts.append(text[pos:s])
        seg = text[s:e]
        parts.append(re.sub(r"[^\n]", " ", seg) if LF in seg else " " * (e - s))
        pos = e
    parts.append(text[pos:])
    return "".join(parts)


def _r10_statement_head(code, at):
    """The statement text before offset `at`, back to the previous `;`, `{` or
    `}`, with attribute groups removed and whitespace collapsed."""
    j = at - 1
    while j >= 0 and code[j] not in ";{}":
        j -= 1
    head = re.sub(r"\[[^\[\]]*\]", " ", code[j + 1:at])
    return " ".join(head.split())


def _r10_is_declaration(code, at):
    head = _r10_statement_head(code, at)
    if "(" in head or "=" in head:
        return False
    return bool(_R8_DECL_HEAD.match(head + " "))


@functools.lru_cache(maxsize=1024)
def _r10_scalar_writers_in(fname, text):
    """((file, line, text), ...) for every non-tuple write of a banner input in
    one source, found over its whole comment-blanked text."""
    if ("LastSeries" not in text and "activeTeamSeriesId" not in text
            and _R7_BANNER_LATCH not in text):
        return ()
    code = _r10_blank_comments(text)
    lines = text.split(LF)
    seen, out = set(), []
    for rx in _R10_WRITE_FORMS:
        for m in rx.finditer(code):
            name = _R10_ANY_NAME.search(code, m.start(), m.end())
            at = name.start() if name else m.start()
            if _r10_is_declaration(code, at):
                continue
            ln = _cs_line(code, at)
            if ln in seen:
                continue
            seen.add(ln)
            out.append((fname, ln, lines[ln - 1].strip()))
    return tuple(sorted(out, key=lambda w: w[1]))


def _r7_writer_lines(sources):
    """Every (file, line, text) in `sources` that CHANGES a banner input.

    Declarations are excluded -- a field's own declaration is not a writer, and
    it is recognised by its statement head (R9-L4).  `sources` is a {name:
    text} map so a control can put a writer in another file without touching
    the tree.  The line reported is the line the NAME sits on."""
    if not isinstance(sources, dict):
        sources = {"ApiClient.cs": sources}
    out = []
    for fname in sorted(sources):
        out.extend(_r10_scalar_writers_in(fname, sources[fname]))
    # L10 (round 9): tuple and deconstruction assignment, found over the whole
    # text so a target list that wraps a line is still one write
    have = set((f, i) for f, i, _ in out)
    for f, i, s in _r9_tuple_writer_lines(sources):
        if (f, i) not in have:
            out.append((f, i, s))
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
    # L10 (round 9): a writer is inside a path when its (file, line) lies in
    # that path's LINE SPAN, located by offset -- never because its text
    # occurs somewhere inside one.
    outside = _r9_writers_outside_paths(writers, api)
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


# ROUND 13 -- OWED TO THIS LANE BY THE SERVER LANE'S ROUND-9 REVIEW (OI-2,
# OI-4).  The server lane's round-9 notes, R9.2, list the client rows its
# contract expects; two of them this lane had not answered.  OI-2: the
# three-value passage's false row said that two of the five exits answering
# false settle the series without naming which two.  OI-4: the deferral
# paragraph named the sweep and a later real-totals report as what closes a
# deferred row, while three more server paths -- its revival and resume
# funnels and its room-issue clear -- end a deferral by clearing the row's
# marker.  Each sentence below is read from SendTeamSeriesDcReport's own
# text with its comment wrapping removed, so a reflow cannot turn the check
# (#342), and counted within that method, never file-wide (#330, #279).
_R13_OI2_NAMED = (
    "of the five exits that answer false, two settle the series (the "
    "lead-forfeit completion and the dc_incomplete settle) and the other three "
    "(the settled-row exit and the two room fences) write nothing and say so "
    'with "ignored": true')
# the round-12 wording of the same row, which named neither set
_R13_OI2_UNNAMED = "two settle the series and the other three write nothing"
_R13_OI4_ENDS = (
    "three more paths end a deferral: the server's revival and resume funnels "
    "and its room-issue clear, each of which clears the row's deferred marker")
_R13_OI4_NOT_SETTLED = (
    "A deferral that ends that way ends without this report settling anything, "
    'so "the deferral ended" is not "the series settled" either')
# the false row as round 12 wrote it and as this round writes it, line by
# line, and the paragraph this round adds: the pre-fix shape is the control
# (#391)
_R13_OI2_ROW_ROUND12 = (
    'of the five exits that answer false,',
    'two settle the series and the other',
    'three write nothing and say so with an',
    '"ignored" key in the same body')
_R13_OI2_ROW_NOW = (
    'of the five exits that answer false,',
    'two settle the series (the',
    'lead-forfeit completion and the',
    'dc_incomplete settle) and the other',
    'three (the settled-row exit and the',
    'two room fences) write nothing and',
    'say so with "ignored": true in the',
    'same body')
_R13_OI4_LINES = (
    '',
    'AND A DEFERRAL CAN END WITHOUT BEING SETTLED -- the round-13',
    "addition, owed to this lane by the server lane's round-9 review",
    '(OI-4). Besides the sweep and a later real-totals report, three',
    "more paths end a deferral: the server's revival and resume",
    'funnels and its room-issue clear, each of which clears the',
    "row's deferred marker. A deferral that ends that way ends",
    'without this report settling anything, so "the deferral ended"',
    'is not "the series settled" either, and nothing in this process',
    'observes which path ended it.')
_R13_OI_GUTTER = " " * 20 + "//" + " " * 22


def _r13_oi_rows(rows):
    """The false row's continuation lines as the source writes them."""
    return LF.join(_R13_OI_GUTTER + r for r in rows)


def _r13_oi4_paragraph():
    """The paragraph this round adds, as the source writes it."""
    return LF.join(" " * 20 + "//" + (" " + x if x else "")
                   for x in _R13_OI4_LINES)


def _r13_oi_claim(s):
    """Whether SendTeamSeriesDcReport's text names the false row's exits on
    both sides and every path that ends a deferral, each once, and not the
    round-12 row."""
    body = _method_body(s, "private static IEnumerator SendTeamSeriesDcReport")
    if not body:
        return False
    flat = _flat_comment(body)
    return (flat.count(_R13_OI2_NAMED) == 1
            and _R13_OI2_UNNAMED not in flat
            and flat.count(_R13_OI4_ENDS) == 1
            and flat.count(_R13_OI4_NOT_SETTLED) == 1)


def test_r13_oi2_oi4_the_false_row_names_its_exits_and_every_path_that_ends_a_deferral():
    """OI-2 and OI-4, owed to this lane by the server lane's round-9 review
    (its R8-L9 and residual 33), answered this round as additions.

    The three-value passage's false row names the two exits that settle the
    series and the three that write nothing, as the contract's definition
    beside it names the three; the deferral paragraph names the three
    server paths that end a deferral without this report settling
    anything, besides the sweep and a later real-totals report.  The
    round-12 row, the row with its settling exits unnamed, the paragraph
    as round 12 left it and the paragraph naming one path fewer each fail
    the check; rewording a neighbouring clause does not."""
    api = _src("ApiClient.cs")
    assert _r13_oi_claim(api), "the false row or the deferral paragraph is not as required"
    now = _r13_oi_rows(_R13_OI2_ROW_NOW)
    para = _r13_oi4_paragraph()
    assert api.count(now) == 1, "the false row is not written as this round wrote it"
    assert api.count(para) == 1, "the paragraph is not written as this round wrote it"

    _assert_discriminating(
        _r13_oi_claim, api,
        _mutate(api, now, _r13_oi_rows(_R13_OI2_ROW_ROUND12),
                "R13-OI2a the false row as round 12 wrote it"),
        "R13-OI2a the false row names the exits on both sides")
    _assert_discriminating(
        _r13_oi_claim, api,
        _mutate(api, "two settle the series (the" + LF + _R13_OI_GUTTER
                + "lead-forfeit completion and the" + LF + _R13_OI_GUTTER
                + "dc_incomplete settle) and the other",
                "two settle the series and the other",
                "R13-OI2b the settling exits unnamed"),
        "R13-OI2b the false row names the two exits that settle")
    _assert_discriminating(
        _r13_oi_claim, api,
        _mutate(api, LF + para, "", "R13-OI4a the paragraph as round 12 left it"),
        "R13-OI4a the paths that end a deferral are named")
    _assert_discriminating(
        _r13_oi_claim, api,
        _mutate(api, "three" + LF + " " * 20 + "// more paths end a deferral: the "
                "server's revival and resume" + LF + " " * 20 + "// funnels and "
                "its room-issue clear,",
                "two" + LF + " " * 20 + "// more paths end a deferral: the "
                "server's revival and resume" + LF + " " * 20 + "// funnels,",
                "R13-OI4b the room-issue clear left out"),
        "R13-OI4b every path that ends a deferral is named")

    # INERT TWINS: rewording a neighbouring clause keeps the claim
    assert _r13_oi_claim(_mutate(api, "claim that this call settled anything:",
                                 "claim that the call settled anything:",
                                 "R13-OI2 inert twin"))
    assert _r13_oi_claim(_mutate(api, "// observes which path ended it.",
                                 "// sees which path ended it.",
                                 "R13-OI4 inert twin"))
    print("R13-OI2 FALSE ROW: the two exits that settle and the three that "
          "write nothing named once each in SendTeamSeriesDcReport; R13-OI4 "
          "DEFERRAL: the revival and resume funnels and the room-issue clear "
          "named once as paths that end a deferral without settling")


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
    body7 = inspect.getsource(_r7_plugin_sources)
    assert body7.count("_r12_compile_sources(") == 1, body7
    assert 'glob("*.cs")' not in body7, body7


# ── B18, RE-EXECUTED RATHER THAN INHERITED (#308) ──────────────────────────
# Round 6 reported B18 MET on prose alone: two canonicals read as identical and
# a configuration read as unchanged.  A row whose evidence is a careful reading
# is the defect L1 named one row over, so the row now has a check that can go
# red, on both lanes and on the build configuration.
#
# R9-L3 (round 10): THE ROLES THEMSELVES, IN ORDER.  The round-7 check reduced
# every placeholder of both canonicals to an identical `{}` and compared the
# skeletons, which proves the COUNT of the parts and the literal tail and
# nothing about which value sits in which position: a server-only swap of the
# reporter and the series stayed green.  The two lanes spell the same values
# with different identifiers, so the identifiers are not compared either.
# What binds a position on one lane to the same position on the other is the
# WIRE: the client puts each signed value into the request under a name, and
# the server reads that name into the variable its verifier signs.  So each
# lane's canonical is read back to the ORDERED tuple of the request names its
# positions carry, and each request name to the role the contract gives it.
# A position whose expression is not a bare value the request carries -- a
# transformed or renamed expression -- has no role and refuses.
_R10_DC_ROLES = ("reporter", "series", "disconnected-player", "dc")
_R10_WIRE_ROLE = {"reporter_steam_id": "reporter", "series_id": "series",
                  "dc_player_steam_id": "disconnected-player"}
_R10_DC_ROUTE = re.compile(
    r'@app\.post\("(/api/v1/team/series/\{[A-Za-z_]\w*\}/report-dc)"')
_R10_BARE = re.compile(r"^[A-Za-z_]\w*$")


def _r10_canonical_positions(canonical):
    """(the stripped hole expressions in order, why).  The canonical must be
    exactly `{a}:{b}:{c}:dc` -- three holes, colons between, the literal tail
    `dc` as the fourth part -- and every hole a BARE name."""
    parts = re.split(r"(\{[^{}]*\})", canonical)
    holes = [p[1:-1].strip() for p in parts if p.startswith("{")]
    lits = [p for p in parts if not p.startswith("{")]
    if len(holes) != 3 or lits != ["", ":", ":", ":dc"]:
        return None, "the canonical is not three positions and the dc tail: " + canonical
    for h in holes:
        if not _R10_BARE.match(h):
            return None, "a position carries a transformed expression: " + h
    return holes, ""


def _r10_roles_of(wires):
    roles = []
    for w in wires:
        if w not in _R10_WIRE_ROLE:
            return None, "a position carries a request name no role owns: " + str(w)
        roles.append(_R10_WIRE_ROLE[w])
    if len(set(roles)) != len(roles):
        return None, "one role fills two positions: " + repr(roles)
    return tuple(roles) + ("dc",), ""


def _r10_py_params(sig_text):
    """[(name, wire name)] of a Python def's parameters, `alias=` honoured."""
    out = []
    depth, cur, parts = 0, "", []
    for ch in sig_text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    for p in parts:
        p = p.strip()
        if not p or p.startswith("*"):
            continue
        name = re.match(r"([A-Za-z_]\w*)", p).group(1)
        alias = re.search(r'alias\s*=\s*"([^"]+)"', p)
        out.append((name, alias.group(1) if alias else name))
    return out


def _r10_py_def(server, head):
    """(parameter text, body text) of the top-level def starting at `head`."""
    i = server.find(head)
    if i < 0:
        return None, None
    j = server.find("(", i)
    depth, k = 0, j
    while k < len(server):
        if server[k] == "(":
            depth += 1
        elif server[k] == ")":
            depth -= 1
            if depth == 0:
                break
        k += 1
    colon = server.find(":" + LF, k)
    if colon < 0:
        return None, None
    # the body ends at the next line that starts in column 0
    m = re.search(r"^\S", server[colon + 2:], re.M)
    end = colon + 2 + m.start() if m else len(server)
    return server[j + 1:k], server[colon + 1:end]


def _r10_server_dc_roles(server):
    """(ordered role tuple, why) of the server lane's DC canonical, bound
    through the verifier's parameters, the route's call and the route's own
    request names."""
    vparams, vbody = _r10_py_def(server, "def _verify_team_dc_hmac(")
    if vparams is None:
        return None, "the DC verifier could not be found"
    vnames = [n for n, _ in _r10_py_params(vparams)]
    cans = re.findall(r'f"([^"]*)"\.encode\(\)', vbody)
    if len(cans) != 1:
        return None, "the verifier signs %d f-strings, not one" % len(cans)
    holes, why = _r10_canonical_positions(cans[0])
    if holes is None:
        return None, why
    route = _R10_DC_ROUTE.search(server)
    if route is None:
        return None, "the report-dc route could not be found"
    m = re.search(r"async def ([A-Za-z_]\w*)\(", server[route.end():])
    rparams, rbody = _r10_py_def(server, server[route.end() + m.start():
                                                route.end() + m.end()])
    if rparams is None:
        return None, "the report-dc route's def could not be read"
    wire_of = dict(_r10_py_params(rparams))
    calls = re.findall(r"_verify_team_dc_hmac\(([^()]*)\)", rbody)
    if len(calls) != 1:
        return None, "the route calls the DC verifier %d times, not once" % len(calls)
    args = [a.strip() for a in calls[0].split(",")]
    if len(args) != len(vnames):
        return None, "the route passes %d values to %d parameters" % (len(args), len(vnames))
    wires = []
    for h in holes:
        if h not in vnames:
            return None, "a position names no verifier parameter: " + h
        a = args[vnames.index(h)]
        if not _R10_BARE.match(a) or a not in wire_of:
            return None, "the route passes a value it did not read from the request: " + a
        wires.append(wire_of[a])
    return _r10_roles_of(wires)


def _r10_client_dc_roles(api, server):
    """(ordered role tuple, why) of this lane's DC canonical, bound through the
    request names ReportTeamSeriesDc puts each signed value under.  The path
    position is named by the SERVER route's own template, aligned segment for
    segment with the client's."""
    body = _method_body(api, "public static void ReportTeamSeriesDc(")
    if not body:
        return None, "ReportTeamSeriesDc's own text could not be delimited"
    cans = re.findall(r'ComputeHmacHex\(\$"([^"]*)"\)', body)
    if len(cans) != 1:
        return None, "the report signs %d canonicals, not one" % len(cans)
    holes, why = _r10_canonical_positions(cans[0])
    if holes is None:
        return None, why
    wire_of = {}
    for key, ident in re.findall(
            r"[?&]([a-z_]+)=\{UnityWebRequest\.EscapeURL\(\s*([A-Za-z_]\w*)\s*\)\}",
            body):
        if ident in wire_of:
            return None, "one value is sent under two request names: " + ident
        wire_of[ident] = key
    route = _R10_DC_ROUTE.search(server or "")
    path = re.search(r'\$"\{baseUrl\}(/api/v1/team/series/\{[^{}"]*\}/report-dc)"', body)
    if route is None or path is None:
        return None, "the report-dc path could not be aligned between the lanes"
    ct, st = path.group(1).split("/"), route.group(1).split("/")
    if len(ct) != len(st):
        return None, "the two report-dc paths have different shapes"
    for c, s in zip(ct, st):
        if c.startswith("{") and s.startswith("{"):
            ident = c[1:-1].strip()
            if ident in wire_of:
                return None, "one value is sent under two request names: " + ident
            wire_of[ident] = s[1:-1]
        elif c != s:
            return None, "the two report-dc paths differ at " + c
    wires = []
    for h in holes:
        if h not in wire_of:
            return None, "a signed value the request never carries: " + h
        wires.append(wire_of[h])
    return _r10_roles_of(wires)


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
      * both lanes' canonicals carry the SAME ORDERED ROLES -- reporter,
        series, disconnected player, dc -- each position bound to its role
        through the request name that carries it, the server's read out of
        the frozen extract rather than described from this lane (#341, #444,
        #635: two halves of one contract are grepped for the same literals).
        Round 7 compared placeholder skeletons, which proves the count and
        not the order (R9-L3);
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
        if len(_r7_b18_client_canonicals(api_text)) != 1:
            return False
        if len(_r7_b18_server_canonicals(server_text)) != 1:
            return False
        if _r10_client_dc_roles(api_text, server_text)[0] != _R10_DC_ROLES:
            return False
        if _r10_server_dc_roles(server_text)[0] != _R10_DC_ROLES:
            return False
        return ("<DebugType>none</DebugType>" in csproj_text
                and "<Deterministic>true</Deterministic>" in csproj_text)

    assert claim(api, server, csproj), (
        "client roles: %r; server roles: %r"
        % (_r10_client_dc_roles(api, server), _r10_server_dc_roles(server)))

    # CONTROL 1 -- a fifth field on the client half, found by the canonical's
    # shape so whitespace inside a hole does not move the control
    bad_api = re.sub(r'(ComputeHmacHex\(\$"[^"]*)(:dc"\))', r"\1:{roomId}\2",
                     api, count=1)
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


def test_r10_l3_the_dc_roles_are_bound_in_order_on_both_lanes():
    """R9-L3 (B18): the ordered roles of the DC canonical -- reporter, series,
    disconnected player, dc -- are read back on BOTH lanes and compared as a
    tuple, and the check REJECTS a permutation, one role used in place of
    another, and a transformed or renamed expression standing in for a role.

    The FIRST assertion is the tree itself, on both lanes: a role mutation
    planted in the client source reddens THIS line and nothing before it.
    The server half is the hash-verified frozen extract, which no tree
    control may edit (its digest is the binding), so the server-side
    rejections are exercised here on the text in memory."""
    api = _src("ApiClient.cs")
    server, how = _server_lane_main()
    assert server and _frozen_identity_holds(how), how
    got_c, why_c = _r10_client_dc_roles(api, server)
    got_s, why_s = _r10_server_dc_roles(server)
    assert got_c == _R10_DC_ROLES, "client roles %r -- %s" % (got_c, why_c)
    assert got_s == _R10_DC_ROLES, "server roles %r -- %s" % (got_s, why_s)
    print("R9-L3 ROLES: client %s | server %s" % (" ".join(got_c), " ".join(got_s)))

    can_c = _r7_b18_client_canonicals(api)[0]
    can_s = _r7_b18_server_canonicals(server)[0]
    hc = _r10_canonical_positions(can_c)[0]
    hs = _r10_canonical_positions(can_s)[0]

    def with_c(holes):
        new = "{" + "}:{".join(holes) + "}:dc"
        return api.replace('ComputeHmacHex($"' + can_c + '")',
                           'ComputeHmacHex($"' + new + '")', 1)

    def with_s(holes):
        new = "{" + "}:{".join(holes) + "}:dc"
        return server.replace('f"' + can_s + '".encode()', 'f"' + new + '".encode()', 1)

    # THE REMOVED REDUCTION IS BLIND TO EVERY CASE BELOW: each one keeps the
    # count of placeholders and the tail, so `{}`-skeletons stay equal.  That
    # is the RED the round-9 review named; the role tuple is what rejects them.
    def skeleton(expr):
        return re.sub(r"\{[^{}]*\}", "{}", expr)

    swapped_s = [hs[1], hs[0], hs[2]]
    rejected = {
        "server permutation": (api, with_s(swapped_s)),
        "server duplicate": (api, with_s([hs[0], hs[0], hs[2]])),
        "server transformed": (api, with_s([hs[0] + ".lower()", hs[1], hs[2]])),
        "server renamed": (api, with_s(["sid", hs[1], hs[2]])),
        "server call-site permutation": (api, server.replace(
            "_verify_team_dc_hmac(reporter_steam_id, series_id,",
            "_verify_team_dc_hmac(series_id, reporter_steam_id,", 1)),
        "client permutation": (with_c([hc[1], hc[0], hc[2]]), server),
        "client duplicate": (with_c([hc[0], hc[1], hc[0]]), server),
        "client transformed": (with_c([hc[0] + ".ToLowerInvariant()", hc[1], hc[2]]), server),
        "client renamed": (with_c(["reporterId", hc[1], hc[2]]), server),
    }
    for label, (a, s) in rejected.items():
        assert (a, s) != (api, server), label + ": the planted change did not apply"
        c_ok = _r10_client_dc_roles(a, s)[0] == _R10_DC_ROLES
        s_ok = _r10_server_dc_roles(s)[0] == _R10_DC_ROLES
        assert not (c_ok and s_ok), label + ": the role check did not reject it"
        if label in ("server permutation", "server duplicate", "client permutation",
                     "client duplicate"):
            ca = _r7_b18_client_canonicals(a)[0]
            sa = _r7_b18_server_canonicals(s)[0]
            assert skeleton(ca) == skeleton(can_c) and skeleton(sa) == skeleton(can_s), (
                label + ": the skeleton reduction was not blind here")

    # TWINS: whitespace inside a hole and a comment beside the signing site
    # keep every role and its position
    spaced_c = api.replace('ComputeHmacHex($"' + can_c + '")',
                           'ComputeHmacHex($"' + can_c.replace("{", "{ ").replace("}", " }")
                           + '")', 1)
    spaced_s = server.replace('f"' + can_s + '".encode()',
                              'f"' + can_s.replace("{", "{ ").replace("}", " }")
                              + '".encode()', 1)
    assert spaced_c != api and spaced_s != server
    assert _r10_client_dc_roles(spaced_c, spaced_s)[0] == _R10_DC_ROLES
    assert _r10_server_dc_roles(spaced_s)[0] == _R10_DC_ROLES
    commented = server.replace('f"' + can_s + '".encode(),',
                               'f"' + can_s + '".encode(),  # the canonical', 1)
    assert commented != server
    assert _r10_server_dc_roles(commented)[0] == _R10_DC_ROLES


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
    #
    # ROUND 9 (L4): the five comparison spellings this row listed are replaced
    # by the status VALUE as a complete literal in code, which every comparison
    # form needs -- static string.Equals, case labels, `is` patterns and
    # constants included.  See `_r9_dead_literal_hits`.
    ("the dead dc_paused predicate", "literal", ("dc_paused",)),
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
                if kind == "literal" or (kind == "code" and comment):
                    continue
                for needle in needles:
                    if needle in line:
                        hits.append((cls, fname, i, line.strip()))
                        break
    for cls, kind, needles in _R8_DELETED_CLASSES:
        if kind == "literal":
            for needle in needles:
                for fname, i, text in _r9_dead_literal_hits(sources, needle):
                    hits.append((cls, fname, i, text))
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

    # the file set is the compile set's, not a list that could have gone
    # stale: every top-level source is in it and every key is a file (the
    # nested half is test_r12_l1_...)
    on_disk = sorted(p.name for p in PLUGIN.glob("*.cs"))
    assert set(on_disk) <= set(names), sorted(set(on_disk) - set(names))
    assert all((PLUGIN / k).is_file() for k in names), names
    assert len(names) > 3, names

    hits = _r8_deleted_class_hits(sources)
    assert not hits, ("a deleted mechanism was found in plugin source: "
                      + repr(hits))

    # EVERY CLASS CAN FIRE, and it fires in a file neither round-7 check read.
    # The scratch source is a THIRD file, handed in through the map rather than
    # written to the tree, so nothing has to be restored afterwards.
    for cls, kind, needles in _R8_DELETED_CLASSES:
        for needle in needles:
            if kind == "literal":
                line = ("                if (string.Equals(dcStatus, " + chr(34)
                        + needle + chr(34) + ", StringComparison.Ordinal)) { }")
            elif kind == "code":
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
    outside = _r9_writers_outside_paths(writers, twinned["ApiClient.cs"])
    assert not outside, ("a write inside a repaint path was counted outside it: "
                         + repr(outside))

    # the file set is resolved, not listed
    import inspect
    body7 = inspect.getsource(_r7_plugin_sources)
    assert body7.count("_r12_compile_sources(") == 1, body7
    assert 'glob("*.cs")' not in body7, body7


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



# ══ ROUND 9: the round-8 review's findings, by number ════════════════════════
#
# The round-8 harness findings were each about whether this harness tells the
# truth about what it did, and the five closed here are five places where it
# did not: a delivered comment stated a resolver this file does not have
# (CL2), the domination check stopped short of the three changes that would
# end it (L3), the dead-status rule was a list of comparison spellings (L4),
# one provenance field was verified by nobody (L9), and writers were excused
# by their TEXT rather than by where they sit (L10).  The tool-side findings
# (H1, C6, CL3, L1, L2, L5-L8) are closed in the round-9 tools the notes name.


# ── THE C# LEXER: comments and complete string literals, by position ───────
#
# Two round-9 rules need to know what a plugin byte IS -- comment, string
# literal or code -- and a line-shape guess (`startswith("//")`) answers that
# for whole-line comments only.  This is the smallest lexer that answers it for
# every form the plugin uses: line and block comments, preprocessor lines, char
# literals, regular, verbatim and raw strings, and interpolated strings whose
# holes nest further strings (the shape `$"{(ok ? "a" : "b")}"`; ApiClient.cs
# holds about a hundred of them).  A hole is lexed as CODE, so a literal inside
# one is a literal in code.  It runs once per source text per process and is cached by
# text, because this suite is re-run once per mutation control.
#
# R10-L4 (round-10 review) -- THE HOLES OF A RAW INTERPOLATED STRING ARE CODE
# TOO.  Round 10 consumed a raw string (`"""..."""`, `$"""..."""`,
# `$$"""..."""`) whole, and when it was interpolated it recorded the literal
# with no value and never lexed its holes, so a complete literal inside one
# (`$"""{(s == "<the status>" ? 1 : 0)}"""`) was invisible to every sweep that
# reads the lexer.  A raw string with N dollars opens a hole at a run of N
# braces (a longer run's first braces are text) and closes it at N braces;
# each hole is now lexed as CODE, exactly as the holes of `$"..."` and
# `$@"..."` always were, so a literal inside it is a literal in code.  A raw
# literal without holes has its VALUE computed by the language's rule (a
# multi-line one loses its first and last line breaks and the closing line's
# indentation), so a complete literal written across lines compares as the
# value it spells.  `_cs_code_mask` exposes the same lexing as a mask of what
# is code, holes included, for the log-call exemption (R10-L3).
_CS_START = re.compile(
    r'//|/\*|^[ \t]*#|@\$+"|\$+@"|@"|\$+"""+|\$+"|"""+|"|' + "'", re.M)
_CS_HOLE_START = re.compile(
    r'//|/\*|@\$+"|\$+@"|@"|\$+"""+|\$+"|"""+|"|' + "'" + r"|[{}]")
_CS_CHAR = re.compile(
    r"'(?:\\(?:u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|x[0-9A-Fa-f]{1,4}|.)|[^'\\\r\n])'")
_CS_STR = re.compile(r'"(?:[^"\\\r\n]|\\.)*"')
_CS_VERB = re.compile(r'@"(?:[^"]|"")*"')
_CS_INTERP_SPECIAL = re.compile(r'[\\"{}\n]')
_CS_VINTERP_SPECIAL = re.compile(r'["{}]')
_CS_ESC = re.compile(
    r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|x[0-9A-Fa-f]{1,4}|.)", re.S)
_CS_SIMPLE_ESC = {"n": LF, "t": chr(9), "r": chr(13), "0": chr(0), "a": chr(7),
                  "b": chr(8), "f": chr(12), "v": chr(11), "e": chr(27)}


def _cs_unescape(raw):
    """A regular literal's VALUE: `"dc\\u005fpaused"` is the same literal."""
    if "\\" not in raw:
        return raw

    def one(m):
        e = m.group(1)
        if e[0] in "uUx" and len(e) > 1:
            return chr(int(e[1:], 16))
        return _CS_SIMPLE_ESC.get(e, e)
    return _CS_ESC.sub(one, raw)


def _cs_raw_close(text, start, quotes, dollars, comments, literals, holes):
    """(offset of the closing quote run, number of holes) of the raw string
    whose body begins at `start`, or (-1, 0) when it never closes (R10-L4).
    With `dollars` > 0 a run of at least that many braces opens a hole after
    the run; the hole is lexed as CODE by `_cs_scan` and closed by that many
    braces."""
    n = len(text)
    i, found = start, 0
    close = '"' * quotes
    while i < n:
        if text.startswith(close, i):
            return i, found
        ch = text[i]
        if dollars and ch == "{":
            j = i
            while j < n and text[j] == "{":
                j += 1
            if j - i < dollars:
                i = j                      # fewer braces than dollars: text
                continue
            found += 1
            k = _cs_scan(text, j, comments, literals, True, holes)
            if holes is not None:
                holes.append((j, k))
            i = k
            m = 0
            while i < n and text[i] == "}" and m < dollars:
                i += 1
                m += 1
            continue
        i += 1
    return -1, 0


def _cs_raw_value(body):
    """The VALUE of a raw literal without holes (R10-L4): a single-line one is
    its body; a multi-line one loses the line break after its opening quotes
    and before its closing line, and every content line loses the closing
    line's indentation."""
    if LF not in body:
        return body
    lines = body.split(LF)
    if lines[0].strip() or lines[-1].strip():
        return body
    indent = lines[-1]
    out = []
    for ln in lines[1:-1]:
        ln = ln.rstrip(chr(13))
        out.append(ln[len(indent):] if ln.startswith(indent) else ln.lstrip(" " + chr(9)))
    return LF.join(out)


def _cs_scan(text, pos, comments, literals, hole, spans=None):
    """Lex CODE from `pos`; inside an interpolation hole, stop at the brace
    that closes it and return its offset.  `spans`, when given, receives the
    (start, end) of every interpolation hole lexed, in any string form."""
    n = len(text)
    depth = 0
    pat = _CS_HOLE_START if hole else _CS_START
    while True:
        m = pat.search(text, pos)
        if m is None:
            return n
        tok = m.group()
        s = m.start()
        if tok == "{":
            depth += 1
            pos = s + 1
            continue
        if tok == "}":
            if depth == 0:
                return s
            depth -= 1
            pos = s + 1
            continue
        if tok == "//":
            e = text.find(LF, s)
            e = n if e < 0 else e
            comments.append((s, e))
            pos = e
            continue
        if tok == "/*":
            e = text.find("*/", s + 2)
            e = n if e < 0 else e + 2
            comments.append((s, e))
            pos = e
            continue
        if tok.endswith("#"):
            e = text.find(LF, s)
            pos = n if e < 0 else e
            continue
        if tok == "'":
            mm = _CS_CHAR.match(text, s)
            pos = mm.end() if mm else s + 1
            continue
        dollars = tok.count("$")
        verb = "@" in tok
        quotes = tok.count('"')
        if quotes >= 3:
            start = s + len(tok)
            e, found = _cs_raw_close(text, start, quotes, dollars, comments,
                                     literals, spans)
            if e < 0:
                pos = s + 1
                continue
            content = None if found else _cs_raw_value(text[start:e])
            literals.append((s, e + quotes, content))
            pos = e + quotes
            continue
        if not dollars:
            mm = (_CS_VERB if verb else _CS_STR).match(text, s)
            if mm is None:
                pos = s + 1
                continue
            raw = mm.group()
            content = (raw[2:-1].replace('""', '"') if verb
                       else _cs_unescape(raw[1:-1]))
            literals.append((s, mm.end(), content))
            pos = mm.end()
            continue
        special = _CS_VINTERP_SPECIAL if verb else _CS_INTERP_SPECIAL
        i = s + len(tok)
        body_start = i
        holes = 0
        end = -1
        while True:
            mm = special.search(text, i)
            if mm is None:
                break
            j = mm.start()
            ch = text[j]
            if ch == "\\":
                i = j + 2
                continue
            if ch == LF:
                break
            if ch == '"':
                if verb and text.startswith('""', j):
                    i = j + 2
                    continue
                end = j + 1
                break
            if ch == "{":
                if text.startswith("{{", j):
                    i = j + 2
                    continue
                holes += 1
                k = _cs_scan(text, j + 1, comments, literals, True, spans)
                if spans is not None:
                    spans.append((j + 1, k))
                i = k + 1
                continue
            i = j + 2 if text.startswith("}}", j) else j + 1
        if end < 0:
            pos = s + 1
            continue
        if holes:
            content = None            # not a constant: it has holes
        else:
            raw = text[body_start:end - 1]
            raw = raw.replace('""', '"') if verb else _cs_unescape(raw)
            content = raw.replace("{{", "{").replace("}}", "}")
        literals.append((s, end, content))
        pos = end


@functools.lru_cache(maxsize=512)
def _cs_lex(text):
    """(comment spans, literal spans) of one C# source.  A literal is
    (start, end, value) with value None when it has interpolation holes."""
    comments, literals = [], []
    _cs_scan(text, 0, comments, literals, False)
    comments.sort()
    literals.sort()
    return tuple(comments), tuple(literals)


def _cs_code_mask(text):
    """`text` with every comment and the TEXT of every literal blanked to
    spaces, and every interpolation hole -- of `$"..."`, `$@"..."` and raw
    interpolated strings alike -- kept as the code it is (R10-L3, R10-L4).
    Line breaks are kept, so offsets and line numbers are unchanged."""
    comments, literals, spans = [], [], []
    _cs_scan(text, 0, comments, literals, False, spans)
    events = ([(s, e, False) for s, e in comments]
              + [(s, e, False) for s, e, _c in literals]
              + [(s, e, True) for s, e in spans])
    events.sort(key=lambda t: (t[0], t[0] - t[1]))
    keep = [True] * len(text)
    for s, e, code in events:
        for k in range(s, min(e, len(text))):
            keep[k] = code
    return "".join(c if keep[k] or c == LF else " " for k, c in enumerate(text))


def _cs_span_at(spans, offset):
    """The span in `spans` that contains `offset`, or None."""
    i = bisect.bisect_right(spans, (offset, float("inf"), None)) - 1
    if i >= 0 and spans[i][0] <= offset < spans[i][1]:
        return spans[i]
    return None


def _cs_line(text, offset):
    return text.count(LF, 0, offset) + 1


# ── L3 (B8): the three changes that would end the domination ───────────────
#
# The DcReportSync head comment says the outcome quorum is dominated by the
# election quorum only while three things stay as they are, and names them.
# `test_r4lens_f3_...` requires each as its own clause, so a reflow that drops
# one reddens it rather than leaving a weaker comment standing.
_R9_DOMINATION_ENDERS = (
    "split the two writes",
    "add a caller that arms outside the census arm",
    "ship one key ahead of the other",
)


def _r9_drop_clause(src, clause):
    """`src` with the first occurrence of `clause` deleted, wherever the
    comment wraps it."""
    pat = re.compile(r"\s+(?:///\s*)?".join(re.escape(w) for w in clause.split()))
    m = pat.search(src)
    assert m, "the clause is not in the source: " + clause
    return src[:m.start()] + "(deleted)" + src[m.end():]


# ── L4 (B10): the dead status value, rejected as a COMPLETE literal in code ─
#
# WHAT WAS WRONG.  The dead-predicate class was five comparison needles, and
# `string.Equals(dcStatus, "dc_paused", StringComparison.Ordinal)` is none of
# them -- nor is a `case` label, an `is` pattern or a constant.  A list of
# spellings certifies the spellings it lists (#432).
#
# THE RULE.  No complete C# string literal in plugin CODE -- regular, verbatim,
# raw or interpolated without holes -- has the VALUE of the dead status IN ANY
# LETTER CASE.  The comparison is case-folded because a case-insensitive
# comparison (`StringComparison.OrdinalIgnoreCase`, `ToUpperInvariant() ==`)
# restores the predicate with a differently cased literal (round-9 cold lens).
# A comparison form that spells the value, in any case, needs such a literal,
# so the rule rejects those forms.  A value assembled at run time (two literals
# joined by `+`, an interpolation hole) spells no such literal and is outside
# this rule; the notes carry that as a residual.  The word itself is still
# permitted in comments and INSIDE a longer literal, which is how the client
# names the status today.
_R9_DEAD_STATUS = "dc_paused"


def _r9_dead_literal_hits(sources, value=_R9_DEAD_STATUS):
    """[(file, line, text)] for every complete literal in code whose value is
    `value` in any letter case.  Every source is lexed and every literal
    DECODED and case-folded before it is compared, so a literal spelled with an
    escape, or in capitals, is the same literal."""
    hits = []
    folded = value.casefold()
    for fname in sorted(sources):
        text = sources[fname]
        _, literals = _cs_lex(text)
        for s, e, content in literals:
            if content is not None and content.casefold() == folded:
                ln = _cs_line(text, s)
                hits.append((fname, ln, text.split(LF)[ln - 1].strip()))
    return hits


def _r9_word_census(sources, value=_R9_DEAD_STATUS):
    """[(file, line, where)] for every occurrence of the word in any letter
    case, each classified by the lexer as a comment, a longer literal, or
    code."""
    out = []
    folded = value.casefold()
    word = re.compile(re.escape(value), re.I)
    for fname in sorted(sources):
        text = sources[fname]
        if not word.search(text):
            continue
        comments, literals = _cs_lex(text)
        for m in word.finditer(text):
            o = m.start()
            if _cs_span_at(comments, o):
                where = "comment"
            else:
                lit = _cs_span_at(literals, o)
                if lit is None:
                    where = "CODE"
                elif lit[2] is not None and lit[2].casefold() == folded:
                    where = "COMPLETE LITERAL"
                else:
                    where = "inside a longer literal"
            out.append((fname, _cs_line(text, o), where))
    return out


def test_r9_l4_the_dead_status_is_rejected_as_a_complete_literal_in_code():
    """L4 (B10): THE DEAD PREDICATE IS A CLASS, AND THE CLASS IS ITS LITERAL.

    The round-8 sweep rejected five comparison spellings.  Static
    `string.Equals(x, "dc_paused", StringComparison.Ordinal)` was none of them,
    so the predicate could return in that form with the sweep green.  The rule
    now rejects the status VALUE as a complete literal anywhere in plugin code,
    in any letter case, comments excluded, over every `.cs` by glob -- so every
    comparison form that spells the value is rejected, because each one needs
    such a literal.  Round 9's cold lens: an exact-case match let
    `OrdinalIgnoreCase` against the value in capitals pass, so the literal is
    compared case-folded.  A value assembled at run time is outside the rule.  The word census is
    printed with each occurrence's classification, so the permitted uses are
    visible rather than asserted."""
    sources = _r7_plugin_sources()
    names = sorted(sources)
    assert set(p.name for p in PLUGIN.glob("*.cs")) <= set(names)
    assert all((PLUGIN / k).is_file() for k in names), names
    hits = _r9_dead_literal_hits(sources)
    census = _r9_word_census(sources)
    print("L4 COMPLETE-LITERAL SWEEP: %d plugin sources, %d complete literals"
          % (len(names), len(hits)))
    print("L4 WORD CENSUS: %d occurrences" % len(census))
    for fname, ln, where in census:
        print("  L4 WORD %s:%d %s" % (fname, ln, where))
    assert not hits, ("the dead status value is a complete literal in plugin "
                      "code: " + repr(hits))
    assert all(w in ("comment", "inside a longer literal")
               for _, _, w in census), census
    assert census, "the census found no occurrence -- the rule cannot be judged"

    def probe(line):
        return _r9_dead_literal_hits(
            {"ZzProbe.cs": "class ZzProbe {" + LF + line + LF + "}" + LF})

    q = chr(34)
    lit = q + _R9_DEAD_STATUS + q
    for form in (
            "  bool a = string.Equals(dcStatus, " + lit + ", StringComparison.Ordinal);",
            "  switch (dcStatus) { case " + lit + ": break; }",
            "  bool b = dcStatus is " + lit + ";",
            "  const string P = " + lit + ";",
            "  bool c = dcStatus == " + lit + ";",
            "  bool d = " + lit + ".Equals(dcStatus);",
            "  int e = string.Compare(dcStatus, " + lit + ");",
            "  bool f = StringComparer.Ordinal.Equals(dcStatus, " + lit + ");",
            "  bool g = dcStatus == @" + lit + ";",
            "  bool h = dcStatus == $" + lit + ";",
            "  Log($" + q + "{(dcStatus == " + lit + " ? 1 : 0)}" + q + ");",
            "  bool i = dcStatus == " + q + "dc\\u005fpaused" + q + ";",
            # ROUND-9 COLD LENS (R9CL6): the value in another letter case,
            # compared case-insensitively, is the same predicate.
            "  bool j = string.Equals(dcStatus, " + q + _R9_DEAD_STATUS.upper()
            + q + ", StringComparison.OrdinalIgnoreCase);",
            "  bool k = dcStatus.ToUpperInvariant() == " + q
            + _R9_DEAD_STATUS.upper() + q + ";",
            "  bool l = dcStatus.Equals(" + q + _R9_DEAD_STATUS.title() + q
            + ", StringComparison.OrdinalIgnoreCase);"):
        assert probe(form), "the sweep did not reject: " + form.strip()

    for permitted in (
            "  Log(" + q + "statuses (active, " + _R9_DEAD_STATUS
            + ") are accepted" + q + ");",
            "  // the old predicate compared == " + lit,
            "  /* compared == " + lit + " */",
            "  Log($" + q + "dc_{kind}" + q + ");",
            "  char c = '" + q + "'; string s = " + q + "dc" + q + ";"):
        assert not probe(permitted), "the sweep rejected: " + permitted.strip()


def test_r11_l4_the_holes_of_a_raw_interpolated_string_are_swept():
    """R10-L4 (B10): the holes of a raw interpolated string are lexed as CODE,
    so a complete dead-status literal inside one is a complete literal in
    code, and a multi-line raw literal compares as the value it spells.
    Round 10 consumed a raw string whole and recorded an interpolated one
    with no value, so every form below was invisible to the sweep."""
    q = chr(34)
    q3, q4 = q * 3, q * 4
    lit = q + _R9_DEAD_STATUS + q
    cmp_hole = "(dcStatus == " + lit + " ? 1 : 0)"

    def probe(body):
        return _r9_dead_literal_hits(
            {"ZzProbe.cs": "class ZzProbe {" + LF + body + LF + "}" + LF})

    red = {
        "a one-dollar raw hole": "  Log($" + q3 + "{" + cmp_hole + "}" + q3 + ");",
        "a two-dollar raw hole": "  Log($$" + q3 + "{{" + cmp_hole + "}}" + q3 + ");",
        "a two-dollar raw hole after a text brace":
            "  Log($$" + q3 + "{ {{" + cmp_hole + "}} }" + q3 + ");",
        "a multi-line raw hole": "  Log($" + q3 + LF + "      state {" + cmp_hole
            + "}" + LF + "      " + q3 + ");",
        "a four-quote raw hole": "  Log($" + q4 + "{" + cmp_hole + "}" + q4 + ");",
        "a raw literal in a regular hole": "  Log($" + q + "{(dcStatus == " + q3
            + _R9_DEAD_STATUS + q3 + " ? 1 : 0)}" + q + ");",
        "a multi-line raw literal": "  bool a = dcStatus == " + q3 + LF + "      "
            + _R9_DEAD_STATUS + LF + "      " + q3 + ";",
        "a raw hole inside a raw hole": "  Log($" + q3 + "{Wrap($" + q3 + "{"
            + cmp_hole + "}" + q3 + ")}" + q3 + ");",
    }
    for label, body in red.items():
        hits = probe(body)
        assert hits, "the sweep did not reject " + label + ": " + body.strip()
        print("R10-L4 REJECTED %s: %s" % (label, hits[0][2]))

    inert = {
        "an inert one-dollar raw hole": "  Log($" + q3 + "{dcStatus.Length}" + q3 + ");",
        "an inert two-dollar raw hole": "  Log($$" + q3 + "{{dcStatus}} {x}" + q3 + ");",
        "the word inside a longer raw literal": "  Log(" + q3 + "statuses (active, "
            + _R9_DEAD_STATUS + ") are accepted" + q3 + ");",
        "the word as raw text around a hole": "  Log($" + q3 + _R9_DEAD_STATUS
            + " {n}" + q3 + ");",
        "a multi-line raw literal holding more than the word": "  Log(" + q3 + LF
            + "      " + _R9_DEAD_STATUS + LF + "      and more" + LF + "      " + q3 + ");",
    }
    for label, body in inert.items():
        assert not probe(body), "the sweep rejected " + label + ": " + body.strip()

    # the holes are CODE to the mask as well (the log-call exemption reads it)
    masked = _cs_code_mask("Log($" + q3 + "{Zz(1)} text" + q3 + ");")
    assert "Zz(1)" in masked and "text" not in masked, masked
    print("R10-L4 RAW HOLES: %d forms rejected, %d inert forms accepted"
          % (len(red), len(inert)))


# ── L10 (B19): writers classified by WHERE they sit, tuple forms included ───
#
# WHAT WAS WRONG.  A writer was excused when its TEXT occurred inside any
# permitted repaint path, so a second `LastSeriesT1Wins = 0;` anywhere else in
# ApiClient.cs was excused by the identical valid line in the id setter.  And
# the write grammar had no tuple or deconstruction form.
#
# THE RULE.  Each repaint path is located by its OFFSETS at run time and turned
# into a line span; a writer is inside only when its (file, line) falls in one
# of those spans.  Text equality decides nothing.
#
# WHICH GROUP IS A LEFT SIDE, BY TOKEN (round-9 cold lens).  A group before
# `=` is the left side of an assignment when the TOKEN before its `(` lets an
# expression begin there.  The round-8 rule looked at one CHARACTER and dropped
# `() => (a, b) = ...` (a `>`), `else (a, b) = ...` and `do (a, b) = ...` (a
# letter).  The token rule: nothing, or any punctuator other than `]` and a
# lone `>`, or the arrow `=>`, or one of _R9_EXPR_KEYWORDS, begins an
# expression.  Any other identifier makes the group a call (`f(a) = ...`) or a
# declaration (`var (a, b) = ...`); `]` an indexer or attribute; a lone `>` a
# generic argument list.  Comments between the token and the group are
# skipped, so a comment that ends in a word decides nothing.
_R9_TUPLE_END = re.compile(r"\)\s*=(?![=>])")
_R9_EXPR_KEYWORDS = frozenset(("return", "else", "do", "yield", "await", "in"))


def _r9_group_starts_expression(text, i, comments):
    """True when the token before the `(` at offset `i` lets an expression
    begin there (see the rule above)."""
    j = i - 1
    while j >= 0:
        if text[j].isspace():
            j -= 1
            continue
        c = _cs_span_at(comments, j)
        if c is not None:
            j = c[0] - 1
            continue
        break
    if j < 0:
        return True
    ch = text[j]
    if ch == ">":
        return j >= 1 and text[j - 1] == "="
    if ch == "]":
        return False
    if ch.isalnum() or ch == "_":
        k = j
        while k >= 0 and (text[k].isalnum() or text[k] == "_"):
            k -= 1
        if k >= 0 and text[k] == "@":
            return False
        return text[k + 1:j + 1] in _R9_EXPR_KEYWORDS
    return True


_R9_BANNER_NAMES = "|".join(_R7_BANNER_INPUTS + (_R7_BANNER_LATCH,))
_R9_BANNER_NAME = re.compile(r"\b(?:" + _R9_BANNER_NAMES + r")\b")
_R9_BANNER_TARGET = re.compile(r"^" + _R10_QUALIFIER + r"(?:" + _R9_BANNER_NAMES + r")$")


def _r9_tuple_writer_lines(sources):
    """[(file, line, text)] for every tuple or deconstruction assignment whose
    targets include a banner input.  A target that is itself a declaration
    (`var x`, `int x`) declares a new local and is not a write; the match must
    sit in code, not in a comment or a literal.  Cached per source text,
    because the census is re-taken once per planted case."""
    out = []
    for fname in sorted(sources):
        out.extend(_r9_tuple_writers_in(fname, sources[fname]))
    return out


@functools.lru_cache(maxsize=1024)
def _r9_tuple_writers_in(fname, text):
    # Every assignment whose left side ENDS in a closing parenthesis is a
    # candidate; there are a few dozen in the whole plugin, so the search
    # starts from them rather than from each banner-input name.
    out = []
    if ("LastSeries" not in text and "activeTeamSeriesId" not in text
            and _R7_BANNER_LATCH not in text):
        return ()
    comments = literals = code = None
    for end in _R9_TUPLE_END.finditer(text):
        close = end.start()
        if comments is None:
            comments, literals = _cs_lex(text)
            code = _r10_blank_comments(text)
        if _cs_span_at(comments, close) or _cs_span_at(literals, close):
            continue
        # R9-L4 (round 10): THE GROUP IS MATCHED BY BALANCE, WITH NO CAP.  The
        # round-9 walk gave up 600 characters back, so a longer left side was
        # invisible wherever it sat, and its pattern admitted one level of
        # nesting.  The walk now runs back to the `(` that balances this `)`
        # however far that is, stopping only at a `;`, `{` or `}` in code, and
        # a comment or a literal inside the group is stepped over whole, so a
        # `;` or a paren inside one cannot end the walk early.
        depth, i = 0, close
        while i >= 0:
            span = _cs_span_at(comments, i) or _cs_span_at(literals, i)
            if span is not None:
                i = span[0] - 1
                continue
            ch = text[i]
            if ch == ")":
                depth += 1
            elif ch == "(":
                depth -= 1
                if depth == 0:
                    break
            elif ch in ";{}":
                i = -1
                break
            i -= 1
        if i < 0 or depth != 0:
            continue
        # every element at every depth of nesting, comments blanked; a typed
        # element (`int a`) declares a local and simply fails the target match
        inner = code[i + 1:close]
        elems = [x.strip() for x in
                 inner.replace("(", " ").replace(")", " ").split(",")]
        if not any(_R9_BANNER_TARGET.match(x) for x in elems):
            continue
        if not _r9_group_starts_expression(text, i, comments):
            continue
        name = _R9_BANNER_NAME.search(code, i, close)
        ln = _cs_line(text, name.start() if name else i)
        out.append((fname, ln, text.split(LF)[ln - 1].strip()))
    return tuple(out)


def _r9_repaint_line_spans(api):
    """{path name: (first line, last line)} for every repaint path, located by
    OFFSET in `api` -- the same spans `_r7_repaint_paths` returns as text, which
    the L10 test asserts character for character."""
    spans = {}
    a = api.find("        public static string ActiveTeamSeriesId")
    b = api.find("        public static bool IsTeamQueuePolling", a) if a >= 0 else -1
    spans["the id setter"] = (a, b)
    sig = "public static void PollTeamSeriesStatusReadOnly"
    poller = _method_body(api, sig)
    p = api.find(sig) if poller else -1
    r = poller.find("if (!affirmed)") if poller else -1
    e = poller.find("return;", r) if r >= 0 else -1
    spans["the refusal path (and the timeout)"] = (
        (p + r, p + e + len("return;")) if (p >= 0 and r >= 0 and e >= 0)
        else (-1, -1))
    d = poller.find("catch (Exception ex)") if poller else -1
    spans["the dispatch-throw path"] = ((p + d, p + len(poller))
                                        if (p >= 0 and d >= 0) else (-1, -1))
    sig2 = "private static void ApplySeriesStateResponse"
    parse = _method_body(api, sig2)
    q = api.find(sig2) if parse else -1
    spans["the shared parse"] = (q, q + len(parse)) if q >= 0 else (-1, -1)
    out = {}
    for name, (s, t) in spans.items():
        if s < 0 or t <= s:
            out[name] = None
            continue
        out[name] = (_cs_line(api, s), _cs_line(api, t - 1), s, t)
    return out


def _r9_writers_outside_paths(writers, api):
    """The writers whose (file, line) lies in NO repaint path's line span."""
    spans = [v for v in _r9_repaint_line_spans(api).values() if v]
    return [w for w in writers
            if not (w[0] == "ApiClient.cs"
                    and any(lo <= w[1] <= hi for lo, hi, _, _ in spans))]


def test_r9_l10_writers_are_classified_by_source_location():
    """L10 (B19): A WRITER IS INSIDE A PATH BY LOCATION, NEVER BY TEXT.

    The round-8 census excused a writer whose text occurred in any permitted
    span, so an identical line elsewhere in the file was excused by the valid
    one.  Each span is now located by its offsets and turned into a line span,
    and the spans are asserted equal, character for character, to the text
    spans the repaint-count assertions read -- one location, two uses.  The
    census also recognises tuple and deconstruction assignment."""
    api = _src("ApiClient.cs")
    text_spans = _r7_repaint_paths(api)
    line_spans = _r9_repaint_line_spans(api)
    assert set(text_spans) == set(line_spans), (sorted(text_spans), sorted(line_spans))
    for name, span in line_spans.items():
        assert span, "the span for " + name + " could not be located"
        lo, hi, s, t = span
        assert api[s:t] == text_spans[name], (
            name + ": the located span is not the span the repaint count reads")
        print("L10 SPAN %s: ApiClient.cs:%d-%d" % (name, lo, hi))

    sources = _r7_plugin_sources()
    writers = _r7_writer_lines(sources)
    outside = _r9_writers_outside_paths(writers, api)
    print("L10 CENSUS: %d writer lines, %d outside every span, %d tuple writers"
          % (len(writers), len(outside), len(_r9_tuple_writer_lines(sources))))
    assert not outside, outside

    probe_at = "        public static int LastSeriesStateConfirmations = 0;"
    assert api.count(probe_at) == 1

    def planted(body):
        m = dict(sources)
        m["ApiClient.cs"] = api.replace(
            probe_at, probe_at + LF + "        static void ZzProbe()" + LF
            + "        {" + LF + body + LF + "        }", 1)
        return m

    # an identical-text duplicate of the setter's own write, outside every span
    dup = planted("                    LastSeriesT1Wins = 0;")
    got = _r9_writers_outside_paths(_r7_writer_lines(dup), dup["ApiClient.cs"])
    assert len(got) == 1 and got[0][2] == "LastSeriesT1Wins = 0;", got
    for body in ("            (LastSeriesT1Wins, LastSeriesT2Wins) = (0, 0);",
                 "            (LastSeriesT1Wins, LastSeriesT2Wins) = ReadWins();",
                 "            (int zz, ApiClient.LastSeriesT2Wins) = ReadWins();",
                 "            (LastSeriesT1Wins, LastSeriesT2Wins)" + LF
                 + "                = ReadWins();",
                 # ROUND-9 COLD LENS (R9CL7): the token before the group, not
                 # its last character, decides
                 "            Action zz = () => (LastSeriesT1Wins, LastSeriesT2Wins) = (0, 0);",
                 "            Action zz = () =>(LastSeriesT1Wins, LastSeriesT2Wins) = (0, 0);",
                 "            if (zz) { } else (LastSeriesT1Wins, LastSeriesT2Wins) = (0, 0);",
                 "            do (LastSeriesT1Wins, zz) = (0, 0); while (false);",
                 "            zz = 1; // a comment that ends in a word" + LF
                 + "            (LastSeriesT1Wins, zz) = (0, 0);"):
        m = planted(body)
        got = _r9_writers_outside_paths(_r7_writer_lines(m), m["ApiClient.cs"])
        assert len(got) == 1, (body.strip(), got)

    # TWINS: the same text inside a permitted span, and tuples that only READ
    anchor = "                    LastSeriesT1Wins = 0;"
    setter = text_spans["the id setter"]
    assert setter.count(anchor) == 1
    inside = dict(sources)
    inside["ApiClient.cs"] = api.replace(anchor, anchor + LF + anchor, 1)
    w2 = _r7_writer_lines(inside)
    assert len(w2) == len(writers) + 1
    assert not _r9_writers_outside_paths(w2, inside["ApiClient.cs"])
    for body in ("            var zz = (LastSeriesT1Wins, LastSeriesT2Wins);",
                 "            if ((LastSeriesT1Wins, LastSeriesT2Wins) == (0, 0)) { }",
                 "            var (LastSeriesT1Wins, zz) = ReadWins();",
                 "            // (LastSeriesT1Wins, LastSeriesT2Wins) = (0, 0);",
                 "            Log(" + chr(34) + "(LastSeriesT1Wins, x) = (0, 0)" + chr(34) + ");",
                 # a call, a generic argument list and an escaped identifier
                 # are not expression starts
                 "            zz.Set(LastSeriesT1Wins, zz) = 0;",
                 "            Wrap<int>(LastSeriesT1Wins, zz) = 0;",
                 "            @else(LastSeriesT1Wins, zz) = 0;"):
        m = planted(body)
        assert not _r9_writers_outside_paths(_r7_writer_lines(m), m["ApiClient.cs"]), body


def _r10_line_census(sources):
    """THE ROUND-9 DETECTOR, kept here only as the thing the R9-L4 cases must
    defeat: the same write forms applied to one physical line at a time,
    comment lines skipped.  Nothing in the census calls it."""
    out = set()
    for fname in sources:
        out.update(_r10_line_census_in(fname, sources[fname]))
    return out


@functools.lru_cache(maxsize=256)
def _r10_line_census_in(fname, text):
    # Every write form contains a banner-input name or the latch, so a line
    # without one cannot match any form; skipping it changes no result and
    # keeps the per-case cost to the lines that can.
    out = []
    for i, line in enumerate(text.split(LF), 1):
        if not _R10_ANY_NAME.search(line):
            continue
        if line.strip().startswith("//"):
            continue
        if any(rx.search(line) for rx in _R10_WRITE_FORMS):
            out.append((fname, i))
    return tuple(out)


def test_r10_l4_the_writer_census_reads_statements_not_lines():
    """R9-L4 (B19): a write split across physical lines is ONE write, and a
    tuple left side of any length is a write.

    The round-9 census tested each physical line on its own, so a name, its
    operator and its value split across a line break were not recognised,
    and its tuple walk gave up 600 characters before the `)` -- a longer
    left side was invisible wherever it sat.  Each case below is planted
    OUTSIDE every repaint span (so the census must report it outside); the
    split scalar INSIDE the id setter's span (counted, and classified inside)
    is the test that follows, so a control can name that half on its own.
    The round-9 line detector is run over
    the same split cases and must MISS them, which is the red this finding
    names; and on the unplanted tree the new census must find every writer
    that detector finds, so nothing it saw was lost."""
    api = _src("ApiClient.cs")
    sources = _r7_plugin_sources()
    writers = _r7_writer_lines(sources)
    old = _r10_line_census(sources)
    new = set((f, i) for f, i, _ in writers)
    assert old <= new, ("writers the round-9 detector found and this census "
                        "does not: %r" % sorted(old - new))
    print("R9-L4 CENSUS: %d writer lines (the line-at-a-time detector finds %d, "
          "every one of them among these)" % (len(new), len(old)))

    probe_at = "        public static int LastSeriesStateConfirmations = 0;"
    assert api.count(probe_at) == 1

    def planted(body):
        m = dict(sources)
        m["ApiClient.cs"] = api.replace(
            probe_at, probe_at + LF + "        static void ZzProbe(int zz)" + LF
            + "        {" + LF + body + LF + "        }", 1)
        return m

    split = (
        "            LastSeriesT1Wins" + LF + "                = 0;",
        "            ApiClient.LastSeriesT2Wins" + LF + "                += 1;",
        "            LastSeriesDcDeferred /* a comment in the gap */" + LF
        + "                = false;",
        "            ++" + LF + "            LastSeriesT2Wins;",
        "            LastSeriesT2Wins" + LF + "                ++;",
        "            _statusPollDarkSeries" + LF + "                .Remove(" + chr(34)
        + "x" + chr(34) + ");",
        "            Interlocked.Increment(ref" + LF + "                LastSeriesT1Wins);",
        "            zz = 0; LastSeriesT1Wins" + LF + "                = zz;",
        "            Interlocked.Increment(ref ApiClient" + LF
        + "                .LastSeriesT1Wins);",
        "            ++ApiClient" + LF + "                .LastSeriesT2Wins;",
    )
    for body in split:
        m = planted(body)
        got = _r9_writers_outside_paths(_r7_writer_lines(m), m["ApiClient.cs"])
        assert len(got) == 1, ("a split write was not seen outside every span",
                               body, got)
        # the planted lines shift every later line number, so the round-9
        # detector is compared by COUNT: it must find exactly what it found
        # on the tree, i.e. miss the split write
        assert len(_r10_line_census(m)) == len(old), (
            "the round-9 line detector saw a split write, so this case does "
            "not reproduce the finding", body)

    # a tuple left side LONGER than 600 characters, with the banner input at
    # either end, nested, and with a `;` and a paren inside a literal
    pad = ", ".join("zz%03d" % k for k in range(120))
    long_first = "(LastSeriesT1Wins, " + pad + ")"
    long_last = "(" + pad + ", LastSeriesT2Wins)"
    assert len(long_first) > 600 and len(long_last) > 600
    for body in ("            " + long_first + " = ZzMany();",
                 "            " + long_last + LF + "                = ZzMany();",
                 "            ((LastSeriesT1Wins, zz), (zz, (zz, zz))) = ZzNested();",
                 "            (LastSeriesT1Wins, zz[" + chr(34) + ";)" + chr(34)
                 + "]) = (0, 0);",
                 "            (ApiClient" + LF + "                .LastSeriesT1Wins, zz) = (0, 0);"):
        m = planted(body)
        got = _r9_writers_outside_paths(_r7_writer_lines(m), m["ApiClient.cs"])
        assert len(got) == 1, ("a tuple write was not seen", body[:80], got)

    # the qualified name spelled in full on one line is the same write
    for body in ("            System.Threading.Interlocked.Exchange(ref "
                 "CompetitiveRounds.ApiClient.LastSeriesT1Wins, 0);",
                 "            ++global::CompetitiveRounds.ApiClient.LastSeriesT2Wins;",
                 "            (global::CompetitiveRounds.ApiClient.LastSeriesT1Wins, zz)"
                 " = (0, 0);"):
        m = planted(body)
        got = _r9_writers_outside_paths(_r7_writer_lines(m), m["ApiClient.cs"])
        assert len(got) == 1, ("a qualified write was not seen", body, got)

    # TWINS: an ordinary single-line scalar write and an ordinary short tuple
    # write are unaffected (one writer each, outside); a READ split across
    # lines and a long tuple that is only READ are not writers at all
    for body in ("            LastSeriesT1Wins = 0;",
                 "            (LastSeriesT1Wins, LastSeriesT2Wins) = (0, 0);"):
        m = planted(body)
        got = _r9_writers_outside_paths(_r7_writer_lines(m), m["ApiClient.cs"])
        assert len(got) == 1, (body, got)
    for body in ("            bool zb = LastSeriesT1Wins" + LF + "                == 0;",
                 "            bool zb = LastSeriesT1Wins" + LF + "                <= 0;",
                 "            bool zb = ApiClient" + LF
                 + "                .LastSeriesT1Wins == 0;",
                 "            var zt = " + long_first + ";",
                 "            // LastSeriesT1Wins" + LF + "            zz = 0;"):
        m = planted(body)
        assert not _r9_writers_outside_paths(_r7_writer_lines(m), m["ApiClient.cs"]), body


def test_r10_l4_a_split_write_inside_a_span_is_counted_there():
    """R9-L4 (B19), the in-span half: a write of a banner input split across
    physical lines INSIDE a repaint path's span is ONE writer -- counted, and
    classified inside that span.  The round-9 line detector does not count it,
    so a census that reads lines reports one writer fewer than the plugin
    carries, and every count stated from it is short by the split writes."""
    api = _src("ApiClient.cs")
    sources = _r7_plugin_sources()
    writers = _r7_writer_lines(sources)
    anchor = "                    LastSeriesT1Wins = 0;"
    assert api.count(anchor) == 1
    assert _r7_repaint_paths(api)["the id setter"].count(anchor) == 1
    inside = dict(sources)
    inside["ApiClient.cs"] = api.replace(
        anchor, anchor + LF + "                    LastSeriesT2Wins" + LF
        + "                        = 0;", 1)
    w2 = _r7_writer_lines(inside)
    assert len(w2) == len(writers) + 1, (
        "the split write inside the id setter was not counted", len(w2), len(writers))
    assert not _r9_writers_outside_paths(w2, inside["ApiClient.cs"]), (
        "the split write inside the id setter was classified outside it")
    # the round-9 line detector, over the same text, does NOT count it: the
    # red this finding names, reproduced
    assert len(_r10_line_census(inside)) == len(_r10_line_census(sources))


# ── L9 (B16): every provenance field is verified, and the coverage asserted ──
#
# WHAT WAS WRONG.  The record's header said every field below it was
# re-derived, but `source` was checked by neither verifier, and each verifier
# omitted fields the other checked.  A record header is a claim about its
# verifiers, and it is true only when their coverage is ASSERTED.
#
# THE SOURCE FIELD NOW CARRIES A RESOLVABLE IDENTITY: the pin's directory name,
# its HEAD, and the file inside it -- no workstation path.  The freeze tool
# resolves it under a pins root it is handed and requires the bytes to hash to
# source-sha256-bytes; this harness compares it with the constant below.
_FROZEN_SOURCE = ("pin scr-codex-886bed8-r6-client-5aa2607 at HEAD "
                  "5aa260793065eac58aebe83f86629b64232ce552, file "
                  "REVIEW-INPUT/server-lane/main.py")
_FROZEN_SOURCE_BYTES = "3086099"
_FROZEN_SOURCE_SPLIT_ELEMENTS = "56062"

# A field is a line that starts at column 0 with a lower-case name of letters,
# digits and hyphens, then spaces, a colon and a space.
_R9_PROVENANCE_FIELD = re.compile(r"^([a-z][a-z0-9-]*)[ \t]*:[ \t]", re.M)

# EVERY LINE IS CLASSIFIED (round-9 cold lens).  The field grammar alone let a
# field-shaped line with a capital, a leading digit or an indent ride in the
# record while neither verifier enumerated it.  So the record's lines are now
# classified TOTALLY: blank; a comment (`#` at column 0); a field (above); or a
# line of a SUPERSEDED block, which opens at a line starting `SUPERSEDED -- `,
# closes at the next blank line, and holds only quoted `#` lines, the two
# annotations and four-space continuations that are not field-shaped.  Any
# other line is refused by its number.  The annotations and continuations are
# a NAMED exemption, printed with its reason.
_R9_PROVENANCE_BLOCK = re.compile(r"^SUPERSEDED -- ")
_R9_PROVENANCE_ANNOTATION = re.compile(r"^  (?:WHY IT IS WRONG|CORRECT) : ")
_R9_PROVENANCE_CONTINUATION = re.compile(r"^    \S")
_R9_FIELD_SHAPED = re.compile(r"^[ \t]*[A-Za-z0-9_][A-Za-z0-9_-]*[ \t]*:")
_R9_PROVENANCE_LINE_EXEMPTION = (
    "SUPERSEDED annotations and their continuations -- prose about a quoted "
    "passage of the sealed extract, bound by the supersession pairing; no "
    "value in them is a field")


def _r9_provenance_lines(record):
    """([(line number, class)], [(line number, text)] refused).  Classes:
    blank, comment, field, block-head, quoted, annotation, continuation."""
    out, refused = [], []
    block = False
    for n, ln in enumerate(record.split(LF), 1):
        if not ln.strip():
            block = False
            out.append((n, "blank"))
        elif _R9_PROVENANCE_FIELD.match(ln):
            out.append((n, "field"))
        elif ln.startswith("#"):
            out.append((n, "quoted" if block else "comment"))
        elif _R9_PROVENANCE_BLOCK.match(ln):
            block = True
            out.append((n, "block-head"))
        elif block and _R9_PROVENANCE_ANNOTATION.match(ln):
            out.append((n, "annotation"))
        elif (block and _R9_PROVENANCE_CONTINUATION.match(ln)
              and not _R9_FIELD_SHAPED.match(ln)):
            out.append((n, "continuation"))
        else:
            refused.append((n, ln))
    return out, refused

# THE FIELDS THIS HARNESS VERIFIES, each by a constant it records or by
# re-derivation from the body in hand.  No field is exempt here, and the
# coverage assertion in `_frozen_provenance_binds` refuses a record whose field
# set differs from this one in either direction.
_R9_PROVENANCE_VERIFIED = (
    "extract-path", "extract-sha256", "body-sha256", "body-split-elements",
    "source", "source-bytes", "source-sha256-bytes", "source-sha256-lf",
    "source-split-elements", "source-lines")
_R9_PROVENANCE_EXEMPT = {}


def _r9_provenance_fields(record):
    """The field names the record carries, in order, duplicates kept -- read
    from the lines the classification calls fields, and from no others."""
    lines = record.split(LF)
    classes, _ = _r9_provenance_lines(record)
    return [_R9_PROVENANCE_FIELD.match(lines[n - 1]).group(1)
            for n, c in classes if c == "field"]


def _r9_provenance_coverage(record):
    """None when every line is classified and every field is verified exactly
    once, else the refusal."""
    at = "the provenance record at " + _FROZEN_PROVENANCE_REL
    _, refused = _r9_provenance_lines(record)
    if refused:
        n, ln = refused[0]
        return (at + " carries %d line(s) that are neither blank, a comment, "
                "a field nor a SUPERSEDED block line; the first is line %d: %r"
                % (len(refused), n, ln[:72]))
    fields = _r9_provenance_fields(record)
    dup = sorted(set(f for f in fields if fields.count(f) > 1))
    if dup:
        return at + " carries a field more than once: " + ", ".join(dup)
    have = set(fields)
    covered = set(_R9_PROVENANCE_VERIFIED) | set(_R9_PROVENANCE_EXEMPT)
    extra = sorted(have - covered)
    if extra:
        return (at + " carries a field no verifier checks: "
                + ", ".join(extra))
    missing = sorted(set(_R9_PROVENANCE_VERIFIED) - have)
    if missing:
        return (at + " lacks a field this harness verifies: "
                + ", ".join(missing))
    return None


def test_r9_l9_every_provenance_field_is_verified():
    """L9 (B16): THE RECORD'S HEADER IS TRUE BY COVERAGE, NOT BY PROSE.

    The record's field set is enumerated and asserted EQUAL to the set this
    harness verifies; an extra field, a missing one and a repeated one are each
    a refusal naming it.  The `source` field is compared with a recorded
    constant, so pointing it at another pin reddens this -- and the freeze
    tool, which resolves the same field against the pin itself, refuses the
    same edit in its own log."""
    record = _FROZEN_PROVENANCE.read_text(encoding="utf-8")
    raw = _FROZEN_SERVER_EXTRACT.read_bytes().decode("utf-8")
    fields = _r9_provenance_fields(record)
    classes, refused = _r9_provenance_lines(record)
    tally = dict((k, sum(1 for _, c in classes if c == k)) for k in (
        "blank", "comment", "field", "block-head", "quoted", "annotation",
        "continuation"))
    print("L9 PROVENANCE LINES: %d -- %s; refused %d"
          % (len(classes) + len(refused), ", ".join(
              "%s %d" % (k, tally[k]) for k in (
                  "blank", "comment", "field", "block-head", "quoted",
                  "annotation", "continuation")), len(refused)))
    print("L9 LINE EXEMPTION: %d lines -- %s"
          % (tally["annotation"] + tally["continuation"],
             _R9_PROVENANCE_LINE_EXEMPTION))
    print("L9 PROVENANCE FIELDS: %d -- %s" % (len(fields), ", ".join(fields)))
    print("L9 VERIFIED BY THIS HARNESS: %d; EXEMPTIONS: %s"
          % (len(_R9_PROVENANCE_VERIFIED),
             ", ".join(sorted(_R9_PROVENANCE_EXEMPT)) or "none"))
    assert _r9_provenance_coverage(record) is None, _r9_provenance_coverage(record)
    ok, why = _frozen_provenance_binds(raw)
    assert ok, why

    src_line = [ln for ln in record.split(LF) if ln.startswith("source ")]
    assert len(src_line) == 1, src_line
    other = record.replace("scr-codex-886bed8-r6-client-5aa2607",
                           "scr-codex-886bed8-r7-client-0c57c4e", 1)
    bad, why_bad = _frozen_provenance_binds(raw, record=other)
    assert not bad and "source" in why_bad, why_bad
    extra = record.replace("source-lines          :",
                           "reviewed-by           : nobody" + LF
                           + "source-lines          :", 1)
    bad, why_bad = _frozen_provenance_binds(raw, record=extra)
    assert not bad and "reviewed-by" in why_bad, why_bad
    twice = record.replace("source-lines          :",
                           "source-bytes          : 3086099" + LF
                           + "source-lines          :", 1)
    bad, why_bad = _frozen_provenance_binds(raw, record=twice)
    assert not bad and "more than once" in why_bad, why_bad
    # ROUND-9 COLD LENS (R9CL8): a field-shaped line the field grammar does
    # not match is refused by its line, not carried unenumerated
    for shaped in ("Reviewed-By           : nobody",
                   "2nd-source            : nobody",
                   "  reviewed-by         : nobody",
                   "\treviewed-by : nobody"):
        planted = record.replace("source-lines          :",
                                 shaped + LF + "source-lines          :", 1)
        bad, why_bad = _frozen_provenance_binds(raw, record=planted)
        assert not bad and "neither blank" in why_bad and repr(
            shaped[:72]) in why_bad, (shaped, why_bad)
    correct = "  CORRECT : 38671-40545 of 56062, 1-indexed inclusive"
    assert record.count(correct) == 1
    inblock = record.replace(correct, "    reviewed-by : nobody" + LF + correct, 1)
    bad, why_bad = _frozen_provenance_binds(raw, record=inblock)
    assert not bad and "neither blank" in why_bad, why_bad
    # TWIN: a continuation line added inside a SUPERSEDED block is prose
    at = record.find(correct)
    eol = record.find(LF, at)
    cont = record[:eol] + LF + "    a further continuation line." + record[eol:]
    ok3, why3 = _frozen_provenance_binds(raw, record=cont)
    assert ok3, why3
    # TWIN: a comment line reworded binds nothing.  The line is one that no
    # tree control edits: the round-8 tree twin rewords the digest heading, and
    # an in-test twin on that same heading finds nothing to replace while that
    # tree twin is applied, which reddens this test for a reason that is not L9.
    twin = record.replace("# WHAT source-lines COUNTS.",
                          "# WHAT source-lines MEASURES.", 1)
    assert twin != record
    ok2, why2 = _frozen_provenance_binds(raw, record=twin)
    assert ok2, why2


# ── CL2 (B16): no claim in the named scope restores the removed resolution ──
#
# WHAT WAS WRONG.  A comment in this harness stated, of the merge, a resolution
# order this file does not have, and the round-8 check read only the sealed
# extract's paragraph and its supersession.  The check now reads a NAMED
# SCOPE, printed by the test: every comment and docstring of every Python file
# under backend/ (this harness included), every comment in every plugin
# source, every Markdown file under docs/, the extract's header and the
# provenance record -- with exactly the sealed passage removed from the last
# two, because that passage is quoted on purpose and its pairing is checked
# both ways by the round-8 case.  The round-9 notes checker applies THIS
# grammar, loaded from this file, to the round-9 tools and the round-9 notes.
# The scope is found by glob at run time and its size is printed, so what it
# covers is visible rather than asserted.
#
# THE FORM IS A GRAMMAR over vocabulary classes, not a list of sentences.  Its
# pieces are single words kept in code below, so this file's own prose never
# spells the form it rejects (R8-D6).  A sentence is a candidate when it
# mentions the merge (form 1) or a fallback (form 2).  It is REJECTED when one
# of its clauses has a source-tree noun as the subject of a supply verb, or as
# the object of a consult verb, with no negation governing either and no
# extract noun standing between them as the actual subject.
#
# THE MANUAL EXEMPTION IS PER CLAUSE, NOT PER SENTENCE (round-9 cold lens).  A
# clause that describes the MANUAL operation -- deleting the extract,
# re-pointing the harness by hand -- is the correct disposition, and a hit
# inside THAT clause is not a claim.  The exemption used to be read once per
# sentence, so the removed ordering passed whenever the same sentence also
# mentioned a deletion in another clause.  Now every hit is judged by the
# clause it sits in: the words between the nearest clause boundaries around
# it (punctuation, a comma, or a joining word such as `and`, `which` or
# `once`), and only a manual word inside that span exempts it.  The merge
# vocabulary is likewise a class of forms rather than three stems: the
# sentence that joins the lanes, lands them or unifies them is a merge
# sentence too.  Because a clause is now judged on its own, a Markdown table
# row, list item or heading is a sentence of its own and a table cell a
# clause of its own: a row carries no terminal stop, and gluing a whole table
# into one sentence let one row's merge word pair with another row's tree.
def _r9_w(*words):
    return frozenset(words)


_R9_MERGE_STEMS = ("merg", "combin", "integrat")
_R9_MERGE_FORMS = (r"join(?:s|ed|ing)?", r"rejoin\w*",
                   r"unif(?:y|ies|ied|ying|ication)", r"consolidat\w*",
                   r"rebas\w*", r"reunit\w*", r"amalgamat\w*", r"absorb\w*",
                   r"fus(?:e|es|ed|ing|ion)",
                   r"land(?:s|ed|ing)?", r"unit(?:e|es|ed|ing)")
_R9_MERGE = re.compile(r"\b(?:" + "|".join(
    [s + r"\w*" for s in _R9_MERGE_STEMS] + list(_R9_MERGE_FORMS)) + r")\b", re.I)
_R9_TREE = _r9_w("tree", "trees", "worktree", "worktrees", "repository",
                 "repositories", "repo", "repos", "checkout", "checkouts",
                 "checked-out", "codebase", "module", "modules", "main.py",
                 "working_copy")
_R9_SUBJ = _r9_w("answer", "answers", "answered", "answering", "supplies",
                 "supply", "supplied", "provides", "provide", "provided",
                 "serves", "serve", "served", "wins", "win", "decides", "decide",
                 "takes_over", "take_over", "is_read", "is_consulted",
                 "is_preferred", "is_used", "resolves", "resolve", "resolved")
_R9_OBJ = _r9_w("reads", "read", "prefers", "prefer", "preferred", "consults",
                "consult", "tries", "try", "uses", "use", "opens", "open",
                "binds", "bind", "resolves", "resolve", "resolved")
_R9_NEG = _r9_w("no", "not", "never", "cannot", "can't", "nothing", "none",
                "neither", "nor", "without", "nobody", "isn't", "doesn't",
                "don't", "won't", "no_longer")
_R9_EXTRACT = _r9_w("extract", "extracts", "frozen", "sealed", "slice")
_R9_MANUAL = re.compile(r"\b(?:" + "|".join((
    "by hand", "manual", "manually", r"re-?points?", r"re-?pointed",
    r"delet\w*")) + r")\b", re.I)
_R9_FALLBACK = re.compile(r"\b(?:" + "|".join((
    r"falls? back", "falling back", "fallback", "failing that")) + r")\b", re.I)
_R9_BIGRAMS = (("working copy", "working_copy"), ("takes over", "takes_over"),
               ("take over", "take_over"), ("is read", "is_read"),
               ("is consulted", "is_consulted"), ("is preferred", "is_preferred"),
               ("is used", "is_used"), ("no longer", "no_longer"))
_R9_TOKEN = re.compile(r"[a-z0-9_][a-z0-9_'./-]*|;|--|—|:|,|[()\[\]]")
_R9_BREAKS = frozenset((";", "--", "—", ":", "(", ")", "[", "]"))
_R9_SENTENCE = re.compile(r"(?<=[.!?])\s+")
# Where a clause ends, for the manual exemption: the grammar's own breaks, a
# comma, and the words that join one clause to the next.
_R9_CLAUSE_EDGES = _R9_BREAKS | frozenset((",",)) | _r9_w(
    "and", "but", "or", "nor", "so", "then", "which", "who", "whom", "whose",
    "while", "whereas", "where", "when", "whenever", "once", "after",
    "before", "until", "unless", "if", "because", "since", "though",
    "although")


def _r9_words(sentence, commas=False):
    """The sentence's words, bigrams joined.  Commas are kept only on request:
    the claim windows below were measured without them, and only the clause
    edges of the manual exemption read them."""
    s = sentence.lower()
    for a, b in _R9_BIGRAMS:
        s = s.replace(a, b)
    out = [w for w in (x.strip("'.") for x in _R9_TOKEN.findall(s)) if w]
    return out if commas else [w for w in out if w != ","]


def _r9_clause_hits(words):
    """Every (first, last) word index pair where a clause has a tree supplying,
    or being consulted, unnegated and with no extract noun as the real subject
    between them."""
    n = len(words)
    hits = []
    for v, w in enumerate(words):
        if w in _R9_SUBJ:
            for t in range(v - 1, max(-1, v - 9), -1):
                if words[t] in _R9_BREAKS:
                    break
                if words[t] in _R9_TREE:
                    lo = t
                    while lo > 0 and lo > t - 3 and words[lo - 1] not in _R9_BREAKS:
                        lo -= 1
                    neg = (any(x in _R9_NEG for x in words[lo:t])
                           or any(x in _R9_NEG for x in words[max(t + 1, v - 2):v]))
                    ex = any(words[e] in _R9_EXTRACT
                             and not any(x in _R9_NEG
                                         for x in words[max(t + 1, e - 2):e])
                             for e in range(t + 1, v))
                    if not neg and not ex:
                        hits.append((t, v))
                    break
        if w in _R9_OBJ:
            lo = v
            while lo > 0 and lo > v - 3 and words[lo - 1] not in _R9_BREAKS:
                lo -= 1
            if any(x in _R9_NEG for x in words[lo:v]):
                continue
            for t in range(v + 1, min(n, v + 7)):
                if words[t] in _R9_BREAKS or words[t] in _R9_EXTRACT:
                    break
                if words[t] in _R9_TREE:
                    hits.append((v, t))
                    break
    return hits


def _r9_clause_hit(words):
    """True when any clause of `words` has the rejected form."""
    return bool(_r9_clause_hits(words))


def _r9_hit_clause(wc, a, b):
    """The clause of the comma-bearing word list `wc` that holds the hit
    spanning wc[a]..wc[b]: out to the nearest clause edge on each side."""
    lo = a
    while lo > 0 and wc[lo - 1] not in _R9_CLAUSE_EDGES:
        lo -= 1
    hi = b + 1
    while hi < len(wc) and wc[hi] not in _R9_CLAUSE_EDGES:
        hi += 1
    return " ".join(wc[lo:hi])


def _r9_unexempted_hits(sent):
    """The clauses of one sentence that carry the rejected form and do not
    themselves describe the manual operation."""
    wc = _r9_words(sent, commas=True)
    at = [i for i, w in enumerate(wc) if w != ","]
    words = [wc[i] for i in at]
    out = []
    for a, b in _r9_clause_hits(words):
        clause = _r9_hit_clause(wc, at[a], at[b])
        if not _R9_MANUAL.search(clause):
            out.append(clause)
    return out


# A line that opens a Markdown block -- a table row, a heading, a quotation,
# a list item -- starts a unit of its own, and a table cell is a unit.
_R9_UNIT_START = re.compile(r"\n[ \t]*(?=[|#>]|[-*+][ \t]|\d+[.)][ \t])")


def _r9_merged_tree_claims(prose):
    """Every sentence of `prose` that has the rejected form in a clause the
    manual operation does not govern."""
    found = []
    for para in re.split(r"\n[ \t]*\n", prose):
        for unit in _R9_UNIT_START.split(para):
            for cell in unit.split("|"):
                flat = " ".join(cell.split())
                for sent in _R9_SENTENCE.split(flat):
                    if not sent:
                        continue
                    if not (_R9_MERGE.search(sent) or _R9_FALLBACK.search(sent)):
                        continue
                    if _r9_unexempted_hits(sent):
                        found.append(sent)
    return found


def _r9_py_prose(text):
    """Every comment and docstring of a Python source, as paragraphs.  Comment
    lines that are not consecutive are separate paragraphs, so two unrelated
    comments never read as one sentence."""
    import ast
    import io
    import tokenize
    parts, last = [], None
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            row = tok.start[0]
            if last is not None and row != last + 1:
                parts.append("")
            parts.append(tok.string.lstrip("#"))
            last = row
    parts.append("")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            d = ast.get_docstring(node, clean=True)
            if d:
                parts.extend(("", d, ""))
    return LF.join(parts)


def _r9_cs_prose(text):
    """Every comment of a C# source, XML tags stripped, as paragraphs."""
    comments, _ = _cs_lex(text)
    parts, last = [], None
    for a, b in comments:
        c = re.sub(r"^\s*(?:///?|/\*+|\*+/?)", "", text[a:b], flags=re.M)
        c = re.sub(r"</?[a-zA-Z][^>]*>", "", c.replace("*/", ""))
        # code between two comments ends the paragraph
        if last is not None and text[last:a].strip():
            parts.append("")
        parts.append(c)
        last = b
    return LF.join(parts)


def _r9_sealed_removed(text):
    """The text with EXACTLY the sealed merge passage removed, once."""
    passage = _FROZEN_SUPERSEDED[2]
    assert text.count(passage) <= 1, "the sealed passage occurs twice"
    return text.replace(passage, "", 1)


def _r9_hash_prose(text):
    return LF.join(ln.lstrip("#") for ln in text.split(LF))


def _r9_cl2_scope():
    """{scope name: prose} for the named scope: every Python file under
    backend/ (this harness included), every plugin source, every Markdown file
    under docs/, the extract's header and the provenance record."""
    scope = {}
    here = pathlib.Path(__file__)
    scope[here.name] = _r9_py_prose(here.read_text(encoding="utf-8"))
    for p in sorted((ROOT / "backend").rglob("*.py")):
        if p.resolve() == here.resolve():
            continue
        scope[p.relative_to(ROOT).as_posix()] = _r9_py_prose(
            p.read_text(encoding="utf-8"))
    for p in sorted((ROOT / "docs").rglob("*.md")):
        scope[p.relative_to(ROOT).as_posix()] = p.read_text(encoding="utf-8")
    for name, text in _r7_plugin_sources().items():
        scope["plugin/" + name] = _r9_cs_prose(text)
    raw = _FROZEN_SERVER_EXTRACT.read_bytes().decode("utf-8")
    head = raw[:raw.find(_ROUTE_ANCHOR)]
    scope[_FROZEN_SERVER_EXTRACT.name + " (header)"] = _r9_hash_prose(
        _r9_sealed_removed(head))
    record = _FROZEN_PROVENANCE.read_text(encoding="utf-8")
    scope[_FROZEN_PROVENANCE.name] = _r9_hash_prose(_r9_sealed_removed(record))
    return scope


def test_r9_cl2_no_delivered_claim_restores_the_removed_resolution():
    """CL2 (B16): THE CHECK READS A NAMED SCOPE, NOT ONE PARAGRAPH.

    The round-8 CL2 check bound only the sealed paragraph and its supersession,
    so a comment elsewhere in this harness stating the removed order passed.
    This check applies one grammar to every comment and docstring in its named
    scope -- every Python file under backend/, every plugin source, every
    Markdown file under docs/, the extract's header and the provenance record
    -- and prints how many texts of each kind it read; the grammar is
    proven to reject the sealed passage itself, and to leave a correct
    statement of the manual merge operation alone.  A manual word exempts only
    the clause it sits in, so the removed ordering beside a deletion mentioned
    in another clause is still rejected."""
    scope = _r9_cl2_scope()
    found = []
    for name in sorted(scope):
        for s in _r9_merged_tree_claims(scope[name]):
            found.append((name, s[:200]))
    n_py = len([k for k in scope if k.endswith(".py")])
    n_cs = len([k for k in scope if k.startswith("plugin/")])
    n_md = len([k for k in scope if k.startswith("docs/")])
    print("CL2 SCOPE: %d delivered texts read -- %d Python files under backend/ "
          "(this harness included), %d plugin sources, %d Markdown files under "
          "docs/, the extract header and the provenance record"
          % (len(scope), n_py, n_cs, n_md))
    assert n_py > 1 and n_cs == len(_r7_plugin_sources()) and n_md >= 1, (
        n_py, n_cs, n_md)
    assert not found, ("a delivered claim restores the removed resolution: "
                       + repr(found))

    # THE GRAMMAR CAN FIRE: on the sealed passage, which is exactly the form ...
    sealed = _r9_hash_prose(_FROZEN_SUPERSEDED[2])
    assert _r9_merged_tree_claims(sealed), "the grammar does not see the sealed form"
    # ... and on a wording no list ever carried, assembled from its pieces
    w = ("Once the branches are " + _R9_MERGE_STEMS[1] + "ed, the checked-out "
         "repository supplies the status route.")
    assert _r9_merged_tree_claims(w), w
    # TWINS: the correct disposition, in two different wordings
    for ok in ("At merge the integrator deletes the extract and its constant and "
               "points the harness at the merged backend/api/main.py.",
               "Merging the branches does not change who answers: the extract "
               "answers until the integrator removes it.",
               "On this branch, and on any tree it is " + _R9_MERGE_STEMS[0]
               + "ed into, the hash-verified extract is the only text the "
               "resolver reads."):
        assert not _r9_merged_tree_claims(ok), ok

    # ROUND-9 COLD LENS (R9CL5): THE MANUAL EXEMPTION GOVERNS ITS OWN CLAUSE
    # ONLY.  The removed ordering with a deletion mentioned in ANOTHER clause
    # of the same sentence is still the removed ordering; and a merge sentence
    # spelled with a word outside the three stems is still a merge sentence.
    m0 = _R9_MERGE_STEMS[0]
    for bad in ("When the lanes " + m0 + "e, the resolver prefers the " + m0
                + "ed repository and falls back to this extract, which is "
                "deleted later.",
                "Once " + m0 + "ed, the repository answers for the route; the "
                "extract is deleted afterwards.",
                "Once the lanes are joined, the repository answers for the "
                "status route.",
                "After the lanes land, the checked-out tree supplies the "
                "deferral fields and the extract is deleted by hand."):
        assert _r9_merged_tree_claims(bad), "the grammar did not reject: " + bad
    # TWINS: a hit INSIDE the clause that describes the manual operation is
    # exempt, and so is a joined-lanes sentence that states the manual step.
    for ok in ("At merge the integrator re-points the harness by hand to read "
               "the " + m0 + "ed main.py.",
               "Once the lanes are joined, the integrator deletes the extract "
               "and re-points the harness by hand."):
        assert not _r9_merged_tree_claims(ok), ok

