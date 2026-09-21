using System;
using System.Collections.Generic;
using CompetitiveRounds;

// Bug 389 - executable checks over the SHIPPED seam.
//
// run-tests.ps1 compiles plugin/ProximityVictimSeam.cs itself, so what these
// cases execute is the file that ships. The wiring cases (W*, N*, S4) READ the
// shipped files the harness cannot compile - they carry Unity, Photon and
// MSBuild - through BUG389_SOURCE_ROOT.
//
// ROUND 3 DELETED THE SELECTOR, and the cases that measured it went with it
// rather than being left green against dead code (#310). F1-F18, the
// ProximityCandidate boards, the vision tri-state and the `selpos`/`range`/
// `flat`/`misindex`/`unread`/`ffaskip`/`sqrange`/`anyselect`/`prefixwrite`
// mutations are GONE with ProximityVictim.Choose. What replaces them is the V
// series over ProximityVictim.VictimAction and the N series, which assert that
// no selector exists here at all.
//
// WHICH CASES HAVE A MUTANT, exactly - a reader may not assume the rest do:
//   mutation once       : V1 must FAIL;  V2 control must PASS
//   mutation ringless   : V3 must FAIL;  V2 control must PASS
//   mutation writenull  : V4 must FAIL;  V2 control must PASS
//   mutation suppress   : V5 must FAIL;  V2 control must PASS
//   mutation ownplayer  : V6 must FAIL;  V2 control must PASS
//   mutation gate       : G1 must FAIL;  G2 control must PASS
//   mutation gatereason : G4 must FAIL;  G2 control must PASS
//   mutation localgate  : G6 must FAIL;  G2 control must PASS
//   mutation norevoke   : G7 must FAIL;  G2 control must PASS
//   mutation answerreason: D4 D5 must FAIL; D2 control must PASS
//   mutation answerline : D5 must FAIL;  D4 control must PASS
//   mutation reasonkey  : S1 must FAIL;  S2 control must PASS
//   mutation capkey     : C1 must FAIL;  C2 control must PASS
//   mutation fighterkeys: K1 must FAIL;  K2 control must PASS
//   mutation chainlast  : P3 P5 must FAIL; P1 control must PASS
//   mutation guardopen  : P4 P5 must FAIL; P1 control must PASS
//   wiring   wire-spec  : W1 must FAIL;  W5 control must PASS
//   wiring   wire-prop  : W2 must FAIL;  W5 control must PASS
//   wiring   wire-gen   : W3 must FAIL;  W5 control must PASS
//   wiring   wire-doc   : W8 must FAIL;  W1 control must PASS
//   wiring   wire-msb   : W10 must FAIL; W1 control must PASS
//   wiring   wire-perf  : W11 must FAIL; W1 control must PASS
//   wiring   wire-sitekey: S4 must FAIL; W1 control must PASS
//   wiring   wire-rank  : N1 must FAIL;  W1 control must PASS
//   wiring   wire-roster: N2 must FAIL;  W1 control must PASS
//   wiring   wire-keyclaim:   K3 must FAIL; W1 control must PASS
//   wiring   wire-boundclaim: W13 must FAIL; W1 control must PASS
//   wiring   wire-advertise:  W14b W15b must FAIL; W1 control must PASS
//   wiring   wire-patcheslive: W14c must FAIL; W1 control must PASS
//   wiring   wire-compatclaim: W17 must FAIL; W1 control must PASS
//   wiring   wire-logquote:   W19 must FAIL; W1 control must PASS
//   wiring   wire-blindwrite: W20 must FAIL; W1 control must PASS
//   wiring   wire-monotone:   W21 must FAIL; W1 control must PASS
//   prior-r2            : N1 N2 N3 N4 N5 N6 must all FAIL; W1 control must PASS
// Every OTHER case here has NO mutant of its own, and this is the whole list
// with the reason each one is on it:
//   G3, G5, C3, D1, D2, D3, S2, S3, K2, P1, P2  - controls and companion
//     assertions over functions another mutant already reaches.
//   G8                                          - companion of the withdrawal
//     group: wire-blindwrite holds the branch that emits its line, and the
//     distinctness it asserts is the same property D4 and S1 already carry a
//     mutant for.
//   W4, W6, W7a-c, W9a-c, W12                   - wiring anchors whose finding
//     is carried by a sibling wiring mutant.
//   W14, W15a, W16a, W16b, W16c                 - the same, for the capability
//     advertisement: wire-advertise is this group's mutant and reddens W14b and
//     W15b; these five are the companions it does not move.
//   W18                                         - the structural half of W17's
//     property (the compat withdrawal sits above the earliest point from which
//     this key can be staged); wire-compatclaim is that group's mutant.
//   W22                                         - the structural fact W21's
//     corrected paragraph cites; wire-monotone is that group's mutant.
// The list is derived by reading it against the run list above, not asserted -
// which is how V6 came to sit outside BOTH lists for a round while the header
// claimed the accounting was complete. A documented "every case has a mutant"
// can be true of the list and false of the suite.
//
// run-tests.ps1 also carries ONE check that is not a case here at all: the
// capability key's absence from the base release tag, which K3's argument
// rests on and no compiled case can reach. It has a positive control of its
// own - a key of the same family that did ship - and is reported in the log
// as "RESULT capability key never released".
internal static class Program
{
    private static int _failed;
    private static int _passed;

    private static void Check(string name, bool ok, string detail)
    {
        if (ok) { _passed++; Console.WriteLine("PASS  " + name); }
        else { _failed++; Console.WriteLine("FAIL  " + name + "  -- " + detail); }
    }

    private static readonly ProximityGateState[] GateStates =
        (ProximityGateState[])Enum.GetValues(typeof(ProximityGateState));

    private static readonly bool[] Booleans = new[] { true, false };

    private static readonly ProximityVanillaAnswer[] VanillaAnswers =
        (ProximityVanillaAnswer[])Enum.GetValues(typeof(ProximityVanillaAnswer));

    // ---------------------------------------------------------------------
    // Reading the shipped files the harness cannot compile.
    //
    // An UNSET root is a FAILURE and never a skip: a check that quietly does
    // nothing when its input is missing is the check that cannot fail (#342).
    // ---------------------------------------------------------------------
    private static readonly string SourceRoot = Environment.GetEnvironmentVariable("BUG389_SOURCE_ROOT");

    private static string LoadSource(string relative)
    {
        if (string.IsNullOrEmpty(SourceRoot)) return null;
        string path = System.IO.Path.Combine(SourceRoot, relative.Replace('/', System.IO.Path.DirectorySeparatorChar));
        if (!System.IO.File.Exists(path)) return null;
        return System.IO.File.ReadAllText(path);
    }

    /// <summary>CountOf, restricted to lines that are not whole-line comments.
    ///
    /// "This global is read in exactly one place" is a statement about CODE, and
    /// the prose around the member names the same identifier several times, so a
    /// raw count can neither be 1 nor be made 1 without deleting the explanation.
    /// Both files here comment by whole line, so dropping lines whose first
    /// non-space characters are "//" is the whole rule; a needle inside a string
    /// literal would still count, which is the safe direction for a bound.</summary>
    private static int CountOnCodeLines(string text, string needle)
    {
        if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(needle)) return 0;
        int n = 0;
        foreach (string line in text.Split((char)10))
        {
            string t = line.TrimStart();
            if (t.StartsWith("//", StringComparison.Ordinal)) continue;
            n += CountOf(line, needle);
        }
        return n;
    }

    private static int CountOf(string text, string needle)
    {
        if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(needle)) return 0;
        int n = 0, i = 0;
        while (true)
        {
            int at = text.IndexOf(needle, i, StringComparison.Ordinal);
            if (at < 0) return n;
            n++;
            i = at + needle.Length;
        }
    }

    /// <summary>Bound a C# member by INDENTATION, not by counting braces.
    ///
    /// Counting braces reads a literal `{` inside a string as structure, and
    /// ApiClient.cs is full of JSON in string literals - the count never returns
    /// to zero and the member cannot be bounded at all, which is how W7b failed
    /// on a file whose wiring was perfectly correct. Every member here closes with
    /// a brace alone on a line at the declaration's own indentation, so that is
    /// what this looks for.</summary>
    private static int MemberEnd(string text, int signatureAt, int open)
    {
        char nl = (char)10;
        int lineStart = text.LastIndexOf(nl, signatureAt) + 1;
        int indent = 0;
        while (lineStart + indent < text.Length && text[lineStart + indent] == ' ') indent++;
        string closer = nl + new string(' ', indent) + "}";
        int close = text.IndexOf(closer, open, StringComparison.Ordinal);
        if (close < 0) return -1;
        return close + closer.Length - 1;
    }

    /// <summary>Assert an anchor occurs EXACTLY ONCE inside the member that must
    /// carry it - never file-wide (#432). A file-wide count cannot tell a line
    /// that is where it belongs from the same line relocated into another member,
    /// which is how wiring drifts off the branch it documents while the case that
    /// names it stays green.</summary>
    private static void CheckAnchorInMember(string name, string relative, string signature, string anchor)
    {
        string text = LoadSource(relative);
        if (text == null)
        {
            Check(name, false, "cannot read " + relative + " under BUG389_SOURCE_ROOT='"
                + (SourceRoot ?? "<unset>") + "' - an unset or wrong root is a failure, not a skip");
            return;
        }
        int sigs = CountOf(text, signature);
        if (sigs != 1) { Check(name, false, "member signature found " + sigs + " time(s) (want 1) in " + relative + ": " + signature); return; }
        int sig = text.IndexOf(signature, StringComparison.Ordinal);
        int open = text.IndexOf('{', sig);
        int close = open < 0 ? -1 : MemberEnd(text, sig, open);
        if (open < 0 || close < 0) { Check(name, false, "could not bound the member span in " + relative + ": " + signature); return; }
        string span = text.Substring(open, close - open + 1);
        int inSpan = CountOf(span, anchor);
        Check(name, inSpan == 1,
            "anchor occurs " + inSpan + " time(s) inside " + signature + " in " + relative
            + " (want 1), " + (CountOf(text, anchor) - inSpan) + " elsewhere in the file: " + anchor);
    }

    /// <summary>The same member bound, for a member that must carry one anchor
    /// and must carry NONE of another set.
    ///
    /// "It asks the one predicate" and "it does not read the facts behind the
    /// predicate itself" are two halves of one property, and only the pair of them
    /// says there is no second copy. A required-only check stays green on a member
    /// that calls the predicate AND re-derives the conjunction beside it, which is
    /// exactly the shape that produced the finding this closes.</summary>
    private static void CheckMemberAnchors(string name, string relative, string signature,
        string[] requiredOnce, string[] forbidden)
    {
        string text = LoadSource(relative);
        if (text == null)
        {
            Check(name, false, "cannot read " + relative + " under BUG389_SOURCE_ROOT='"
                + (SourceRoot ?? "<unset>") + "' - an unset or wrong root is a failure, not a skip");
            return;
        }
        int sigs = CountOf(text, signature);
        if (sigs != 1) { Check(name, false, "member signature found " + sigs + " time(s) (want 1) in " + relative + ": " + signature); return; }
        int sig = text.IndexOf(signature, StringComparison.Ordinal);
        int open = text.IndexOf('{', sig);
        int close = open < 0 ? -1 : MemberEnd(text, sig, open);
        if (open < 0 || close < 0) { Check(name, false, "could not bound the member span in " + relative + ": " + signature); return; }
        string span = text.Substring(open, close - open + 1);

        var problems = new List<string>();
        foreach (string anchor in requiredOnce)
        {
            int n = CountOf(span, anchor);
            if (n != 1) problems.Add("'" + anchor + "' occurs " + n + " time(s) inside (want 1)");
        }
        foreach (string anchor in forbidden)
        {
            int n = CountOf(span, anchor);
            if (n != 0) problems.Add("'" + anchor + "' occurs " + n + " time(s) inside (want 0)");
        }
        Check(name, problems.Count == 0,
            "in " + signature + " in " + relative + ": " + string.Join("; ", problems.ToArray()));
    }

    /// <summary>The same, for a file with no C# members: bound the region by a
    /// unique opening marker and the first closing marker after it.</summary>
    private static void CheckAnchorInSpan(string name, string relative, string startMarker, string endMarker, string anchor)
    {
        string text = LoadSource(relative);
        if (text == null)
        {
            Check(name, false, "cannot read " + relative + " under BUG389_SOURCE_ROOT='"
                + (SourceRoot ?? "<unset>") + "' - an unset or wrong root is a failure, not a skip");
            return;
        }
        int starts = CountOf(text, startMarker);
        if (starts != 1) { Check(name, false, "span marker found " + starts + " time(s) (want 1) in " + relative + ": " + startMarker); return; }
        int open = text.IndexOf(startMarker, StringComparison.Ordinal);
        int close = text.IndexOf(endMarker, open, StringComparison.Ordinal);
        if (close < 0) { Check(name, false, "could not bound the span in " + relative + ": " + startMarker); return; }
        string span = text.Substring(open, close - open);
        int inSpan = CountOf(span, anchor);
        Check(name, inSpan == 1,
            "anchor occurs " + inSpan + " time(s) inside the span in " + relative + " (want 1): " + anchor);
    }

    /// <summary>Assert a needle is ABSENT from a file. Used only where the file
    /// itself is the unit - "no selector of our own lives anywhere in here" is a
    /// statement about the file, not about one member, and scoping it to a member
    /// would let the thing move next door and stay green.</summary>
    private static void CheckAbsentFromFiles(string name, string[] relatives, string[] needles, string why)
    {
        var found = new List<string>();
        foreach (string rel in relatives)
        {
            string text = LoadSource(rel);
            if (text == null)
            {
                Check(name, false, "cannot read " + rel + " under BUG389_SOURCE_ROOT='"
                    + (SourceRoot ?? "<unset>") + "' - an unset or wrong root is a failure, not a skip");
                return;
            }
            foreach (string needle in needles)
            {
                int n = CountOf(text, needle);
                if (n > 0) found.Add(rel + " x" + n + " '" + needle + "'");
            }
        }
        Check(name, found.Count == 0, why + " -- found: " + string.Join(", ", found.ToArray()));
    }

    private static int Main()
    {
        Console.WriteLine("=== bug 389 - the repair decision, the gate, and the method change ===");

        // =================================================================
        // V - THE REPAIR DECISION. ProximityVictim.VictimAction is the whole
        // of it: four facts in, one action out, and no selector anywhere.
        // =================================================================

        // ---- V2: NEGATIVE CONTROL for "once", and for every V mutation. -------
        // One call, the accepting case, and it runs BEFORE V1 on purpose: a repair
        // that answers only the first time still answers the FIRST one, so this
        // control cannot see "once" while V1, which asks twice, must. Put it after
        // V1 and V1's own first call consumes the answer, the control reddens too,
        // and the mutation stops being a measurement of repetition. It is also untouched
        // by the ringless, writenull and suppress mutations, all of which move a
        // DECLINING branch.
        Check("V2 Repair_AnswersOnTheFirstCall",
            ProximityVictim.VictimAction(ProximityGateState.Capable, true, true, true)
                == ProximityPrefixAction.WriteVictimAndRun,
            "a capable room, an opponent effect, a ring-driven call and a resolved victim must be written");

        // ---- V1: the repair answers AGAIN on every call. RED under "once". ----
        // THE DEFECT, PUT BACK. Vanilla resolves its victim once and keeps it in a
        // private field it never re-derives (`if (!target)`,
        // DealDamageToPlayer.cs:33-40) while the ring that fires it re-evaluates
        // who is nearby every frame. If this decision answered only the first
        // time, the effect would keep its first victim exactly as an unpatched
        // build does - the repair would be inert and every other case here would
        // still pass. This is the case that measures the bug rather than the
        // reachability of a function.
        var first = ProximityVictim.VictimAction(ProximityGateState.Capable, true, true, true);
        var second = ProximityVictim.VictimAction(ProximityGateState.Capable, true, true, true);
        Check("V1 Repair_AnswersAgainOnEveryCall",
            first == ProximityPrefixAction.WriteVictimAndRun
            && second == ProximityPrefixAction.WriteVictimAndRun,
            "first=" + first + " second=" + second + " (both must write: the defect is a victim that survives repetition)");

        // ---- V3: no ring, no repair. RED under "ringless". --------------------
        // The defect is a field that survives REPEATED invocation, and only a
        // PlayerInRangeTrigger invokes these effects repeatedly. A_DemonicPact's
        // DealDamageToPlayer is AttackTrigger-driven and E_StunOverTime's
        // StunPlayer is DelayEvent-driven (BUG389-GATE0-OFFLINE.md); each has its
        // own rule that this repair does not model, so each keeps vanilla's
        // answer. Repairing them would be a selection of our own applied to a
        // call we never measured.
        Check("V3 Repair_LeavesVanillaAloneWhenNoRingDrivesTheCall",
            ProximityVictim.VictimAction(ProximityGateState.Capable, true, false, true)
                == ProximityPrefixAction.RunVanillaUntouched,
            "a call no proximity ring drives must keep vanilla's own resolution");

        // ---- V4: nobody resolved, nothing written. RED under "writenull". -----
        // This is the STALE-VICTIM decision, and round 3 makes it from what the
        // game's own targeting returned rather than from a ranking of our own.
        // When that call answers with nobody the field is left exactly as it was
        // found - vanilla runs against its own cached target, which is today's
        // shipped behaviour. Writing the empty answer instead would hand vanilla
        // a field it dereferences with no null guard (DealDamageToPlayer.cs:45,
        // StunPlayer.cs:27, TeleportToOpponent.cs:24).
        Check("V4 Repair_NeverWritesWhenTheGamesTargetingAnsweredWithNobody",
            ProximityVictim.VictimAction(ProximityGateState.Capable, true, true, false)
                == ProximityPrefixAction.RunVanillaUntouched,
            "an unresolved victim must leave vanilla's field untouched");

        // ---- V5: THE REPAIR CANNOT SUPPRESS ANYTHING. RED under "suppress". ---
        // Over the WHOLE cross product of the four facts, the action is never
        // SkipOriginal and the return to Harmony is always true.
        //
        // This is the bar row the previous design could not meet. It re-derived
        // vanilla's own predicate - visibility, range, liveness - and returned
        // false when its re-derivation disagreed, which was the one route by
        // which a repair meant to change WHO takes damage could change WHETHER
        // anyone does. The predicate is deleted, so the route is gone; this case
        // is what keeps it gone.
        bool neverSuppresses = true;
        string suppressAt = "";
        foreach (var gate in GateStates)
            foreach (bool other in Booleans)
                foreach (bool ring in Booleans)
                    foreach (bool answered in Booleans)
                    {
                        var act = ProximityVictim.VictimAction(gate, other, ring, answered);
                        if (act == ProximityPrefixAction.SkipOriginal || !ProximityVictim.PrefixReturn(act))
                        {
                            neverSuppresses = false;
                            if (suppressAt.Length == 0)
                                suppressAt = gate + "/other=" + other + "/ring=" + ring + "/answered=" + answered + " -> " + act;
                        }
                    }
        Check("V5 Repair_NeverSuppressesTheOriginal", neverSuppresses,
            "a victim repair may never decline a tick vanilla applies; first at " + suppressAt);

        // ---- V6: the accepting case is EXACTLY one corner of that product. ----
        // Companion to V5 rather than a mutant of its own: it states that the
        // four terms are all required, so none of them can be dropped without
        // another case noticing.
        bool onlyTheOneCorner = true;
        string acceptLeak = "";
        foreach (var gate in GateStates)
            foreach (bool other in Booleans)
                foreach (bool ring in Booleans)
                    foreach (bool answered in Booleans)
                    {
                        bool writes = ProximityVictim.VictimAction(gate, other, ring, answered)
                            == ProximityPrefixAction.WriteVictimAndRun;
                        bool wanted = gate == ProximityGateState.Capable && other && ring && answered;
                        if (writes != wanted)
                        {
                            onlyTheOneCorner = false;
                            if (acceptLeak.Length == 0)
                                acceptLeak = gate + "/other=" + other + "/ring=" + ring + "/answered=" + answered
                                    + " writes=" + writes + " wanted=" + wanted;
                        }
                    }
        Check("V6 Repair_WritesOnlyWhenAllFourTermsHold", onlyTheOneCorner,
            "every one of the four terms is required; wrong answer at " + acceptLeak);

        // =================================================================
        // D - THE DECLINE REASONS. A feature that is INACTIVE and one that is
        // active and declining must not produce the same silence (#438/#443).
        // =================================================================

        // ---- D1: a ring-less call says so. ------------------------------------
        Check("D1 Decline_NamesTheRingWhenNoRingDrivesTheCall",
            ProximityVictim.DeclineReason(ProximityGateState.Capable, true, false, ProximityVanillaAnswer.NotAsked)
                == "no proximity ring drives this call",
            "got '" + ProximityVictim.DeclineReason(ProximityGateState.Capable, true, false, ProximityVanillaAnswer.NotAsked) + "'");

        // ---- D2: an empty resolution says so, and does not blame the room. ----
        // CONTROL for the "answerreason" mutation: this path keeps its own line
        // when two OTHER paths are made to share one, which is what makes D4/D5 a
        // measurement of the collision and not of this sentence.
        Check("D2 Decline_NamesTheGamesTargetingWhenItAnsweredWithNobody",
            ProximityVictim.DeclineReason(ProximityGateState.Capable, true, true, ProximityVanillaAnswer.Nobody)
                == "the game's own targeting answered with nobody",
            "got '" + ProximityVictim.DeclineReason(ProximityGateState.Capable, true, true, ProximityVanillaAnswer.Nobody) + "'");

        // ---- D3: a reason never names a term the decision did not reach. ------
        // DeclineReason answers in the SAME order VictimAction decides, so a
        // declined call cannot be told "no ring drives this" when the gate
        // refused before the ancestor was ever walked, nor "the targeting
        // answered with nobody" when no call was made. Both would be false
        // statements about the call (#351).
        bool reasonsReachable = true;
        string unreachableReason = "";
        foreach (var gate in GateStates)
            foreach (bool other in Booleans)
                foreach (bool ring in Booleans)
                    foreach (var answer in VanillaAnswers)
                    {
                        string why = ProximityVictim.DeclineReason(gate, other, ring, answer);
                        bool gateRefused = !ProximityVictim.ShouldRepair(gate, other);
                        bool blamesRing = why == "no proximity ring drives this call";
                        bool blamesTargeting = why != ProximityVictim.GateReason(gate)
                            && why != "the effect targets its own player"
                            && !blamesRing;
                        if (gateRefused && (blamesRing || blamesTargeting))
                        {
                            reasonsReachable = false;
                            if (unreachableReason.Length == 0)
                                unreachableReason = gate + "/other=" + other + " -> '" + why + "'";
                        }
                        // A ring-less call may never be told anything about a
                        // resolution that was never made, whatever value the term
                        // carries.
                        if (!gateRefused && !ring && why != "no proximity ring drives this call")
                        {
                            reasonsReachable = false;
                            if (unreachableReason.Length == 0)
                                unreachableReason = "ring-less call reported '" + why + "'";
                        }
                        if (!gateRefused && ring && answer == ProximityVanillaAnswer.Answered
                            && why != "the repair is active")
                        {
                            reasonsReachable = false;
                            if (unreachableReason.Length == 0)
                                unreachableReason = "accepting call reported '" + why + "'";
                        }
                    }
        Check("D3 Decline_NeverNamesATermTheDecisionDidNotReach", reasonsReachable,
            "a reason named a fact that was never established: " + unreachableReason);

        // ---- D4: every outcome of the one vanilla call has its OWN line. ------
        // RED under "answerreason". Four different paths through
        // ProximityVictimResolver.VanillaVictimFor used to arrive as one null and
        // print one sentence - "the game's own targeting answered with nobody" -
        // which was a false statement on three of them. The line is ALSO the
        // budget key (SignalKey keys on outcome and reason, deliberately not on
        // the site), so two paths sharing a line means the second cause can never
        // be printed in a session at all: the reader is told the first one
        // instead, and the repair that stayed vanilla for a missing holder reads
        // as a room where nobody was in range.
        var answerOwner = new Dictionary<string, string>();
        bool answerLinesDistinct = true;
        string answerCollision = "";
        foreach (var answer in VanillaAnswers)
        {
            string answerLine = ProximityVictim.VanillaAnswerReason(answer);
            if (string.IsNullOrEmpty(answerLine))
            { answerLinesDistinct = false; answerCollision = answer + " has no reason line"; break; }
            if (answer == ProximityVanillaAnswer.Answered) continue;   // the accepting line is shared with the gate by design
            if (answerOwner.ContainsKey(answerLine))
            { answerLinesDistinct = false; answerCollision = answer + " shares a line with " + answerOwner[answerLine] + ": " + answerLine; break; }
            answerOwner[answerLine] = answer.ToString();
        }
        // Distinct lines are distinct BUDGETS, which is the property that makes
        // each cause printable once per session rather than at most one of them.
        bool budgetsDistinct = ProximityVictim.SignalKey("defer", ProximityVictim.VanillaAnswerReason(ProximityVanillaAnswer.NoHolder))
            != ProximityVictim.SignalKey("defer", ProximityVictim.VanillaAnswerReason(ProximityVanillaAnswer.Nobody));
        Check("D4 Decline_EveryVanillaOutcomeHasItsOwnReasonAndItsOwnBudget",
            answerLinesDistinct && budgetsDistinct && VanillaAnswers.Length == 6,
            "outcomes=" + VanillaAnswers.Length + " (want 6) budgets distinct=" + budgetsDistinct
            + " " + answerCollision);

        // ---- D5: the line named is the line of the path that happened. --------
        // RED under "answerreason" AND under "answerline". D4 says the lines differ
        // from each other; this says each one is attached to its own outcome. Two
        // paths could carry distinct-but-swapped sentences and D4 alone would stay
        // green (#342).
        //
        // WHAT USED TO STAND HERE COULD NOT FAIL. The loop compared
        // DeclineReason(Capable, true, true, answer) with VanillaAnswerReason(
        // answer) - and DeclineReason DELEGATES to VanillaAnswerReason at exactly
        // that fall-through (Seam: "return VanillaAnswerReason(vanilla);"), so the
        // two sides were the same expression and the loop was true for every
        // possible assignment of lines to outcomes. All the swap detection this
        // case claimed sat in the three literals beside it, which covered three of
        // the six outcomes. NotAsked's line was pinned NOWHERE in the suite: it
        // could be given any distinct sentence and all 65 clean checks stayed green
        // (#342/#441).
        //
        // So the expectation is now an INDEPENDENT table, written out here rather
        // than read back from the thing under test, and it covers every outcome.
        // The count assertion is what stops a new outcome being added to the enum
        // and silently skipped.
        var expectedAnswerLines = new Dictionary<ProximityVanillaAnswer, string>
        {
            { ProximityVanillaAnswer.Answered,  "the repair is active" },
            { ProximityVanillaAnswer.NotAsked,  "the game's own targeting was not asked" },
            { ProximityVanillaAnswer.NoManager, "the game's player manager was not available" },
            { ProximityVanillaAnswer.NoHolder,  "this effect has no player of its own to target from" },
            { ProximityVanillaAnswer.Nobody,    "the game's own targeting answered with nobody" },
            { ProximityVanillaAnswer.Threw,     "the game's own targeting could not complete" },
        };
        bool eachOutcomeNamed = true;
        string misnamed = "";
        foreach (var answer in VanillaAnswers)
        {
            string expected;
            if (!expectedAnswerLines.TryGetValue(answer, out expected))
            {
                eachOutcomeNamed = false;
                if (misnamed.Length == 0) misnamed = answer + " is an outcome this case does not name at all";
                continue;
            }
            string stated = ProximityVictim.VanillaAnswerReason(answer);
            if (stated != expected)
            {
                eachOutcomeNamed = false;
                if (misnamed.Length == 0)
                    misnamed = answer + " reads '" + stated + "' (want '" + expected + "')";
                continue;
            }
            // ...and the decline path's fall-through must carry that same line.
            // NotAsked is excluded HERE only: with a ring driving the call the ring
            // term cannot have answered, and D3 owns that ordering.
            if (answer == ProximityVanillaAnswer.NotAsked) continue;
            string why = ProximityVictim.DeclineReason(ProximityGateState.Capable, true, true, answer);
            if (why != expected)
            {
                eachOutcomeNamed = false;
                if (misnamed.Length == 0) misnamed = answer + " declined as '" + why + "' (want '" + expected + "')";
            }
        }
        Check("D5 Decline_NamesTheOutcomeThatActuallyHappened",
            eachOutcomeNamed && expectedAnswerLines.Count == VanillaAnswers.Length,
            "named=" + expectedAnswerLines.Count + " outcomes=" + VanillaAnswers.Length
            + " a declined call named another path's outcome: " + misnamed);

        // =================================================================
        // G - THE CAPABILITY GATE.
        // =================================================================

        // ---- G1: the gate is load-bearing. RED under the "gate" mutation. -----
        Check("G1 Gate_RefusesWhenRoomNotCapable",
            ProximityVictim.ShouldRepair(ProximityGateState.RoomNotAllCapable, true) == false,
            "a room that does not all carry the fix must stay on vanilla");

        // ---- G2: NEGATIVE CONTROL for "gate" and "gatereason". ----------------
        // The own-player branch caches data.player without ever calling
        // GetOtherPlayer, so it stays vanilla whatever the room advertises, and
        // its reason line is its own either way.
        Check("G2 Gate_RefusesWhenEffectTargetsOwnPlayer",
            ProximityVictim.ShouldRepair(ProximityGateState.Capable, false) == false,
            "the own-player branch caches data.player and must stay vanilla");

        Check("G3 Gate_AllowsWhenCapableAndTargetingOther",
            ProximityVictim.ShouldRepair(ProximityGateState.Capable, true), "should repair");

        // ---- G4: REASON UNIQUENESS, and nothing else. RED under "gatereason". -
        // Five different facts leave the repair inactive and only one of them is
        // about the peers. The reason is also the budget key (SignalKey), so two
        // causes sharing a line means the second is never printed at all and the
        // reader is told the first one instead - which is how "the room does not
        // all carry the repair" came to be printed for a patch that failed to
        // attach locally, and in the main menu, where there is no room (#430).
        //
        // The gate-state x polarity cross product is G5's, not this one's: a
        // report that credits the coverage to the wrong case sends the next
        // reader to a test that does not contain it.
        var reasonOwner = new Dictionary<string, string>();
        bool reasonsDistinct = true;
        string reasonCollision = "";
        foreach (var gs in GateStates)
        {
            string reason = ProximityVictim.InactiveReason(gs, true);
            if (string.IsNullOrEmpty(reason))
            { reasonsDistinct = false; reasonCollision = gs + " has no reason line"; break; }
            if (reasonOwner.ContainsKey(reason))
            { reasonsDistinct = false; reasonCollision = gs + " shares a line with " + reasonOwner[reason] + ": " + reason; break; }
            reasonOwner[reason] = gs.ToString();
        }
        string ownPlayerReason = ProximityVictim.InactiveReason(ProximityGateState.Capable, false);
        Check("G4 Gate_EveryInactiveCauseHasItsOwnReason",
            reasonsDistinct && GateStates.Length == 6 && !reasonOwner.ContainsKey(ownPlayerReason),
            "states=" + GateStates.Length + " (want 6) "
            + (reasonCollision.Length > 0 ? reasonCollision : "own-player line collides with a gate line: " + ownPlayerReason));

        // ---- G5: the gate-state x polarity cross product, in the case that ----
        // claims it. Anything that is not Capable refuses, and so does the
        // own-player polarity, so every unhandled combination falls toward
        // vanilla-unchanged rather than toward applying something (#276/#430).
        bool onlyCapableRepairs = true;
        string repairLeak = "";
        foreach (var gs in GateStates)
            foreach (bool other in Booleans)
            {
                bool repairs = ProximityVictim.ShouldRepair(gs, other);
                bool wanted = gs == ProximityGateState.Capable && other;
                if (repairs != wanted)
                { onlyCapableRepairs = false; repairLeak = gs + "/targetsOther=" + other + " -> " + repairs; break; }
            }
        Check("G5 Gate_OnlyACapableRoomAndAnOpponentEffectRepairs",
            onlyCapableRepairs && GateStates.Length == 6,
            "states=" + GateStates.Length + " (want 6) wrong answer at " + repairLeak);

        // ---- G6: WHAT THIS SEAT ADVERTISES IS WHAT THIS SEAT WILL DO. ---------
        // RED under "localgate". The advert and the local gate are one answer to
        // one question, and this is the whole of that answer: the mod being
        // switched off and the patches not being attached BOTH refuse, and the
        // disabled state outranks the attachment count because it is a statement
        // about the whole build.
        //
        // The defect this closes: the advert was staged on the attachment count
        // alone while the gate also required the mod to be on, so a seat whose
        // compat check disabled the mod kept telling the room it would repair. Its
        // peers' census then found the key on every fighter and re-resolved the
        // victim every armed tick while this seat drained the stale cached one -
        // one drain tick debiting a different player's health on different
        // screens, which decides a round, a series and a rating.
        bool localAnswers =
            ProximityVictim.LocalGateState(false, true) == ProximityGateState.Capable
            && ProximityVictim.LocalGateState(true, true) == ProximityGateState.ModDisabled
            && ProximityVictim.LocalGateState(false, false) == ProximityGateState.PatchesNotAttached
            && ProximityVictim.LocalGateState(true, false) == ProximityGateState.ModDisabled;
        // Only the both-true corner may advertise, over the whole product.
        bool onlyBothTermsAdvertise = true;
        string advertLeak = "";
        foreach (bool disabled in Booleans)
            foreach (bool live in Booleans)
            {
                bool capable = ProximityVictim.LocalGateState(disabled, live) == ProximityGateState.Capable;
                bool wanted = !disabled && live;
                if (capable != wanted)
                {
                    onlyBothTermsAdvertise = false;
                    if (advertLeak.Length == 0)
                        advertLeak = "disabled=" + disabled + "/live=" + live + " -> capable=" + capable;
                }
            }
        Check("G6 Gate_TheAdvertisedBitIsTheConjunctionTheLocalGateEvaluates",
            localAnswers && onlyBothTermsAdvertise,
            "a seat that will not repair must not advertise; wrong answer at " + advertLeak);

        // ---- G7: a seat that stops being capable withdraws. RED under ---------
        // "norevoke". The polarity is the point and it runs one way only: this
        // function has no advertising direction, because a capability that appears
        // mid-room is the racy path the pre-join staging exists to avoid (#287),
        // while one that disappears can only move the room toward
        // vanilla-unchanged (#276/#430). A seat that never advertised has nothing
        // to withdraw and must not write per tick for nothing.
        bool revokesExactlyWhenNeeded = true;
        string revokeLeak = "";
        foreach (var gs in GateStates)
            foreach (bool advertised in Booleans)
            {
                bool revokes = ProximityVictim.ShouldRevokeCapability(gs, advertised);
                bool wanted = advertised && gs != ProximityGateState.Capable;
                if (revokes != wanted)
                {
                    revokesExactlyWhenNeeded = false;
                    if (revokeLeak.Length == 0)
                        revokeLeak = gs + "/advertised=" + advertised + " -> " + revokes + " (want " + wanted + ")";
                }
            }
        Check("G7 Gate_AnAdvertisedSeatThatStopsBeingCapableWithdrawsIt",
            revokesExactlyWhenNeeded && GateStates.Length == 6,
            "states=" + GateStates.Length + " (want 6) wrong answer at " + revokeLeak);

        // ---- G8: a withdrawal the client REFUSED to send has its own line. ----
        // No mutant of its own - wire-blindwrite is this group's, and it holds the
        // branch that emits this line. The property is the one D4 and S1 hold for
        // every other cause: the sentence is also the budget key, so a cause that
        // shares a line with another is never printed once that other has spoken.
        //
        // Why this cause exists at all: the property write that withdraws the key
        // reports refusal by RETURNING false, not by throwing. A refused write sent
        // nothing and cached nothing, so the seat is still advertising a repair it
        // will not perform and the next tick must try again - a state the reader
        // has to be able to tell apart from "withdrew", which is a line about a
        // write the room actually received.
        bool withdrawLineDistinct = !string.IsNullOrEmpty(ProximityVictim.WithdrawRefusedReason);
        string withdrawCollision = withdrawLineDistinct ? "" : "the refusal has no line at all";
        foreach (var gs in GateStates)
            if (ProximityVictim.GateReason(gs) == ProximityVictim.WithdrawRefusedReason)
            {
                withdrawLineDistinct = false;
                if (withdrawCollision.Length == 0) withdrawCollision = "shares the line of gate state " + gs;
            }
        foreach (var answer in VanillaAnswers)
            if (ProximityVictim.VanillaAnswerReason(answer) == ProximityVictim.WithdrawRefusedReason)
            {
                withdrawLineDistinct = false;
                if (withdrawCollision.Length == 0) withdrawCollision = "shares the line of outcome " + answer;
            }
        bool withdrawKeyDistinct =
            ProximityVictim.SignalKey("withdraw", ProximityVictim.WithdrawRefusedReason)
                != ProximityVictim.SignalKey("withdraw", ProximityVictim.GateReason(ProximityGateState.ModDisabled));
        Check("G8 Gate_ARefusedWithdrawalHasItsOwnReasonAndItsOwnBudget",
            withdrawLineDistinct && withdrawKeyDistinct,
            "the refused-withdrawal line must be its own: " + withdrawCollision);

        // =================================================================
        // C - THE CAPABILITY CACHE KEY.
        // =================================================================

        // ---- C1: re-derives on a same-frame change. RED under "capkey". -------
        // An actor can join, an actor can leave, and a property delivery can land
        // inside one frame - one PUN Dispatch drains several with no frame
        // boundary between them. A cached TRUE that survives such a change says
        // "every seat in this room carries the repair" about a room that has since
        // changed, and this gate decides whether seats re-resolve the victim.
        var cache1 = new ProximityCapabilityCache();
        bool capBefore = cache1.Evaluate(7, 1, delegate { return true; });
        bool capAfter = cache1.Evaluate(7, 2, delegate { return false; });
        Check("C1 Cache_ReDerivesWhenTheRoomChangesInsideAFrame",
            capBefore && !capAfter,
            "before=" + capBefore + " after=" + capAfter + " (want true then false)");

        // ---- C2: NEGATIVE CONTROL for "capkey". -------------------------------
        // With BOTH key terms unchanged the answer must be reused and the census
        // run exactly once. A frame-only key reuses it here too, so this control
        // cannot see the mutation - which is what makes C1 a measurement of the
        // stamp specifically and not of caching in general.
        var cache2 = new ProximityCapabilityCache();
        int censusRuns = 0;
        Func<bool> counting = delegate { censusRuns++; return true; };
        bool reuse1 = cache2.Evaluate(11, 4, counting);
        bool reuse2 = cache2.Evaluate(11, 4, counting);
        Check("C2 Cache_ReusesTheAnswerWhenNothingChanged",
            reuse1 && reuse2 && censusRuns == 1,
            "runs=" + censusRuns + " (want 1) answers=" + reuse1 + "/" + reuse2);

        // ---- C3: a cache with no census answers the inert way. ----------------
        Check("C3 Cache_WithoutACensusIsInert",
            new ProximityCapabilityCache().Evaluate(1, 1, null) == false,
            "a cache with nothing to ask must not report a capable room");

        // =================================================================
        // S - THE BOUNDED OUTCOME SIGNALS.
        // =================================================================

        // ---- S1: outcome AND reason are both in the budget key. RED under -----
        // "reasonkey", which drops the reason so two causes share a budget and
        // the second is never printed.
        string kRing = ProximityVictim.SignalKey("defer", "no proximity ring drives this call");
        string kNobody = ProximityVictim.SignalKey("defer", "the game's own targeting answered with nobody");
        string kInactive = ProximityVictim.SignalKey("inactive", "no proximity ring drives this call");
        Check("S1 Signals_EachOutcomeAndReasonGetsItsOwnBudget",
            kRing != kNobody && kRing != kInactive && kNobody != kInactive
            && kRing == ProximityVictim.SignalKey("defer", "no proximity ring drives this call"),
            "keys collided or were unstable: " + kRing + " | " + kNobody + " | " + kInactive);

        // ---- S2: NEGATIVE CONTROL for "reasonkey" and for "wire-sitekey". -----
        // The LINE keeps naming all three things whatever the KEY is charged to,
        // so the reader still learns which effect spoke. That is what makes it
        // safe for the key to drop the site (S4).
        string line = ProximityVictim.SignalText("StunPlayer", "defer", "no proximity ring drives this call");
        Check("S2 Signals_TheLineNamesSiteOutcomeAndReason",
            line.Contains("StunPlayer") && line.Contains("defer") && line.Contains("no proximity ring drives this call"),
            "got " + line);

        // ---- S3: one line per reason, not one per tick. -----------------------
        Check("S3 Signals_AreBoundedToOnePerReason",
            ProximityVictim.MaxOutcomeSignals == 1,
            "got " + ProximityVictim.MaxOutcomeSignals + " (a per-tick effect may not repeat itself)");

        // ---- S4: THE BUDGET IS PER REASON PER SESSION, NOT PER SITE. ----------
        // RED under the "wire-sitekey" wiring mutation, which charges the key per
        // site again.
        //
        // With the site in the key, "the room does not all carry the repair" -
        // one fact about one room - was charged to three separate budgets and
        // could print three times, and the same held for every local cause. The
        // key is built in exactly one place and this asserts what it is built
        // from. A compiled case cannot reach this: SignalKey no longer takes a
        // site, so the only way to put one back is at the call, which is a file
        // this harness cannot compile.
        CheckAnchorInMember("S4 Signals_TheBudgetKeyIsNotChargedPerSite",
            "plugin/ProximityVictimPatches.cs",
            "internal static void NoteOutcome(string site, string outcome, string why)",
            "ProximityVictim.SignalKey(outcome, why),");

        // =================================================================
        // K - THE CAPABILITY KEY ITSELF.
        // =================================================================

        // ---- K1: the fighter capability list carries this key. RED under ------
        // "fighterkeys", which empties the list.
        bool carriesProx = false;
        foreach (var key in ProximityVictim.FighterCapabilityKeys)
            if (key == ProximityVictim.CapabilityProp) carriesProx = true;
        Check("K1 Capability_SpectatorStagingClearsTheProximityKey",
            carriesProx && ProximityVictim.FighterCapabilityKeys.Length > 0,
            "the key a spectator must stop advertising is not in the cleared set");

        // ---- K2: NEGATIVE CONTROL for "fighterkeys". --------------------------
        // The key's NAME carries the protocol version and is read by peers; it is
        // unaffected by what the cleared set contains.
        //
        // Round 3 kept cr_prox1, and NOT because the two builds choose alike.
        // They do not: round 2 ranked the candidates with a selector of its own
        // and deferred entirely on an Any-target ring, where this build re-runs
        // PlayerManager.GetOtherPlayer unconditionally. Under the key's own rule
        // that is a cr_prox2 change. What makes cr_prox1 correct is narrower: no
        // released build advertises the key at all, so there is no population for
        // a census to be wrong about. K3 holds the seam to that argument and the
        // runner checks the absence at the base release tag.
        Check("K2 Capability_KeyIsTheVersionedName",
            ProximityVictim.CapabilityProp == "cr_prox1" && ProximityVictim.CapabilityValue == 1,
            "got " + ProximityVictim.CapabilityProp + "=" + ProximityVictim.CapabilityValue);

        // ---- K3: the non-rotation argument is the checkable one. RED under ---
        // the "keyclaim" wiring mutant.
        //
        // A capability key is a promise to peers, so the argument for NOT moving
        // it is load-bearing and the one that shipped was false: it said both
        // builds resolve alike. This asserts the seam rests on the fact instead -
        // that the key has never left this branch - and that the refuted sentence
        // is gone rather than merely joined by a truer one.
        string seamForKey = LoadSource("plugin/ProximityVictimSeam.cs");
        Check("K3 Capability_TheNonRotationArgumentIsTheNeverReleasedOne",
            seamForKey != null
            && CountOf(seamForKey, "released build advertises it at all") == 1
            && CountOf(seamForKey, "comparing like with like") == 0,
            "the key paragraph must rest on the key never having been released, not on the two builds choosing alike");

        // =================================================================
        // P - THE TWO PREFIXES ON StunPlayer.Go.
        // =================================================================

        // ---- P1: NEGATIVE CONTROL for "chainlast" and "guardopen". ------------
        // The return mapping itself: only SkipOriginal suppresses. Neither the
        // fold nor the null guard's own answer can reach this.
        Check("P1 Prefix_OnlySkipOriginalSuppressesTheOriginal",
            ProximityVictim.PrefixReturn(ProximityPrefixAction.RunVanillaUntouched)
            && ProximityVictim.PrefixReturn(ProximityPrefixAction.WriteVictimAndRun)
            && !ProximityVictim.PrefixReturn(ProximityPrefixAction.SkipOriginal),
            "the mapping from action to Harmony's bool is wrong");

        // ---- P2: the victim repair writes only on its accepting action. -------
        Check("P2 Prefix_WritesOnlyOnTheAcceptingAction",
            ProximityVictim.VictimAction(ProximityGateState.Capable, true, true, true)
                == ProximityPrefixAction.WriteVictimAndRun
            && ProximityVictim.VictimAction(ProximityGateState.NotInARoom, true, true, true)
                == ProximityPrefixAction.RunVanillaUntouched,
            "the write and the run must be the same decision");

        // ---- P3: the run decision is order-independent. RED under "chainlast". -
        // StunPlayer.Go carries TWO prefixes - this repair and
        // PerfPatches.StunPlayerGoNullGuard - and neither declares a priority, so
        // their order is undefined. This composes the seam's model of HarmonyX's
        // fold in BOTH orders over the two SHIPPED decision functions:
        // ProximityVictim.VictimAction, which the repair returns through, and
        // ProximityVictim.NullGuardAction, which the null guard now returns
        // through. Neither side is a boolean this test invented - that was the
        // defect in the previous version of this case, and it is why the sibling's
        // body had to move into the seam.
        //
        // WHAT THIS PROVES AND WHAT IT DOES NOT. It proves the seam's own model is
        // order-stable and that the mutation can break it. It does NOT prove that
        // HarmonyX composes this way in the running game; the emitted fold is read
        // from the shipped 0Harmony.dll and cited on RunOriginalAfter, and the
        // claim that this game build takes that code path is the witness's (#83).
        // What holds without either is NARROWER than this case used to say, and P5
        // is where it is measured: on the two methods this repair patches alone it
        // returns true on every path (V5), so a different fold can only fail to run
        // it and leave the seat on vanilla - but on StunPlayer.Go, which also
        // carries the perf null guard, an unconditional true is the identity
        // element of a CONJUNCTION and of nothing else.
        bool orderStable = true;
        string firstDivergence = "";
        foreach (var gate in GateStates)
            foreach (bool other in Booleans)
                foreach (bool ring in Booleans)
                    foreach (bool answered in Booleans)
                        foreach (bool guardOn in Booleans)
                            foreach (bool instPresent in Booleans)
                                foreach (bool ancPresent in Booleans)
                                {
                                    bool ours = ProximityVictim.PrefixReturn(
                                        ProximityVictim.VictimAction(gate, other, ring, answered));
                                    bool sibling = ProximityVictim.PrefixReturn(
                                        ProximityVictim.NullGuardAction(guardOn, instPresent, ancPresent));

                                    // Harmony starts from "the original runs" and
                                    // folds each prefix's answer in, in whatever
                                    // order it called them.
                                    bool oursFirst = ProximityVictim.RunOriginalAfter(
                                        ProximityVictim.RunOriginalAfter(true, ours), sibling);
                                    bool siblingFirst = ProximityVictim.RunOriginalAfter(
                                        ProximityVictim.RunOriginalAfter(true, sibling), ours);
                                    if (oursFirst != siblingFirst)
                                    {
                                        orderStable = false;
                                        if (firstDivergence.Length == 0)
                                            firstDivergence = gate + "/other=" + other + "/ring=" + ring
                                                + "/answered=" + answered + "/guard=" + guardOn
                                                + "/inst=" + instPresent + "/anc=" + ancPresent
                                                + " ours-first=" + oursFirst + " sibling-first=" + siblingFirst;
                                    }
                                }
        Check("P3 Prefix_RunDecisionIsOrderIndependentWithTheSiblingPrefix",
            orderStable,
            "the two shipped prefixes disagree depending on order; first at " + firstDivergence);

        // ---- P4: the sibling still suppresses exactly when it used to. --------
        // RED under "guardopen". Moving the null guard's decision into the seam
        // is a refactor and must not change what it decides: gate off -> run
        // vanilla; instance and ancestor both present -> run vanilla; otherwise
        // skip the original, which is the cascade of exceptions it exists to stop
        // (PerfPatches.cs:185-190).
        bool guardMatches = true;
        string guardLeak = "";
        foreach (bool guardOn in Booleans)
            foreach (bool instPresent in Booleans)
                foreach (bool ancPresent in Booleans)
                {
                    var act = ProximityVictim.NullGuardAction(guardOn, instPresent, ancPresent);
                    bool wantedSkip = guardOn && !(instPresent && ancPresent);
                    if ((act == ProximityPrefixAction.SkipOriginal) != wantedSkip)
                    {
                        guardMatches = false;
                        if (guardLeak.Length == 0)
                            guardLeak = "guard=" + guardOn + "/inst=" + instPresent + "/anc=" + ancPresent + " -> " + act;
                    }
                }
        Check("P4 Prefix_TheSiblingNullGuardStillSuppressesWhenTheAncestorIsMissing",
            guardMatches, "the refactored guard changed its answer at " + guardLeak);

        // ---- P5: the unconditional bound is CONJUNCTION-scoped. RED under -----
        // "chainlast" (first half) and under "guardopen" (second half).
        //
        // The seam's bound on a foreign fold used to be stated over ANY
        // composition. It does not hold there, and this is the case that says so
        // in numbers rather than in prose. Two halves, both computed from the two
        // SHIPPED decision functions:
        //
        //   a. Under the fold the seam models - the conjunction read from the
        //      shipped 0Harmony.dll - the sibling's refusal SURVIVES this
        //      prefix at every corner. That is the bound that is actually true.
        //   b. The two prefixes DO disagree at some corner: the guard refuses
        //      where this repair runs vanilla. So a fold that is not a
        //      conjunction can reach a different answer there, which is exactly
        //      why the bound cannot be stated composition-independently.
        //
        // Half b is what keeps half a from being decoration: if the two prefixes
        // could never disagree, scoping the claim to a conjunction would be an
        // argument about nothing. "guardopen" removes the disagreement and this
        // case reddens on it; "chainlast" breaks the conjunction and it reddens
        // on that. P1 is the control for both.
        bool refusalSurvivesTheConjunction = true;
        string conjunctionLeak = "none";
        bool prefixesCanDisagree = false;
        string disagreeingCorner = "NONE";
        foreach (bool guardOn in Booleans)
            foreach (bool instPresent in Booleans)
                foreach (bool ancPresent in Booleans)
                {
                    bool sibling = ProximityVictim.PrefixReturn(
                        ProximityVictim.NullGuardAction(guardOn, instPresent, ancPresent));
                    foreach (var gate in GateStates)
                        foreach (bool other in Booleans)
                            foreach (bool ring in Booleans)
                                foreach (bool answered in Booleans)
                                {
                                    bool ours = ProximityVictim.PrefixReturn(
                                        ProximityVictim.VictimAction(gate, other, ring, answered));
                                    bool folded = ProximityVictim.RunOriginalAfter(
                                        ProximityVictim.RunOriginalAfter(true, sibling), ours);
                                    string corner = "guard=" + guardOn + "/inst=" + instPresent
                                        + "/anc=" + ancPresent + " " + gate + "/other=" + other
                                        + "/ring=" + ring + "/answered=" + answered;
                                    if (!sibling && folded)
                                    {
                                        refusalSurvivesTheConjunction = false;
                                        if (conjunctionLeak == "none") conjunctionLeak = corner;
                                    }
                                    if (!sibling && ours)
                                    {
                                        prefixesCanDisagree = true;
                                        if (disagreeingCorner == "NONE") disagreeingCorner = corner;
                                    }
                                }
                }
        Check("P5 Prefix_TheUnconditionalBoundIsScopedToAConjunction",
            refusalSurvivesTheConjunction && prefixesCanDisagree,
            "the guard's refusal was lifted at " + conjunctionLeak
            + "; the corner where the two shipped prefixes disagree = " + disagreeingCorner
            + (prefixesCanDisagree ? "" : " - they never disagree, so scoping the bound to a conjunction argues about nothing"));

        // =================================================================
        // N - THE METHOD CHANGE. These read the shipped sources and assert
        // that round 3's deletions actually happened: no selector, no roster,
        // no mode branch, and the victim taken from the game's own call.
        // They are the acceptance bar for this round and they RED on the
        // round-2 files (run "prior-r2").
        // =================================================================

        string[] bothFiles = new[] { "plugin/ProximityVictimSeam.cs", "plugin/ProximityVictimPatches.cs" };

        // ---- N1: NOT ONE AUTHORED PROXIMITY COMPARISON. RED under "wire-rank" -
        // and on the round-2 files.
        //
        // THE ACCEPTANCE ASSERTION FOR ROUND 3. Ranking candidates against one
        // another is what the game's own selector does, and every attempt to
        // reproduce it here had to be shown equivalent to vanilla IL under NaN,
        // partial data and exceptions - an unbounded obligation, because a prefix
        // that predicts what the original will read is measuring a prediction
        // (#510). The obligation is discharged by not having a comparison at all.
        // The needles are code-shaped so prose about the change cannot satisfy
        // or trip them.
        CheckAbsentFromFiles("N1 Method_NoAuthoredProximityComparisonInTheSeamOrThePatches",
            bothFiles,
            new[] { "Distance(", "sqrMagnitude", "magnitude" },
            "the repair must author no ranking of its own; the game's own selector does the ranking");

        // ---- N2: THE PATCHES BUILD NO ROSTER OF THEIR OWN. RED under ----------
        // "wire-roster" and on the round-2 files.
        //
        // The round-2 marshaller walked PlayerManager.instance.players and read
        // every entry's team, position and liveness - a read set wider than what
        // vanilla reads for the same call, so a later friendly with unreadable
        // data could make the seam decline where vanilla armed. Nothing here
        // reads the roster now; the one call into the game's own targeting reads
        // whatever it reads.
        //
        // The census is a different question and a different list: it walks
        // PhotonNetwork.PlayerList to decide whether the ROOM carries the repair,
        // never to decide who is hit.
        CheckAbsentFromFiles("N2 Method_ThePatchesBuildNoRosterOfTheirOwn",
            new[] { "plugin/ProximityVictimPatches.cs" },
            new[] { ".players" },
            "the repair must not walk the player roster; it asks the game for one player");

        // ---- N3: NO MODE-SPECIFIC SELECTOR. RED on the round-2 files. ---------
        // Round 2 read the game mode and branched, because the free-for-all
        // engine substitutes a different targeting function. It does that by
        // PREFIXING PlayerManager.GetOtherPlayer (FfaMode.cs:3752-3764) - the
        // same method the effect's own body calls and the same one the ring
        // resolves through - so one call inherits the substitution, including the
        // case where that prefix throws and falls back to the team original. A
        // branch here could only disagree with it.
        CheckAbsentFromFiles("N3 Method_NoModeSpecificSelector",
            bothFiles,
            new[] { "ProximitySelection", "NearestEnemyFfa", "EngineActive" },
            "the repair must not choose a selector by mode; one call covers every mode");

        // ---- N4: THE VICTIM COMES FROM THE GAME'S OWN CALL. RED on round-2. ---
        // Exactly one call, inside the one member whose whole job is to make it.
        CheckAnchorInMember("N4 Method_TheVictimComesFromTheGamesOwnSelector",
            "plugin/ProximityVictimPatches.cs",
            "private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)",
            "pm.GetOtherPlayer(holder)");

        // ---- N5: NO PREFIX IN THAT FILE CAN SUPPRESS. RED on round-2. ---------
        // The compiled half of this is V5; this is the half that would notice a
        // prefix reintroducing a refusal at its own call site rather than in the
        // seam.
        CheckAbsentFromFiles("N5 Method_NoPrefixInThePatchesCanSuppressTheOriginal",
            new[] { "plugin/ProximityVictimPatches.cs" },
            new[] { "ProximityPrefixAction.SkipOriginal" },
            "none of the three victim prefixes may suppress the original");

        // ---- N6: THE HOLDER IS DERIVED AS EACH EFFECT DERIVES IT. RED on ------
        // round-2, which had no such member.
        //
        // The argument decides which team the game's selector ranks and from
        // which position, so handing GetOtherPlayer a different asker would be a
        // selection of our own by the back door. Two effects take the ancestor
        // Player (StunPlayer.cs:21, TeleportToOpponent.cs:21) and one takes its
        // cached CharacterData's player (DealDamageToPlayer.cs:35); this asserts
        // that split is what the member contains.
        CheckAnchorInMember("N6a Method_TheHolderIsTheAncestorPlayerForTheTwoSiblings",
            "plugin/ProximityVictimPatches.cs",
            "internal static Player HolderOf(Component instance)",
            "stun.GetComponentInParent<Player>()");
        CheckAnchorInMember("N6b Method_TheHolderIsTheAncestorPlayerForTheTeleport",
            "plugin/ProximityVictimPatches.cs",
            "internal static Player HolderOf(Component instance)",
            "teleport.GetComponentInParent<Player>()");
        CheckAnchorInMember("N6c Method_TheHolderIsTheCachedCharacterDataPlayerForTheDamage",
            "plugin/ProximityVictimPatches.cs",
            "internal static Player HolderOf(Component instance)",
            "damage.data.player");

        // =================================================================
        // W - THE SHIPPED WIRING THIS HARNESS CANNOT COMPILE.
        // Every anchor is asserted EXACTLY ONCE INSIDE THE MEMBER that must
        // carry it (#432). A file-wide count cannot tell a line that is where
        // it belongs from the same line relocated next door.
        // =================================================================

        // W1 - the spectator pre-join merge clears the fighter capability.
        CheckAnchorInMember("W1 Wiring_SpectatorStagingClearsTheCapabilityKeys",
            "plugin/SpectatorSession.cs",
            "internal static bool StagePreJoinProperties(string localSteamId)",
            "foreach (var capabilityKey in ProximityVictim.FighterCapabilityKeys)");

        // W2 - a cr_prox1 delivery moves the census key. Without it a key that
        // lands inside a frame cannot reach the cached census answer.
        CheckAnchorInMember("W2 Wiring_CapabilityDeliveryMovesTheRosterGeneration",
            "plugin/Plugin.cs",
            "public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps)",
            "|| changedProps.ContainsKey(ProximityVictim.CapabilityProp))");

        // W3 - a room change moves it too: every actor is replaced.
        CheckAnchorInMember("W3 Wiring_ARoomChangeMovesTheRosterGeneration",
            "plugin/RoomActors.cs",
            "private static void EnsureCacheRoom()",
            "                _rosterGeneration++;");

        // W4 - and so does an enter/leave callback.
        CheckAnchorInMember("W4 Wiring_ARosterCallbackMovesTheRosterGeneration",
            "plugin/RoomActors.cs",
            "internal static void InvalidateFighterCache()",
            "NoteRosterIdentityChange();");

        // W5 - the census cache is keyed on that counter and not on the frame
        // alone. CONTROL for every wiring mutation in another file.
        CheckAnchorInMember("W5 Wiring_TheCensusCacheIsKeyedOnTheRosterGeneration",
            "plugin/ProximityVictimPatches.cs",
            "internal static ProximityGateState GateState()",
            "RoomActors.RosterGeneration");

        // W6 - the advert is written only where attachment has been proven (#83).
        CheckAnchorInMember("W6 Wiring_TheAdvertIsStagedOnlyWhenPatchesAreLive",
            "plugin/ProximityVictimPatches.cs",
            "internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)",
            "prejoin[ProximityVictim.CapabilityProp] = ProximityVictim.CapabilityValue;");

        // W7a-c - the advert rides the three pre-join sites, each asserted inside
        // the member that carries it. A file-wide count of three cannot tell
        // three correct sites from two correct ones and a stray.
        CheckAnchorInMember("W7a Wiring_TheAdvertRidesTheTeamQueuePreJoin",
            "plugin/ApiClient.cs",
            "private static void ParseTeamQueuePoll(string response)",
            "ProximityVictimGate.StageInto(prejoin);");
        CheckAnchorInMember("W7b Wiring_TheAdvertRidesTheOneVersusTwoPreJoin",
            "plugin/ApiClient.cs",
            "public static void UpdateOvtQueuePoll(bool force)",
            "ProximityVictimGate.StageInto(prejoin);");
        CheckAnchorInMember("W7c Wiring_TheAdvertRidesTheFreeForAllPreJoin",
            "plugin/ApiClient.cs",
            "public static void UpdateFfaQueuePoll(bool force)",
            "ProximityVictimGate.StageInto(prejoin);");

        // W8 - the no-owning-ring reasoning sits on the member that implements
        // it, not on the diagnostic sink it once drifted onto.
        CheckAnchorInMember("W8 Wiring_TheNoRingReasoningSitsOnTheWalkThatSettlesIt",
            "plugin/ProximityVictimPatches.cs",
            "internal static PlayerInRangeTrigger OwningTrigger(Transform start)",
            "This is the ONLY thing the walk is asked.");

        // W9a-c - all three victim prefixes answer Harmony through the one seam
        // function, each asserted inside its own prefix body.
        CheckAnchorInMember("W9a Wiring_TheDamagePrefixReturnsThroughTheSeam",
            "plugin/ProximityVictimPatches.cs",
            "private static bool BeforeGo(DealDamageToPlayer __instance)",
            "return ProximityVictim.PrefixReturn(action);");
        CheckAnchorInMember("W9b Wiring_TheStunPrefixReturnsThroughTheSeam",
            "plugin/ProximityVictimPatches.cs",
            "private static bool BeforeGo(StunPlayer __instance)",
            "return ProximityVictim.PrefixReturn(action);");
        CheckAnchorInMember("W9c Wiring_TheTeleportPrefixReturnsThroughTheSeam",
            "plugin/ProximityVictimPatches.cs",
            "private static bool BeforeGo(TeleportToOpponent __instance)",
            "return ProximityVictim.PrefixReturn(action);");

        // W10 - the provenance build stays green on a checkout without the music
        // tree: the literal manifest Include is existence-conditioned, so the copy
        // step cannot fail a build whose assembly is already written. Scoped to
        // the ItemGroup that carries it rather than to the whole project file.
        CheckAnchorInSpan("W10 Wiring_TheMusicManifestCopyIsExistenceConditioned",
            "plugin/CompetitiveRounds.csproj",
            "<MusicPreviewsToCopy Include=\"music\\*_preview.ogg\" />",
            "</ItemGroup>",
            "<MusicManifestToCopy Include=\"music\\manifest.json\" Condition=\"Exists('music\\manifest.json')\" />");

        // W11 - the SIBLING prefix returns through the same seam function. RED
        // under "wire-perf". Without this the two prefixes on StunPlayer.Go can
        // drift back apart on what an answer means, and P3 would be composing one
        // real decision with one the test invented.
        CheckAnchorInMember("W11 Wiring_TheSiblingNullGuardReturnsThroughTheSeam",
            "plugin/PerfPatches.cs",
            "static bool Prefix(StunPlayer __instance)",
            "return ProximityVictim.PrefixReturn(action);");

        // W12 - the HarmonyX fold claim names its source. A claim about the host's
        // composition that cites nothing is a claim the next reader has to take on
        // trust; the file is the right unit for a citation, so this one is counted
        // file-wide on purpose.
        string seamText = LoadSource("plugin/ProximityVictimSeam.cs");
        Check("W12 Wiring_TheHarmonyFoldClaimNamesItsSource",
            seamText != null
            && CountOf(seamText, "0Harmony.dll") >= 1
            && CountOf(seamText, "2.9.0.0") == 1
            && CountOf(seamText, "WritePrefixes") == 1,
            "the fold claim must name the shipped assembly, its version and the emitter it was read from");

        // W13 - the composition bound names the method it does NOT cover.
        // RED under the "boundclaim" wiring mutant.
        //
        // The seam used to bound a foreign fold with "under ANY composition the
        // worst it could do is fail to run them". That is true of the two methods
        // this repair patches alone and false of StunPlayer.Go, which carries the
        // perf null guard as well: an unconditional true is the identity element
        // of a CONJUNCTION and of nothing else. P5 measures it; this holds the
        // prose to what P5 measured, because the file is what the next reader has.
        Check("W13 Wiring_TheCompositionBoundIsScopedToAConjunction",
            seamText != null
            && CountOf(seamText, "StunPlayer.Go is NOT covered by that bound") == 1
            && CountOf(seamText, "under ANY composition") == 0,
            "the fold bound must be scoped to a conjunction and must name the method that sits outside it");

        // W14 - ONE PREDICATE, AND THE FILE PROVES IT IS ONE. RED under
        // "wire-advertise", which plants a second copy of the conjunction into the
        // gate. The pure half is G6's; this is the half a case cannot execute: the
        // two globals are read in exactly one member, so no caller can hold a
        // private opinion about what this seat will do.
        CheckMemberAnchors("W14 Wiring_TheLocalAnswerIsComputedInExactlyOnePlace",
            "plugin/ProximityVictimPatches.cs",
            "internal static ProximityGateState LocalCapability()",
            new[] { "ProximityVictim.LocalGateState(Plugin.modDisabled, PatchesLive)" },
            new string[0]);
        string patchesText = LoadSource("plugin/ProximityVictimPatches.cs");
        Check("W14b Wiring_TheDisabledFlagIsReadNowhereElseInTheFile",
            patchesText != null && CountOf(patchesText, "Plugin.modDisabled") == 1,
            "the mod-disabled flag must be read exactly once in the file (inside LocalCapability); found "
            + (patchesText == null ? -1 : CountOf(patchesText, "Plugin.modDisabled")));
        // W14c - THE SAME BOUND FOR THE OTHER GLOBAL. RED under "wire-patcheslive".
        // The property was claimed for BOTH globals ("read in exactly one place in
        // the patches half") and guarded file-wide for only one: W14b counted the
        // mod-disabled flag, while PatchesLive was forbidden only inside the three
        // members W15a, W15b and W16a name. A second read anywhere else - an
        // early-out at the top of Census, a diagnostic branch in DecidePrefix - left
        // all 65 clean checks green while re-creating the two-expressions shape the
        // round-3 HIGH was about. Two code lines is the whole budget: the property's
        // own declaration, and the single read inside LocalCapability that W14
        // anchors.
        Check("W14c Wiring_TheAttachmentAnswerIsReadNowhereElseInTheFile",
            patchesText != null && CountOnCodeLines(patchesText, "PatchesLive") == 2,
            "PatchesLive must occur on exactly two code lines - its own declaration and the read "
            + "inside LocalCapability; found "
            + (patchesText == null ? -1 : CountOnCodeLines(patchesText, "PatchesLive")));

        // W15 - the advertiser and the gate BOTH ask it, and neither re-derives
        // it. The advert used to be staged on the attachment count alone while the
        // gate also required the mod to be on, so a disabled seat advertised a
        // repair it would not perform and its peers repaired against it.
        CheckMemberAnchors("W15a Wiring_TheAdvertAsksTheLocalPredicate",
            "plugin/ProximityVictimPatches.cs",
            "internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)",
            new[] { "LocalCapability()", "prejoin[ProximityVictim.CapabilityProp] = ProximityVictim.CapabilityValue;" },
            new[] { "Plugin.modDisabled", "PatchesLive" });
        CheckMemberAnchors("W15b Wiring_TheGateAsksTheSameLocalPredicate",
            "plugin/ProximityVictimPatches.cs",
            "internal static ProximityGateState GateState()",
            new[] { "LocalCapability()" },
            new[] { "Plugin.modDisabled", "PatchesLive" });

        // W16 - the withdrawal can only withdraw. The capable value reaches a peer
        // through the pre-join merge or not at all: a capability that APPEARS
        // mid-room is the racy path pre-join staging exists to avoid (#287), while
        // one that disappears moves the room toward vanilla-unchanged (#276/#430).
        // So this member writes the value 0 and the capable value is forbidden
        // inside it.
        CheckMemberAnchors("W16a Wiring_TheWithdrawalNeverAdvertises",
            "plugin/ProximityVictimPatches.cs",
            "internal static void RepublishCapability()",
            new[] { "ProximityVictim.ShouldRevokeCapability(local, _advertised)", "{ ProximityVictim.CapabilityProp, 0 }" },
            new[] { "ProximityVictim.CapabilityValue", "Plugin.modDisabled", "PatchesLive" });

        // W16b/c - and it is DRIVEN, from the always-on persistent tick and from
        // the compat check that disables the mod. The tick is what makes the
        // guarantee survive a respawned persistent host or a later toggle without
        // anyone having to remember the member (#275); the compat site is the one
        // transition that exists today.
        // The span deliberately ENDS at the modDisabled return: the withdrawal
        // exists for a seat that has been disabled, so a driver placed below that
        // return would inherit the dead zone of the very condition it answers
        // (#272/#98). This case is what holds it above the line.
        CheckAnchorInSpan("W16b Wiring_TheWithdrawalIsDrivenAboveTheDisabledReturn",
            "plugin/Plugin.cs",
            "            TickBroadcastWindowPin();",
            "            if (Plugin.modDisabled) return;",
            "ProximityVictimGate.RepublishCapability();");
        CheckAnchorInMember("W16c Wiring_TheWithdrawalRidesTheCompatDisable",
            "plugin/Plugin.cs",
            "private void DoInitialize()",
            "ProximityVictimGate.RepublishCapability();");

        // W17 - THE COMPAT SITE CLAIMS ONLY WHAT IT CAN DO. RED under
        // "wire-compatclaim". Both files used to present the compat disable as the
        // transition that exercises the withdrawal - "A pre-join stage may already
        // have advertised it" beside the call, "the one transition that exists
        // today" in the member's own doc. Neither is true of a first
        // initialisation: this key is staged PRE-JOIN from the queue poll, which
        // cannot run before ApiClient.Initialize, and the compat-fail branch
        // returns above that call (W18), so _advertised is false there by
        // construction and the member returns on its first line. The two siblings
        // beside it really are the other shape - PoisonSync stages at Awake,
        // GrowNormalize from the tick - which is what made the claim plausible.
        //
        // It matters because it is an ACCEPTANCE claim: a tester told to validate
        // the fix by disabling the mod sees the poison and grow revocations in the
        // same frame and never sees this one, and reads the absence as a defect or,
        // worse, reads the two that did print as covering this one. The signal this
        // feature emits has to be producible by the route the prose names
        // (#438/#443).
        string pluginText = LoadSource("plugin/Plugin.cs");
        Check("W17 Wiring_TheCompatSiteClaimsOnlyWhatItCanDo",
            pluginText != null && patchesText != null
            && CountOf(pluginText, "A pre-join stage may already have advertised") == 0
            && CountOf(pluginText, "This call is a no-op on a first initialisation.") == 1
            && CountOf(patchesText, "the one transition that exists today") == 0
            && CountOf(patchesText, "THE TICK IS THE TRANSITION THAT EXISTS TODAY") == 1,
            "the compat site and the member's doc must both say that site can only withdraw on a "
            + "second initialisation, and must not claim a first-init advert");

        // W18 - and the ORDERING that claim rests on. No mutant of its own: it is
        // the structural half of W17's property and wire-compatclaim is the group's
        // mutant. The span runs from the sibling revocation to the initialisation
        // that is the earliest point from which this key can ever be staged, and
        // the withdrawal has to sit inside it.
        CheckAnchorInSpan("W18 Wiring_TheCompatWithdrawalSitsAboveTheCallThatCanStage",
            "plugin/Plugin.cs",
            "            try { GrowNormalize.RevokeCapability(); } catch { }",
            "            ApiClient.Initialize(Plugin.ApiBaseUrl.Value);",
            "ProximityVictimGate.RepublishCapability();");

        // W19 - a comment may only quote a line this build can emit. RED under
        // "wire-logquote". The TeleportToOpponent doc tells the next maintainer
        // that an attachment shortfall is loud and gives the sentence to grep for;
        // round 4 rewrote StageInto's message and the doc kept quoting the deleted
        // one, so the grep would have returned nothing and the absence would have
        // read as "the attachment count is complete" for a repair that had gone
        // inert on every seat. Two occurrences: the doc's quote and the expression
        // that builds it. A probe has to be bound to the thing it probes (#306).
        Check("W19 Wiring_TheAttachmentShortfallCommentQuotesALineTheFileEmits",
            patchesText != null
            && CountOf(patchesText, " patches live); this seat stays on vanilla for the session") == 2
            && CountOf(patchesText, "patches did NOT attach") == 0,
            "the quoted shortfall sentence must appear twice - in the doc and in the log expression - "
            + "and the deleted wording must be gone");

        // W20 - THE WITHDRAWAL MOVES ITS FLAGS ONLY ON A WRITE THAT WAS ACCEPTED.
        // RED under "wire-blindwrite". Player.SetCustomProperties RETURNS a bool:
        // in room it forwards to the actor-property op, and an op the client cannot
        // send at that instant comes back false having sent nothing, cached nothing
        // and thrown nothing. The member used to read only the throw and clear
        // _advertised and latch _withdrawn regardless, so a refused write was
        // dropped permanently: the per-tick driver returned on its first line for
        // the rest of the session, StageInto refused for the rest of the session,
        // cr_prox1 stayed set on every peer, and the log said "withdrew" for a
        // write that never left the process. Every peer then re-resolved the victim
        // each armed tick while this seat ran vanilla against its stale cached
        // target - the state H1 exists to prevent.
        CheckMemberAnchors("W20 Wiring_TheWithdrawalMovesItsFlagsOnlyOnAnAcceptedWrite",
            "plugin/ProximityVictimPatches.cs",
            "internal static void RepublishCapability()",
            new[] { "bool sent = me.SetCustomProperties(", "if (!sent)", "VanillaFixSupport.DiagLimited(" },
            new[] { "ProximityVictim.CapabilityValue" });

        // W21 - the withdrawal's doc states the direction that actually holds. RED
        // under "wire-monotone". It used to argue that the two globals made the
        // local answer move from Capable to not-Capable and never back; the second
        // premise argues the opposite, and G6 executes the refutation - a count
        // that only INCREMENTS moves PatchesNotAttached to Capable. The paragraph
        // nominated itself as the place reversibility "has to be answered rather
        // than assumed", so the one site a later reader would check stated a false
        // fact about the state space (#351/#432).
        Check("W21 Wiring_TheWithdrawalDocStatesTheDirectionThatActuallyHolds",
            seamText != null
            && CountOf(seamText, "the local answer moves from Capable to not-Capable and") == 0
            && CountOf(seamText, "THE LOCAL ANSWER IS NOT MONOTONIC") == 1,
            "the monotonicity claim must be gone and replaced by the narrower one that holds");

        // W22 - and what the corrected paragraph now rests on instead. No mutant of
        // its own: wire-monotone is the group's, and this is the structural fact
        // the corrected prose cites. A seat whose patches complete AFTER its first
        // staging attempt is Capable, un-advertised, and has nothing for the
        // withdrawal to withdraw; what keeps that room safe is that the census
        // walks the room's own actor list INCLUDING this seat, so this seat's
        // missing key refuses the repair for every seat including itself. A census
        // that special-cased the local actor out would delete that guarantee
        // silently.
        CheckMemberAnchors("W22 Wiring_TheCensusCountsThisSeatToo",
            "plugin/ProximityVictimPatches.cs",
            "private static bool Census()",
            new[] { "PhotonNetwork.PlayerList" },
            new[] { "RoomActors.ActiveFighters", "PhotonNetwork.LocalPlayer" });

        Console.WriteLine("=== passed=" + _passed + " failed=" + _failed + " ===");
        return _failed == 0 ? 0 : 1;
    }
}
