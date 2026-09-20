using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;

namespace CompetitiveRounds
{
    /// <summary>
    /// Removes this machine's identity from a log bundle before the bundle
    /// leaves the process.
    ///
    /// Deliberately free of Unity, Photon, BepInEx and I18n so the rules can
    /// be EXECUTED by a plain console harness rather than asserted about as
    /// source text (the H2HRules precedent). Everything the caller supplies —
    /// the account name and the profile directory — is a parameter on the
    /// testable overload, so the tests do not depend on who is logged in.
    ///
    /// Two things are removed, and they are separate passes because they fail
    /// in different directions:
    ///
    ///  * PATHS. Every path through a `Users` directory, and the real profile
    ///    directory when it is somewhere else entirely. The whole PREFIX goes,
    ///    up to and including the account segment; the remainder of the path
    ///    is kept, because `&lt;userprofile&gt;\AppData\LocalLow\...` still tells a
    ///    reader which file produced a line while naming nobody. The pattern
    ///    is written against `Users&lt;sep&gt;&lt;anything&gt;` rather than against this
    ///    machine's own directory so that a second account's path in the same
    ///    log is scrubbed too.
    ///  * THE ACCOUNT NAME on its own, in running text, with nothing path- or
    ///    address-shaped around it.
    ///
    /// WHAT "LOCAL PATHS" DOES NOT MEAN (Codex r1 MEDIUM, this class's three
    /// findings). The old wording invited the reading "any local path is
    /// removed", and that was never what the passes do. Stated as a bound
    /// rather than a promise, so it can be checked:
    ///
    ///    REMOVED — any `&lt;sep&gt;Users&lt;sep&gt;&lt;segment&gt;` run, with or without a
    ///    drive letter in front of it, in ANY MIX of the four separator
    ///    spellings a log carries (plain backslash; the doubled backslash of
    ///    anything JSON- or C-escaped; forward slash; and the `%5C` of a
    ///    file:// URL); and this process's own profile directory, wherever it
    ///    lives, in any mix of those same spellings. MIXED separators are
    ///    covered because a log really does carry them — one component writes
    ///    `C:\Users\x`, another rewrites half of it — and the combination used
    ///    to survive both passes while the consent said otherwise (Codex
    ///    client r2 MEDIUM).
    ///
    ///    NOT REMOVED — a local directory that is neither under a Users folder
    ///    nor the profile (a game on D:\Games, a UNC share that does not go
    ///    through Users, a POSIX home); the account name where it sits inside
    ///    a path or an address this process did not recognise, because it is
    ///    not "on its own" there; Steam IDs; display or player names; room and
    ///    series IDs; IP addresses; e-mail addresses; the machine's name;
    ///    tokens.
    ///
    /// The Settings caption says the same thing in a player's words, and the
    /// two are edited together: a consent that claims more than this list is
    /// the defect, not a wording preference. A consent that claims LESS than
    /// the code does is the same defect from the other side, and that is the
    /// half the bare-name boundary below closes — it used to fire inside
    /// `/name/`, `\name\` and `name@example`, none of which is "on its own".
    ///
    /// THE SHORT-NAME POLICY, stated rather than left as a silent skip. The
    /// bare-name pass needs a name long enough that "the same letters, alone"
    /// is evidence of the account rather than a coincidence, so it runs only
    /// for names of THREE characters or more. A one- or two-character account
    /// is still removed by the PATH passes — it is a path segment there like
    /// any other — so what the floor gives up is the standalone mention only,
    /// and a two-letter standalone token is not identifying on its own. The
    /// consent caption states this floor; it is not a hidden exception.
    ///
    /// Failure is fail-CLOSED by contract: <see cref="Scrub(string,string,string,out int)"/>
    /// returns null if any pass throws, and a null return means the caller must
    /// withhold the text rather than send it (CompetitiveUI.ComposeLogBundle
    /// does exactly that). A scrub that silently passed the text through on an
    /// exception would be a check that cannot fail.
    /// </summary>
    internal static class LogScrub
    {
        internal const string PathPlaceholder = "<userprofile>";
        internal const string NamePlaceholder = "<user>";

        /// <summary>The floor under which the bare-name pass does not run.
        /// Named, not inlined, so the policy has one home and the consent
        /// caption's "three characters or longer" can be checked against
        /// it.</summary>
        internal const int MinBareNameLength = 3;

        /// <summary>The boundary either side of a BARE account name. '_', '.'
        /// and '-' are inside the class, not outside it: they join identifiers
        /// (`cr_admin_ready`, `Landfall.User.Config`, `map-test-3`), and an
        /// account name that happens to be an ordinary word must not rewrite
        /// every one of them.
        ///
        /// THE SEPARATORS AND '@' ARE INSIDE IT TOO (Codex client r2 MEDIUM,
        /// this constant). They were outside, so `/name/`, `\name\`,
        /// `%5Cname%5C` and `name@example.com` all satisfied the boundary and
        /// were rewritten — while the class contract and the consent both said
        /// the pass fires only where the name stands on its own, and the
        /// consent added "nothing else is removed". Two ways out of that, and
        /// this is the one that keeps the promise instead of widening it: the
        /// path shapes worth removing are removed by the PATH passes, which
        /// take the whole identifying prefix rather than one segment, and an
        /// e-mail local part is listed as not-removed and now genuinely is.
        /// What this gives up is the account name inside a path the path
        /// passes do not recognise — a UNC share or POSIX home that does not
        /// go through Users — which the NOT REMOVED list names.
        ///
        /// Shared with the residue counter deliberately, and it is the one
        /// thing they do share. The counter's PATH check is independently
        /// written (a plain `Users&lt;sep&gt;` scan, not the scrub's regexes) so a
        /// broken pattern cannot certify itself — but the BOUNDARY is the
        /// policy itself, not an implementation of it, and two copies of a
        /// policy drift (#279). What keeps the counter honest here is the
        /// self-test's before/after control: every positive case asserts the
        /// residue count was non-zero BEFORE the scrub ran.</summary>
        internal const string NameBoundaryBefore = "(?<![A-Za-z0-9_.\\-\\\\/%@])";
        internal const string NameBoundaryAfter = "(?![A-Za-z0-9_.\\-\\\\/%@])";

        /// <summary>One separator, four spellings a real log carries: a plain
        /// backslash; the doubled backslash of anything that was JSON- or
        /// C-escaped before it was logged; a forward slash (Unity, MSBuild and
        /// every URI form write these); and the percent-encoding a file:// URL
        /// uses. Longest first, so the doubled form is consumed whole instead
        /// of the single-backslash pattern taking half of it.</summary>
        private static readonly string[] SepForms = { "\\\\", "\\", "/", "%5C" };

        /// <summary>ONE separator, any spelling, matched independently at each
        /// position. This is what makes a MIXED-separator path removable: the
        /// old patterns fixed one spelling for the whole run, so `C:\Users/x`
        /// matched none of the four and survived every pass.</summary>
        private static readonly string SepAny = BuildSepAny();

        private static string BuildSepAny()
        {
            var sb = new StringBuilder("(?:");
            for (int i = 0; i < SepForms.Length; i++)
            {
                if (i > 0) sb.Append('|');
                sb.Append(Regex.Escape(SepForms[i]));   // longest first: see SepForms
            }
            return sb.Append(')').ToString();
        }

        /// <summary>A path segment ends at any separator spelling, at
        /// whitespace, or at a delimiter a log line wraps a path in. '%'
        /// terminates a segment because the percent-encoded separator begins
        /// with it.</summary>
        private const string SegmentClass = "[^\\\\/%\\s\"'\\]\\)\\},;]+";

        /// <summary>`[drive:]&lt;sep&gt;Users&lt;sep&gt;&lt;segment&gt;`, every separator
        /// independent. The drive is OPTIONAL so the same pattern covers a UNC
        /// share that goes through Users (`\\host\Users\x`) and a forward-slash
        /// Users root, both of which carry exactly the identifying segment the
        /// drive-anchored form was written for.</summary>
        private static readonly Regex UsersDirPattern =
            new Regex("(?:[A-Za-z]:)?" + SepAny + "Users" + SepAny + SegmentClass,
                      RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

        /// <summary>The profile directory as a pattern rather than as four
        /// literal spellings: each separator inside it accepts any spelling,
        /// so a profile that arrives half-rewritten is still removed.</summary>
        private static Regex ProfilePattern(string profile)
        {
            if (string.IsNullOrEmpty(profile)) return null;
            string plain = profile.TrimEnd('\\', '/');
            if (plain.Length == 0) return null;
            string[] parts = plain.Split('\\', '/');
            var sb = new StringBuilder();
            for (int i = 0; i < parts.Length; i++)
            {
                if (i > 0) sb.Append(SepAny);
                sb.Append(Regex.Escape(parts[i]));
            }
            try
            {
                return new Regex(sb.ToString(),
                                 RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            }
            catch { return null; }
        }

        /// <summary>Scrub with this process's own account name and profile
        /// directory. Reading them can throw on a locked-down host, which is
        /// why both reads are separately guarded and a failure to read leaves
        /// the corresponding pass to the generic `Users\&lt;segment&gt;` one.</summary>
        internal static string Scrub(string text, out int replacements)
        {
            string user = null, profile = null;
            try { user = Environment.UserName; } catch { }
            try { profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile); } catch { }
            return Scrub(text, user, profile, out replacements);
        }

        /// <summary>Returns the scrubbed text, or NULL if a pass threw — null
        /// means "do not send this", never "nothing needed removing".</summary>
        internal static string Scrub(string text, string userName, string userProfile, out int replacements)
        {
            replacements = 0;
            if (string.IsNullOrEmpty(text)) return text;
            try
            {
                int n = 0;
                string s = text;

                // 1. The profile directory as this process reports it, with
                //    every separator inside it matched in ANY spelling. Runs
                //    FIRST and is the only pass that can reach a profile
                //    outside \Users (a redirected or domain profile, e.g.
                //    D:\Profiles\name).
                var profileRx = ProfilePattern(userProfile);
                if (profileRx != null)
                    s = profileRx.Replace(s, m => { n++; return PathPlaceholder; });

                // 2. Any [drive:]<sep>Users<sep><segment> run, whoever it
                //    belongs to, each separator independent. Counted from the
                //    evaluator, so the number is of matches actually replaced
                //    rather than a separately computed guess.
                s = UsersDirPattern.Replace(s, m => { n++; return PathPlaceholder; });

                // 3. The bare account name, at a TRUE word boundary.
                //
                //    The bound used to be [A-Za-z0-9] on both sides, which
                //    treats '_', '.' and '-' as boundaries — so an account
                //    called "admin", "user", "test" or "game" (all of them
                //    ordinary account names) rewrote `cr_admin_ready`,
                //    `Landfall.User.Config` and `map-test-3` in every
                //    diagnostic line that carried one (Codex r1 MEDIUM,
                //    LogScrub.cs:115). Those are identifiers, not mentions of
                //    a person, and a scrub that mangles them makes the log it
                //    was protecting useless to read.
                //
                //    NameBoundary adds '_', '.' and '-' to the class, so the
                //    pass fires only where the name stands genuinely alone —
                //    which is exactly what the consent caption claims.
                //
                //    AND THE SEPARATORS AND '@' (Codex client r2 MEDIUM,
                //    LogScrub.cs:174). The previous revision argued that
                //    leaving them OUT was deliberate, so the pass would catch
                //    a path the path passes did not recognise. It did — and
                //    that made `/name/`, `\name\` and `name@example.com` into
                //    removals the class contract and the consent both denied
                //    ("on its own", "nothing else is removed"). The claim and
                //    the code have to agree; this narrows the code, because
                //    the paths worth removing are removed properly by passes 1
                //    and 2 (which take the whole identifying prefix, not one
                //    segment) and an e-mail local part was already on the
                //    NOT-REMOVED list.
                //
                //    Bounded on both sides, so "name2" and "xname" keep their
                //    spelling. Skipped under three characters — see THE
                //    SHORT-NAME POLICY on the class.
                if (!string.IsNullOrEmpty(userName) && userName.Length >= MinBareNameLength)
                {
                    var rx = new Regex(NameBoundaryBefore + Regex.Escape(userName) + NameBoundaryAfter,
                                       RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
                    s = rx.Replace(s, m => { n++; return NamePlaceholder; });
                }

                replacements = n;
                return s;
            }
            catch
            {
                replacements = -1;
                return null;   // fail CLOSED — the caller withholds the text
            }
        }

        // SpellingsOf / ReplaceCounted are GONE, not merely unused: they
        // enumerated the profile in four HOMOGENEOUS spellings and replaced
        // each as a literal, which is the shape that let a mixed-separator
        // profile through. ProfilePattern replaces both.

        // ── Self-test ────────────────────────────────────────────────────
        //
        // Lives in the repo rather than in a scratch harness so the numbers it
        // prints can be reproduced from a checkout; the console harness only
        // calls it. Every case is a two-way control: the same corpus is
        // measured with the scrub and WITHOUT it, and a case passes only when
        // the unscrubbed measurement is non-zero. A test whose negative
        // control is silent is measuring nothing.

        /// <summary>Counts the residues the scrub exists to remove: any
        /// `Users&lt;sep&gt;` in the four spellings, plus the bare account name.
        /// This is the ASSERTION function — it is deliberately not the scrub's
        /// own regex set reused, so a broken pattern cannot certify itself.
        /// </summary>
        internal static int CountResidues(string text, string userName)
        {
            if (string.IsNullOrEmpty(text)) return 0;
            int n = 0;
            foreach (string sep in new[] { "\\\\", "\\", "/", "%5C" })
            {
                string needle = "Users" + sep;
                int i = 0;
                while (true)
                {
                    int at = text.IndexOf(needle, i, StringComparison.OrdinalIgnoreCase);
                    if (at < 0) break;
                    n++;
                    i = at + needle.Length;
                }
                // The doubled form contains the single one, so one residue can
                // be counted by two spellings. That is deliberate: this is a
                // "is any of it still here" gauge, and every assertion built on
                // it compares against zero, never against a specific total.
            }
            if (!string.IsNullOrEmpty(userName) && userName.Length >= MinBareNameLength)
            {
                var rx = new Regex(NameBoundaryBefore + Regex.Escape(userName) + NameBoundaryAfter,
                                   RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
                n += rx.Matches(text).Count;
            }
            return n;
        }

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        // The canned cases are ASSEMBLED AT RUN TIME from the parts below and
        // are never written as whole literals. A shipped DLL is byte-scanned
        // for the four spellings of the Users directory and that scan is a
        // zero / non-zero gate; a fixture carrying one of those spellings in
        // the literal heap turns the gate into a judgement call about which
        // hits are "only test data", which is exactly the judgement the scan
        // exists to remove. `Bsl` is static readonly, not const, so the
        // compiler cannot fold the joins back into a single literal.
        private static readonly string Bsl = "\\";
        private static readonly string UsersWord = "Users";

        /// <summary>drive + ':' + sep + "Users" + sep + segments, joined at run
        /// time; `sep` carries whichever of the four spellings the case
        /// exercises.</summary>
        private static string JoinUsers(string drive, string sep, params string[] segments)
        {
            var b = new StringBuilder(drive).Append(':').Append(sep).Append(UsersWord);
            foreach (string seg in segments) b.Append(sep).Append(seg);
            return b.ToString();
        }

        /// <summary>The same, with a DIFFERENT separator spelling at each
        /// position — the shape that survived every pass before the r2 fix.
        /// The spellings are taken in rotation from <paramref name="seps"/> so
        /// the case is a genuine mix rather than one odd separator.</summary>
        private static string JoinUsersMixed(string drive, string[] seps, params string[] segments)
        {
            int i = 0;
            var b = new StringBuilder(drive).Append(':').Append(seps[i++ % seps.Length]).Append(UsersWord);
            foreach (string seg in segments) b.Append(seps[i++ % seps.Length]).Append(seg);
            return b.ToString();
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            const string user = "testuser";
            string profile = JoinUsers("C", Bsl, user);

            // (input, what the scrub must leave behind unchanged, "neg" when
            // the case must survive with NO replacement at all)
            var cases = new[]
            {
                new[] { "[Info] Unity log at " + JoinUsers("C", Bsl, user, "AppData", "LocalLow", "Landfall", "ROUNDS", "Player.log"), "AppData", "" },
                new[] { "path=" + JoinUsers("C", "/", user, "AppData", "LocalLow", "x.log"), "AppData", "" },
                new[] { "{\"p\":\"" + JoinUsers("C", Bsl + Bsl, user, "AppData", "x.log") + "\"}", "AppData", "" },
                new[] { "file:///" + JoinUsers("C", "%5C", user, "AppData", "x.log"), "AppData", "" },
                new[] { JoinUsers("D", Bsl, user, "game", "out.txt"), "out.txt", "" },
                new[] { "user is testuser, greeting them", "greeting", "" },
                new[] { "TESTUSER wrote the config", "config", "" },
                new[] { "another account at " + JoinUsers("C", Bsl, "someoneelse", "Desktop", "a.txt"), "Desktop", "" },
                new[] { "testuser2 is a different identifier", "testuser2", "neg" },
                new[] { "no identity here at all", "identity", "neg" },
                // MIXED SEPARATORS (Codex client r2 MEDIUM). One component
                // writes the path, another rewrites half of it, and the result
                // matched none of the four homogeneous patterns while the
                // consent claimed every Users path was removed. Two rotations,
                // so a fix that only handled "backslash then slash" is not
                // enough.
                new[] { "mixed " + JoinUsersMixed("C", new[] { Bsl, "/" }, user, "AppData", "x.log"), "AppData", "" },
                new[] { "mixed2 " + JoinUsersMixed("C", new[] { "/", Bsl + Bsl, "%5C" }, user, "AppData", "y.log"), "AppData", "" },
                // The PROFILE directory with mixed separators, which pass 1
                // owns. `profile` below is built with plain backslashes, so
                // this case only passes once that pass matches spellings
                // independently.
                new[] { "profile at " + JoinUsersMixed("C", new[] { "/", Bsl }, user) + Bsl + "Documents", "Documents", "" },
                // A Users path with NO DRIVE LETTER — a UNC share or a
                // forward-slash root. It carries the same identifying segment
                // the drive-anchored form was written for.
                new[] { "share at " + Bsl + Bsl + "host" + Bsl + UsersWord + Bsl + user + Bsl + "x.log", "x.log", "" },
                // The boundary cases. An account name that is also an ordinary
                // word used to rewrite every identifier that contained it, and
                // all of these must come back untouched (Codex r1 MEDIUM,
                // LogScrub.cs:115).
                //
                // The first three are surrounded on BOTH sides, so each of them
                // survives a widening of either boundary on its own — which
                // makes them useless as controls for one side. The four after
                // them touch the name on ONE side each, so a widening of the
                // LEADING boundary is caught by the two that lead with a
                // joiner, and a widening of the TRAILING boundary by the two
                // that follow with one. Keep both groups.
                new[] { "cr_testuser_ready staged", "cr_testuser_ready", "neg" },
                new[] { "Landfall.testuser.Config loaded", "Landfall.testuser.Config", "neg" },
                new[] { "map-testuser-3 selected", "map-testuser-3", "neg" },
                new[] { "testuser_ready was staged", "testuser_ready", "neg" },     // trailing '_'
                new[] { "testuser.log rotated", "testuser.log", "neg" },            // trailing '.'
                new[] { "queued cr_testuser now", "cr_testuser", "neg" },           // leading '_'
                new[] { "selected map-testuser now", "map-testuser", "neg" },       // leading '-'
                // THE r2 BOUNDARY CASES. Each of these used to be rewritten
                // while the class contract said "on its own" and the consent
                // said "nothing else is removed". They are NOT paths this
                // process recognises (no Users segment, no profile prefix), so
                // nothing else removes them either — which is what makes them
                // controls for the boundary and not for the path passes.
                new[] { "posix home /testuser/logs/a.txt", "/testuser/", "neg" },
                new[] { "share " + Bsl + Bsl + "host" + Bsl + "share" + Bsl + "testuser" + Bsl + "a.txt",
                        Bsl + "testuser" + Bsl, "neg" },
                new[] { "mail from testuser@example.com bounced", "testuser@example.com", "neg" },
                new[] { "encoded %5Ctestuser%5Clog", "%5Ctestuser%5C", "neg" },
            };

            foreach (var c in cases)
            {
                string input = c[0], keep = c[1];
                int before = CountResidues(input, user);
                int reps;
                string outp = Scrub(input, user, profile, out reps);

                bool isNegativeCase = c[2] == "neg";
                int after = outp == null ? -1 : CountResidues(outp, user);

                bool ok = outp != null
                          && after == 0
                          && outp.IndexOf(keep, StringComparison.Ordinal) >= 0
                          && (isNegativeCase ? (before == 0 && reps == 0) : (before > 0 && reps > 0));

                if (ok) r.Passed++; else r.Failed++;
                // BOTH sides of the case on the line. Printing only the OUTPUT
                // is how a reader — human or gate — loses the ability to say
                // WHICH case a line belongs to the moment the scrub starts
                // rewriting the very text being searched for: the identifier
                // cases exist to prove a token survives, and a line that no
                // longer contains that token is indistinguishable from a line
                // that was never run.
                r.Report.Append(ok ? "PASS " : "FAIL ")
                        .Append("before=").Append(before)
                        .Append(" after=").Append(after)
                        .Append(" reps=").Append(reps)
                        .Append(" | in=").Append(input)
                        .Append(" | out=").Append(outp ?? "(null)")
                        .Append('\n');
            }

            // Negative control on the whole corpus: with the scrub NOT applied
            // the residue counter must be loudly non-zero, or every PASS above
            // is a measurement of nothing.
            var all = new StringBuilder();
            foreach (var c in cases) all.Append(c[0]).Append('\n');
            int controlUnscrubbed = CountResidues(all.ToString(), user);
            int scrubbedReps;
            string scrubbedAll = Scrub(all.ToString(), user, profile, out scrubbedReps);
            int controlScrubbed = scrubbedAll == null ? -1 : CountResidues(scrubbedAll, user);
            bool controlOk = controlUnscrubbed > 0 && controlScrubbed == 0;
            if (controlOk) r.Passed++; else r.Failed++;
            r.Report.Append(controlOk ? "PASS " : "FAIL ")
                    .Append("CONTROL unscrubbed=").Append(controlUnscrubbed)
                    .Append(" scrubbed=").Append(controlScrubbed)
                    .Append(" reps=").Append(scrubbedReps)
                    .Append('\n');
            return r;
        }
    }
}
