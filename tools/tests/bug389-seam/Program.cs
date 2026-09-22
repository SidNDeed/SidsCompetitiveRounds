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
//   wiring   wire-compatharness: W17 must FAIL; W1 control must PASS
//   wiring   wire-logquote:   W19 must FAIL; W1 control must PASS  (and the
//     W23, W24 and W25 inert twins must all stay green)
//   wiring   wire-blindwrite: W20 must FAIL; W1 control must PASS
//   wiring   wire-monotone:   W21 must FAIL; W1 control must PASS
//   wiring   wire-stagelatch: W23 must FAIL; W1 control must PASS
//   wiring   wire-stagewithdraw: W23 must FAIL; W1 control must PASS (and the
//     W25 inert twin must stay green - that mutant's write is one-way, so the
//     premise W25 pins is untouched and only W23's own assertion moves)
//   wiring   wire-stagewithdrawtight: W23 must FAIL; W1 control must PASS (and
//     the W25 inert twin must stay green). The SAME latch as the row above,
//     spelled "_withdrawn=true;" with no spaces. It is a separate row because
//     the round-5 W23 recognised only the spaced form and stayed green on this
//     one - the property and the spelling are different claims.
//   wiring   wire-latchprose: W24 must FAIL; W1 control must PASS (and the W23
//     inert twin must stay green - it plants prose and no code)
//   wiring   wire-reach   :   W25 must FAIL; W1 control must PASS (and the W23
//     inert twin must stay green). Resets the attachment count when the
//     argument is the literal the StunPlayer cleanup passes, so the reset is on
//     a path this assembly actually walks; spelled "_attached=0;". The round-5
//     form keyed on `which == null`, which no caller can produce, so it changed
//     the text and not the program (#342).
//   wiring   wire-reachdecline: W25 must FAIL; W1 control must PASS (and the
//     W23 inert twin must stay green - the planted write shares a line with the
//     shortfall flag's own write, so none of W23's counts move). Writes the
//     attachment count to RequiredAttachments on the DECLINING branch of
//     StageInto: the write is outside MarkAttached and is not monotone, which
//     is two of W25's clauses at once.
//   wiring   wire-commentwrite: W25 must FAIL; W1 control must PASS (and the
//     W23 inert twin must stay green). The SAME two-way write as wire-reach,
//     spelled "_attached /* n */ = 0;". A separate row because the round-6
//     classifier reached the operator with SkipWs, which skips space, tab, CR
//     and LF and NOT a comment, so this spelling classified as "not a write"
//     and left the count two-way with W25 green.
//   wiring   wire-disabledelsewhere: W25 must FAIL; W1 control must PASS (and
//     the W23 inert twin must stay green). Writes Plugin.modDisabled from
//     PerfPatches, a file the round-6 scan never opened for it: that flag is
//     `internal`, not private, so the privateness that mitigated the narrow
//     surface never covered it.
//   wiring   wire-secondpatchsite: W25 must FAIL; W1 control must PASS (and
//     the W23 inert twin must stay green). Adds a second Harmony instance and
//     a PatchAll beside the one the premise names, in a file that is not
//     Plugin.cs - which is the only file the two patch-site clauses read.
//   wiring   wire-cleanuptag: W25 must FAIL; W1 control must PASS (and the W23
//     inert twin must stay green). Renames the cleanup tag wire-reach keys on.
//     It is the mutant that guards a MUTANT: without it a renamed tag makes
//     wire-reach unreachable again while W25 goes on reddening for the write
//     count, so the RESULT row keeps printing OK (#342/#431).
//   wiring   wire-ffarank : N1b must FAIL; W1 control must PASS (and the N1
//     inert twin must stay green - N1 reads the seam and the patches, which
//     this mutant does not touch). Authors a third distance comparison in
//     FfaMode, whose two are INHERITED by the seam's single vanilla call.
//   wiring   wire-stageabove: W25 must FAIL; W1 control must PASS (and the W23
//     inert twin must stay green). MOVES the FFA queue poll from below the
//     tick's "if (!initialized) return;" to above it - a staging merge that can
//     run before DoInitialize has called ApiClient.Initialize. The round-6 W25
//     counted three StageInto calls and said they were downstream; a count is
//     true of any order, so it stayed green on exactly this (#342/#431).
//   wiring   wire-stagecaller: W25 must FAIL; W1 control must PASS (and the W23
//     inert twin must stay green). Calls the FFA queue poll from
//     PerfPatches.Hit - a Harmony postfix driven by patched game code, so a
//     route into the pre-join merge with no initialisation gate in front of it.
//     The number of merges does not move when a new way of reaching one appears.
//   wiring   wire-deconstructwrite: W25 AND W23 must both FAIL; W1 control must
//     PASS (and the W22 inert twin must stay green). Writes both guard terms by
//     DECONSTRUCTION on the declining branch - "(_attached, _withdrawn) = (0,
//     true);" - the one legal assignment form that puts no operator next to the
//     name, so it was filed as a READ by the case named "every write in ANY
//     spelling". Both cases seeing it is correct: it is two drifts in one line.
//   wiring   wire-blockcommentcall: W25 AND W7c must both FAIL; W1 control must
//     PASS (and the W23 inert twin must stay green). Leaves the FFA pre-join
//     merge alive only inside a /* ... */ comment: dead to the compiler, live
//     to a counter that skips whole-line "//" and to a raw anchor count.
//   wiring   wire-lifecycledrop: W26 must FAIL; W1 control must PASS (and the
//     W25 inert twin must stay green - it makes no claim about that sentence,
//     which is the point of it). Removes the untested-lifecycle-step disclosure
//     from the seam, leaving the two shipped accounts disagreeing again.
//   wiring   wire-severitycensus: H1 must FAIL; W1 control must PASS (and the
//     W25 inert twin must stay green). Changes ONE finding body's SEVERITY
//     marker and leaves the declared census line alone, so the derived census
//     MOVES and the declared one no longer matches.
//   wiring   wire-stagemember: W25 must FAIL; W1 control must PASS (and the W23
//     inert twin must stay green). MOVES the FFA queue poll out of the tab
//     refresher R5 pins to the gated tick and into NativeUI.Open, which menu
//     construction reaches. Same file, same count, same link totals - the
//     round-7 route walk placed calls only in Plugin.cs and stayed green.
//   wiring   wire-stageapimember: W25 must FAIL; W1 control must PASS (and the
//     W23 inert twin must stay green). Calls the FFA queue poll from
//     ApiClient.Initialize itself, inside a file the caller set already
//     permits, so nothing the FILE-grain clause reads moves at all.
//   wiring   wire-stageunbound: W25 must FAIL; W1 control must PASS (and the
//     W23 inert twin must stay green). Lifts the 1v2 merge out of its response
//     callback to just after it - still AFTER the member's baseUrl request, so
//     the ordering clause passes, but running on entry rather than on a reply.
//   wiring   wire-urlwriter: W25 must FAIL; W1 control must PASS (and the W23
//     inert twin must stay green). Gives the request prefix a third writer, in
//     a member the FFA tab reaches on first open, so a reply can come back from
//     a prefix initialisation never set.
//   wiring   wire-qualifiedgateflag: W25 must FAIL; W1 control must PASS (and
//     the W22 inert twin must stay green). Gives the gate flag assembly
//     visibility, has a second file declare one of its own, and writes the HOME
//     flag from it through the qualified spelling. The whole-file exclusion
//     dropped that file - for this one field with no line in any log.
//   wiring   wire-qualifieddeconstruct: W25 AND W23 must both FAIL; W1 control
//     must PASS (and the W22 inert twin must stay green). The QUALIFIED
//     deconstruction - "(ProximityVictimGate._attached,
//     ProximityVictimGate._withdrawn) = (0, true);" - which the bare-name
//     recogniser filed as a read because the character before the name is '.'.
//   wiring   wire-callerextra: W25 must FAIL; W1 control must PASS. Calls the
//     API client's initialiser a second time, from Plugin.Start - a member
//     outside the bound caller set. R8 closed who may WRITE the request prefix
//     and nothing closed who may CALL that writer, so this moved no count and
//     no file and stayed green.
//   wiring   wire-probecaller: W25 must FAIL; W1 control must PASS. Calls the
//     permitted FFA wrapper from the 1v2 tab refresher. That wrapper is a
//     permitted MEMBER of the staging set and is not itself a staging entry
//     point, so nothing placed its own callers.
//   wiring   wire-callerinert: W25 and W1 must BOTH stay green. An edit of
//     comparable size in the same file that touches no call site - the half
//     that stops the two rows above reading as "the file changed".
//   wiring   wire-qualifiedprefix: W25 must FAIL; W1 control must PASS. A
//     QUALIFIED pre-decrement and a qualified `out` use of the attachment count
//     on the declining branch. Both forms read BACKWARDS from the name, and the
//     backward half stopped at the '.' of the qualifier and filed each as a
//     read.
//   wiring   wire-qualifiedprefixinert: W25, W23 and W1 must all stay green.
//   wiring   wire-nullcoalesceassign: W25 must FAIL; W1 control must PASS.
//     Rewrites the TLS fallback to "??=". The prefix is declared with the empty
//     string, which is not null, so that form reads as a writer and retargets
//     nothing - and the classifier did not know the operator at all.
//   wiring   wire-nullcoalesceinert: W25 and W1 must both stay green.
//   wiring   wire-bodynomarker: H1 must FAIL; W25 control must PASS. Adds a
//     finding body with no SEVERITY marker. The census was derived FROM the
//     markers, so the body moved neither number and left the round unrecorded.
//   wiring   wire-bodymarked: H1 and W25 must both stay green. The same body
//     WITH its marker and with the declared census moved to match.
//   wiring   wire-uncachedview: W27 must FAIL; W25 control must PASS. Puts a
//     re-blank of raw text back inside a counter, so a shipped file is blanked
//     in two places while the register names one cached view.
//   wiring   wire-viewinert: W27 and W25 must both stay green.
//   wiring   wire-prosecount: H2 must FAIL; W25 control must PASS. Adds a ninth
//     entry to the permitted-member set, so the two route sentences no longer
//     carry the set's own size.
//   wiring   wire-streakrow: H2 must FAIL; W25 control must PASS. Adds a round
//     to the streak list, so the declared streak is no longer its length.
//   wiring   wire-proseinert: H2 and W25 must both stay green.
//   wiring   wire-closuresmissing: H3 must FAIL; W25 control must PASS. Leaves
//     the promised repository copy unnamed, which is the state that made a
//     reviewer's pin-only read of the round-7 promise resolve to nothing.
//   wiring   wire-closuresinert: H3 and W25 must both stay green.
//   wiring   wire-prosemember: H2 must FAIL; W25 control must PASS. Writes a
//     FOURTH assignment to the permitted-member set, outside the block whose
//     size the route sentences are held to - the state in which the first cut
//     of H2 counted part of the set and passed.
//   wiring   wire-secondmarker: W28 must FAIL; W25 control must PASS. Plants
//     a second literal spelling of the severity marker, which is the state in
//     which H1 holds two counts of one thing to each other.
//   wiring   wire-markerinert: W28 and W25 must both stay green.
//   wiring   wire-aliasusing: W25 must FAIL; W1 control must PASS. Gives the
//     writers' owner a second name in a shipped file, which is the premise
//     the bare-name half of the caller bound rests on.
//   wiring   wire-aliasinert: W25 and W1 must both stay green.
//   wiring   wire-pathswap:   D6 must FAIL;  D4 and D5 controls must PASS
//   wiring   wire-paththrew:  D6 must FAIL;  D4 and D5 controls must PASS
//   prior-r2            : N1 N2 N3 N4 N5 N6 must all FAIL; W1 control must PASS
//     N1b is DELIBERATELY NOT on that list and its absence is not an omission:
//     it pins FfaMode's two comparisons as INHERITED, and FfaMode carries the
//     same two at the round-2 tip, so N1b is green there and green here. It
//     asserts nothing round 3 deleted, which is the whole of what prior-r2
//     measures. Said here because a case sitting outside a list while the list
//     claims to be complete is how V6 went a round unnoticed.
// Every OTHER case here has NO mutant of its own, and this is the whole list
// with the reason each one is on it:
//   G3, G5, C3, D1, D2, D3, S2, S3, K2, P1, P2  - controls and companion
//     assertions over functions another mutant already reaches.
//   G8                                          - companion of the withdrawal
//     group: wire-blindwrite holds the branch that emits its line, and the
//     distinctness it asserts is the same property D4 and S1 already carry a
//     mutant for.
//   W4, W6, W7a, W7b, W9a-c, W12                - wiring anchors whose finding
//     is carried by a sibling wiring mutant. W7c is NO LONGER on this list:
//     wire-blockcommentcall reddens it directly, because the view its anchor is
//     counted in is the thing that case now measures.
//   W14, W15a, W16a, W16b, W16c                 - the same, for the capability
//     advertisement: wire-advertise is this group's mutant and reddens W14b and
//     W15b; these five are the companions it does not move.
//   W18                                         - the structural half of W17's
//     property (the compat withdrawal sits above the earliest point from which
//     this key can be staged); wire-compatclaim is that group's mutant.
//   W22                                         - the structural fact W21's
//     corrected paragraph cites; wire-monotone is that group's mutant.
//   W25b, W25c                                  - the two structural premises
//     W25's paragraph rests on (the patch loop sits inside Awake's Harmony
//     bootstrap; the staging prerequisite sits in the deferred init). wire-reach
//     is this group's mutant and it reddens W25; these two are the companions it
//     does not move.
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

    // ---------------------------------------------------------------------
    // ONE VIEW OF THE SOURCE PER QUESTION, AND EVERY COUNTER SAYS WHICH.
    //
    // The same file used to be read through THREE incompatible views. CountOf
    // saw everything. CountOnCodeLines dropped lines whose first non-space
    // characters were "//" and nothing else. CallsTo and AttributesOf skipped a
    // hit on such a line. The member anchors used raw CountOf. So a call left
    // only inside a /* ... */ block was DEAD to the compiler, LIVE to CallsTo
    // and LIVE to every anchor - the spelling survived while the call did not,
    // and the checks that count it went on printing the same number. A counter
    // that cannot tell a live call from its own spelling is a check that cannot
    // fail for the thing it names (#342/#431), and three views of one source is
    // three different answers to one question (#342: two numbers from the same
    // expression means two different inputs).
    //
    // There are now TWO views, named, and each counter declares the one it
    // reads. ONE PLACE BLANKS A FILE, and W27 is what holds it to one: the
    // register entry claiming a single cached view was written while four
    // counters and three call sites still blanked raw text of their own, and a
    // register entry nobody can check is the next false mechanism a reader
    // builds on (#302/#351/#342).
    //   * CODE  - the comment-blanked, offset-preserving copy, built once per
    //             file and cached. Every counter of CODE reads it.
    //   * PROSE - the raw text. An ABSENCE bound reads it on purpose, because
    //             over-counting an absence REDDENS, which is the safe
    //             direction; and the cases that assert a deleted SENTENCE have
    //             to see comments or they could never find one.
    // BlankComments returns the text unchanged for a file that is not C#: "//"
    // is not a comment in an MSBuild project, and a C# blanker would eat the
    // line W10 reads.
    // ---------------------------------------------------------------------
    private enum SourceView { Code, Prose }

    private static readonly Dictionary<string, string> _blankCache =
        new Dictionary<string, string>(StringComparer.Ordinal);

    /// <summary>The CODE view of a shipped file: comments blanked, offsets and
    /// line numbers preserved. Null when the file cannot be read, exactly as
    /// LoadSource is - an unreadable file is a failure, not a skip.</summary>
    private static string LoadBlanked(string relative)
    {
        string got;
        if (_blankCache.TryGetValue(relative, out got)) return got;
        string text = LoadSource(relative);
        got = (text == null) ? null
            : (relative.EndsWith(".cs", StringComparison.OrdinalIgnoreCase) ? BlankComments(text) : text);
        _blankCache[relative] = got;
        return got;
    }

    /// <summary>The view a case asked for, by name.</summary>
    private static string LoadView(string relative, SourceView view)
    {
        return view == SourceView.Code ? LoadBlanked(relative) : LoadSource(relative);
    }

    /// <summary>CountOf over the CODE view: a needle that survives only inside a
    /// comment is not counted, in any comment form. This used to drop whole-line
    /// "//" lines and nothing else, so a block comment was code to it.
    ///
    /// IT IS HANDED THE CODE VIEW; IT DOES NOT BUILD ONE. The deletion register
    /// named "one cached CODE view read by every code counter" as the
    /// replacement for the three-views defect, and this counter - with CallsTo,
    /// AttributesOf and WritesTo - went on blanking raw text itself, so the
    /// shipped files were blanked in seven places and cached in one. The
    /// semantics agreed, because blanking is deterministic and every caller held
    /// a .cs file; the CLAIM did not, and a register entry nobody can check is
    /// the next false mechanism a reader will build on (#302/#351). The single
    /// place a file is blanked is now LoadBlanked, and W27 is what holds it
    /// there. Callers pass LoadBlanked(rel), or a member body, which came from
    /// it.</summary>
    private static int CountOnCodeLines(string text, string needle)
    {
        if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(needle)) return 0;
        return CountOf(text, needle);
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

    // ----------------------------------------------------------------------
    // A WRITE IS AN OPERATION, NOT A SPELLING.
    //
    // Round 5 held "the attachment count is one-way" with
    // CountOnCodeLines(text, "_attached = ") and "StageInto installs no latch"
    // with CountOnCodeLines(stageBody, "_withdrawn = "). Both count ONE
    // whitespace form of one operator. `_attached=0;`, `_attached  =  0;`,
    // `_attached--`, `_attached -= 1`, `--_attached` and `out _attached` are all
    // writes those counts cannot see, so the cases could be evaded by typing,
    // and the mutant written to prove one of them could only ever prove that
    // the recognised spelling was present. A flag names a line; the defect is a
    // class (#432), and a check that cannot fail for the defect it names is
    // worse than no check (#342/#431).
    //
    // What follows classifies every occurrence of an identifier as a WRITE or a
    // READ by what follows it, with whitespace - including a line break -
    // skipped, so every spelling above reaches the same assertion. Two bounds
    // are stated rather than hidden: an occurrence inside a string literal is
    // counted (over-counting reddens, which is the safe direction), and a
    // right-hand side is read only as far as the statement's own ';' or the end
    // of its line, so an assignment whose value spans lines reports a
    // right-hand side that will not match a required literal - again red.
    // ----------------------------------------------------------------------

    /// <summary>One write to one field, as the source spells it.</summary>
    private sealed class FieldWrite
    {
        internal int Line;          // 1-based, within the text that was scanned
        internal int Index;         // character offset of the identifier
        internal string Kind;       // "= (simple assignment)", "++ (increment)", ...
        internal string Rhs;        // for = and compound forms: the value, trimmed
        internal bool Declaration;  // the write is a field declaration's initialiser
        internal bool Qualified;    // the occurrence carries a qualifier: `Type.field`
        internal string Text;       // the whole source line, whitespace-collapsed
        internal string Rel;        // the file it was found in, when scanned over many
    }

    private static bool IsIdentChar(char c)
    {
        return c == '_' || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
    }

    private static int SkipWs(string text, int i)
    {
        while (i < text.Length && (text[i] == ' ' || text[i] == '\t' || text[i] == '\r' || text[i] == (char)10)) i++;
        return i;
    }

    /// <summary>Index of the last non-whitespace character at or before i, or -1.</summary>
    private static int SkipWsBack(string text, int i)
    {
        while (i >= 0 && (text[i] == ' ' || text[i] == '\t' || text[i] == '\r' || text[i] == (char)10)) i--;
        return i;
    }

    /// <summary>True when this occurrence is written with a QUALIFIER in front of
    /// it - `Plugin.modDisabled`, `ProximityVictimGate._attached` - rather than
    /// bare. Which field a BARE name binds to depends on what the file itself
    /// declares; a qualified one names its owner outright, and that is the
    /// difference a surface scan needs in a file that declares its own field of
    /// the same name.</summary>
    private static bool QualifiedAt(string text, int at)
    {
        int b = SkipWsBack(text, at - 1);
        return b >= 0 && text[b] == '.';
    }

    /// <summary>The last non-whitespace character BEFORE an occurrence and before
    /// any qualifier standing in front of it, or -1.
    ///
    /// WHY THIS EXISTS. The deconstruction recogniser asks what the previous
    /// non-whitespace character is, and it read that off the BARE name - so
    /// `(ProximityVictimGate._attached, _advertised) = (0, true);`, a legal
    /// deconstruction and legal for a private static field from inside its own
    /// class, found '.' there, returned null, and was filed as a READ by the
    /// pass whose case is called "every write in ANY spelling". Every OTHER form
    /// this classifier knows is recognised qualified already, because an
    /// operator FOLLOWS the name and nothing looks at what precedes it; the
    /// deconstruction form is the one that reads backwards, so it was the one
    /// form where the qualifier decided the answer (#342/#431/#432).
    ///
    /// A qualifier is a '.'-separated chain of identifiers, so `A.B._attached`
    /// and `this._attached` both skip back to whatever stands before the chain.
    /// A '.' that is NOT preceded by an identifier - `?.`, or a numeric literal -
    /// stops the walk at the '.' itself, which keeps the answer "not a
    /// deconstruction" rather than guessing past a form this rule has not
    /// read.</summary>
    private static int SkipQualifierBack(string text, int at)
    {
        int b = SkipWsBack(text, at - 1);
        while (b >= 0 && text[b] == '.')
        {
            int q = SkipWsBack(text, b - 1);
            if (q < 0 || !IsIdentChar(text[q])) return b;
            while (q >= 0 && IsIdentChar(text[q])) q--;
            b = SkipWsBack(text, q);
        }
        return b;
    }

    private static int LineStartAt(string text, int index)
    {
        if (index <= 0) return 0;
        return text.LastIndexOf((char)10, index - 1) + 1;
    }

    private static int LineOf(string text, int index)
    {
        int n = 1;
        for (int i = 0; i < index && i < text.Length; i++) if (text[i] == (char)10) n++;
        return n;
    }

    /// <summary>The whole line the offset sits on, trimmed and with runs of
    /// whitespace collapsed to one space, so a failure message shows what was
    /// actually written rather than only a line number.</summary>
    private static string LineTextAt(string text, int index)
    {
        int s = LineStartAt(text, index);
        int e = text.IndexOf((char)10, index);
        if (e < 0) e = text.Length;
        string raw = text.Substring(s, e - s);
        var sb = new System.Text.StringBuilder();
        bool pendingSpace = false;
        foreach (char c in raw)
        {
            if (c == ' ' || c == '\t' || c == '\r') { pendingSpace = true; continue; }
            if (pendingSpace && sb.Length > 0) sb.Append(' ');
            pendingSpace = false;
            sb.Append(c);
        }
        return sb.ToString();
    }

    // OnCommentLine is DELETED, not kept beside its replacement. It was the
    // third view of the source: "the first non-space characters of this line
    // are //". It answered a question about a LINE while the thing being asked
    // about is a REGION, so a call inside /* ... */ passed it as live. The
    // replacement is the single comment-blanked CODE view above, which every
    // counter of code now reads - so there is one answer to "is this spelling
    // live", not three (#342/#431/#432).

    /// <summary>A copy of the text with every COMMENT's content replaced by
    /// spaces. Newlines are kept, so every offset and every line number is
    /// unchanged and a failure message still prints the real line.
    ///
    /// WHY THIS EXISTS. ClassifyWrite decides what an occurrence DOES from the
    /// characters around it, and it reached them with SkipWs, which skips space,
    /// tab, CR and LF. A comment is none of those. So `_attached /* n */ = 0;`
    /// named the field in a recognised spelling, reached the classifier, matched
    /// no operator, and came back as "not a write" - a write missed on
    /// WHITESPACE grounds by the very pass that removed the SPELLING bound. Same
    /// class of defect, one typing further on (#342/#431).
    ///
    /// Blanking, not deleting: a deletion would move every offset after it.
    /// String and character literals are tracked so a "//" or "/*" inside one is
    /// not read as a comment start, and "//" is matched before "/*" so a doc
    /// comment that happens to contain "/*" is consumed as the line comment it
    /// is. Verbatim strings carry their own doubled-quote escape.</summary>
    private static string BlankComments(string text)
    {
        if (string.IsNullOrEmpty(text)) return text;
        var sb = new System.Text.StringBuilder(text);
        char nl = (char)10;
        int i = 0;
        while (i < text.Length)
        {
            char c = text[i];
            char n = (i + 1 < text.Length) ? text[i + 1] : '\0';
            if (c == '/' && n == '/')
            {
                while (i < text.Length && text[i] != nl) { sb[i] = ' '; i++; }
                continue;
            }
            if (c == '/' && n == '*')
            {
                while (i < text.Length && !(text[i] == '*' && i + 1 < text.Length && text[i + 1] == '/'))
                {
                    if (text[i] != nl) sb[i] = ' ';
                    i++;
                }
                if (i < text.Length) { sb[i] = ' '; sb[i + 1] = ' '; i += 2; }
                continue;
            }
            if (c == '@' && n == '"')
            {
                i += 2;
                while (i < text.Length)
                {
                    if (text[i] == '"' && i + 1 < text.Length && text[i + 1] == '"') { i += 2; continue; }
                    if (text[i] == '"') { i++; break; }
                    i++;
                }
                continue;
            }
            if (c == '"' || c == '\'')
            {
                char quote = c;
                i++;
                while (i < text.Length && text[i] != quote)
                {
                    if (text[i] == '\\') i++;
                    i++;
                }
                i++;
                continue;
            }
            i++;
        }
        return sb.ToString();
    }

    /// <summary>Every shipped C# file of the plugin project, ENUMERATED from the
    /// source root rather than listed in this file.
    ///
    /// The round-6 build widened W25's write scan from two files to a list of
    /// seven. That was right about the direction and wrong about the kind: a
    /// list written here is a surface guessed from where the fields happen to
    /// live today, and a hardcoded target is the check that cannot fail
    /// (#342/#431) - the same shape as the spelling bound the same round removed.
    /// The compiler's own rule for this project is "every .cs under plugin/ that
    /// is not build output", so that is the rule here and the scan surface IS
    /// the compilation unit set, by construction rather than by maintenance.
    ///
    /// The count is reported by the cases that use it, so a root that resolves
    /// to a sparse tree is visible in the log rather than a silent narrowing.</summary>
    private static string[] ShippedCsFiles(out string problem)
    {
        problem = null;
        if (string.IsNullOrEmpty(SourceRoot))
        {
            problem = "BUG389_SOURCE_ROOT is unset, so the shipped-source surface cannot be enumerated";
            return new string[0];
        }
        string dir = System.IO.Path.Combine(SourceRoot, "plugin");
        if (!System.IO.Directory.Exists(dir))
        {
            problem = "no plugin directory under source root '" + SourceRoot + "'";
            return new string[0];
        }
        var found = new List<string>();
        foreach (string full in System.IO.Directory.GetFiles(dir, "*.cs", System.IO.SearchOption.AllDirectories))
        {
            string rel = full.Substring(SourceRoot.Length).Replace('\\', '/').TrimStart('/');
            if (rel.Contains("/bin/") || rel.Contains("/obj/")) continue;
            found.Add(rel);
        }
        found.Sort(StringComparer.Ordinal);
        return found.ToArray();
    }

    /// <summary>The value written, read from just after the operator to the
    /// statement's own ';' or the end of its line, whichever comes first.</summary>
    private static string RhsTo(string text, int i)
    {
        int end = text.IndexOf(';', i);
        if (end < 0) end = text.Length;
        int nl = text.IndexOf((char)10, i);
        if (nl >= 0 && nl < end) end = nl;
        if (end < i) return "";
        return text.Substring(i, end - i).Trim();
    }

    /// <summary>What this occurrence DOES to the field, or null when it reads
    /// it. Comparisons are the trap: ==, =>, !=, &lt;= and &gt;= all put an '='
    /// next to the name and none of them writes anything.
    ///
    /// TWO HALVES, AND THEY DO NOT SEE THE SAME SPELLINGS. The FORWARD half
    /// reads the operator that follows the name, so it recognises a qualified
    /// occurrence for free - nothing in front of the name is looked at. The
    /// BACKWARD half - the pre-increment, pre-decrement, `ref` and `out` forms -
    /// used to read the character immediately before the BARE name, so on
    /// `--ProximityVictimGate._attached` it found the '.' of the qualifier,
    /// stopped, and filed the occurrence as a READ. That is the round-7 hole in
    /// the DECONSTRUCTION form all over again, in the three other places that
    /// read backwards, and `SkipQualifierBack` - which already solved it - was
    /// wired only into the deconstruction recogniser. The backward half now
    /// skips the qualifier chain first, so the qualified spelling of a
    /// pre-decrement or of a `ref`/`out` argument classifies in the same terms
    /// as the bare one (#342/#431/#432).
    ///
    /// `??=` IS A WRITE, and it was absent from the forward table. It is
    /// classified as a compound assignment with its right-hand side, exactly as
    /// `+=` and `&lt;&lt;=` are, because a bound that reads "every write in ANY
    /// spelling" must not be a list of the spellings that happened to be in the
    /// file when it was written.
    ///
    /// THE SPELLINGS IT NOW SEES: bare and qualified, for the increment and
    /// decrement forms in both positions, `ref` and `out`, every compound
    /// assignment including `??=`, the simple assignment, and the deconstruction
    /// target. WHAT IT STILL CANNOT SEE, unchanged and disclosed: a write
    /// through a PROPERTY SETTER, through an ALIAS whose name this scan does not
    /// know, through REFLECTION, and behind a null-conditional '.' that
    /// `SkipQualifierBack` refuses to walk past because no identifier precedes
    /// it.</summary>
    private static string ClassifyWrite(string text, int at, int after, out string rhs)
    {
        rhs = null;
        int f = SkipWs(text, after);
        if (f < text.Length)
        {
            char c0 = text[f];
            char c1 = (f + 1 < text.Length) ? text[f + 1] : '\0';
            char c2 = (f + 2 < text.Length) ? text[f + 2] : '\0';
            if (c0 == '+' && c1 == '+') return "++ (increment)";
            if (c0 == '-' && c1 == '-') return "-- (decrement)";
            if (c0 == '<' && c1 == '<' && c2 == '=') { rhs = RhsTo(text, f + 3); return "<<= (compound assignment)"; }
            if (c0 == '>' && c1 == '>' && c2 == '=') { rhs = RhsTo(text, f + 3); return ">>= (compound assignment)"; }
            if (c0 == '?' && c1 == '?' && c2 == '=') { rhs = RhsTo(text, f + 3); return "??= (compound assignment)"; }
            if (c1 == '=' && (c0 == '+' || c0 == '-' || c0 == '*' || c0 == '/' || c0 == '%'
                              || c0 == '&' || c0 == '|' || c0 == '^'))
            {
                rhs = RhsTo(text, f + 2);
                return c0 + "= (compound assignment)";
            }
            if (c0 == '=' && c1 != '=' && c1 != '>')
            {
                rhs = RhsTo(text, f + 1);
                return "= (simple assignment)";
            }
        }
        // THE QUALIFIER CHAIN IS SKIPPED BEFORE THE BACKWARD HALF LOOKS. On
        // `--A._attached` and `out A._attached` the character immediately before
        // the name is the '.' of the qualifier, and reading it there answers a
        // question about the qualifier rather than about the operator.
        int b = SkipQualifierBack(text, at);
        if (b >= 1)
        {
            if (text[b] == '+' && text[b - 1] == '+') return "++ (pre-increment)";
            if (text[b] == '-' && text[b - 1] == '-') return "-- (pre-decrement)";
        }
        if (b >= 0 && IsIdentChar(text[b]))
        {
            int w = b;
            while (w >= 0 && IsIdentChar(text[w])) w--;
            string word = text.Substring(w + 1, b - w);
            if (word == "out" || word == "ref") return word + " (indirect write)";
        }
        string dec = DeconstructionRhs(text, at, after);
        if (dec != null) { rhs = dec; return "deconstruction assignment"; }
        return null;
    }

    /// <summary>The value a DECONSTRUCTION assignment writes to this occurrence's
    /// tuple, or null when the occurrence is not a deconstruction target.
    ///
    /// WHY THIS EXISTS. `ClassifyWrite` decides what an occurrence DOES from the
    /// operator that follows it, and a deconstruction target is followed by ','
    /// or ')' and never by an operator at all: `(_attached, _advertised) = (0,
    /// true);` and `(_withdrawn, _advertised) = (true, false);` both name the
    /// field in full, in a form the project compiles today - the csproj sets
    /// LangVersion `latest` - and both came back as READS. So "every write in ANY
    /// spelling" was a claim about the spellings that happen to put an operator
    /// next to the name (#342/#431/#432).
    ///
    /// THE RULE. An occurrence whose previous non-whitespace character - taken
    /// BEFORE any qualifier chain in front of it - is '(' or
    /// ',' and whose next non-whitespace character is ',' or ')' is a candidate;
    /// it is a target when the enclosing parenthesis group - found by scanning
    /// out through nested closes - is followed by a single '=' that is neither
    /// '==' nor '=>'. The scan stops at the statement's own ';' or at a brace, so
    /// it cannot run away down the file, and an argument list (`Foo(a, x);`), a
    /// comparison (`if (a == x)`) and a lambda parameter list (`(a, x) => ...`)
    /// all fall out at the character after the close.
    ///
    /// The right-hand side is the whole tuple, deliberately: an element-wise
    /// answer would be a second claim about which element this name is, and a
    /// one-way latch's premise ("every write writes true") must REDDEN on a form
    /// nothing here can prove writes true. Over-reporting reddens, which is the
    /// safe direction for a bound.
    ///
    /// THE SPELLINGS IT NOW SEES, said rather than implied: the bare name, and
    /// the name behind a '.'-separated qualifier chain - `ProximityVictimGate.
    /// _attached`, `this._attached`, `A.B._attached`. The qualified form was the
    /// round-7 hole: the previous rule read the character before the BARE name,
    /// found the '.', and filed the occurrence as a read.
    ///
    /// What it still does not see is unchanged and stays disclosed: a write
    /// through a property setter, through an alias the scan does not know the
    /// name of, through reflection, or behind a '.' this rule refuses to walk
    /// past because no identifier precedes it (`?.`).</summary>
    private static string DeconstructionRhs(string text, int at, int after)
    {
        int back = SkipQualifierBack(text, at);
        if (back < 0) return null;
        if (text[back] != '(' && text[back] != ',') return null;
        int f = SkipWs(text, after);
        if (f >= text.Length) return null;
        if (text[f] != ',' && text[f] != ')') return null;

        int depth = 0;
        int limit = Math.Min(text.Length, after + 4000);
        for (int i = f; i < limit; i++)
        {
            char c = text[i];
            if (c == ';' || c == '{' || c == '}') return null;
            if (c == '(') { depth++; continue; }
            if (c != ')') continue;
            if (depth > 0) { depth--; continue; }
            // A close of the group this occurrence sits in.
            int g = SkipWs(text, i + 1);
            if (g >= text.Length) return null;
            if (text[g] == ')' || text[g] == ',') { i = g - 1; continue; }
            if (text[g] != '=') return null;
            char h = (g + 1 < text.Length) ? text[g + 1] : '\0';
            if (h == '=' || h == '>') return null;
            return RhsTo(text, g + 1);
        }
        return null;
    }

    /// <summary>True when this occurrence is a FIELD DECLARATION's initialiser
    /// rather than a later write. A one-way latch's declaration carries its
    /// starting value, so the two have to be told apart rather than counted
    /// together - and telling them apart by whether the name happens to be
    /// written Plugin.modDisabled or bare, which is how the round-5 count did
    /// it, is an accident rather than a rule.</summary>
    private static bool IsDeclarationSite(string text, int at)
    {
        int start = LineStartAt(text, at);
        string prefix = text.Substring(start, at - start).Trim();
        if (prefix.Length == 0) return false;
        string[] words = prefix.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
        if (words.Length == 0) return false;
        bool modifier = false;
        foreach (string w in words)
            if (w == "private" || w == "internal" || w == "public" || w == "protected"
                || w == "static" || w == "readonly" || w == "const" || w == "volatile") modifier = true;
        return modifier && IsTypeShaped(words[words.Length - 1]);
    }

    /// <summary>A token that can be the TYPE in a field declaration: an
    /// identifier, possibly generic, arrayed, qualified or nullable.
    ///
    /// The previous rule listed the primitive names and nothing else, so
    /// `private static readonly List&lt;Attachment&gt; _attached = new
    /// List&lt;Attachment&gt;();` did not read as a declaration at all and came
    /// back as an ordinary write to a field it has nothing to do with. That is
    /// the whole reason one file had to be kept out of the scan BY NAME, and a
    /// named exclusion is a hardcoded target wearing a different coat.</summary>
    private static bool IsTypeShaped(string token)
    {
        if (string.IsNullOrEmpty(token)) return false;
        char c0 = token[0];
        if (!(c0 == '_' || (c0 >= 'a' && c0 <= 'z') || (c0 >= 'A' && c0 <= 'Z'))) return false;
        foreach (char c in token)
            if (!(IsIdentChar(c) || c == '<' || c == '>' || c == '[' || c == ']'
                  || c == ',' || c == '.' || c == '?')) return false;
        // Keywords that can stand last before an identifier without being a type.
        return token != "private" && token != "internal" && token != "public"
            && token != "protected" && token != "static" && token != "readonly"
            && token != "const" && token != "volatile" && token != "return"
            && token != "else" && token != "new" && token != "case";
    }

    /// <summary>True when this text DECLARES a field of that name itself - so a
    /// write to the name here is a write to a DIFFERENT field.
    ///
    /// This is the RULE that replaced a hardcoded exclusion. EmojiSprites.cs
    /// carries its own `_attached`, a List&lt;Attachment&gt;, and the round-6
    /// scan kept it out by NAME - which holds exactly until the next file does
    /// the same and nobody remembers to add it, and which cannot be re-derived
    /// by a reader who does not already know why the name is there. Deciding by
    /// the property means the scan is right about WHICH field it is reading for
    /// any file at all. Pass text that has already been comment-blanked.
    ///
    /// WHAT THE ANSWER IS USED FOR HAS CHANGED, and the old use is the reason.
    /// A true answer used to DROP the file from the surface; it now NARROWS the
    /// file to its QUALIFIED occurrences, because a bare name there binds to the
    /// local field while `Home.field` names the home one and is legal wherever
    /// the home field is visible. Dropping missed exactly that write - and for
    /// plugin/CustomCosmetics.cs, which declares its own `initialized`, the drop
    /// was reported in no line of any run log at all, so the gate flag's
    /// "exactly one write across the shipped files" was counted over a surface
    /// a reader could not reconstruct (#302/#342). ScanField prints every
    /// narrowing it makes, for every field, on every run.</summary>
    private static bool DeclaresFieldIn(string blanked, string field)
    {
        if (string.IsNullOrEmpty(blanked) || string.IsNullOrEmpty(field)) return false;
        int i = 0;
        while (true)
        {
            int at = blanked.IndexOf(field, i, StringComparison.Ordinal);
            if (at < 0) return false;
            i = at + field.Length;
            if (at > 0 && IsIdentChar(blanked[at - 1])) continue;
            int after = at + field.Length;
            if (after < blanked.Length && IsIdentChar(blanked[after])) continue;
            // A declaration either ends there or runs on into an initialiser.
            int f = SkipWs(blanked, after);
            if (f >= blanked.Length) continue;
            if (blanked[f] != ';' && blanked[f] != '=') continue;
            if (blanked[f] == '=' && f + 1 < blanked.Length
                && (blanked[f + 1] == '=' || blanked[f + 1] == '>')) continue;
            if (IsDeclarationSite(blanked, at)) return true;
        }
    }

    /// <summary>Every WRITE to one field in one text ALREADY in the CODE view,
    /// in any spelling. Its two callers hand it a member body, which MemberBody
    /// took from the cached view, so there is nothing left to blank.</summary>
    private static List<FieldWrite> WritesTo(string code, string field)
    {
        return WritesToBlanked(code, code, field);
    }

    /// <summary>The same, over a text whose comments have ALREADY been blanked -
    /// so a caller scanning ninety-one files for three fields blanks each once
    /// instead of three times. Classification reads the blanked copy; the line
    /// TEXT a failure message prints is read from the original, because blanking
    /// preserves every offset and a message quoting a row of spaces would be
    /// worse than no message.</summary>
    private static List<FieldWrite> WritesToBlanked(string original, string blanked, string field)
    {
        var found = new List<FieldWrite>();
        if (string.IsNullOrEmpty(blanked) || string.IsNullOrEmpty(field)) return found;
        int i = 0;
        while (true)
        {
            int at = blanked.IndexOf(field, i, StringComparison.Ordinal);
            if (at < 0) return found;
            i = at + field.Length;
            if (at > 0 && IsIdentChar(blanked[at - 1])) continue;
            int after = at + field.Length;
            if (after < blanked.Length && IsIdentChar(blanked[after])) continue;
            string rhs;
            string kind = ClassifyWrite(blanked, at, after, out rhs);
            if (kind == null) continue;
            var w = new FieldWrite();
            w.Index = at;
            w.Qualified = QualifiedAt(blanked, at);
            w.Line = LineOf(blanked, at);
            w.Kind = kind;
            w.Rhs = rhs;
            w.Declaration = IsDeclarationSite(blanked, at);
            w.Text = LineTextAt(original, at);
            found.Add(w);
        }
    }

    /// <summary>What one field's writes look like across a whole surface of
    /// files: the real writes with the file each was found in, the files whose
    /// reading was NARROWED because they declare a field of that name
    /// themselves, how many files were actually read, and whether the home file
    /// declares it at all.</summary>
    private sealed class SurfaceScan
    {
        internal string Field;
        internal List<FieldWrite> Real = new List<FieldWrite>();
        internal List<string> Narrowed = new List<string>();
        internal List<string> DeclProblems = new List<string>();
        internal int Scanned;
        internal bool HomeDeclares;
    }

    /// <summary>One line a reader can reconstruct the SURFACE from: how many
    /// files this field's scan actually read and which of them were narrowed.
    /// Printed for EVERY field scanned, clean run or not. The round-6 build
    /// printed it for two of its three scans and the round-7 build added a
    /// fourth without a line at all, so the one field the round's gate-flag
    /// argument newly rested on had a surface nobody could see (#302/#351).</summary>
    private static string ScanNote(string what, SurfaceScan scan)
    {
        return what + " '" + scan.Field + "' read " + scan.Scanned + " file(s), "
            + (scan.Narrowed.Count == 0
                ? "none narrowed"
                : scan.Narrowed.Count + " narrowed to qualified writes (declares its own field of that name): "
                  + string.Join(", ", scan.Narrowed.ToArray()));
    }

    /// <summary>Every write to one field across a surface of files.
    ///
    /// A FILE THAT DECLARES ITS OWN FIELD OF THE NAME IS NARROWED, NOT DROPPED.
    /// The round-6 rule removed such a file from the surface entirely, which is
    /// correct about the BARE occurrences in it - those bind to the local field -
    /// and wrong about the qualified ones, which name the home field outright
    /// and are legal wherever the home field is visible. So the count that says
    /// "exactly one write across the shipped files" was taken over a surface
    /// smaller than the one its own message named, and for one of the four
    /// fields the drop was not reported anywhere (#302/#342). Narrowing keeps
    /// every file in the scan and reads only what is unambiguous in it, and the
    /// narrowing itself is printed.</summary>
    private static SurfaceScan ScanField(string[] surface,
                                         Dictionary<string, string> texts,
                                         Dictionary<string, string> blanks,
                                         string field, string home, string wantDeclInit)
    {
        var scan = new SurfaceScan();
        scan.Field = field;
        foreach (string rel in surface)
        {
            string text;
            if (!texts.TryGetValue(rel, out text)) continue;
            string blanked = blanks[rel];
            scan.Scanned++;
            bool declares = DeclaresFieldIn(blanked, field);
            bool narrowed = false;
            if (rel == home) scan.HomeDeclares = declares;
            else if (declares) { scan.Narrowed.Add(rel); narrowed = true; }
            foreach (FieldWrite w in WritesToBlanked(text, blanked, field))
            {
                if (narrowed && !w.Qualified) continue;
                w.Rel = rel;
                if (w.Declaration)
                {
                    if (wantDeclInit != null && w.Rhs != wantDeclInit)
                        scan.DeclProblems.Add("the declaration initialiser for " + field + " must be '"
                            + wantDeclInit + "'; found '" + w.Rhs + "' in " + rel + " line " + w.Line);
                    continue;
                }
                scan.Real.Add(w);
            }
        }
        return scan;
    }

    private static List<FieldWrite> RealIn(SurfaceScan scan, string rel)
    {
        var got = new List<FieldWrite>();
        foreach (FieldWrite w in scan.Real) if (w.Rel == rel) got.Add(w);
        return got;
    }

    private static List<string> RealOutside(SurfaceScan scan, string rel)
    {
        var got = new List<string>();
        foreach (FieldWrite w in scan.Real)
            if (w.Rel != rel) got.Add(w.Rel + " line " + w.Line + " " + w.Kind + " [" + w.Text + "]");
        return got;
    }

    /// <summary>A write that can only ever make the value larger.</summary>
    private static bool IsMonotoneWrite(FieldWrite w)
    {
        if (w.Kind == "++ (increment)" || w.Kind == "++ (pre-increment)") return true;
        if (w.Kind != "+= (compound assignment)") return false;
        if (string.IsNullOrEmpty(w.Rhs)) return false;
        foreach (char c in w.Rhs) if (c < '0' || c > '9') return false;
        return true;
    }

    private static string Describe(List<FieldWrite> writes)
    {
        if (writes.Count == 0) return "(none)";
        var parts = new List<string>();
        foreach (FieldWrite w in writes) parts.Add("line " + w.Line + " " + w.Kind + " [" + w.Text + "]");
        return string.Join(" | ", parts.ToArray());
    }

    /// <summary>Calls to one (optionally qualified) name, whitespace-tolerant:
    /// "Foo.Bar (x)" is the same call as "Foo.Bar(x)" and a count that reads one
    /// and not the other is the same class of defect as a spelling-bound
    /// assignment count. It is handed the CODE view, like every other counter of
    /// code here; CallsTo, which blanked raw text of its own, is DELETED and its
    /// two callers pass LoadBlanked's answer to this one instead.
    ///
    /// It is the COUNT of CallSitesIn and never a second rule - two counters of
    /// one thing is two answers waiting to disagree (#342).</summary>
    private static int CallsToIn(string blanked, string name)
    {
        return CallSitesIn(blanked, name).Count;
    }

    /// <summary>Every call site of one name in the CODE view, as offsets - for a
    /// case that has to ask WHERE a call is and not only how many there are.
    ///
    /// A DECLARATION IS NOT A CALL. `private static void MaybeRefreshFfaTab()`
    /// puts the name in front of a '(' exactly as a call does, so a route check
    /// that counted it would read "two call sites" for a member called once and
    /// declared once. The declaration is told apart by the same positional rule
    /// IsDeclarationSite applies to a field: a modifier on the line and a
    /// type-shaped token immediately before the name. `return Foo();` has
    /// neither and stays a call.</summary>
    private static List<int> CallSitesIn(string blanked, string name)
    {
        var found = new List<int>();
        if (string.IsNullOrEmpty(blanked) || string.IsNullOrEmpty(name)) return found;
        int i = 0;
        while (true)
        {
            int at = blanked.IndexOf(name, i, StringComparison.Ordinal);
            if (at < 0) return found;
            i = at + name.Length;
            if (at > 0 && IsIdentChar(blanked[at - 1])) continue;
            int f = SkipWs(blanked, at + name.Length);
            if (f < blanked.Length && blanked[f] == '(' && !IsDeclarationSite(blanked, at)) found.Add(at);
        }
    }

    /// <summary>The call sites of a BARE name: the same, minus every occurrence
    /// that stands behind a '.'.
    ///
    /// CallSitesIn accepts a '.' in front of the name, because a '.' is not an
    /// identifier character - which is right for a name searched WITH its
    /// qualifier ("ApiClient.Initialize") and wrong for one searched bare.
    /// `Initialize` is declared by nine shipped types, and six of their calls
    /// sit in the SAME member as the one call this round binds, so a bare search
    /// that counted `GameStateWatcher.Initialize()` would resolve every one of
    /// them into the bound set and the clause could never fail (#342/#431). A
    /// bare search is therefore confined to the file that DECLARES the target,
    /// and rejects a qualified occurrence there too.</summary>
    private static List<int> BareCallSitesIn(string blanked, string name)
    {
        var kept = new List<int>();
        foreach (int at in CallSitesIn(blanked, name))
        {
            int b = SkipWsBack(blanked, at - 1);
            if (b >= 0 && blanked[b] == '.') continue;
            kept.Add(at);
        }
        return kept;
    }

    /// <summary>Attribute applications [Name] or [Name(...)], likewise
    /// whitespace-tolerant, over a text already in the CODE view.</summary>
    private static int AttributesOf(string blanked, string name)
    {
        if (string.IsNullOrEmpty(blanked) || string.IsNullOrEmpty(name)) return 0;
        int n = 0, i = 0;
        while (true)
        {
            int at = blanked.IndexOf(name, i, StringComparison.Ordinal);
            if (at < 0) return n;
            i = at + name.Length;
            if (at > 0 && IsIdentChar(blanked[at - 1])) continue;
            int after = at + name.Length;
            if (after < blanked.Length && IsIdentChar(blanked[after])) continue;
            int b = SkipWsBack(blanked, at - 1);
            if (b < 0 || blanked[b] != '[') continue;
            int f = SkipWs(blanked, after);
            if (f < blanked.Length && (blanked[f] == ']' || blanked[f] == '(')) n++;
        }
    }

    /// <summary>The offsets of one member's body, for a case that has to ask
    /// WHERE a site is rather than only how many there are. Pass the CODE view:
    /// a signature quoted in a comment is not a second declaration of it, and
    /// blanking preserves every offset so the answer indexes the real file
    /// either way.</summary>
    private static bool TryMemberSpan(string text, string signature, out int open, out int close, out string problem)
    {
        open = -1; close = -1; problem = null;
        int sigs = CountOf(text, signature);
        if (sigs != 1) { problem = "member signature found " + sigs + " time(s) (want 1): " + signature; return false; }
        int sig = text.IndexOf(signature, StringComparison.Ordinal);
        open = text.IndexOf('{', sig);
        close = open < 0 ? -1 : MemberEnd(text, sig, open);
        if (open < 0 || close < 0) { problem = "could not bound the member span: " + signature; return false; }
        return true;
    }

    /// <summary>The member span that CONTAINS a given offset, for a signature
    /// the file repeats - plugin/Plugin.cs declares three `private void Update()`
    /// across three MonoBehaviours, so "the persistent tick" cannot be named by
    /// its signature alone. The caller supplies an offset it has already proved
    /// unique (the tick's own gate line), and the span is taken from the nearest
    /// declaration above it; the offset is then re-checked to be inside the span
    /// it produced, so a signature that does not actually enclose it FAILS
    /// rather than bounding the wrong member.</summary>
    private static bool TryMemberSpanAround(string text, string signature, int inside,
                                            out int open, out int close, out string problem)
    {
        open = -1; close = -1; problem = null;
        if (string.IsNullOrEmpty(text) || inside < 0 || inside >= text.Length)
        { problem = "no text to bound '" + signature + "' in"; return false; }
        int sig = text.LastIndexOf(signature, inside, StringComparison.Ordinal);
        if (sig < 0) { problem = "no declaration '" + signature + "' above offset " + inside; return false; }
        open = text.IndexOf('{', sig);
        close = open < 0 ? -1 : MemberEnd(text, sig, open);
        if (open < 0 || close < 0) { problem = "could not bound the member span: " + signature; return false; }
        if (inside < open || inside > close)
        {
            problem = "the member bounded by '" + signature + "' does not contain offset " + inside;
            return false;
        }
        return true;
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

    /// <summary>The MEMBER that encloses an offset, named by its declaration
    /// line, or null when no member above it bounds it.
    ///
    /// WHY THIS EXISTS. W25's route clauses pinned WHERE a staging call sits in
    /// plugin/Plugin.cs and nowhere else: the per-file loop skipped every file
    /// that was not Plugin.cs, so seven of the ten entry-point call sites the
    /// run's own map printed were counted and never placed. "Only these files
    /// may call it" does not say WHICH MEMBER of those files, and a member is
    /// what a route is made of (#342/#431).
    ///
    /// The rule is the one MemberEnd already uses: a declaration is a line at a
    /// member's own indentation that opens with an access modifier and carries a
    /// parameter list, and its body runs to a brace alone on a line at that same
    /// indentation. The nearest such declaration above the offset whose span
    /// CONTAINS the offset is the answer, so a member inside a nested class -
    /// ApiClient.HostLobbyClient holds one of the five - is found at its own
    /// indentation rather than attributed to the class around it. A line whose
    /// text before the '(' carries a brace, an '=' or the word `class` is a
    /// property, an expression-bodied member or a type and is not one of these.
    /// Pass the CODE view: a signature quoted in a comment declares nothing.</summary>
    private static string EnclosingMemberOf(string blanked, int at)
    {
        if (string.IsNullOrEmpty(blanked) || at < 0 || at >= blanked.Length) return null;
        char nl = (char)10;
        int ls = LineStartAt(blanked, at);
        while (ls > 0)
        {
            ls = LineStartAt(blanked, ls - 1);
            int ind = 0;
            while (ls + ind < blanked.Length && blanked[ls + ind] == ' ') ind++;
            if (ind >= 8 && ind <= 16 && ind % 4 == 0)
            {
                int eol = blanked.IndexOf(nl, ls);
                if (eol < 0) eol = blanked.Length;
                string line = blanked.Substring(ls + ind, eol - ls - ind).TrimEnd();
                if (StartsWithModifier(line) && line.IndexOf('(') > 0 && !line.EndsWith(";", StringComparison.Ordinal))
                {
                    string head = line.Substring(0, line.IndexOf('('));
                    bool typeOrProperty = head.IndexOf('{') >= 0 || head.IndexOf('=') >= 0
                        || (" " + head + " ").IndexOf(" class ", StringComparison.Ordinal) >= 0;
                    if (!typeOrProperty)
                    {
                        int open = blanked.IndexOf('{', ls);
                        int close = open < 0 ? -1 : MemberEnd(blanked, ls, open);
                        if (open >= 0 && close >= open && at >= open && at <= close) return line.Trim();
                    }
                }
            }
            if (ls == 0) break;
        }
        return null;
    }

    private static bool StartsWithModifier(string line)
    {
        return line.StartsWith("public ", StringComparison.Ordinal)
            || line.StartsWith("private ", StringComparison.Ordinal)
            || line.StartsWith("internal ", StringComparison.Ordinal)
            || line.StartsWith("protected ", StringComparison.Ordinal);
    }

    /// <summary>The body span of the first LAMBDA opened at or after an offset:
    /// its '{' and the matching brace alone on a line at the lambda's own
    /// indentation, or null.
    ///
    /// This is how a merge is tied to a RESPONSE rather than to a position. The
    /// round-7 clause asked only that the merge sit at a larger offset than the
    /// member's baseUrl request, which is also true of a statement written after
    /// the whole StartCoroutine call - it would then run on ENTRY, on whatever
    /// tick reached the member, with no response involved at all. Inside the
    /// callback it runs only when a request this client built has come back.
    /// Braces are not counted: ApiClient.cs is full of JSON in string literals
    /// and a count never returns to zero there, which is the same reason
    /// MemberEnd bounds by indentation.</summary>
    private static bool TryLambdaSpanAfter(string blanked, int from, out int open, out int close)
    {
        open = -1; close = -1;
        if (string.IsNullOrEmpty(blanked) || from < 0 || from >= blanked.Length) return false;
        int arrow = blanked.IndexOf("=>", from, StringComparison.Ordinal);
        if (arrow < 0) return false;
        char nl = (char)10;
        int ls = LineStartAt(blanked, arrow);
        int indent = 0;
        while (ls + indent < blanked.Length && blanked[ls + indent] == ' ') indent++;
        open = blanked.IndexOf('{', arrow);
        if (open < 0) return false;
        string closer = nl + new string(' ', indent) + "}";
        int at = blanked.IndexOf(closer, open, StringComparison.Ordinal);
        if (at < 0) { open = -1; return false; }
        close = at + closer.Length - 1;
        return true;
    }

    /// <summary>The text of ONE member's body, or null when the file cannot be
    /// read or the signature is not unique.
    ///
    /// The same bound CheckAnchorInMember applies, exposed for the cases that
    /// have to say more about a member than "this anchor occurs once" - the
    /// exit-path table in D6 asks which outcome each guarded exit assigns and in
    /// what ORDER two statements occur, and neither is a count. The span starts
    /// at the opening brace, so the member's own signature is NOT part of it:
    /// `out ProximityVanillaAnswer answer` in a declaration must not be mistaken
    /// for an assignment inside the body.</summary>
    private static string MemberBody(string relative, string signature, out string problem)
    {
        problem = null;
        // THE CODE VIEW. The body a case reasons about is code: a commented-out
        // assignment is not an assignment, and a signature named in prose is not
        // a second member. Offsets and line numbers are preserved by blanking,
        // so a failure message still quotes the real line number.
        string text = LoadBlanked(relative);
        if (text == null)
        {
            problem = "cannot read " + relative + " under BUG389_SOURCE_ROOT='"
                + (SourceRoot ?? "<unset>") + "' - an unset or wrong root is a failure, not a skip";
            return null;
        }
        int sigs = CountOf(text, signature);
        if (sigs != 1)
        {
            problem = "member signature found " + sigs + " time(s) (want 1) in " + relative + ": " + signature;
            return null;
        }
        int sig = text.IndexOf(signature, StringComparison.Ordinal);
        int open = text.IndexOf('{', sig);
        int close = open < 0 ? -1 : MemberEnd(text, sig, open);
        if (open < 0 || close < 0)
        {
            problem = "could not bound the member span in " + relative + ": " + signature;
            return null;
        }
        return text.Substring(open, close - open + 1);
    }

    /// <summary>Assert an anchor occurs EXACTLY ONCE inside the member that must
    /// carry it - never file-wide (#432). A file-wide count cannot tell a line
    /// that is where it belongs from the same line relocated into another member,
    /// which is how wiring drifts off the branch it documents while the case that
    /// names it stays green.</summary>
    private static void CheckAnchorInMember(string name, string relative, string signature, string anchor)
    {
        CheckAnchorInMember(name, relative, signature, anchor, SourceView.Code);
    }

    /// <summary>The same, with the view named. Every anchor here is code except
    /// W8's, which IS a comment - the reasoning that has to sit on the member
    /// that implements it - so that one case declares PROSE at its call site
    /// rather than being handed a blanked copy it could never match.</summary>
    private static void CheckAnchorInMember(string name, string relative, string signature, string anchor, SourceView view)
    {
        string text = LoadView(relative, view);
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
        // THE CODE VIEW, both halves. A required anchor that survives only in a
        // comment is not the wiring the case certifies, and a forbidden one
        // named in a comment is not a second copy of the conjunction.
        string text = LoadBlanked(relative);
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
        // THE CODE VIEW - which for plugin/CompetitiveRounds.csproj is the raw
        // text, because "//" is not a comment in an MSBuild project and a C#
        // blanker would eat the line this case reads. LoadBlanked states that
        // rule in one place rather than leaving each caller to remember it.
        string text = LoadBlanked(relative);
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

    /// <summary>The severity census a set of finding bodies produces, counted
    /// from their own `SEVERITY:` markers and never typed.
    ///
    /// IT COUNTS MARKERS, AND THAT IS ALL IT CAN COUNT. The round-7 comment here
    /// said "a body added without a marker changes the total and is visible".
    /// It does not: the total is derived FROM the markers, so a body with no
    /// marker moves neither the derived census nor the declared one, H1 stays
    /// green, and the body disappears from the round. The guarantee was a claim
    /// about the whole state space written from the one state the author had in
    /// mind (#351/#434). What closes it is not a better sentence here but a
    /// SECOND, INDEPENDENT count - FindingBodies, which counts the bodies by
    /// their own heading and knows nothing about markers - and H1 requiring the
    /// two to agree.</summary>
    /// <summary>How a finding body declares its severity. ONE PLACE KNOWS
    /// THIS SPELLING, and W28 holds it to one: the census and the body
    /// counter both read it from here, so the two cannot come to disagree
    /// about what a marker is while still being held to each other. A second
    /// copy of the rule is two counters of one thing (#342).</summary>
    private const string SeverityMarker = "SEVERITY:";

    private static string DerivedCensus(string findings, out int markers)
    {
        int high = 0, medium = 0, low = 0, other = 0, total = 0;
        if (findings != null)
            foreach (string line in findings.Split((char)10))
            {
                string t = line.Trim();
                // The marker must OPEN its line. Prose that NAMES the marker -
                // including the paragraph in that file explaining what this
                // counts - would otherwise be counted as a body, which is a
                // reading that finds its own needle (#342).
                if (!t.StartsWith(SeverityMarker, StringComparison.Ordinal)) continue;
                total++;
                string v = t.Substring(SeverityMarker.Length).Trim();
                if (v == "HIGH") high++;
                else if (v == "MEDIUM") medium++;
                else if (v == "LOW") low++;
                else other++;
            }
        markers = total;
        return total + " findings: " + high + " HIGH, " + medium + " MEDIUM, " + low + " LOW"
            + (other == 0 ? "" : ", " + other + " UNRECOGNISED");
    }

    /// <summary>The finding BODIES in a findings file, counted by their own
    /// heading and knowing nothing about the SEVERITY markers, together with the
    /// heading of every body that carries none.
    ///
    /// A body opens with a line whose trimmed text starts with "### " and runs
    /// to the next such line or to the end of the file; it is MARKED when a line
    /// inside it opens with "SEVERITY:". Counting the bodies a SECOND way, off
    /// different evidence, is the whole point - a marker count and a body count
    /// can only be held to each other when neither is derived from the other
    /// (#342/#431). A marker standing outside every body makes markers exceed
    /// bodies and reddens in the same clause.</summary>
    private static int FindingBodies(string findings, out List<string> unmarked)
    {
        unmarked = new List<string>();
        if (findings == null) return 0;
        int bodies = 0;
        string heading = null;
        bool marked = false;
        foreach (string line in findings.Split((char)10))
        {
            string t = line.Trim();
            if (t.StartsWith("### ", StringComparison.Ordinal))
            {
                if (heading != null && !marked) unmarked.Add(heading);
                heading = t;
                marked = false;
                bodies++;
                continue;
            }
            if (heading != null && t.StartsWith(SeverityMarker, StringComparison.Ordinal)) marked = true;
        }
        if (heading != null && !marked) unmarked.Add(heading);
        return bodies;
    }

    /// <summary>The number of lines in a text whose trimmed form OPENS with a
    /// marker. The marker has to open the line for the same reason the census
    /// requires it: prose naming the marker would otherwise be counted as one
    /// more of the thing it describes, a reading that finds its own needle
    /// (#342).</summary>
    private static int LinesOpeningWith(string text, string marker)
    {
        if (text == null) return 0;
        int n = 0;
        foreach (string line in text.Split((char)10))
            if (line.Trim().StartsWith(marker, StringComparison.Ordinal)) n++;
        return n;
    }

    /// <summary>The name a member signature declares: the identifier that stands
    /// immediately before its parameter list.</summary>
    private static string MemberName(string signature)
    {
        int paren = signature.IndexOf('(');
        if (paren <= 0) return signature;
        int end = paren - 1;
        while (end >= 0 && !IsIdentChar(signature[end])) end--;
        int start = end;
        while (start >= 0 && IsIdentChar(signature[start])) start--;
        return signature.Substring(start + 1, end - start);
    }

    /// <summary>Assert a needle is ABSENT from a file. Used only where the file
    /// itself is the unit - "no selector of our own lives anywhere in here" is a
    /// statement about the file, not about one member, and scoping it to a member
    /// would let the thing move next door and stay green.
    ///
    /// THE PROSE VIEW, DELIBERATELY. This is the one place raw text is the right
    /// reading: for an ABSENCE bound, counting a needle that survives only in a
    /// comment REDDENS, and a bound that errs toward reddening is the safe
    /// direction. Blanking here would let a ranking be commented out and still
    /// satisfy "no ranking is authored in this file".</summary>
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
        // RED under "ownplayer", which drops the polarity term at VictimAction's
        // OWN call site into ShouldRepair - G1, G5 and D3 ask ShouldRepair
        // directly and stay green, so this is the case that sees it. It states
        // that all four terms are required, so none can be dropped without a case
        // noticing.
        //
        // This paragraph used to call V6 a companion to V5 with no mutant of its
        // own. That was true for exactly one round and was left standing when the
        // mutant was added, so the run list at the top of this file and the
        // explanation beside the case contradicted each other: a reader asking
        // whether V6 was load-bearing got opposite answers from two places in one
        // file, and the coverage accounting could not be read at all (#342).
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

        // ---- D6: the outcome an exit assigns is the outcome that exit IS. -----
        // RED under "pathswap" and "paththrew". THE SURFACE D4 AND D5 CANNOT
        // REACH, AND THE REASON THIS CASE EXISTS.
        //
        // D4 says the six sentences differ from each other; D5 says each sentence
        // is attached to its own outcome. Both are statements about the seam, and
        // both are blind to the half that decides which outcome a PATH gets -
        // VanillaVictimFor in the patches file, five exits, one assignment each.
        // Swap two of those assignments and every sentence is still distinct and
        // still bound to its own enum value, so D4, D5 and BOTH of their mutation
        // runs stay green while a missing PlayerManager reports itself as an
        // effect with no holder of its own: the exact false statement the whole
        // reason-plumbing was built to end. A mutant that cannot reach the code
        // its case claims to close is a check that cannot fail (#342/#431).
        //
        // The expectation is a table keyed on the PATH - the guard is the
        // identity of the exit - derived by reading that member and written out
        // here. It never asks the seam what a path ought to produce, so path to
        // outcome and outcome to sentence are measured against two independent
        // statements and neither half can certify the other.
        string exitProblem;
        string victimForBody = MemberBody("plugin/ProximityVictimPatches.cs",
            "private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)",
            out exitProblem);
        var expectedExits = new[]
        {
            new[] { "pm == null - the game's player manager was not available",
                    "if (pm == null) { answer = ProximityVanillaAnswer.NoManager; return null; }",
                    "NoManager" },
            new[] { "holder == null - this effect has no player of its own",
                    "if (holder == null) { answer = ProximityVanillaAnswer.NoHolder; return null; }",
                    "NoHolder" },
            new[] { "victim == null - the game's own call answered with nobody",
                    "if (victim == null) { answer = ProximityVanillaAnswer.Nobody; return null; }",
                    "Nobody" },
            new[] { "the fall-through - a usable player came back",
                    "answer = ProximityVanillaAnswer.Answered;",
                    "Answered" },
            new[] { "catch - the resolution could not complete",
                    "catch { answer = ProximityVanillaAnswer.Threw; return null; }",
                    "Threw" },
        };
        var exitProblems = new List<string>();
        if (victimForBody == null) exitProblems.Add(exitProblem);
        else
        {
            foreach (string[] row in expectedExits)
            {
                int onItsExit = CountOf(victimForBody, row[1]);
                if (onItsExit != 1)
                    exitProblems.Add("the exit [" + row[0] + "] must assign " + row[2]
                        + " on exactly one line of its own; that line occurs " + onItsExit + " time(s)");
                int perOutcome = CountOf(victimForBody, "ProximityVanillaAnswer." + row[2]);
                if (perOutcome != 1)
                    exitProblems.Add(row[2] + " is named on " + perOutcome
                        + " line(s) in this member (want exactly 1 - one exit owns it)");
            }
            // No sixth exit and no exit that assigns twice.
            int assignments = CountOf(victimForBody, "answer = ProximityVanillaAnswer.");
            if (assignments != expectedExits.Length)
                exitProblems.Add("this member assigns the outcome " + assignments
                    + " time(s); the table names " + expectedExits.Length + " exits");
            // NotAsked describes a call that was never made. A member that HAS
            // made the call may never claim otherwise (#351).
            int notAsked = CountOf(victimForBody, "ProximityVanillaAnswer.NotAsked");
            if (notAsked != 0)
                exitProblems.Add("NotAsked is assigned here " + notAsked
                    + " time(s); it belongs to the caller's ring-less path and to nothing in this member");
        }
        // Every value of the outcome type is either owned by one exit above or is
        // NotAsked. A COUNT against the enum, never a sentence read back from it -
        // this is what stops a new outcome being added and silently skipped.
        if (expectedExits.Length + 1 != VanillaAnswers.Length)
            exitProblems.Add("the outcome type has " + VanillaAnswers.Length
                + " values; this table accounts for " + (expectedExits.Length + 1));
        Check("D6 Decline_EachExitOfTheVanillaCallAssignsItsOwnOutcome",
            exitProblems.Count == 0,
            string.Join("; ", exitProblems.ToArray()));

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

        // ---- N1b: FFA'S RANKING IS INHERITED, AND PINNED AS INHERITED --------
        //
        // A LATER HAZARD OBSERVATION, not a restatement of the acceptance bar.
        // The provenance matters and the earlier wording of this comment had it
        // wrong, so it is corrected here against the sources rather than left to
        // be re-derived: round 3's bar named THE SEAM AND THE PATCHES and no
        // third file. Every historical artifact says so - the round-5 brief's B1
        // ("ZERO authored distance or sqrMagnitude comparisons", of the seam and
        // the patches), the round-5 report's B1 row (no mention of FfaMode at
        // all), and the five places the notes carry the clause, each of which
        // reads "in the seam and the patches" or "in either file". N1 is that
        // bar, and its surface is exactly those two files.
        //
        // WHAT THIS CASE IS FOR is a hazard the round-6 cold lens raised
        // afterwards: FfaTargeting.NearestOpponent ranks candidates with
        // Vector2.Distance and the ring sampler measures a signed separation the
        // same way, the seam's single vanilla call routes through the first in
        // FFA, and NO case in the suite read that file. Both comparisons
        // PRE-DATE this branch - the count is the same at the round-2 tip - so
        // neither is a regression; but "inherited, not authored" was a claim
        // with nothing behind it (#351/#434), and a reader could re-open a
        // sub-mechanism rounds 3, 4 and 5 settled on the strength of it.
        //
        // WHAT IS TRUE, and what this case asserts: the seam and the patches
        // author no ranking (N1), and FfaMode's own ranking is INHERITED through
        // the single vanilla call the seam makes - FfaMode prefixes
        // PlayerManager.GetOtherPlayer, so one call picks the substitution up
        // whole, which is the reason round 3 chose inheriting over authoring
        // (N3's paragraph reasons about the same prefix). Inherited is a claim
        // about a COUNT, so it is pinned as one: two comparisons, no more, one
        // of them the selector's own. A third appearing here would be a ranking
        // this branch did not inherit, and no other case would see it, because
        // no other case reads this file.
        string ffaText = LoadSource("plugin/FfaMode.cs");
        var ffaProblems = new List<string>();
        if (ffaText == null)
            ffaProblems.Add("cannot read plugin/FfaMode.cs - an unread file is a failure, not a skip");
        else
        {
            string ffaBlank = LoadBlanked("plugin/FfaMode.cs");
            int dist = CountOf(ffaBlank, "Vector2.Distance(") + CountOf(ffaBlank, "Vector3.Distance(");
            if (dist != 2)
                ffaProblems.Add("FfaMode.cs must carry exactly the two distance comparisons this branch "
                    + "INHERITED - the targeting selector's and the ring sampler's; found " + dist);
            int sqr = CountOf(ffaBlank, "sqrMagnitude");
            if (sqr != 0)
                ffaProblems.Add("and no squared ranking anywhere in it; found " + sqr + " sqrMagnitude");
            int fOpen, fClose; string fProblem;
            if (!TryMemberSpan(ffaBlank, "public static Player NearestOpponent(PlayerManager pm, Vector3 position,",
                    out fOpen, out fClose, out fProblem))
                ffaProblems.Add(fProblem);
            else
            {
                int inSelector = CountOf(ffaBlank.Substring(fOpen, fClose - fOpen + 1),
                    "Vector2.Distance(");
                if (inSelector != 1)
                    ffaProblems.Add("and exactly one of them is the selector's own, inside NearestOpponent - "
                        + "the one the seam's single vanilla call inherits; found " + inSelector);
            }
        }
        Check("N1b Method_FfaRankingIsInheritedNotAuthored",
            ffaProblems.Count == 0,
            string.Join("; ", ffaProblems.ToArray()));

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
        // THE ONE ANCHOR THAT IS ITSELF A COMMENT, so this case declares the
        // PROSE view. Every other anchor in the suite is code and reads the
        // CODE view; handing this one a comment-blanked copy would leave it
        // counting zero on a correct tree - a check that cannot pass is no
        // better than one that cannot fail.
        CheckAnchorInMember("W8 Wiring_TheNoRingReasoningSitsOnTheWalkThatSettlesIt",
            "plugin/ProximityVictimPatches.cs",
            "internal static PlayerInRangeTrigger OwningTrigger(Transform start)",
            "This is the ONLY thing the walk is asked.",
            SourceView.Prose);

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
        // The CODE view of the same file, from the one cache. Every counter of
        // code below reads THIS; the PROSE copy above keeps its declared job.
        string patchesCode = LoadBlanked("plugin/ProximityVictimPatches.cs");
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
            patchesCode != null && CountOnCodeLines(patchesCode, "PatchesLive") == 2,
            "PatchesLive must occur on exactly two code lines - its own declaration and the read "
            + "inside LocalCapability; found "
            + (patchesCode == null ? -1 : CountOnCodeLines(patchesCode, "PatchesLive")));

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
        // anyone having to remember the member (#275).
        // W17 holds the other half of that in the shipped files AND, since this
        // sentence survived a round here, in this one: the compat site can only withdraw on a second DoInitialize.
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
        // AND IN THE HARNESS'S OWN TEXT, which is where the deleted claim was
        // still standing a round later. W16b/c's comment above called the compat
        // site "the one transition that exists today" - outside every file this
        // case inspected - so the sentence the round had deleted from two shipped
        // files was still being handed to the next reader by the suite that
        // certifies the deletion. A search surface that stops short of the
        // document making the claim is not a bound on the claim (#306/#434).
        //
        // A CASE THAT SEARCHES ITS OWN FILE MAY NOT SPELL ITS NEEDLE WHOLE. The
        // literal would be found in this very expression and the forbidden count
        // could never be zero, nor the required count one - a check that cannot
        // fail (#342). Both needles are therefore built from halves, and the
        // sentences they look for live in the comment above, spelled out once.
        string progText = LoadSource("tools/tests/bug389-seam/Program.cs");
        string deletedCompatClaim = "the compat site is the one " + "transition that exists today";
        string correctedCompatClaim = "the compat site can only withdraw on a second " + "DoInitialize";
        string pluginText = LoadSource("plugin/Plugin.cs");
        Check("W17 Wiring_TheCompatSiteClaimsOnlyWhatItCanDo",
            pluginText != null && patchesText != null && progText != null
            && CountOf(pluginText, "A pre-join stage may already have advertised") == 0
            && CountOf(pluginText, "This call is a no-op on a first initialisation.") == 1
            && CountOf(patchesText, "the one transition that exists today") == 0
            && CountOf(patchesText, "THE TICK IS THE TRANSITION THAT EXISTS TODAY") == 1
            && CountOf(progText, deletedCompatClaim) == 0
            && CountOf(progText, correctedCompatClaim) == 1,
            "the compat site, the member's doc and this harness must all say that site can only "
            + "withdraw on a later initialisation, and none of them may claim a first-init advert"
            + " [deleted-claim/required-wording counts, want 0/1 each - Plugin.cs="
            + (pluginText == null ? "unread" : CountOf(pluginText, "A pre-join stage may already have advertised")
                + "/" + CountOf(pluginText, "This call is a no-op on a first initialisation."))
            + ", patches=" + (patchesText == null ? "unread" : CountOf(patchesText, "the one transition that exists today")
                + "/" + CountOf(patchesText, "THE TICK IS THE TRANSITION THAT EXISTS TODAY"))
            + ", harness=" + (progText == null ? "unread" : CountOf(progText, deletedCompatClaim)
                + "/" + CountOf(progText, correctedCompatClaim)) + "]");

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
        // the corrected prose cites. A seat can be Capable and simply not have
        // reached a pre-join merge yet - un-advertised, with nothing for the
        // withdrawal to withdraw; what keeps that room safe is that the census
        // walks the room's own actor list INCLUDING this seat, so this seat's
        // missing key refuses the repair for every seat including itself. A census
        // that special-cased the local actor out would delete that guarantee
        // silently.
        //
        // An earlier wording of this comment reached that corner by the other
        // route - a seat whose patches complete after its first staging attempt -
        // which is a state this build cannot reach (W25). The census fact is
        // unchanged; only the route named for it was wrong.
        CheckMemberAnchors("W22 Wiring_TheCensusCountsThisSeatToo",
            "plugin/ProximityVictimPatches.cs",
            "private static bool Census()",
            new[] { "PhotonNetwork.PlayerList" },
            new[] { "RoomActors.ActiveFighters", "PhotonNetwork.LocalPlayer" });

        // W23 - THE ADVERTISEMENT IS NOT LATCHED: NOT BY THE SHORTFALL FLAG, AND
        // NOT BY A SECOND WRITE TO THE WITHDRAWAL LATCH. RED under
        // "wire-stagelatch" and under "wire-stagewithdraw"; green under
        // "wire-logquote", which edits another line of the same member and is this
        // case's inert twin.
        //
        // Two files used to say _stageFailedPermanently latched the ADVERTISEMENT
        // - the field's own doc had us never advertising later in the session once
        // we had declined, and the withdrawal's argument for having no advertising
        // direction carried the same latch as a premise. The flag does no such
        // thing. It is read only on the branch that has already declined, where it
        // bounds a second LogError, and the advertising branch asks the local gate
        // and the withdrawal latch and nothing else.
        //
        // THE CONCLUSION THOSE COMMENTS DREW WAS TRUE; ONLY THE MECHANISM WAS
        // WRONG. A decline IS final - because every term of the advertising guard
        // is settled before the first staging attempt can run, which is W25 and
        // not this case. The intermediate wording went the other way and had both
        // shipped files telling a reader that a seat whose third patch attaches
        // late goes on to advertise on a later merge. That state is not reachable
        // on this build; the wording also contradicted the line StageInto actually
        // emits (W19), and it would have licensed exactly the in-room advertising
        // direction the seam forbids (#351/#434).
        //
        // THE FLAG IS NOT THE ONLY WAY TO LATCH THIS BRANCH, which is why this
        // case grew a fourth assertion. Checking the guard's two terms, the flag's
        // two code lines and their order leaves a latch installed through the
        // OTHER one-way flag entirely green: an assignment to _withdrawn on the
        // declining branch would make the shortfall flag gate a capability after
        // all - the exact drift the paragraphs above say cannot happen - with
        // every other assertion here unmoved. The member must therefore assign no
        // _withdrawn at all; its one writer is RepublishCapability. A flag names a
        // line, the defect is a class (#432).
        string stageProblem;
        string stageBody = MemberBody("plugin/ProximityVictimPatches.cs",
            "internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)",
            out stageProblem);
        var stageProblems = new List<string>();
        if (stageBody == null) stageProblems.Add(stageProblem);
        else
        {
            string advertGuard = "if (local == ProximityGateState.Capable && !_withdrawn)";
            string advertWrite = "prejoin[ProximityVictim.CapabilityProp] = ProximityVictim.CapabilityValue;";
            int guards = CountOf(stageBody, advertGuard);
            if (guards != 1)
                stageProblems.Add("the advertising guard must be exactly '" + advertGuard
                    + "' and occur once - two terms, neither of them the shortfall flag; found " + guards);
            int flagReads = CountOnCodeLines(stageBody, "_stageFailedPermanently");
            if (flagReads != 2)
                stageProblems.Add("_stageFailedPermanently must occur on exactly two code lines here - "
                    + "the test and the set, both on the declining branch; found " + flagReads);
            int writeAt = stageBody.IndexOf(advertWrite, StringComparison.Ordinal);
            int flagAt = stageBody.IndexOf("_stageFailedPermanently", StringComparison.Ordinal);
            if (writeAt < 0 || flagAt < 0 || writeAt > flagAt)
                stageProblems.Add("the key must be staged BEFORE this member reads the flag at all "
                    + "(staged at " + writeAt + ", first flag read at " + flagAt + ")");
            // THE PROPERTY, NOT THE SPELLING. This assertion used to be
            // CountOnCodeLines(stageBody, "_withdrawn = "), which recognises one
            // whitespace form of one operator: "_withdrawn=true;" installed the
            // very latch the assertion exists to forbid and left the case green.
            // WritesTo classifies by OPERATION, so every spelling of every
            // assignment reaches the same bound (#432/#342). Line numbers in the
            // message are counted from the start of this member, not the file.
            var stageWithdrawWrites = WritesTo(stageBody, "_withdrawn");
            if (stageWithdrawWrites.Count != 0)
                stageProblems.Add("this member must ASSIGN no _withdrawn in ANY spelling - its one writer is "
                    + "RepublishCapability, and a latch installed through that flag instead would "
                    + "leave every other assertion here green; found " + Describe(stageWithdrawWrites));
            // And the flag this case is named for: written exactly once here,
            // writing true. "Occurs on two code lines" counts occurrences and
            // cannot tell the set from a second read; this says which of the two
            // is the write and what it writes, so a flag that started gating a
            // capability by being cleared somewhere would redden.
            var stageFlagWrites = WritesTo(stageBody, "_stageFailedPermanently");
            if (stageFlagWrites.Count != 1 || stageFlagWrites[0].Kind != "= (simple assignment)"
                || stageFlagWrites[0].Rhs != "true")
                stageProblems.Add("the shortfall flag must be written exactly once in this member and write true - "
                    + "that is what makes it a bound on a log line rather than a latch on a capability; found "
                    + Describe(stageFlagWrites));
        }
        Check("W23 Wiring_TheAdvertisementIsNotLatchedByTheShortfallFlag",
            stageProblems.Count == 0,
            string.Join("; ", stageProblems.ToArray()));

        // W24 - THE RETRACTED LATCH LANGUAGE IS ABSENT FROM EVERY FILE THAT
        // CERTIFIES ITS DELETION. RED under "wire-latchprose".
        //
        // Seven earlier deletions each carry an absence bound: W13, W17, W19 and
        // W21 all count the removed text and require zero. The eighth - the latch
        // language above - had only a line in the notes and a STRUCTURAL case
        // (W23) that reads code and never reads a comment, so the sentence could
        // walk back into either file with all checks green and the next reader
        // would re-derive the withdrawal's polarity from a mechanism the code does
        // not implement. That is the same gap the compat claim had, closed one
        // deletion earlier by widening W17, and not applied to this one.
        //
        // THE SURFACE IS ALL FOUR FILES, not just the two shipped ones. Last time,
        // the document still making the deleted claim was this harness's own
        // comment; the mutant driver is the same kind of document and is included
        // for the same reason. A ninth deletion rides here too: the intermediate
        // late-staging wording, which was a claim about an unreachable state.
        //
        // EVERY NEEDLE IS BUILT FROM HALVES, because this case searches the file
        // it is written in - a needle spelled whole here would be found here and
        // could never count zero, a check that cannot fail (#342). The comments
        // around it name these sentences only in paraphrase or across a line
        // break, which is the same discipline.
        string runnerText = LoadSource("tools/tests/bug389-seam/run-tests.ps1");
        string latchDoc = "once we have declined to advertise, we never "
            + "advertise later in the session";
        string latchSeam = "a seat that declined once never "
            + "stages again in that session";
        string latchSeamAlt = "a seat that declined once never "
            + "staging again in that session";
        string lateStage = "pre-join merge " + "stages the key";
        string lateStageSeam = "DOES stage the key on its " + "next pre-join merge";
        string[] latchNeedles = new[] { latchDoc, latchSeam, latchSeamAlt, lateStage, lateStageSeam };
        string[] latchNames = new[] { "latch-in-the-field-doc", "latch-in-the-seam",
            "latch-in-the-seam-respelled", "late-staging-claim", "late-staging-claim-in-the-seam" };
        string[] latchFiles = new[] { "plugin/ProximityVictimPatches.cs", "plugin/ProximityVictimSeam.cs",
            "tools/tests/bug389-seam/Program.cs", "tools/tests/bug389-seam/run-tests.ps1" };
        string[] latchTexts = new[] { patchesText, seamText, progText, runnerText };
        var latchProblems = new List<string>();
        for (int f = 0; f < latchTexts.Length; f++)
        {
            if (latchTexts[f] == null)
            {
                latchProblems.Add("cannot read " + latchFiles[f] + " - an unread file in this surface is a "
                    + "failure, not a skip: it is exactly how the last deletion stayed certified");
                continue;
            }
            for (int n = 0; n < latchNeedles.Length; n++)
            {
                int hits = CountOf(latchTexts[f], latchNeedles[n]);
                if (hits != 0)
                    latchProblems.Add(latchFiles[f] + " still carries the " + latchNames[n]
                        + " (" + hits + " hit(s), want 0)");
            }
        }
        // ...and the replacement is actually stated, so this case cannot pass by
        // both the claim and its correction being absent.
        if (patchesText != null && CountOf(patchesText, "SETTLED BEFORE THE FIRST STAGING ATTEMPT") != 1)
            latchProblems.Add("the patches file must state the replacement exactly once - that the guard's "
                + "terms are fixed before the first attempt, which is why a decline is final");
        if (seamText != null && CountOf(seamText, "settled before the first staging attempt") != 1)
            latchProblems.Add("the seam must state the same replacement exactly once, in the paragraph "
                + "that used to carry the latch as its premise");
        Check("W24 Wiring_TheRetractedLatchLanguageIsAbsentFromEveryFileThatCertifiesIt",
            latchProblems.Count == 0,
            string.Join("; ", latchProblems.ToArray()));

        // W25 - THE TERMS OF THE ADVERTISING GUARD ARE SETTLED BEFORE THE FIRST
        // STAGING ATTEMPT. RED under "wire-reach" and under "wire-reachdecline";
        // green under "wire-logquote", which edits the same file on a line this
        // case makes no claim about, and green under "wire-stagewithdraw" and
        // "wire-stagewithdrawtight", whose writes are one-way.
        //
        // This is what makes the corrected paragraphs checkable rather than merely
        // plausible. Both shipped files now say a decline is final because the
        // guard's inputs cannot move afterwards, and StageInto says so out loud in
        // a line W19 pins and the TeleportToOpponent doc tells a maintainer to grep
        // a session log for. A sentence about the whole session is a claim about
        // the whole state space and needs a pin, not a re-reading (#351/#434).
        //
        // EVERY PREMISE BELOW IS ASSERTED AS A PROPERTY OF AN OPERATION, not as a
        // count of a spelling. The round-5 version of this case counted the texts
        // "_attached++", "_attached = ", "_withdrawn = " and "Plugin.modDisabled = ".
        // Each recognised one whitespace form of one operator, so "_attached=0;",
        // "_attached--" and an unqualified "modDisabled = true;" all passed it,
        // and the mutant written to prove it could only ever prove that the
        // recognised spelling was present. WritesTo classifies by what follows the
        // identifier and sees every spelling; CallsTo and AttributesOf do the same
        // for the call and attribute counts (#432/#342/#431). The premises:
        //   - the attachment count has exactly ONE write across every shipped C#
        //     file this harness reads, in any spelling; that write is MONOTONE; and
        //     it lives inside MarkAttached, so the count can only ever rise and only
        //     the patch loop's callbacks can make it rise. The surface is the whole
        //     read set and not just the file declaring the field, because the field
        //     being private is not something this case asserts;
        //   - that writer is called from exactly three sites, and there are
        //     exactly three Harmony cleanup callbacks for them to be;
        //   - the assembly has exactly one patch site and no PatchAll beside it,
        //     and that site is inside Awake's Harmony bootstrap block (W25b);
        //   - ApiClient.Initialize - which the three pre-join merges that can
        //     stage this key are all downstream of - is inside the deferred
        //     initialisation, not inside Awake (W25c);
        //   - every write to either boolean term writes true, so neither can move
        //     back - the ONE-WAY direction is the premise, and it is deliberately
        //     not "exactly one writer": a second write that also writes true would
        //     leave the reachability argument intact. Whether StageInto itself may
        //     write one is a different question, and W23 owns it. A declaration
        //     INITIALISER is the starting value and is checked separately: false
        //     for a latch that only ever goes true.
        //
        // WHAT THIS CASE DOES NOT PROVE, said plainly so the next reader does not
        // take more from it than it gives: that Awake runs before the first tick
        // that can reach DoInitialize. That is Unity's lifecycle contract, not a
        // fact about this text, and both shipped paragraphs record it as a premise
        // rather than claiming a test for it.
        string apiText = LoadSource("plugin/ApiClient.cs");
        var reachProblems = new List<string>();
        // THE SURFACE IS THE COMPILATION UNIT SET, ENUMERATED - not a list
        // written here. "The count has one writer" is a statement about the
        // ASSEMBLY. The round-6 build got the direction right and the kind
        // wrong: it replaced two files with SEVEN, which is still a surface
        // guessed from where the fields live today, and it defended the gap
        // with "the fields are private, so today no unlisted file can write
        // them". That defence is true of _attached and _withdrawn and FALSE
        // of the third term this case also reads - Plugin.modDisabled is
        // internal and already referenced from six other shipped files - and
        // it is no defence at all for the patch-site clauses below, which
        // need no field access. A hardcoded target is the check that cannot
        // fail (#342/#431), so the list is gone: ShippedCsFiles enumerates
        // every .cs the project compiles and the scan surface is that set.
        //
        // EmojiSprites.cs used to be kept out BY NAME, because it declares an
        // unrelated `_attached` of its own. The name is gone too, replaced by
        // the rule that produced it: a BARE name in a file that declares a
        // field of that name binds to the file's OWN field. Round 6 turned that
        // rule into a whole-file exclusion and printed it for two of the three
        // scans it ran; round 7 added a fourth scan, of `initialized`, and
        // plugin/CustomCosmetics.cs declares one of those too - so that file
        // left the surface with no line in any log, under a count whose message
        // named all 91 files. The rule is now a NARROWING to the qualified
        // spelling, it applies to every field scanned, and ScanNote prints what
        // each scan actually read.
        var scanNotes = new List<string>();
        string surfaceProblem;
        string[] shippedCs = ShippedCsFiles(out surfaceProblem);
        if (surfaceProblem != null)
            reachProblems.Add(surfaceProblem + " - the scan surface is a failure, not a skip");
        // A root resolving to a sparse tree must FAIL for the files this
        // argument names, rather than quietly pass by scanning fewer.
        foreach (string need in new[] { "plugin/ProximityVictimPatches.cs", "plugin/ProximityVictimSeam.cs",
                                        "plugin/Plugin.cs", "plugin/ApiClient.cs" })
            if (Array.IndexOf(shippedCs, need) < 0)
                reachProblems.Add("the shipped-source enumeration must contain " + need
                    + "; it found " + shippedCs.Length + " file(s) and not that one");

        var surfaceText = new Dictionary<string, string>();
        var surfaceBlank = new Dictionary<string, string>();
        foreach (string rel in shippedCs)
        {
            string text = LoadSource(rel);
            if (text == null)
            {
                reachProblems.Add("cannot read " + rel + " - an unread file is a failure, not a skip");
                continue;
            }
            string blank = LoadBlanked(rel);
            if (blank == null)
            {
                reachProblems.Add("cannot build the code view of " + rel
                    + " - an unread file is a failure, not a skip");
                continue;
            }
            surfaceText[rel] = text;
            surfaceBlank[rel] = blank;
        }
        // THE TWO VIEWS ARE ONE MEMBERSHIP. Every scan below reads the code
        // view through "if (!surfaceBlank.TryGetValue(rel, out blanked)) continue;"
        // - a SKIP - and what made that safe was a null check a hundred lines
        // above, on the OTHER dictionary. Nothing said so and nothing would
        // have caught the two drifting apart: the same shape as the register
        // entry N5 closed, a guarantee kept by a mechanism that is not where
        // the reader is (#351/#434). The sparse prior-tip root is where this
        // clause can actually fire.
        if (surfaceText.Count != surfaceBlank.Count)
            reachProblems.Add("the prose view and the code view must cover the same files - one present "
                + "in either and absent from the other is skipped silently by every scan below; "
                + surfaceText.Count + " prose, " + surfaceBlank.Count + " code");

        if (patchesText == null) reachProblems.Add("cannot read plugin/ProximityVictimPatches.cs");
        if (seamText == null) reachProblems.Add("cannot read plugin/ProximityVictimSeam.cs");
        if (patchesText != null && seamText != null)
        {
            // --- the attachment count: ONE write, MONOTONE, inside MarkAttached ---
            //
            // Every clause here is a property of the OPERATION. The round-5
            // version asked whether the text "_attached++" occurred once and the
            // text "_attached = " occurred never, which is true of a file that
            // writes "_attached=0;" or "_attached--" and false of one that
            // harmlessly writes "_attached += 1". Both directions were wrong, and
            // the mutant written against it could only ever prove that the one
            // recognised spelling was present.
            const string attachHome = "plugin/ProximityVictimPatches.cs";
            SurfaceScan attachScan = ScanField(shippedCs, surfaceText, surfaceBlank, "_attached", attachHome, "0");
            SurfaceScan withdrawScan = ScanField(shippedCs, surfaceText, surfaceBlank, "_withdrawn", attachHome, "false");
            reachProblems.AddRange(attachScan.DeclProblems);
            reachProblems.AddRange(withdrawScan.DeclProblems);
            if (!attachScan.HomeDeclares)
                reachProblems.Add("the attachment count must be DECLARED in " + attachHome
                    + " - the home is derived from the declaration, not assumed by name");
            if (!withdrawScan.HomeDeclares)
                reachProblems.Add("the withdrawal latch must be DECLARED in " + attachHome
                    + " - same reason");
            // The narrowings are part of the result and are printed on every
            // run, clean or not, for EVERY field this case scans: a surface a
            // reader cannot reconstruct is how one narrows without anybody
            // deciding to narrow it. The line itself is emitted once, after the
            // last scan is built, so no scan can be added without one.
            scanNotes.Add(ScanNote("attachment count", attachScan));
            scanNotes.Add(ScanNote("withdrawal latch", withdrawScan));

            List<FieldWrite> realAttach = RealIn(attachScan, attachHome);
            List<string> attachElsewhere = RealOutside(attachScan, attachHome);
            foreach (FieldWrite w in withdrawScan.Real)
                if (w.Kind != "= (simple assignment)" || w.Rhs != "true")
                    reachProblems.Add("every write to the withdrawal latch must write true - ONE-WAY is the "
                        + "premise here, not the number of writers, and W23 owns the separate question of "
                        + "whether StageInto makes one; found " + w.Kind + " with right-hand side '" + w.Rhs
                        + "' in " + w.Rel + " line " + w.Line);
            int realWithdraw = withdrawScan.Real.Count;
            if (attachElsewhere.Count != 0)
                reachProblems.Add("only " + attachHome + " may write the attachment count; found "
                    + string.Join(" | ", attachElsewhere.ToArray()));
            if (realAttach.Count != 1)
                reachProblems.Add("the attachment count must have exactly one write across the "
                    + attachScan.Scanned + " shipped file(s) READ by this scan, in ANY spelling; found "
                    + realAttach.Count + " in " + attachHome + ": " + Describe(realAttach));
            else
            {
                FieldWrite w = realAttach[0];
                if (!IsMonotoneWrite(w))
                    reachProblems.Add("that write must be MONOTONE - an increment, or += a non-negative integer "
                        + "literal - or the count can fall back below the required three after a staging attempt "
                        + "has already declined; found " + w.Kind + " at line " + w.Line + " [" + w.Text + "]");
                int mOpen, mClose; string mProblem;
                if (!TryMemberSpan(LoadBlanked(attachHome), "internal static void MarkAttached(string which)",
                        out mOpen, out mClose, out mProblem))
                    reachProblems.Add(mProblem);
                else if (w.Index < mOpen || w.Index > mClose)
                    reachProblems.Add("the one write must live inside MarkAttached - a write anywhere else is how "
                        + "the count stops being the patch loop's alone, and a decline stops being final; found it "
                        + "at line " + w.Line + " [" + w.Text + "]");
            }
            if (realWithdraw < 1)
                reachProblems.Add("the withdrawal latch must have at least one write, or this premise is vacuous");

            int callers = CallsToIn(patchesCode, "ProximityVictimGate.MarkAttached");
            if (callers != 3)
                reachProblems.Add("MarkAttached must be called from exactly three sites; found " + callers);
            int cleanups = AttributesOf(patchesCode, "HarmonyCleanup");
            if (cleanups != 3)
                reachProblems.Add("and those sites must be Harmony cleanup callbacks, which run inside the "
                    + "patch loop; found " + cleanups + " cleanup attribute(s)");

            // THE THREE CALLERS PASS THREE DISTINCT LITERALS, AND THAT IS PINNED.
            // The wiring mutant that proves the count CAN be made two-way keys on
            // one of them ("StunPlayer.Go"). Rename the tag and that mutant stops
            // reaching any call - the round-5 defect exactly - while the clause it
            // reddens goes on passing for the write count, so the RESULT row still
            // prints OK and the reachability claim silently reverts to the refuted
            // one. A mutant's reachability is a property of the source, so it is
            // checked here rather than read once and trusted (#342/#431).
            foreach (string tag in new[] { "DealDamageToPlayer.Go", "StunPlayer.Go", "TeleportToOpponent.Go" })
            {
                int tagged = CountOf(patchesCode,
                    "ProximityVictimGate.MarkAttached(\"" + tag + "\")");
                if (tagged != 1)
                    reachProblems.Add("MarkAttached must be called exactly once with the literal \"" + tag
                        + "\" - the wiring mutant that makes the attachment count two-way keys on one of these "
                        + "three, and a renamed tag makes that mutant unreachable while this case stays green; "
                        + "found " + tagged);
            }
        }

        // --- the patch sites: A STATEMENT ABOUT THE ASSEMBLY, SCANNED AS ONE ---
        //
        // These two clauses used to read plugin/Plugin.cs alone while their own
        // failure text said "the assembly", and the privateness that mitigates
        // the write scan does not reach them at all: nothing restricts a Harmony
        // patch site to one file. A later file adding `new Harmony(id).PatchAll()`
        // from a deferred init would attach the three cleanup callbacks a SECOND
        // time, after ApiClient.Initialize and so after a pre-join merge may
        // already have staged - a seat whose first pass left the count short
        // declines, prints the shortfall line that says it stays on vanilla for
        // the session, and then reaches three on the late pass. Every clause here
        // stayed green on that, because Plugin.cs was unchanged.
        //
        // `new Harmony(` is counted as well as the two call names: it is the
        // constructor every other attachment route has to go through, so it
        // bounds routes this suite has not thought of.
        int patchSites = 0, patchAll = 0, harmonyCtors = 0;
        var patchWhere = new List<string>();
        foreach (string rel in shippedCs)
        {
            string blanked;
            if (!surfaceBlank.TryGetValue(rel, out blanked)) continue;
            int cp = CallsToIn(blanked, "CreateClassProcessor");
            int pa = CallsToIn(blanked, "PatchAll");
            int hc = CountOf(blanked, "new Harmony(");
            patchSites += cp; patchAll += pa; harmonyCtors += hc;
            if (cp + pa + hc != 0)
                patchWhere.Add(rel + " CreateClassProcessor=" + cp + " PatchAll=" + pa + " newHarmony=" + hc);
        }
        string patchMap = patchWhere.Count == 0 ? "nowhere" : string.Join(" | ", patchWhere.ToArray());
        if (patchSites != 1)
            reachProblems.Add("the ASSEMBLY must have exactly one Harmony patch site, or the attachment count "
                + "can still move after this one has run; found " + patchSites + " across " + shippedCs.Length
                + " shipped file(s): " + patchMap);
        if (patchAll != 0)
            reachProblems.Add("and no PatchAll call may stand beside it anywhere in the assembly, or patches "
                + "attach from a second site the reachability argument does not bound; found " + patchAll
                + ": " + patchMap);
        if (harmonyCtors != 1)
            reachProblems.Add("and exactly one Harmony instance may be constructed in the assembly, since every "
                + "other attachment route goes through one; found " + harmonyCtors + ": " + patchMap);

        // --- the disabled flag: ONE-WAY, over the same enumerated surface -----
        //
        // This is the term the privateness mitigation never covered.
        // Plugin.modDisabled is `internal static`, and six other shipped files
        // already reference it, so any file in the assembly may legally write it.
        // Scanning its declaring file alone asserted nothing about the premise.
        SurfaceScan disabledScan = ScanField(shippedCs, surfaceText, surfaceBlank,
            "modDisabled", "plugin/Plugin.cs", "false");
        scanNotes.Add(ScanNote("disabled flag", disabledScan));
        reachProblems.AddRange(disabledScan.DeclProblems);
        if (shippedCs.Length != 0 && !disabledScan.HomeDeclares)
            reachProblems.Add("the disabled flag must be DECLARED in plugin/Plugin.cs");
        // THIS ONE STAYS FATAL, and the narrowing is why it has to be said
        // rather than left to the general rule. For the other three fields a
        // second declarer costs the scan nothing: they are private, so only the
        // qualified spelling could reach the home field and that is exactly what
        // the narrowing keeps reading. This flag is `internal static` and six
        // shipped files already reference it, so the BARE spelling is a legal
        // write to it from anywhere - and in a file that declared its own
        // modDisabled the narrowing would stop reading precisely that spelling.
        // A second declarer of this name is therefore refused outright.
        if (disabledScan.Narrowed.Count != 0)
            reachProblems.Add("no shipped file may declare a second flag named modDisabled - this one is "
                + "internal, so a BARE write to it is legal from any file, and a file declaring its own is "
                + "read for qualified writes only; found " + string.Join(", ", disabledScan.Narrowed.ToArray()));
        foreach (FieldWrite w in disabledScan.Real)
            if (w.Kind != "= (simple assignment)" || w.Rhs != "true")
                reachProblems.Add("every write to the disabled flag must write true, or a seat that reached "
                    + "ModDisabled can return to Capable after a staging attempt has already declined; found "
                    + w.Kind + " with right-hand side '" + w.Rhs + "' in " + w.Rel + " line " + w.Line);
        if (shippedCs.Length != 0 && disabledScan.Real.Count < 1)
            reachProblems.Add("the disabled flag must have at least one write, or this premise is vacuous");
        if (pluginText == null) reachProblems.Add("cannot read plugin/Plugin.cs");
        if (apiText == null) reachProblems.Add("cannot read plugin/ApiClient.cs");

        // --- THE DOWNSTREAM RELATION ITSELF, and not a count of its sites -----
        //
        // This clause used to be `CallsTo(apiText, "...StageInto") == 3`, with a
        // failure message that said "and all three are downstream of
        // ApiClient.Initialize". The count proves the number of sites; it proves
        // nothing whatever about the ORDER, so the check did not reject the
        // change its own message claimed to forbid - a source edit that makes a
        // staging member reachable before initialisation left it at three and
        // green. W25c sits beside it and only LOCATES ApiClient.Initialize
        // inside DoInitialize; where a thing IS is not when it RUNS. A check
        // that cannot fail for the property it names is worse than no check
        // (#342/#431), and the shipped paragraphs in both files rest on this
        // relation being true.
        //
        // WHAT THE RELATION IS, DERIVED BY READING THE SOURCE - AND CORRECTED.
        // The round-7 build wrote here that "every route that can reach
        // StageInto passes through the persistent tick BELOW `if (!initialized)
        // return;`". That is FALSE of the assembly it describes, and its own
        // NOTE line printed the counter-evidence: of the ten staging entry-point
        // call sites, five are inside plugin/ApiClient.cs, reached from a
        // response callback, a coroutine and a delegate the menu stores - none
        // of them the tick. A route walk cannot reach those, because a call made
        // through a delegate names no member and no text scan sees it; writing
        // more route clauses against a model the source contradicts is patching
        // where the model is what is wrong (#310/#389/#473). What replaces it is
        // a BOUND each clause can actually carry:
        //
        //   THE MERGE IS RESPONSE-BOUND. StageInto runs only inside the callback
        //   of a request this client built from `baseUrl`, and `baseUrl` starts
        //   empty and is written only inside ApiClient. So WHO calls a staging
        //   entry point does not decide when a merge runs - a reply does.
        //
        //   THE CALLER SET IS CLOSED AT MEMBER GRAIN. Every entry-point call
        //   site in the assembly is inside one of a named set of members: the
        //   persistent tick below its gate, the two menu tab refreshers R5 pins
        //   to that tick, and five members of ApiClient.cs. A new caller
        //   anywhere - including in a file already permitted - reddens and is
        //   named, which is the condition round 6 asked for and the file-grain
        //   clause could not carry.
        //
        // The clauses below assert that, link by link, each one a position or a
        // count over the CODE view:
        //
        //   R1  every StageInto call in the assembly is in ApiClient.cs (3 of
        //       them), and each sits at a LARGER offset than a baseUrl-built
        //       request inside its own member - the local half;
        //   R2  the flag: exactly one non-declaration write to `initialized`
        //       across the surface, writing true, inside DoInitialize, at a
        //       larger offset than ApiClient.Initialize, with the declaration
        //       initialiser false;
        //   R3  in Plugin.cs every call to a staging entry point lives INSIDE
        //       the persistent tick's own member span and BELOW the gate - so a
        //       merge moved above the gate, planted in an Awake, or planted in
        //       DoInitialize is rejected by position, not by a count;
        //   R4  the caller FILE set is closed: across all 91 shipped files only
        //       ApiClient.cs, NativeUI.cs and Plugin.cs may call a staging entry
        //       point, and the per-file map is printed on failure;
        //   R5  the NativeUI route is anchored to the same gate by counts:
        //       MaybeRefreshOvtTab/MaybeRefreshFfaTab are called only from
        //       inside NativeUI.Tick, NativeUI.Tick only from inside
        //       CompetitiveUI.Tick, and CompetitiveUI.Tick only from the tick
        //       below the gate;
        //   R6  the CALLER SET AT MEMBER GRAIN, over every file: each staging
        //       entry-point call site is resolved to the member that encloses it
        //       and that member must be one of the 8 named below - so a call
        //       lifted out of a tab refresher into another NativeUI member, or
        //       added to a sixth ApiClient member, reddens and is named. This
        //       is what R3/R4 could not do: R3 skipped every file that was not
        //       Plugin.cs and R4 closed only the FILE set, leaving seven of the
        //       ten sites the map prints with no position constraint at all;
        //   R7  the merge is RESPONSE-BOUND: each of the three merges lies
        //       INSIDE the lambda body opened after its member's own
        //       baseUrl-built request - or, for the parser, its one call site
        //       lies inside its host's - so it runs on a reply and never on
        //       entry;
        //   R8  the request prefix those replies come from: `baseUrl` is
        //       declared in ApiClient.cs with the empty initialiser, no other
        //       shipped file writes it, and its writer members are a closed set
        //       containing ApiClient.Initialize.
        //
        // WHAT IT STILL DOES NOT PROVE, said plainly rather than left to be
        // found. A call made through a delegate, an event or reflection names no
        // member and no text scan can see it - the FFA lobby kick is exactly
        // that, and R6 places the member it lands in rather than claiming to
        // have walked to it. The step that Awake runs before the first tick
        // reaching DoInitialize is Unity's lifecycle contract, not a fact about
        // this text. And R7/R8 bound the merge to a reply to a request built
        // from a prefix only initialisation sets; that an EMPTY prefix yields no
        // such reply is a property of the transport, not of this source. Those
        // three are the round's carried OPEN PREMISES; the lifecycle one is
        // disclosed in both shipped files (W26).
        const string stageCall = "ProximityVictimGate.StageInto";
        string[] stageEntries = new[] { "ParseTeamQueuePoll", "UpdateTeamQueuePoll",
                                        "UpdateOvtQueuePoll", "UpdateFfaQueuePoll" };
        const string apiRel = "plugin/ApiClient.cs";
        const string uiRel = "plugin/NativeUI.cs";
        const string pluginRel = "plugin/Plugin.cs";
        const string compRel = "plugin/CompetitiveUI.cs";

        // R1 - the staging surface, over the whole assembly and not one file.
        var stageWhere = new List<string>();
        int stageTotal = 0;
        foreach (string rel in shippedCs)
        {
            string blanked;
            if (!surfaceBlank.TryGetValue(rel, out blanked)) continue;
            int n = CallsToIn(blanked, stageCall);
            stageTotal += n;
            if (n != 0) stageWhere.Add(rel + " x" + n);
        }
        string stageMap = stageWhere.Count == 0 ? "nowhere" : string.Join(" | ", stageWhere.ToArray());
        if (stageTotal != 3 || stageWhere.Count != 1 || !stageWhere[0].StartsWith(apiRel, StringComparison.Ordinal))
            reachProblems.Add("this key may be staged from exactly three sites and all three must live in "
                + apiRel + ", the file whose merges are downstream of initialisation; found " + stageTotal
                + " across the assembly: " + stageMap);

        string apiBlank = LoadBlanked(apiRel);
        if (apiBlank != null)
        {
            // ...and each one sits after a request URL built from baseUrl. A
            // merge lifted to the top of its member would run on ENTRY rather
            // than on a response, which is the local form of the same drift.
            //
            // Two of the three build their own request and carry the merge in
            // its callback. The third does not and must not be forced to: the
            // 2v2 parser is handed a response body, so the request that reaches
            // it is its CALLER's, and the pairing says which member that is
            // rather than accepting "no baseUrl here" as a pass. A member whose
            // merge cannot be tied to a request either way FAILS.
            string[][] stageMembers = new[]
            {
                new[] { "private static void ParseTeamQueuePoll(string response)",
                        "public static void UpdateTeamQueuePoll(string steamId)" },
                new[] { "public static void UpdateOvtQueuePoll(bool force)", null },
                new[] { "public static void UpdateFfaQueuePoll(bool force)", null }
            };
            foreach (string[] pair in stageMembers)
            {
                string sig = pair[0], host = pair[1];
                int mo, mc; string mp;
                if (!TryMemberSpan(apiBlank, sig, out mo, out mc, out mp)) { reachProblems.Add(mp); continue; }
                string body = apiBlank.Substring(mo, mc - mo + 1);
                int site = body.IndexOf(stageCall, StringComparison.Ordinal);
                if (site < 0)
                {
                    reachProblems.Add("the pre-join merge in '" + sig + "' must stage this key");
                    continue;
                }
                int url = body.IndexOf("baseUrl", StringComparison.Ordinal);
                if (host == null)
                {
                    if (url < 0 || url > site)
                    {
                        reachProblems.Add("the merge in '" + sig + "' must sit AFTER the request built from "
                            + "baseUrl in that member - a merge that runs on entry rather than on a response "
                            + "is not downstream of anything; baseUrl at " + url + ", merge at " + site);
                        continue;
                    }
                    // R7 - and AFTER is not the property. A statement written
                    // below the whole StartCoroutine call is also "after
                    // baseUrl" and runs on entry, on whatever tick reached the
                    // member. The merge has to be INSIDE the callback opened for
                    // that request, which is what makes it run on a reply.
                    int lo, lc;
                    if (!TryLambdaSpanAfter(body, url, out lo, out lc))
                        reachProblems.Add("the request in '" + sig + "' must open a response callback for the "
                            + "merge to live in; none found after its baseUrl request");
                    else if (site < lo || site > lc)
                        reachProblems.Add("the merge in '" + sig + "' must sit INSIDE that request's response "
                            + "callback, not merely after it in the file - outside it the merge runs on entry "
                            + "and no reply is involved at all; callback spans " + lo + ".." + lc
                            + ", merge at " + site);
                    continue;
                }
                // The parser's own entry: called exactly once in the assembly,
                // from inside the named host, after that host's request.
                int ho, hc; string hp;
                if (!TryMemberSpan(apiBlank, host, out ho, out hc, out hp)) { reachProblems.Add(hp); continue; }
                string name = MemberName(sig);
                var callers = new List<string>();
                int inHost = 0;
                foreach (string rel in shippedCs)
                {
                    string b2;
                    if (!surfaceBlank.TryGetValue(rel, out b2)) continue;
                    var sites = CallSitesIn(b2, name);
                    if (rel != apiRel) sites.AddRange(CallSitesIn(b2, "ApiClient." + name));
                    if (sites.Count == 0) continue;
                    callers.Add(rel + " x" + sites.Count);
                    if (rel != apiRel) continue;
                    foreach (int at in sites)
                    {
                        if (at < ho || at > hc) continue;
                        int hostUrl = apiBlank.IndexOf("baseUrl", ho, StringComparison.Ordinal);
                        if (hostUrl < 0 || hostUrl >= hc || hostUrl >= at) continue;
                        // R7 for the borrowed request: the parser's call site
                        // has to be inside the host's response callback, not
                        // merely below the host's request.
                        int lo, lc;
                        if (!TryLambdaSpanAfter(apiBlank, hostUrl, out lo, out lc)) continue;
                        if (at >= lo && at <= lc) inHost++;
                    }
                }
                if (callers.Count != 1 || inHost != 1)
                    reachProblems.Add("'" + name + "' carries a merge but builds no request, so its own entry "
                        + "is what makes it downstream: it must be called exactly once in the assembly, from "
                        + "INSIDE the response callback of '" + host + "'s baseUrl request; found "
                        + (callers.Count == 0 ? "no caller" : string.Join(" | ", callers.ToArray()))
                        + ", " + inHost + " of them in place");
            }
        }

        // R8 - the prefix every one of those replies comes back from.
        //
        // R7 says a merge runs inside the callback of a request built from
        // `baseUrl`. That is only a downstream relation if `baseUrl` is the
        // thing initialisation sets, so this reads the field the same way the
        // guard terms are read: declared in ApiClient.cs with the EMPTY
        // initialiser, written by no other shipped file, and written only from a
        // closed set of members one of which is ApiClient.Initialize. The TLS
        // probe re-targets it for the session and is named here rather than
        // waved past, because a writer this case cannot name is a writer nobody
        // reading the run can account for.
        SurfaceScan urlScan = ScanField(shippedCs, surfaceText, surfaceBlank,
            "baseUrl", apiRel, "\"\"");
        scanNotes.Add(ScanNote("request prefix", urlScan));
        reachProblems.AddRange(urlScan.DeclProblems);
        if (shippedCs.Length != 0 && !urlScan.HomeDeclares)
            reachProblems.Add("the request prefix must be DECLARED in " + apiRel);
        List<string> urlElsewhere = RealOutside(urlScan, apiRel);
        if (urlElsewhere.Count != 0)
            reachProblems.Add("only " + apiRel + " may write the request prefix every staging merge's reply "
                + "comes back from; found " + string.Join(" | ", urlElsewhere.ToArray()));
        if (apiBlank != null)
        {
            string[] urlWriters = new[]
            {
                "public static void Initialize(string url)",
                "private static IEnumerator ProbeEndpointThenStart()"
            };
            var urlWhere = new List<string>();
            bool initWrites = false;
            foreach (FieldWrite w in RealIn(urlScan, apiRel))
            {
                string owner = EnclosingMemberOf(apiBlank, w.Index);
                urlWhere.Add("line " + w.Line + " in " + (owner ?? "(no enclosing member)"));
                if (owner != null && owner == urlWriters[0]) initWrites = true;
                if (owner == null || Array.IndexOf(urlWriters, owner) < 0)
                    reachProblems.Add("the request prefix may be written only from " + urlWriters[0]
                        + " or the TLS fallback that runs from it; found a write at " + apiRel + " line "
                        + w.Line + " inside '" + (owner ?? "no member") + "'");
                // AND EVERY ONE OF THOSE WRITES MUST ACTUALLY RETARGET IT. The
                // prefix is declared with the EMPTY string, which is not null,
                // so a conditional form - `baseUrl ??= ...` - reads as a writer
                // and leaves the previous value standing. R7 and R8 rest on the
                // prefix being what initialisation SET; a writer that may
                // decline to write is not that, and the TLS fallback written
                // that way would go on addressing the host it could not reach.
                // A member that owns a write is not the same property as a write
                // that happens (#342).
                if (w.Kind != "= (simple assignment)")
                    reachProblems.Add("every write to the request prefix must RETARGET it - the field is "
                        + "declared with the empty string, which is not null, so a conditional or compound "
                        + "form can leave the previous value in place while still reading as a writer; found "
                        + w.Kind + " at " + apiRel + " line " + w.Line + " [" + w.Text + "]");
            }
            if (!initWrites)
                reachProblems.Add("ApiClient.Initialize must be one of the request prefix's writers - it is "
                    + "what makes a reply downstream of initialisation at all; writers found: "
                    + (urlWhere.Count == 0 ? "none" : string.Join(" | ", urlWhere.ToArray())));
        }

        // R9 - AND WHO CALLS THOSE WRITERS. One link further up than R8.
        //
        // R8 closes the members that may WRITE the request prefix. Nothing
        // closed who may CALL them: W25c requires the existing
        // ApiClient.Initialize call to SIT inside DoInitialize and does not
        // reject a second one elsewhere, so an ordinary startup refactor could
        // initialise the client from another member with every clause above
        // green. The same gap sits under FfaProbeServerState: it is a permitted
        // member of the staging entry-point set, but it is not itself a staging
        // entry point, so R6 never places ITS callers.
        //
        // The map this case prints is evidence for a reader and is not an
        // assertion; a printed map cannot fail (#342/#431). So the resolved
        // caller set is compared, as a SET and site for site, against a closed
        // set written out here - the shape R6 uses for staging entry points,
        // applied to the writers. The map stays, beside it.
        //
        // TWO SPELLING RULES, and both are load-bearing. A call is searched
        // QUALIFIED across the assembly and BARE only in the file that declares
        // the target, because nine shipped types declare a method called
        // Initialize and six of those calls stand in the very member this set
        // names. And a bare hit behind a '.' is rejected, which is what
        // BareCallSitesIn is for.
        //
        // ONE CALL PER NAMED MEMBER, not merely the right members: a second call
        // added inside DoInitialize would leave the SET equal, and it is a
        // second initialisation either way.
        var callerBound = new Dictionary<string, string[]>(StringComparer.Ordinal);
        callerBound["ApiClient.Initialize"] =
            new[] { pluginRel + " :: private void DoInitialize()" };
        callerBound["ApiClient.ProbeEndpointThenStart"] =
            new[] { apiRel + " :: public static void Initialize(string url)" };
        callerBound["ApiClient.FfaProbeServerState"] =
            new[] { uiRel + " :: private static void MaybeRefreshFfaTab()" };
        // { qualified spelling, bare spelling, the file that DECLARES it }
        string[][] callerTargets = new[]
        {
            new[] { "ApiClient.Initialize",             "Initialize",             apiRel },
            new[] { "ApiClient.ProbeEndpointThenStart", "ProbeEndpointThenStart", apiRel },
            new[] { "ApiClient.FfaProbeServerState",    "FfaProbeServerState",    apiRel }
        };
        var callerMap = new List<string>();
        foreach (string[] t in callerTargets)
        {
            string key = t[0], bare = t[1], home = t[2];
            var resolved = new List<string>();
            foreach (string rel in shippedCs)
            {
                string blanked;
                if (!surfaceBlank.TryGetValue(rel, out blanked)) continue;
                var sites = CallSitesIn(blanked, key);
                if (rel == home) sites.AddRange(BareCallSitesIn(blanked, bare));
                foreach (int at in sites)
                {
                    string owner = EnclosingMemberOf(blanked, at);
                    resolved.Add(rel + " :: " + (owner ?? "(no enclosing member)"));
                    callerMap.Add(key + " at " + rel + " line " + LineOf(blanked, at) + " in "
                        + (owner ?? "(no enclosing member)"));
                }
            }
            string[] wanted = callerBound[key];
            var want = new List<string>(wanted);
            resolved.Sort(StringComparer.Ordinal);
            want.Sort(StringComparer.Ordinal);
            string got = resolved.Count == 0 ? "(nothing)" : string.Join(" | ", resolved.ToArray());
            if (resolved.Count != want.Count
                || string.Join(" | ", resolved.ToArray()) != string.Join(" | ", want.ToArray()))
                reachProblems.Add("every call to '" + key + "' must come from the closed set this argument "
                    + "has placed, one call per named member; wanted " + string.Join(" | ", want.ToArray())
                    + "; found " + got);
        }
        Console.WriteLine("NOTE  W25 permitted-writer callers: "
            + (callerMap.Count == 0 ? "none" : string.Join("; ", callerMap.ToArray())));

        // AND THE PREMISE THAT RULE RESTS ON, CHECKED INSTEAD OF WRITTEN
        // DOWN. Confining the bare search to the declaring file is complete
        // only while no other file can reach one of these members by a bare
        // name, and only while the owner has one name. Two constructs break
        // that: "using static" imports the member itself, and a using ALIAS
        // gives the owner a second name this scan does not search for.
        // Neither was present when the rule was written and a comment said
        // so - a premise nothing re-checks is one the next edit is free to
        // falsify, which is the whole of #351/#434. The price is real and
        // named in the residuals: a legitimate static import anywhere under
        // plugin/ reddens this and has to be answered.
        const string apiType = "ApiClient";
        foreach (string rel in shippedCs)
        {
            string usingView;
            if (!surfaceBlank.TryGetValue(rel, out usingView)) continue;
            foreach (string raw in usingView.Split((char)10))
            {
                string t = raw.Trim();
                if (t.StartsWith("using static", StringComparison.Ordinal))
                    reachProblems.Add(rel + " carries '" + t + "' - a static import can bring a bare "
                        + "member name into a file where this bound searches qualified only, so the "
                        + "caller set would no longer be closed");
                else if (t.StartsWith("using ", StringComparison.Ordinal) && t.IndexOf('=') > 0
                         && t.TrimEnd(';', ' ').EndsWith(apiType, StringComparison.Ordinal))
                    reachProblems.Add(rel + " carries '" + t + "' - an alias gives the writers' owner a "
                        + "second name and this bound searches for one");
            }
        }

        // R2 - the gate flag.
        SurfaceScan initScan = ScanField(shippedCs, surfaceText, surfaceBlank,
            "initialized", pluginRel, "false");
        scanNotes.Add(ScanNote("gate flag", initScan));
        // EVERY scan this case runs, in one line, after the last of them is
        // built. plugin/CustomCosmetics.cs declares `private static bool
        // initialized;` of its own, and under the round-7 build that dropped it
        // from this very scan with no output anywhere - the string
        // "CustomCosmetics" appeared nowhere in the run log - while the failure
        // text named all 91 shipped files.
        Console.WriteLine("NOTE  W25 surface: " + shippedCs.Length + " shipped .cs file(s); "
            + string.Join("; ", scanNotes.ToArray()));
        reachProblems.AddRange(initScan.DeclProblems);
        if (shippedCs.Length != 0 && !initScan.HomeDeclares)
            reachProblems.Add("the initialisation gate flag must be DECLARED in " + pluginRel);
        foreach (FieldWrite w in initScan.Real)
            if (w.Kind != "= (simple assignment)" || w.Rhs != "true")
                reachProblems.Add("every write to the initialisation gate flag must write true, or the tick "
                    + "can fall back below its own gate after a staging attempt; found " + w.Kind
                    + " with right-hand side '" + w.Rhs + "' in " + w.Rel + " line " + w.Line);
        List<string> initElsewhere = RealOutside(initScan, pluginRel);
        if (initElsewhere.Count != 0)
            reachProblems.Add("only " + pluginRel + " may write the initialisation gate flag; found "
                + string.Join(" | ", initElsewhere.ToArray()));
        List<FieldWrite> initHere = RealIn(initScan, pluginRel);
        if (initHere.Count != 1)
            reachProblems.Add("the initialisation gate flag must have exactly one write across the "
                + initScan.Scanned + " shipped file(s) READ by this scan, in ANY spelling; found " + initHere.Count
                + ": " + Describe(initHere));

        string pluginBlank = LoadBlanked(pluginRel);
        int gateAt = -1, tickOpen = -1, tickClose = -1;
        if (pluginBlank == null) reachProblems.Add("cannot read " + pluginRel + " in the code view");
        else
        {
            const string gateLine = "if (!initialized) return;";
            int gates = CountOf(pluginBlank, gateLine);
            if (gates != 1)
                reachProblems.Add("the persistent tick must carry exactly one '" + gateLine
                    + "' - it is the position every staging route is measured against; found " + gates);
            else
            {
                gateAt = pluginBlank.IndexOf(gateLine, StringComparison.Ordinal);
                string tickProblem;
                if (!TryMemberSpanAround(pluginBlank, "private void Update()", gateAt,
                        out tickOpen, out tickClose, out tickProblem))
                    reachProblems.Add(tickProblem);
            }

            int io, ic; string ip;
            if (!TryMemberSpan(pluginBlank, "private void DoInitialize()", out io, out ic, out ip))
                reachProblems.Add(ip);
            else
            {
                string initBody = pluginBlank.Substring(io, ic - io + 1);
                int callAt = initBody.IndexOf("ApiClient.Initialize(", StringComparison.Ordinal);
                if (callAt < 0)
                    reachProblems.Add("DoInitialize must call ApiClient.Initialize - it is the point every "
                        + "staging route has to be downstream of");
                if (initHere.Count == 1)
                {
                    int flagAt = initHere[0].Index;
                    if (flagAt < io || flagAt > ic)
                        reachProblems.Add("the gate flag's one write must live inside DoInitialize, or the tick "
                            + "opens on something other than a completed initialisation; found it at line "
                            + initHere[0].Line);
                    else if (callAt < 0 || (io + callAt) > flagAt)
                        reachProblems.Add("the gate flag must be set AFTER ApiClient.Initialize in DoInitialize, "
                            + "or the tick opens before the thing it is waiting for; ApiClient.Initialize at "
                            + (io + callAt) + ", flag written at " + flagAt);
                }
                // R3, first half: no staging route may be reached from
                // DoInitialize at all - above that call it would precede
                // initialisation, and below it the tick is the route.
                foreach (string entry in stageEntries)
                {
                    int here = CallsToIn(initBody, entry) + CallsToIn(initBody, "ApiClient." + entry);
                    if (here != 0)
                        reachProblems.Add("DoInitialize must not reach a staging entry point (" + entry
                            + "); the route is the persistent tick below its gate, and a call here would run "
                            + "on the initialisation path itself; found " + here);
                }
                if (CallsToIn(initBody, stageCall) != 0)
                    reachProblems.Add("DoInitialize must not stage this key directly");
            }
        }

        // R3, second half, R4 and R6 - where the staging entry points are called
        // from, across the whole assembly, at FILE grain AND at MEMBER grain.
        //
        // THE MEMBER SET IS WHAT ROUND 6 ASKED FOR. The file set says which
        // files may hold a caller; it says nothing about WHERE in them, and the
        // per-file loop below used to skip every file that was not Plugin.cs
        // before it looked at a position at all. So of the ten sites this case's
        // own NOTE prints, seven carried no position constraint: the FFA and 1v2
        // tab refreshers in NativeUI.cs, and five members of ApiClient.cs. A
        // staging call moved out of a tab refresher into a menu member, or added
        // to a sixth ApiClient member, changed no count and no file and stayed
        // green. The set below is written out because it is the CLAIM: these
        // 8 members, and no others, reach a staging entry point. Its price
        // is that it must be edited when a caller legitimately moves; that is
        // the point - the edit is where a reader is told the route changed.
        //
        // BOTH NUMBERS ABOVE ARE DERIVED, NOT TYPED. H2 counts the entries of
        // permittedMembers out of this file's own text and requires each
        // sentence to carry that count, so a ninth member reddens the prose that
        // describes the set. A typed number standing beside derived ones is the
        // one a reader has no way to tell apart (#431).
        //
        // The two ApiClient members that are neither the tick nor a tab
        // refresher are exactly the routes no scan can walk: FfaKickFromLobby is
        // reached through a delegate the menu stores, FfaEnrollResult and
        // HandleResolveProbe from response callbacks. R7 and R8 are what bound
        // those, and the set here is what stops a NEW one appearing unremarked.
        var entryWhere = new List<string>();
        var entryMembers = new List<string>();
        var permittedMembers = new Dictionary<string, string[]>(StringComparer.Ordinal);
        permittedMembers[pluginRel] = new[] { "private void Update()" };
        permittedMembers[uiRel] = new[] { "private static void MaybeRefreshOvtTab()",
                                          "private static void MaybeRefreshFfaTab()" };
        permittedMembers[apiRel] = new[]
        {
            "public static void UpdateTeamQueuePoll(string steamId)",
            "private static void FfaEnrollResult(bool ok, string resp, string intendedLobbyId, bool wasRecovery)",
            "public static void FfaProbeServerState()",
            "private void HandleResolveProbe(string status, string resp, string sid)",
            "public static void FfaKickFromLobby(string targetSteamId)"
        };
        foreach (string rel in shippedCs)
        {
            string blanked;
            if (!surfaceBlank.TryGetValue(rel, out blanked)) continue;
            var sites = new List<int>();
            foreach (string entry in stageEntries)
            {
                sites.AddRange(CallSitesIn(blanked, "ApiClient." + entry));
                if (rel == apiRel) sites.AddRange(CallSitesIn(blanked, entry));
            }
            if (sites.Count == 0) continue;
            entryWhere.Add(rel + " x" + sites.Count);
            if (rel != apiRel && rel != uiRel && rel != pluginRel)
                reachProblems.Add("only " + apiRel + ", " + uiRel + " and " + pluginRel + " may reach a "
                    + "staging entry point - every other caller is a route this argument has not shown to "
                    + "run after initialisation; found " + sites.Count + " in " + rel);
            string[] allowedHere;
            bool known = permittedMembers.TryGetValue(rel, out allowedHere);
            foreach (int at in sites)
            {
                string owner = EnclosingMemberOf(blanked, at);
                entryMembers.Add(rel + ":" + LineOf(blanked, at) + " in "
                    + (owner ?? "(no enclosing member)"));
                if (!known) continue;   // the file clause above already reported it
                if (owner == null || Array.IndexOf(allowedHere, owner) < 0)
                    reachProblems.Add("every staging entry-point call must sit inside a member this argument "
                        + "has placed; the one at " + rel + " line " + LineOf(blanked, at) + " is inside '"
                        + (owner ?? "no member") + "', which is not one of: "
                        + string.Join(" / ", allowedHere));
            }
            if (rel != pluginRel) continue;
            foreach (int at in sites)
            {
                if (gateAt < 0 || tickOpen < 0) break;
                if (at < tickOpen || at > tickClose)
                    reachProblems.Add("every staging call in " + pluginRel + " must live inside the persistent "
                        + "tick; one at line " + LineOf(blanked, at) + " does not, so it is reached by a route "
                        + "the gate does not stand in front of");
                else if (at < gateAt)
                    reachProblems.Add("every staging call in the persistent tick must sit BELOW "
                        + "'if (!initialized) return;'; one at line " + LineOf(blanked, at)
                        + " sits above it, so it can run before DoInitialize has called ApiClient.Initialize");
            }
        }
        Console.WriteLine("NOTE  W25 staging routes: merges " + stageMap + "; entry-point callers "
            + (entryWhere.Count == 0 ? "nowhere" : string.Join(" | ", entryWhere.ToArray())));
        Console.WriteLine("NOTE  W25 entry-point call sites, by enclosing member: "
            + (entryMembers.Count == 0 ? "none" : string.Join("; ", entryMembers.ToArray())));

        // R5 - the one route that leaves ApiClient.cs, pinned link by link to
        // the same gate. Each link is "exactly this many call sites, in exactly
        // this file, inside exactly this member", so a new caller anywhere else
        // reddens rather than quietly extending the route.
        string uiBlank = LoadBlanked(uiRel);
        string compBlank = LoadBlanked(compRel);
        if (uiBlank == null) reachProblems.Add("cannot read " + uiRel + " in the code view");
        if (compBlank == null) reachProblems.Add("cannot read " + compRel + " in the code view");
        if (uiBlank != null && compBlank != null && pluginBlank != null)
        {
            int to, tc; string tp;
            if (!TryMemberSpan(uiBlank, "public static void Tick()", out to, out tc, out tp))
                reachProblems.Add(uiRel + ": " + tp);
            else
                foreach (string tab in new[] { "MaybeRefreshOvtTab", "MaybeRefreshFfaTab" })
                {
                    var sites = CallSitesIn(uiBlank, tab);
                    if (sites.Count != 1 || sites[0] < to || sites[0] > tc)
                        reachProblems.Add(tab + " must be called exactly once, from inside " + uiRel
                            + "'s Tick - that is what puts the menu's queue polling behind the same gate; found "
                            + sites.Count + " site(s)");
                    foreach (string rel in shippedCs)
                    {
                        string b2;
                        if (rel == uiRel || !surfaceBlank.TryGetValue(rel, out b2)) continue;
                        if (CallsToIn(b2, tab) + CallsToIn(b2, "NativeUI." + tab) != 0)
                            reachProblems.Add(tab + " is reached from " + rel + " as well, which is a route "
                                + "outside the one this argument walks");
                    }
                }

            int co, cc; string cp2;
            if (!TryMemberSpan(compBlank, "public static void Tick()", out co, out cc, out cp2))
                reachProblems.Add(compRel + ": " + cp2);
            else
            {
                var uiTickSites = new List<string>();
                int inComp = 0;
                foreach (string rel in shippedCs)
                {
                    string b2;
                    if (!surfaceBlank.TryGetValue(rel, out b2)) continue;
                    var sites = CallSitesIn(b2, "NativeUI.Tick");
                    if (sites.Count == 0) continue;
                    uiTickSites.Add(rel + " x" + sites.Count);
                    if (rel != compRel) continue;
                    foreach (int at in sites) if (at >= co && at <= cc) inComp++;
                }
                if (uiTickSites.Count != 1 || inComp != 1)
                    reachProblems.Add("NativeUI.Tick must be called exactly once in the assembly, from inside "
                        + compRel + "'s Tick; found " + string.Join(" | ", uiTickSites.ToArray()));
            }

            var compTickSites = new List<string>();
            int compInTick = 0;
            foreach (string rel in shippedCs)
            {
                string b2;
                if (!surfaceBlank.TryGetValue(rel, out b2)) continue;
                var sites = CallSitesIn(b2, "CompetitiveUI.Tick");
                if (sites.Count == 0) continue;
                compTickSites.Add(rel + " x" + sites.Count);
                if (rel != pluginRel || gateAt < 0 || tickOpen < 0) continue;
                foreach (int at in sites)
                    if (at > gateAt && at >= tickOpen && at <= tickClose) compInTick++;
            }
            if (compTickSites.Count != 1 || compInTick != 1)
                reachProblems.Add("CompetitiveUI.Tick must be called exactly once in the assembly, from the "
                    + "persistent tick below its gate - that is the last link that puts the menu route "
                    + "downstream of initialisation; found " + string.Join(" | ", compTickSites.ToArray()));
        }

        Check("W25 Wiring_TheGuardsTermsAreSettledBeforeTheFirstStagingAttempt",
            reachProblems.Count == 0,
            string.Join("; ", reachProblems.ToArray()));

        // W25b - the one patch site is inside Awake's Harmony bootstrap block, the
        // span that ends with the sibling capability being staged "before anything
        // can connect". No mutant of its own: wire-reach is the group's.
        CheckAnchorInSpan("W25b Wiring_ThePatchLoopIsInsideAwakesHarmonyBootstrap",
            "plugin/Plugin.cs",
            "                HarmonyInstance = new Harmony(ModId);",
            "            try { PoisonSync.StageCapability(\"Awake\"); PoisonSync.Hook(); } catch { }",
            "HarmonyInstance.CreateClassProcessor(type).Patch();");

        // W25c - and the prerequisite for every staging call is in the DEFERRED
        // initialisation, which the tick reaches after startup, not in Awake. W18
        // asserts what sits above this call; this asserts where the call lives.
        CheckAnchorInMember("W25c Wiring_TheStagingPrerequisiteIsInsideTheDeferredInit",
            "plugin/Plugin.cs",
            "private void DoInitialize()",
            "ApiClient.Initialize(Plugin.ApiBaseUrl.Value);");

        // W26 - THE ONE UNTESTED STEP IS DISCLOSED IN BOTH SHIPPED FILES, IN THE
        // SAME WORDS. RED under "wire-lifecycledrop", which removes it from the
        // seam; green under "wire-logquote", which moves another line entirely.
        //
        // The reachability argument has one link no test holds: Awake runs
        // before the first tick that can reach DoInitialize. That is Unity's
        // lifecycle contract, not a fact about this text. The patches file
        // recorded it as a premise; the seam stated the same ordering and then
        // said W25 pinned the premises, which W25 expressly does not do for this
        // one. A shipped comment that presents an untested step as pinned is a
        // claim about the whole state space written from the one state the
        // author had in mind (#351/#434) - and a reader who takes it at face
        // value stops looking for the thing that would falsify it.
        //
        // The sentences are pinned rather than paraphrased, and both files carry
        // them EXACTLY ONCE each: a disclosure in one file and not the other is
        // how the two accounts drifted apart in the first place.
        string[] premiseNeedles = new[]
        {
            "Awake runs before the first tick that can reach DoInitialize.",
            "W25 pins the greppable premises and not this one."
        };
        var premiseProblems = new List<string>();
        foreach (string rel in new[] { "plugin/ProximityVictimPatches.cs", "plugin/ProximityVictimSeam.cs" })
        {
            // The PROSE view: the sentence being asserted IS a comment.
            string text = LoadSource(rel);
            if (text == null)
            {
                premiseProblems.Add("cannot read " + rel + " - an unread file in this surface is a failure, "
                    + "not a skip");
                continue;
            }
            foreach (string needle in premiseNeedles)
            {
                int n = CountOf(text, needle);
                if (n != 1)
                    premiseProblems.Add(rel + " must carry the untested-step disclosure exactly once ('"
                        + needle + "'); found " + n);
            }
        }
        Check("W26 Wiring_TheUntestedLifecycleStepIsDisclosedInBothShippedFiles",
            premiseProblems.Count == 0,
            string.Join("; ", premiseProblems.ToArray()));

        // H1 - THE ROUND'S SEVERITY CENSUS IS DERIVED FROM THE FINDING BODIES.
        // RED under "wire-severitycensus", which changes ONE body's SEVERITY
        // marker and leaves the declared line alone - the NOTE line below then
        // prints the MOVED census, which is the demonstration itself. W25 is the
        // inert twin and stays green: it reads no findings file, so the row
        // cannot be read as "anything in the tree moved".
        //
        // The round-6 log's header said "two MEDIUM, five LOW" while its own
        // seven bodies read three MEDIUM and four LOW. Every NUMBER in that
        // header was counted from the run; the severity line was typed, and a
        // typed number beside derived ones is the one a reader has no way to
        // tell apart (#431). The fix is not a more careful typist: the bodies
        // live in round-findings.md with an explicit SEVERITY: marker each, the
        // census line is COMPUTED from those markers, and the log's header
        // quotes the computed line. This case is what makes the declared line
        // unable to disagree with the bodies.
        //
        // AND AN UNMARKED BODY IS A RED FAILURE, NEVER A SKIP. Deriving the
        // total FROM the markers made a body written without one invisible to
        // both numbers: the census did not move, this case stayed green, and the
        // body left the round without anything saying so. The bodies are now
        // counted a SECOND time, by their own heading, by a counter that knows
        // nothing about markers, and the two counts must agree - the body that
        // has no marker is NAMED. RED under "wire-bodynomarker", which adds a
        // body with no marker; GREEN under "wire-bodymarked", which adds one
        // with its marker and moves the declared census with it.
        const string findRel = "tools/tests/bug389-seam/round-findings.md";
        string findText = LoadSource(findRel);
        var censusProblems = new List<string>();
        if (findText == null)
            censusProblems.Add("cannot read " + findRel + " - the finding bodies are the census's only source, "
                + "so an unread file is a failure, not a skip");
        else
        {
            // THE MARKER COUNT COMES BACK FROM THE CENSUS ITSELF. The first
            // cut of this clause counted the markers a second time here,
            // with a second copy of the rule for what a marker looks like -
            // two counters of one thing, which is the defect N5 closed one
            // screen further up and #342 names outright. The BODIES are
            // still counted off different evidence, which is the half that
            // has to stay independent.
            int markers;
            string derived = DerivedCensus(findText, out markers);
            List<string> unmarked;
            int bodies = FindingBodies(findText, out unmarked);
            if (unmarked.Count != 0)
                censusProblems.Add("every finding body must carry its own SEVERITY marker, or it counts in "
                    + "no census and leaves the round unrecorded; these carry none: "
                    + string.Join(" | ", unmarked.ToArray()));
            if (bodies != markers)
                censusProblems.Add("the finding BODIES and the SEVERITY markers must be equal in number - "
                    + "they are counted off different evidence precisely so they can disagree; " + bodies
                    + " body/bodies, " + markers + " marker(s)");
            Console.WriteLine("NOTE  H1 finding bodies: " + bodies + " heading(s), " + markers + " marker(s), "
                + unmarked.Count + " unmarked");
            int declared = CountOf(findText, "CENSUS: ");
            if (declared != 1)
                censusProblems.Add(findRel + " must declare the census exactly once on a 'CENSUS: ' line; found "
                    + declared);
            else
            {
                int at = findText.IndexOf("CENSUS: ", StringComparison.Ordinal) + "CENSUS: ".Length;
                int end = findText.IndexOf((char)10, at);
                if (end < 0) end = findText.Length;
                string printed = findText.Substring(at, end - at).Trim();
                if (printed != derived)
                    censusProblems.Add("the declared census must be the one the bodies produce - the header "
                        + "line a reader sees is computed, never typed; bodies say '" + derived
                        + "', the file declares '" + printed + "'");
            }
            Console.WriteLine("NOTE  H1 severity census, derived from the bodies: " + derived);
        }
        Check("H1 Report_TheSeverityCensusIsDerivedFromTheFindingBodies",
            censusProblems.Count == 0,
            string.Join("; ", censusProblems.ToArray()));

        // W27 - A SHIPPED FILE IS BLANKED IN EXACTLY ONE PLACE, AND THAT PLACE
        // IS THE CACHE. RED under "wire-uncachedview", which puts a re-blank
        // back inside CountOnCodeLines; GREEN under "wire-viewinert", an edit of
        // comparable size in this same file that touches no blanking call.
        //
        // The deletion register named "one cached CODE view read by every code
        // counter" as the replacement for the three-views defect. LoadBlanked
        // did cache one - and CountOnCodeLines, CallsTo, AttributesOf and
        // WritesTo each blanked raw text again, as did the FFA count, the W25
        // surface map and the MarkAttached tag count. Seven blanking sites and
        // one cache. Nothing was WRONG at that tip, because blanking is
        // deterministic and every one of those callers held a .cs file; the
        // CLAIM was wrong, and an absence bound whose named replacement is not
        // actually present is a register a reader cannot use (#302/#351). The
        // one case where the two answers genuinely differ is a file that is not
        // C#: LoadBlanked returns it unchanged, a direct re-blank would run the
        // C# blanker over it and eat the line W10 reads.
        //
        // This case is written against the CALL, not against the count of the
        // word: a declaration is not a call, and CallSitesIn tells them apart.
        const string progRel = "tools/tests/bug389-seam/Program.cs";
        string progCode = LoadBlanked(progRel);
        var viewProblems = new List<string>();
        if (progCode == null)
            viewProblems.Add("cannot read " + progRel + " in the code view - an unread file is a failure, "
                + "not a skip");
        else
        {
            // SPELLED IN HALVES, because this case searches the file it is
            // written in: a signature written whole here would be found here as
            // well as at its declaration, the span would resolve to neither, and
            // the case could never pass. The same discipline W24's needles use.
            string blankSig = "private static string " + "LoadBlanked(string relative)";
            var blankSites = CallSitesIn(progCode, "BlankComments");
            int bo, bc; string bp;
            if (!TryMemberSpan(progCode, blankSig, out bo, out bc, out bp)) viewProblems.Add(bp);
            else
            {
                var outside = new List<string>();
                foreach (int at in blankSites)
                    if (at < bo || at > bc) outside.Add("line " + LineOf(progCode, at));
                if (blankSites.Count != 1 || outside.Count != 0)
                    viewProblems.Add("a shipped file may be blanked in exactly one place - the cache in '"
                        + blankSig + "' - or 'one cached CODE view read by every code counter' is a claim "
                        + "the code does not implement; found " + blankSites.Count + " call site(s), "
                        + (outside.Count == 0 ? "none" : string.Join(", ", outside.ToArray()))
                        + " outside it");
            }
            Console.WriteLine("NOTE  W27 BlankComments call sites: " + blankSites.Count);
        }
        Check("W27 Report_TheCodeViewIsBuiltInExactlyOnePlace",
            viewProblems.Count == 0,
            string.Join("; ", viewProblems.ToArray()));

        // W28 - THE SEVERITY MARKER IS SPELLED IN EXACTLY ONE PLACE. RED
        // under "wire-secondmarker", which plants a second spelling of it;
        // GREEN under "wire-markerinert".
        //
        // H1 holds two counts of the finding bodies against each other and
        // that is the point of it - but only while they are counted off
        // DIFFERENT evidence. The first cut of this round counted the
        // markers twice, from two copies of the rule for what a marker looks
        // like, so a change to one copy would have made the clause fire on a
        // file that was correct or pass one that was not. The rule lives in
        // SeverityMarker now, and this holds that literal to a single
        // spelling in the harness.
        //
        // ITS NEEDLE IS BUILT IN PIECES, for the same reason W27's is: this
        // case is written in the file it counts, so a needle spelled whole
        // here would be one of the occurrences it counts and the case could
        // never pass (#342).
        var markerProblems = new List<string>();
        if (progCode == null)
            markerProblems.Add("cannot read " + progRel + " in the code view - an unread file is a "
                + "failure, not a skip");
        else
        {
            string quote = ((char)34).ToString();
            string markerLiteral = quote + "SEVER" + "ITY:" + quote;
            int spellings = CountOf(progCode, markerLiteral);
            if (spellings != 1)
                markerProblems.Add("the severity marker must be spelled in exactly one place - two "
                    + "copies of the rule are two counters of one thing, and H1 holds its two counts "
                    + "to each other on the premise that they are taken off different evidence; found "
                    + spellings + " literal spelling(s) in " + progRel);
            Console.WriteLine("NOTE  W28 severity-marker literals: " + spellings);
        }
        Check("W28 Report_TheSeverityMarkerIsSpelledInExactlyOnePlace",
            markerProblems.Count == 0,
            string.Join("; ", markerProblems.ToArray()));

        // H2 - EVERY PROSE COUNT IS DERIVED FROM THE ARTIFACT IT DESCRIBES.
        // RED under "wire-prosecount", which adds a member to permittedMembers
        // so the route sentences no longer carry the set's size, and under
        // "wire-streakrow", which adds a round to the streak list so the streak
        // line no longer carries its length. GREEN under "wire-proseinert".
        //
        // Four prose counts disagreed with the numbers their own artifacts
        // derive: a blind-control lead saying twelve rows over a body of
        // fourteen, another calling six mutant variants "six new rows" over
        // thirteen assertion rows, a route comment naming seven permitted
        // members over a dictionary of eight, and a streak called both sixth and
        // fifth. Correcting the four numbers is not the closure - they would
        // drift again the next time the artifact moved. This is the same class
        // H1 already closed for the severity census (#431), applied to the other
        // typed numbers: the number is READ OUT of the thing it counts, and the
        // sentence has to carry that number.
        //
        // Both counts are taken from the TEXT under test, never from the running
        // harness's own values: a mutant edits what the case READS, so a count
        // taken from the compiled dictionary would move with neither and the
        // check could not fail.
        var proseProblems = new List<string>();
        if (progCode == null || progText == null)
            proseProblems.Add("cannot read " + progRel + " in both views - an unread file is a failure, "
                + "not a skip");
        else
        {
            // THE SPAN IS THE WHOLE DECLARATION, not the first assignment
            // to the nearest brace-shaped line. This clause first opened at
            // the pluginRel assignment and closed at the next "\n        };",
            // which is the apiRel block's closer only because the other two
            // assignments happen to be one-liners and apiRel's happens to
            // come last. Reorder them, or add a fourth file's entries after
            // that block, and the size is read out of a span that no longer
            // holds the set while the sentences still agree with it - a
            // check that cannot fail for the case it exists to catch
            // (#342/#431). It opens at the DECLARATION and closes at the
            // first statement after the assignments, and the number of
            // assignments inside the span must equal the number in the whole
            // file, so one written anywhere else is named instead of missed.
            const string mapOpen = "var permittedMembers = new Dictionary<string, string[]>";
            const string mapClose = "foreach (string rel in shippedCs)";
            int mo = progCode.IndexOf(mapOpen, StringComparison.Ordinal);
            int mc = mo < 0 ? -1 : progCode.IndexOf(mapClose, mo, StringComparison.Ordinal);
            if (mo < 0 || mc < 0)
                proseProblems.Add("could not bound the permitted-member set in " + progRel
                    + " - the count the route sentences carry is read out of it");
            else
            {
                string mapSpan = progCode.Substring(mo, mc - mo);
                // SPELLED IN HALVES. Written whole this needle is itself an
                // occurrence of what it counts, in the file it counts over,
                // so the file read four assignments where three exist and
                // the clause reddened on its own literal - a reading that
                // finds its own needle (#342), and the same discipline W27
                // and W28 already use one screen further down.
                const string assign = "permittedMembers" + "[";
                int assignHere = CountOf(mapSpan, assign);
                int assignAll = CountOf(progCode, assign);
                if (assignHere != assignAll)
                    proseProblems.Add("every assignment to the permitted-member set must stand in the "
                        + "block its size is read from, or the size is read off part of the set; the "
                        + "file carries " + assignAll + " and the block holds " + assignHere);
                // Each entry is a member SIGNATURE, so each ends with the close
                // of its parameter list immediately before the closing quote.
                int members = CountOf(mapSpan, ")\"");
                // The SENTENCES are comments, so they are counted over the PROSE
                // view; the SET is code, so its size is counted over the CODE
                // view, where a signature quoted in a comment declares nothing.
                foreach (string sentence in new[] {
                    "one of the " + members + " named below",
                    members + " members, and no others, reach a staging entry point." })
                {
                    int n = CountOf(progText, sentence);
                    if (n != 1)
                        proseProblems.Add("the route comment must carry the permitted-member set's own size ("
                            + members + "); the sentence '" + sentence + "' occurs " + n + " time(s)");
                }
                Console.WriteLine("NOTE  H2 permitted members, counted from the set: " + members);
            }
        }
        if (findText == null)
            proseProblems.Add("cannot read " + findRel + " - the streak list is the streak count's only "
                + "source, so an unread file is a failure, not a skip");
        else
        {
            int rounds = LinesOpeningWith(findText, "STREAK-ROUND:");
            int streakLines = LinesOpeningWith(findText, "STREAK: ");
            string want = "STREAK: " + rounds + " gate verdicts";
            if (streakLines != 1)
                proseProblems.Add(findRel + " must declare the streak exactly once on a 'STREAK: ' line; found "
                    + streakLines);
            else if (LinesOpeningWith(findText, want) != 1)
                proseProblems.Add("the declared streak must be the length of the list above it - the ordinal "
                    + "was given as both sixth and fifth because it was typed; the list holds " + rounds
                    + " round(s), so the line must open '" + want + "'");
            Console.WriteLine("NOTE  H2 selection-method streak, counted from the list: " + rounds
                + " gate verdict(s)");
        }
        Check("H2 Report_EveryProseCountIsDerivedFromItsOwnArtifact",
            proseProblems.Count == 0,
            string.Join("; ", proseProblems.ToArray()));

        // H3 - THE CLOSURE TABLE IS IN THE SOURCE TREE AND PROMISES THE PATHS
        // THAT WERE PUBLISHED. RED under "wire-closuresmissing", which removes
        // the promised repository path from it; GREEN under "wire-closuresinert".
        //
        // The round-7 closure table promised an identical copy at
        // ai-collab/bugs/R7-CLOSURES.md "so the archived brief is reproducible",
        // and a pin-only read found neither that file nor the directory: the
        // whole ai-collab tree is gitignored, so it never reached the pin, and
        // B19 read NOT MET on that alone. The promise was made by a document
        // that lived only where it could not travel.
        //
        // What makes it travel is being TRACKED. The canonical copy is this
        // file, beside the harness it describes, so every clone and every pin
        // built from the tip carries it by construction rather than by somebody
        // remembering to copy it. The two published copies are named IN it, and
        // this case holds it to naming them.
        const string closRel = "tools/tests/bug389-seam/R8-CLOSURES.md";
        string closText = LoadSource(closRel);
        var closProblems = new List<string>();
        if (closText == null)
            closProblems.Add("cannot read " + closRel + " - the closure table is part of the round's brief, "
                + "so an unread file is a failure, not a skip");
        else
            foreach (string needle in new[] { "ai-collab/bugs/BUG389-R8-CLOSURES.md",
                                              "REVIEW-INPUT/R8-CLOSURES.md",
                                              "tools/tests/bug389-seam/R8-CLOSURES.md" })
            {
                int n = CountOf(closText, needle);
                if (n != 1)
                    closProblems.Add(closRel + " must name the published copy '" + needle
                        + "' exactly once - a promise a reader cannot resolve is what B19 read NOT MET; found "
                        + n);
            }
        Check("H3 Report_TheClosureTableTravelsWithTheTipItDescribes",
            closProblems.Count == 0,
            string.Join("; ", closProblems.ToArray()));

        Console.WriteLine("=== passed=" + _passed + " failed=" + _failed + " ===");
        return _failed == 0 ? 0 : 1;
    }
}
