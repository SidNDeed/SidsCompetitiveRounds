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


def elect(seats, leaver):
    """Transliteration of Plugin.OnPlayerLeftRoom's election.

    `seats` is the list of SURVIVORS as every seat sees them (Photon has
    already removed the leaver), each a dict {uid, team, local}. `leaver` is
    {uid, team}.  Returns the list of (uid, t1p, t2p) each seat would post,
    computed independently per seat exactly as the client does.
    """
    posts = []
    for me in seats:
        my_val, my_team = me["uid"], me["team"]
        if my_val is None:
            continue                      # no local steam id: the client returns
        dc_team = leaver["team"]
        teams_known = dc_team is not None and my_team is not None

        # arm (1) preconditions
        unique = teams_known and len(seats) == 3
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
                continue
            if my_val != lowest_non_dc:
                continue
            posts.append((my_val, "REAL"))
            continue

        # arm (2): the floor election, with zero totals
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
        posts.append((my_val, "ZERO"))
    return posts


def _seats(ids_teams):
    return [{"uid": u, "team": t, "local": i} for i, (u, t) in enumerate(ids_teams)]


def test_h1_healthy_2v2_elects_exactly_one_reporter_with_real_totals():
    # leaver on team 0; survivors: its teammate (team 0) and both of team 1.
    seats = _seats([(10, 0), (20, 1), (30, 1)])
    posts = elect(seats, {"uid": 40, "team": 0})
    assert posts == [(20, "REAL")], posts


def test_h1_every_healthy_permutation_yields_one_reporter():
    for ids in itertools.permutations([11, 22, 33, 44]):
        leaver_id, a, b, c = ids
        for dc_team in (0, 1):
            other = 1 - dc_team
            seats = _seats([(a, dc_team), (b, other), (c, other)])
            posts = elect(seats, {"uid": leaver_id, "team": dc_team})
            assert len(posts) == 1, (ids, dc_team, posts)
            uid, totals = posts[0]
            assert totals == "REAL"
            assert uid == min(b, c)


def test_h1_degenerate_seats_never_post_real_totals_and_never_post_zero_times():
    """Every way the census can be incomplete.  The bar is two-sided: at least
    one report (#276 -- zero reporters is worse than the bug) and never a
    report carrying real totals (#283 -- the conservative direction)."""
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
        assert all(t == "ZERO" for _uid, t in posts), ("real totals", seats, leaver, posts)


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
    # the real election refuses: the split is 1 non-DC vs 3, so it drops to zeros
    assert all(t == "ZERO" for _u, t in elect(seats, leaver))


def test_h1_source_matches_the_model():
    src = _src("Plugin.cs")

    def claim(s):
        return ("conservativeOnly" in s
                and "int t1Points = conservativeOnly ? 0 : GameStateWatcher.LastP1Points;" in s
                and "dcTeamCount != 2 || nonDcCount != 2" in s
                and "PhotonNetwork.PlayerList" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src,
                "int t1Points = conservativeOnly ? 0 : GameStateWatcher.LastP1Points;",
                "int t1Points = GameStateWatcher.LastP1Points;", "H1 totals"),
        "H1 conservative totals")


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
    assert 10 not in [u for u, _t in elect(seats, {"uid": 40, "team": 0})]


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
    body = src[src.index("internal static void DropChatDraftOnRevoke()"):]
    body = body[:body.index("\n        }") + 10]

    def claim(s):
        if "internal static void DropChatDraftOnRevoke()" not in s:
            return False
        b = s[s.index("internal static void DropChatDraftOnRevoke()"):]
        b = b[:b.index("\n        }") + 10]
        return "DropStash();" in b and 'chatInputText = "";' in b

    _assert_discriminating(
        claim, src,
        _mutate(src, 'DropStash();\n            chatInputText = "";',
                "DropStash();", "M5"),
        "M5 revoke clears live input")
    assert "chatResumeNoticeUntil = -999f;" in body


def test_l2_the_stash_reader_applies_the_identity_rule_its_comment_states():
    src = _src("CompetitiveUI.cs")

    def claim(s):
        if "private static string TakeStashedDraft()" not in s:
            return False
        b = s[s.index("private static string TakeStashedDraft()"):]
        b = b[:b.index("\n        }") + 10]
        return "chatDraftStashIdentity" in b and "MatchTracker.LocalSteamId" in b

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
    assert "if (RoomActors.IsSpectator(actor)) continue;" in body
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
    assert "PlayerManager.instance.players = _saved;" in body
    assert "return __exception;" in body        # observes, never contains


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
    exact = src[src.index("private static string SpectateReasonExact"):]
    exact = exact[:exact.index("\n        }") + 10]
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
