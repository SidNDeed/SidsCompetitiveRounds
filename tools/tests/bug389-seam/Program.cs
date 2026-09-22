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
//   wiring   wire-pathswap:   D6 must FAIL;  D4 and D5 controls must PASS
//   wiring   wire-paththrew:  D6 must FAIL;  D4 and D5 controls must PASS
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
        internal string Text;       // the whole source line, whitespace-collapsed
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

    /// <summary>True when the offset sits on a line whose first non-space
    /// characters are "//" - the same rule CountOnCodeLines uses, so prose and
    /// doc comments naming a field are never read as writes to it.</summary>
    private static bool OnCommentLine(string text, int index)
    {
        int i = LineStartAt(text, index);
        while (i < text.Length && (text[i] == ' ' || text[i] == '\t')) i++;
        return i + 1 < text.Length && text[i] == '/' && text[i + 1] == '/';
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
    /// next to the name and none of them writes anything.</summary>
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
        int b = SkipWsBack(text, at - 1);
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
        string last = words[words.Length - 1];
        bool typeLast = last == "int" || last == "bool" || last == "string" || last == "long"
            || last == "float" || last == "double" || last == "byte" || last == "short"
            || last == "uint" || last == "ulong" || last == "char" || last == "object" || last == "var";
        return modifier && typeLast;
    }

    /// <summary>Every WRITE to one field in one text, in any spelling.</summary>
    private static List<FieldWrite> WritesTo(string text, string field)
    {
        var found = new List<FieldWrite>();
        if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(field)) return found;
        int i = 0;
        while (true)
        {
            int at = text.IndexOf(field, i, StringComparison.Ordinal);
            if (at < 0) return found;
            i = at + field.Length;
            if (at > 0 && IsIdentChar(text[at - 1])) continue;
            int after = at + field.Length;
            if (after < text.Length && IsIdentChar(text[after])) continue;
            if (OnCommentLine(text, at)) continue;
            string rhs;
            string kind = ClassifyWrite(text, at, after, out rhs);
            if (kind == null) continue;
            var w = new FieldWrite();
            w.Index = at;
            w.Line = LineOf(text, at);
            w.Kind = kind;
            w.Rhs = rhs;
            w.Declaration = IsDeclarationSite(text, at);
            w.Text = LineTextAt(text, at);
            found.Add(w);
        }
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
    /// assignment count.</summary>
    private static int CallsTo(string text, string name)
    {
        if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(name)) return 0;
        int n = 0, i = 0;
        while (true)
        {
            int at = text.IndexOf(name, i, StringComparison.Ordinal);
            if (at < 0) return n;
            i = at + name.Length;
            if (at > 0 && IsIdentChar(text[at - 1])) continue;
            if (OnCommentLine(text, at)) continue;
            int f = SkipWs(text, at + name.Length);
            if (f < text.Length && text[f] == '(') n++;
        }
    }

    /// <summary>Attribute applications [Name] or [Name(...)], likewise
    /// whitespace-tolerant.</summary>
    private static int AttributesOf(string text, string name)
    {
        if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(name)) return 0;
        int n = 0, i = 0;
        while (true)
        {
            int at = text.IndexOf(name, i, StringComparison.Ordinal);
            if (at < 0) return n;
            i = at + name.Length;
            if (at > 0 && IsIdentChar(text[at - 1])) continue;
            int after = at + name.Length;
            if (after < text.Length && IsIdentChar(text[after])) continue;
            if (OnCommentLine(text, at)) continue;
            int b = SkipWsBack(text, at - 1);
            if (b < 0 || text[b] != '[') continue;
            int f = SkipWs(text, after);
            if (f < text.Length && (text[f] == ']' || text[f] == '(')) n++;
        }
    }

    /// <summary>The offsets of one member's body, for a case that has to ask
    /// WHERE a site is rather than only how many there are.</summary>
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
        string text = LoadSource(relative);
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
            // THE SURFACE IS EVERY SHIPPED C# FILE THIS HARNESS READS, not the two
            // that happen to carry the fields today. "The count has one writer" is a
            // statement about the ASSEMBLY: both fields are private now, but nothing
            // here asserts they stay private, and an accessibility widened by one
            // word would put a second writer in a file a two-file scan never opens -
            // the same shape as the spelling bound this case is being fixed for
            // (#432). Only ProximityVictimPatches.cs may carry the one write, so a
            // hit anywhere else is reported with its file. An unread file is a
            // FAILURE, never a skip.
            //
            // EmojiSprites.cs is deliberately NOT on this list and must not be added
            // without re-reading it: it declares an unrelated `_attached` of its own,
            // a List<Attachment>, whose initialiser would be counted as a write to a
            // field it has nothing to do with. A scan that is wrong about WHICH field
            // it is reading is the same class of defect as one bound to a spelling.
            string[] shippedCs = new string[] {
                "plugin/ProximityVictimPatches.cs",
                "plugin/ProximityVictimSeam.cs",
                "plugin/Plugin.cs",
                "plugin/ApiClient.cs",
                "plugin/PerfPatches.cs",
                "plugin/SpectatorSession.cs",
                "plugin/RoomActors.cs",
            };
            const string attachHome = "plugin/ProximityVictimPatches.cs";
            var realAttach = new List<FieldWrite>();
            var attachElsewhere = new List<string>();
            int realWithdraw = 0;
            foreach (string rel in shippedCs)
            {
                string text = LoadSource(rel);
                if (text == null)
                {
                    reachProblems.Add("cannot read " + rel + " - an unread file is a failure, not a skip");
                    continue;
                }
                foreach (FieldWrite w in WritesTo(text, "_attached"))
                {
                    if (w.Declaration)
                    {
                        if (w.Rhs != "0")
                            reachProblems.Add("a declaration initialiser for the attachment count must start it "
                                + "at 0; found '" + w.Rhs + "' in " + rel + " line " + w.Line);
                        continue;
                    }
                    if (rel == attachHome) realAttach.Add(w);
                    else attachElsewhere.Add(rel + " line " + w.Line + " " + w.Kind + " [" + w.Text + "]");
                }
                foreach (FieldWrite w in WritesTo(text, "_withdrawn"))
                {
                    if (w.Declaration)
                    {
                        if (w.Rhs != "false")
                            reachProblems.Add("a declaration initialiser for the withdrawal latch must start it "
                                + "false; found '" + w.Rhs + "' in " + rel + " line " + w.Line);
                        continue;
                    }
                    realWithdraw++;
                    if (w.Kind != "= (simple assignment)" || w.Rhs != "true")
                        reachProblems.Add("every write to the withdrawal latch must write true - ONE-WAY is the "
                            + "premise here, not the number of writers, and W23 owns the separate question of "
                            + "whether StageInto makes one; found " + w.Kind + " with right-hand side '" + w.Rhs
                            + "' in " + rel + " line " + w.Line);
                }
            }
            if (attachElsewhere.Count != 0)
                reachProblems.Add("only " + attachHome + " may write the attachment count; found "
                    + string.Join(" | ", attachElsewhere.ToArray()));
            if (realAttach.Count != 1)
                reachProblems.Add("the attachment count must have exactly one write in the shipped files, in ANY "
                    + "spelling; found " + realAttach.Count + " in " + attachHome + ": " + Describe(realAttach));
            else
            {
                FieldWrite w = realAttach[0];
                if (!IsMonotoneWrite(w))
                    reachProblems.Add("that write must be MONOTONE - an increment, or += a non-negative integer "
                        + "literal - or the count can fall back below the required three after a staging attempt "
                        + "has already declined; found " + w.Kind + " at line " + w.Line + " [" + w.Text + "]");
                int mOpen, mClose; string mProblem;
                if (!TryMemberSpan(patchesText, "internal static void MarkAttached(string which)",
                        out mOpen, out mClose, out mProblem))
                    reachProblems.Add(mProblem);
                else if (w.Index < mOpen || w.Index > mClose)
                    reachProblems.Add("the one write must live inside MarkAttached - a write anywhere else is how "
                        + "the count stops being the patch loop's alone, and a decline stops being final; found it "
                        + "at line " + w.Line + " [" + w.Text + "]");
            }
            if (realWithdraw < 1)
                reachProblems.Add("the withdrawal latch must have at least one write, or this premise is vacuous");

            int callers = CallsTo(patchesText, "ProximityVictimGate.MarkAttached");
            if (callers != 3)
                reachProblems.Add("MarkAttached must be called from exactly three sites; found " + callers);
            int cleanups = AttributesOf(patchesText, "HarmonyCleanup");
            if (cleanups != 3)
                reachProblems.Add("and those sites must be Harmony cleanup callbacks, which run inside the "
                    + "patch loop; found " + cleanups + " cleanup attribute(s)");
        }
        if (pluginText == null) reachProblems.Add("cannot read plugin/Plugin.cs");
        else
        {
            int patchSites = CallsTo(pluginText, "CreateClassProcessor");
            if (patchSites != 1)
                reachProblems.Add("the assembly must have exactly one Harmony patch site, or the attachment "
                    + "count can still move after this one has run; found " + patchSites);
            // PatchAll is the OTHER way this assembly could attach a patch, and
            // it would attach it outside the one loop the premise names. It is
            // named in three comments here and called nowhere; a call is what
            // this counts.
            int patchAll = CallsTo(pluginText, "PatchAll");
            if (patchAll != 0)
                reachProblems.Add("and no PatchAll call may stand beside it, or patches attach from a second "
                    + "site the reachability argument does not bound; found " + patchAll);
            var disabledWrites = WritesTo(pluginText, "modDisabled");
            int realDisabled = 0;
            foreach (FieldWrite w in disabledWrites)
            {
                if (w.Declaration)
                {
                    if (w.Rhs != "false")
                        reachProblems.Add("the disabled flag's declaration must start it false; found '"
                            + w.Rhs + "' at line " + w.Line);
                    continue;
                }
                realDisabled++;
                if (w.Kind != "= (simple assignment)" || w.Rhs != "true")
                    reachProblems.Add("every write to the disabled flag must write true, for the same reason; "
                        + "found " + w.Kind + " with right-hand side '" + w.Rhs + "' at line " + w.Line);
            }
            if (realDisabled < 1)
                reachProblems.Add("the disabled flag must have at least one write, or this premise is vacuous");
        }
        if (apiText == null) reachProblems.Add("cannot read plugin/ApiClient.cs");
        else
        {
            int stageSites = CallsTo(apiText, "ProximityVictimGate.StageInto");
            if (stageSites != 3)
                reachProblems.Add("the three pre-join merges are the only places this key is staged, and all "
                    + "three are downstream of ApiClient.Initialize; found " + stageSites);
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

        Console.WriteLine("=== passed=" + _passed + " failed=" + _failed + " ===");
        return _failed == 0 ? 0 : 1;
    }
}
