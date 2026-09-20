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


SAFETY_NET_SEC = 45          # Plugin.cs DC_SAFETY_NET_SEC
RETRY_BUDGET_SEC = 34        # PostRequestWithRetry: 3 x 10s timeout + 2 x 2s backoff


def elect(seats, leaver, capable=None):
    """Transliteration of Plugin.OnPlayerLeftRoom's election.

    `seats` is the list of SURVIVORS as every seat sees them (Photon has
    already removed the leaver), each a dict {uid, team, local}.  `leaver` is
    {uid, team}.  `capable` is the set of uids advertising cr_dc2 -- None means
    the whole room advertises it, which is the case the census arm needs.

    Returns one entry per seat that POSTS, as (uid, totals, delay_seconds).
    `totals` is always "REAL": the arm-(2) zeros were withdrawn this round, and
    a test asserting a seat can produce "ZERO" would now be asserting the defect
    (a seat on the LEAVER's team could force every other seat's report to zero
    by withholding one property, turning a forfeit the other team had earned
    into dc_incomplete).  `delay_seconds` is 0 for the prompt report and
    SAFETY_NET_SEC for the seat that only reports if the prompt one never lands.
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
                          0 if my_val == lowest_non_dc else SAFETY_NET_SEC))
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
        posts.append((my_val, "REAL", 0))
    return posts


def _prompt(posts):
    return [p for p in posts if p[2] == 0]


def _net(posts):
    return [p for p in posts if p[2] > 0]


def _seats(ids_teams):
    return [{"uid": u, "team": t, "local": i} for i, (u, t) in enumerate(ids_teams)]


def test_h1_healthy_2v2_elects_exactly_one_prompt_reporter_plus_a_safety_net():
    # leaver on team 0; survivors: its teammate (team 0) and both of team 1.
    seats = _seats([(10, 0), (20, 1), (30, 1)])
    posts = elect(seats, {"uid": 40, "team": 0})
    assert _prompt(posts) == [(20, "REAL", 0)], posts
    assert _net(posts) == [(30, "REAL", SAFETY_NET_SEC)], posts
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
            uid, totals, delay = prompt[0]
            assert totals == "REAL" and delay == 0
            assert uid == min(b, c)
            # and exactly one seat behind it, never a second prompt report
            assert [u for u, _t, _d in _net(posts)] == [max(b, c)], posts


def test_h1_the_safety_net_cannot_overtake_the_prompt_report():
    """The net exists because a single un-retried request used to be the whole
    mechanism, and the disruption that produced the disconnect is the one that
    drops it.  It must wait out the prompt seat's ENTIRE budget, or the two race
    and the arrival order decides a rated completion again -- the defect the
    census arm exists to remove."""
    assert SAFETY_NET_SEC > RETRY_BUDGET_SEC
    src = _src("Plugin.cs")

    def claim(s):
        return "const float DC_SAFETY_NET_SEC = 45f;" in s and "delaySec = DC_SAFETY_NET_SEC;" in s

    _assert_discriminating(
        claim, src,
        _mutate(src, "const float DC_SAFETY_NET_SEC = 45f;",
                "const float DC_SAFETY_NET_SEC = 1f;", "H1 net delay"),
        "H1 safety-net delay")


def test_h1_a_peer_on_the_older_election_drops_the_room_to_the_floor_rule():
    """The census proves ONE reporter only among seats evaluating the census.  A
    seat that does not advertise cr_dc2 is running the previous OR'd election
    and will post regardless, so the rule is not room-wide and this seat must
    not act as though it were."""
    seats = _seats([(10, 0), (20, 1), (30, 1)])
    leaver = {"uid": 40, "team": 0}
    every = elect(seats, leaver, capable={10, 20, 30})
    assert len(_prompt(every)) == 1 and len(_net(every)) == 1

    # one survivor on the old build: every seat falls to the floor election,
    # which is the rule that seat is already running.
    mixed = elect(seats, leaver, capable={20, 30})
    assert all(d == 0 for _u, _t, d in mixed), mixed
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
    and no seat sitting on a safety net when no census elected anyone."""
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
        assert not _net(posts), ("a net without an election", seats, leaver, posts)


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
    assert real and all(d == 0 for _u, _t, d in real), real


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
            owner = c[c.rfind("if ("):] if "if (" in c else c
            if "Plugin.Log.Log" not in owner and "ShowNotification" not in owner:
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


def test_l2_an_unresolved_identity_is_not_treated_as_a_change():
    """First resolution is deliberately not an account change -- the same rule
    DropChatOnAccountChange follows.  Model + the guard it mirrors."""
    def keeps(writer, reader):
        if reader and reader != "unknown" and writer and writer != reader:
            return False
        return True

    assert keeps("A", "A") is True
    assert keeps("A", "B") is False
    assert keeps("A", None) is True
    assert keeps("A", "unknown") is True
    assert keeps(None, "B") is True
    src = _src("CompetitiveUI.cs")
    assert 'if (!string.IsNullOrEmpty(reader) && reader != "unknown"' in src


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
        _mutate(src, "bool sameSet = players != null && players.Count == _order.Count;",
                "bool sameSet = players != null;", "M7 membership"),
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
        return ("if (SawLiveTargetPatch.WindowOpen) return;" in b
                and b.index("if (SawLiveTargetPatch.WindowOpen) return;")
                    < b.index("Player vanillaTarget = Select("))

    _assert_discriminating(
        claim, src,
        _mutate(src, "                if (SawLiveTargetPatch.WindowOpen) return;",
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

    PoisonSync is deliberately NOT swept: its roster GRANTS authority, and there
    the cache is doing real work by holding "joined as a spectator" fixed.  The
    rule this test encodes is the distinction, not "never use the cache"."""
    plug = _src("Plugin.cs")
    vf = _src("VanillaFixes.cs")

    # the census
    census = plug[plug.index("var survivors = new List<Photon.Realtime.Player>();"):]
    census = census[:census.index("catch { survivors.Clear(); }")]
    assert "RoomActors.IsSpectatorReplicated(a)" in census
    assert "RoomActors.IsSpectator(a)" not in census

    # both quorums
    assert vf.count("RoomActors.IsSpectatorReplicated(actor)") == 2
    assert "RoomActors.IsSpectator(actor)" not in vf

    # and the helper itself reads the property every call -- no cache to fall back on
    ra = _src("RoomActors.cs")
    body = _method_body(ra, "internal static bool IsSpectatorReplicated(PhotonPlayer actor)")
    assert body and "props.ContainsKey(SPEC_PROP)" in body
    assert "_roleByActor" not in body

    def claim(s):
        return ("RoomActors.IsSpectatorReplicated(actor)" in s
                and "RoomActors.IsSpectator(actor)" not in s)

    _assert_discriminating(
        claim, vf,
        _mutate(vf, "if (RoomActors.IsSpectatorReplicated(actor)) continue;",
                "if (RoomActors.IsSpectator(actor)) continue;", "sweep"),
        "cross-seat roster basis")


def test_the_dc_report_is_retried_and_carries_the_room_it_was_observed_in():
    """A single un-retried request was the whole mechanism, on the path whose
    failure leaves the series open and every survivor holding a 2v2 lease.  The
    retry is safe against the DEPLOYED endpoint, which re-reads the row under
    FOR UPDATE and answers {"ignored": true} unless the status is still
    active/dc_paused -- so a repeat cannot double-apply ratings or gold."""
    src = _src("ApiClient.cs")
    body = _method_body(src, "private static IEnumerator SendTeamSeriesDcReport")
    assert body, "the dispatch method's own text could not be delimited"
    assert "PostRequestWithRetry(url" in body
    assert "WaitForSecondsRealtime(delaySeconds)" in body

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
                and "string observedRoom = null, float delaySeconds = 0f)" in s)

    _assert_discriminating(
        room_claim, src,
        _mutate(src, "string dcRoom = observedRoom;", "string dcRoom = null;", "DC room"),
        "DC observed room")

    plug = _src("Plugin.cs")
    assert "ApiClient.ReportTeamSeriesDc(seriesId, myId, dcSteamId, t1Points, t2Points,\n                                             observedRoom, delaySec);" in plug


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
