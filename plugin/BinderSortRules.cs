using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The binder's ordering rules, kept free of Unity, Photon, BepInEx and
    /// I18n so they run under a plain compiler: PlayerCardsUI hands them the
    /// keys it has already resolved and paints what comes back. The same
    /// SelfTest runs under tools/client-rules-harness, so the order is
    /// EXECUTED rather than asserted about as source text (#391) — the
    /// arrangement H2HRules.cs:1-16 states and RosterCensusRules.cs follows.
    ///
    /// No catalogue string lives here: the label strings stay at their
    /// I18n.Tr call sites in PlayerCardsUI, where the extractor reads them,
    /// so this file is deliberately NOT in tools/i18n_extract.py's FILES list
    /// (#464). If a string ever moves in here, that list gains this file in
    /// the same commit or the string is silently unharvestable.
    ///
    /// Item 20 (v1.41.0) added Mode.RatingPosition and moved the whole
    /// comparator in here. Two things are deliberate about that move:
    ///   - the member set is ONE enum, so the cycler can derive its length
    ///     from it instead of the "% 5" literal that a sixth member made
    ///     wrong (a flag names a line, the defect is a class — #432);
    ///   - the shared tail that makes the order total is one block of code
    ///     reached from every mode, so a mode added later cannot forget it.
    /// </summary>
    internal static class BinderSortRules
    {
        /// <summary>The front group is the board's first page. 100 is the
        /// number in the ask and the in-game board's own page size
        /// (NativeUI.RefreshLeaderboard pages at 100), so "front group" and
        /// "page one of the leaderboard" are the same set.</summary>
        internal const int TOP_N = 100;

        /// <summary>The binder orders, in cycle order. Position is the
        /// leaderboard position PRINTED on the card (its mint-time
        /// board_rank); RatingPosition is where the subject stands on that
        /// same board TODAY. The two can disagree, and that is the feature.
        /// </summary>
        internal enum Mode { Name, Rarity, Edition, Date, Position, RatingPosition }

        /// <summary>Whether this session has standings to sort by. Three
        /// values, because one boolean must never mean both "we have not
        /// asked yet" and "the server answered and carried none" (#430):
        /// the cycler may treat them alike, the restore may not.</summary>
        internal enum Standings
        {
            /// <summary>No collection answer has been read yet this session —
            /// the binder is painting its loading header.</summary>
            Unknown,
            /// <summary>An answer was read and it computed standings.</summary>
            Present,
            /// <summary>An answer was read and it carried none — an api that
            /// predates the server half of item 20.</summary>
            Absent,
        }

        /// <summary>What to do with a sort restored from the config file.
        /// There is deliberately no member that writes the config back: the
        /// config is written by an explicit player click and by nothing else,
        /// so refusing here costs one session's ordering and never the stored
        /// preference (#430 — a guard is judged by what its refusal costs).
        /// </summary>
        internal enum Restore
        {
            /// <summary>Still pending — try again on the next paint.</summary>
            Keep,
            /// <summary>Apply it now and stop pending.</summary>
            Apply,
            /// <summary>Not available from this api; give up for THIS session
            /// only. The stored value is untouched, so the choice returns by
            /// itself the day the api carries standings.</summary>
            DropForSession,
        }

        /// <summary>One print, reduced to the keys the order reads. The
        /// caller resolves everything locale- or Unity-dependent before it
        /// gets here: Name is the already-translated display name and
        /// RarityOrder is already a number.
        ///
        /// Rank/Inactive/Rated/Rating/SubjectId describe the SUBJECT as of
        /// the collection read. MintBoardRank is the different thing printed
        /// on the card face.</summary>
        internal struct Subject
        {
            // ── the print ──
            internal string PrintId;
            internal string CardId;
            internal string EditionId;
            internal string MintedAt;
            internal string Name;
            internal int RarityOrder;      // 0 legendary .. 4 common
            internal bool Foil;
            internal bool Signed;
            internal int EditionNo;        // int.MaxValue when the edition id is not a number
            internal int PoolRank;
            internal int MintBoardRank;    // the number on the card face; 0 = off the board that day

            // ── the subject, today (item 20) ──
            internal string SubjectId;
            internal int Rank;             // 0 = not on the card's board today
            internal bool Inactive;        // the board's own activity window said so
            internal bool Rated;           // false = no rating row, or the subject deleted their data
            internal float Rating;         // only meaningful while Rated
        }

        // ── membership ──────────────────────────────────────────────────────

        /// <summary>Which modes need the server to have sent standings.
        /// Exactly one does; everything else sorts off the print row that has
        /// always been on the wire.</summary>
        internal static bool RequiresStandings(Mode m)
        {
            return m == Mode.RatingPosition;
        }

        /// <summary>Whether this mode can be chosen right now.</summary>
        internal static bool Offers(Mode m, Standings standings)
        {
            return !RequiresStandings(m) || standings == Standings.Present;
        }

        /// <summary>The next mode the header button lands on.
        ///
        /// The cycle length comes from the enum, never from a literal: the
        /// "% 5" this replaced was correct for exactly as long as there were
        /// five members. A mode the current standings cannot serve is stepped
        /// over rather than shown and then refused, so the button never
        /// offers an order every card would tie under.</summary>
        internal static Mode Next(Mode current, Standings standings)
        {
            var members = (Mode[])Enum.GetValues(typeof(Mode));
            if (members.Length == 0) return current;
            int at = Array.IndexOf(members, current);
            if (at < 0) at = 0;
            for (int step = 1; step <= members.Length; step++)
            {
                Mode candidate = members[(at + step) % members.Length];
                if (Offers(candidate, standings)) return candidate;
            }
            return current;   // unreachable while Mode.Name needs nothing
        }

        /// <summary>What to do with a sort read out of the config file, given
        /// what this session knows about standings.
        ///
        /// The binder's FIRST paint of a session always happens before the
        /// collection fetch has answered, so resolving the stored value there
        /// would coerce RatingPosition to Name every launch. Unknown is
        /// therefore held, not dropped — the whole reason Standings has three
        /// values.</summary>
        internal static Restore Resolve(Mode pending, Standings standings)
        {
            if (!RequiresStandings(pending)) return Restore.Apply;
            if (standings == Standings.Present) return Restore.Apply;
            if (standings == Standings.Absent) return Restore.DropForSession;
            return Restore.Keep;
        }

        /// <summary>The stored config value is the enum MEMBER NAME, never
        /// the ordinal — an ordinal changes meaning the next time a mode is
        /// inserted. An unrecognised name falls back.
        ///
        /// Enum.Parse is not the test, and neither is Enum.IsDefined after
        /// it: Enum.Parse reads a DECIMAL STRING as an ordinal, so "5" came
        /// back as RatingPosition and passed IsDefined — an old config file
        /// carrying a number would have been read as whichever mode happens
        /// to sit at that index today. The stored text is matched against the
        /// member NAMES and nothing else.</summary>
        internal static Mode Parse(string stored, Mode fallback)
        {
            if (string.IsNullOrEmpty(stored)) return fallback;
            var members = (Mode[])Enum.GetValues(typeof(Mode));
            for (int i = 0; i < members.Length; i++)
                if (string.Equals(NameOf(members[i]), stored, StringComparison.Ordinal))
                    return members[i];
            return fallback;
        }

        /// <summary>What Parse reads back.</summary>
        internal static string NameOf(Mode m)
        {
            return m.ToString();
        }

        // ── the order ───────────────────────────────────────────────────────

        /// <summary>Is this print's subject in the front group?
        ///
        /// FRONT ⟺ on the board (1..TOP_N) AND not inactive. The activity
        /// conjunct is belt and braces on purpose: the board the rank comes
        /// from already excludes inactive players, so today it never decides
        /// — but that exclusion lives in SQL on the server, and without this
        /// line a change there would silently promote a long-gone player to
        /// the front of every binder.</summary>
        internal static bool IsFront(Subject s)
        {
            return s.Rank >= 1 && s.Rank <= TOP_N && !s.Inactive;
        }

        private static int MintBoardKey(Subject s)
        {
            return s.MintBoardRank > 0 ? s.MintBoardRank : int.MaxValue;
        }

        /// <summary>The binder order: the chosen key first, then the shared
        /// tail (name, card, rarity, foil, signed, mint date, print id) under
        /// every mode, which is what makes the order total.</summary>
        internal static int Compare(Subject a, Subject b, Mode mode)
        {
            int c;
            switch (mode)
            {
                case Mode.Rarity:
                    c = a.RarityOrder.CompareTo(b.RarityOrder); if (c != 0) return c;
                    c = (b.Foil ? 1 : 0).CompareTo(a.Foil ? 1 : 0); if (c != 0) return c;
                    c = (b.Signed ? 1 : 0).CompareTo(a.Signed ? 1 : 0); if (c != 0) return c;
                    break;
                case Mode.Edition:
                    c = a.EditionNo.CompareTo(b.EditionNo); if (c != 0) return c;
                    c = string.CompareOrdinal(a.EditionId ?? "", b.EditionId ?? ""); if (c != 0) return c;
                    c = a.RarityOrder.CompareTo(b.RarityOrder); if (c != 0) return c;
                    break;
                case Mode.Date:
                    c = string.CompareOrdinal(b.MintedAt ?? "", a.MintedAt ?? ""); if (c != 0) return c;   // newest first
                    break;
                case Mode.Position:
                    c = MintBoardKey(a).CompareTo(MintBoardKey(b)); if (c != 0) return c;
                    c = a.PoolRank.CompareTo(b.PoolRank); if (c != 0) return c;
                    break;
                case Mode.RatingPosition:
                    // 1. the group, first and alone, so the two cannot interleave
                    c = (IsFront(a) ? 0 : 1).CompareTo(IsFront(b) ? 0 : 1); if (c != 0) return c;
                    if (IsFront(a))
                    {
                        // 2. front: board position ascending, #1 first
                        c = a.Rank.CompareTo(b.Rank); if (c != 0) return c;
                    }
                    else
                    {
                        // 3. back: rated before unrated, then rating descending;
                        //    between two UNRATED the subject id decides, because
                        //    there is no rating left to compare (the design's
                        //    step 3 — two RATED subjects on the same rating fall
                        //    through to the shared tail, which reads alphabetical)
                        c = (a.Rated ? 0 : 1).CompareTo(b.Rated ? 0 : 1); if (c != 0) return c;
                        if (a.Rated)
                        {
                            c = b.Rating.CompareTo(a.Rating); if (c != 0) return c;
                        }
                        else
                        {
                            c = string.CompareOrdinal(a.SubjectId ?? "", b.SubjectId ?? ""); if (c != 0) return c;
                        }
                    }
                    break;
            }
            // 4. the shared tail, under every mode
            c = string.Compare(a.Name ?? "", b.Name ?? "", StringComparison.OrdinalIgnoreCase); if (c != 0) return c;
            c = string.CompareOrdinal(a.CardId ?? "", b.CardId ?? ""); if (c != 0) return c;
            c = a.RarityOrder.CompareTo(b.RarityOrder); if (c != 0) return c;
            c = (b.Foil ? 1 : 0).CompareTo(a.Foil ? 1 : 0); if (c != 0) return c;
            c = (b.Signed ? 1 : 0).CompareTo(a.Signed ? 1 : 0); if (c != 0) return c;
            c = string.CompareOrdinal(a.MintedAt ?? "", b.MintedAt ?? "");
            return c != 0 ? c : string.CompareOrdinal(a.PrintId ?? "", b.PrintId ?? "");
        }

        // ── self-test (EXECUTED by tools/client-rules-harness) ──────────────

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>A print of a top-100 active subject. Every field the tail
        /// reads is set, so a fixture only has to state what it is about.</summary>
        private static Subject P(string printId, string subjectId, int rank,
                                 bool inactive, bool rated, float rating)
        {
            return new Subject
            {
                PrintId = printId,
                CardId = "card-" + subjectId,
                EditionId = "1",
                MintedAt = "2026-09-01T00:00:00",
                Name = subjectId,
                RarityOrder = 4,
                Foil = false,
                Signed = false,
                EditionNo = 1,
                PoolRank = 1,
                MintBoardRank = 1,
                SubjectId = subjectId,
                Rank = rank,
                Inactive = inactive,
                Rated = rated,
                Rating = rating,
            };
        }

        private static int Sign(int n) { return n < 0 ? -1 : (n > 0 ? 1 : 0); }

        /// <summary>The cycler as it was before item 20: a hardcoded modulus
        /// over the first five members. Kept as the NEGATIVE CONTROL for the
        /// cycle cases — the measurement that shows the enum-derived length is
        /// doing work is that this one cannot reach the sixth mode (#391).
        /// Never called by anything that paints.</summary>
        private static Mode NextWithHardcodedFive(Mode current)
        {
            return (Mode)(((int)current + 1) % 5);
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // ── T1: the group key comes first ──────────────────────────────
            {
                var onBoard = P("p1", "aaa", 3, false, true, 1500f);
                var off = P("p2", "bbb", 0, false, true, 1900f);
                int before = Sign(Compare(onBoard, off, Mode.RatingPosition));
                // the mutation: the same subject, off the board
                var mutated = onBoard; mutated.Rank = 0;
                int after = Sign(Compare(mutated, off, Mode.RatingPosition));
                Check(r, "a ranked subject precedes an off-board subject",
                      before < 0, "cmp=" + before);
                Check(r, "off the board, the order flips (group key, not rating)",
                      after > 0, "cmp=" + after);
            }

            // ── T2: the boundary is inclusive at 100 ───────────────────────
            {
                var at100 = P("p1", "aaa", TOP_N, false, true, 1000f);
                var at101 = P("p2", "bbb", TOP_N + 1, false, true, 2500f);
                Check(r, "rank " + TOP_N + " is in the front group",
                      IsFront(at100), "front=" + IsFront(at100));
                Check(r, "rank " + (TOP_N + 1) + " is NOT in the front group",
                      !IsFront(at101), "front=" + IsFront(at101));
                Check(r, "the front card precedes the higher-rated card just outside",
                      Compare(at100, at101, Mode.RatingPosition) < 0,
                      "cmp=" + Compare(at100, at101, Mode.RatingPosition));
            }

            // ── T3: inactive is read even when a rank is present ───────────
            {
                var quiet = P("p1", "aaa", 5, true, true, 2000f);
                var active = P("p2", "bbb", 90, false, true, 1200f);
                Check(r, "rank 5 AND inactive sorts to the back",
                      Compare(quiet, active, Mode.RatingPosition) > 0,
                      "cmp=" + Compare(quiet, active, Mode.RatingPosition));
                // the mutation: clear the activity flag on the SAME fixture
                var woken = quiet; woken.Inactive = false;
                Check(r, "clearing inactive on the same fixture makes it front",
                      Compare(woken, active, Mode.RatingPosition) < 0,
                      "cmp=" + Compare(woken, active, Mode.RatingPosition));
            }

            // ── T4: the back group reads the CURRENT rating ────────────────
            {
                // both off the board. Their mint-time numbers (MintBoardRank,
                // here standing in for the frozen fields on the print row) run
                // the opposite way to their current ratings, so a comparator
                // reading the frozen field produces the reversed sequence.
                var decayed = P("p1", "aaa", 0, false, true, 900f);
                decayed.MintBoardRank = 1; decayed.PoolRank = 1;
                var risen = P("p2", "bbb", 0, false, true, 2100f);
                risen.MintBoardRank = 400; risen.PoolRank = 400;
                Check(r, "the back group orders by current rating, descending",
                      Compare(risen, decayed, Mode.RatingPosition) < 0,
                      "cmp=" + Compare(risen, decayed, Mode.RatingPosition));
                Check(r, "the frozen mint numbers order the SAME pair the other way",
                      Compare(risen, decayed, Mode.Position) > 0,
                      "cmp=" + Compare(risen, decayed, Mode.Position));
            }

            // ── T5: unrated is not rating 0 ────────────────────────────────
            {
                var unrated = P("p1", "aaa", 0, false, false, 0f);
                var zeroRated = P("p2", "bbb", 0, false, true, 0f);
                Check(r, "an unrated subject sorts behind a rated one on 0",
                      Compare(unrated, zeroRated, Mode.RatingPosition) > 0,
                      "cmp=" + Compare(unrated, zeroRated, Mode.RatingPosition));
                // the mutation: give the unrated subject a rating row at 0
                var nowRated = unrated; nowRated.Rated = true;
                Check(r, "the same subject, now rated at 0, ties on rating and falls to the tail",
                      Compare(nowRated, zeroRated, Mode.RatingPosition) < 0,
                      "cmp=" + Compare(nowRated, zeroRated, Mode.RatingPosition));
            }

            // ── T6: copies of one subject stay adjacent ────────────────────
            {
                var third = P("p3", "aaa", 0, false, true, 1400f);   // a different subject, between them by rating
                third.SubjectId = "mmm"; third.Name = "mmm"; third.CardId = "card-mmm"; third.Rating = 1400f;
                var copyA = P("p1", "aaa", 0, false, true, 1500f);
                var copyB = P("p2", "aaa", 0, false, true, 1500f);
                copyB.RarityOrder = 0;   // a rarer copy of the same card
                bool adjacent = Compare(copyA, third, Mode.RatingPosition) < 0
                                && Compare(copyB, third, Mode.RatingPosition) < 0;
                Check(r, "two copies of one subject sit together, not split by a third",
                      adjacent, "a<t=" + Compare(copyA, third, Mode.RatingPosition)
                                + " b<t=" + Compare(copyB, third, Mode.RatingPosition));
                int withRarity = Sign(Compare(copyA, copyB, Mode.RatingPosition));
                // the mutation: swap the rarities of the two copies
                var swapA = copyA; swapA.RarityOrder = 0;
                var swapB = copyB; swapB.RarityOrder = 4;
                int swapped = Sign(Compare(swapA, swapB, Mode.RatingPosition));
                Check(r, "copies order by the shared tail, and swapping rarity flips them",
                      withRarity > 0 && swapped < 0,
                      "before=" + withRarity + " after=" + swapped);
            }

            // ── T7: the order is total under every mode ────────────────────
            {
                var a = P("p1", "aaa", 7, false, true, 1500f);
                var b = P("p2", "aaa", 7, false, true, 1500f);   // equal in every key but the print id
                foreach (Mode m in (Mode[])Enum.GetValues(typeof(Mode)))
                {
                    Check(r, "the order is total under " + m + " (only the print id differs)",
                          Compare(a, b, m) < 0 && Compare(b, a, m) > 0,
                          "ab=" + Compare(a, b, m) + " ba=" + Compare(b, a, m));
                }
                var same = a;
                Check(r, "a print compares equal to itself",
                      Compare(a, same, Mode.RatingPosition) == 0,
                      "cmp=" + Compare(a, same, Mode.RatingPosition));
            }

            // ── T8: the cycler offers the sort only when standings are there ─
            {
                Check(r, "Next skips RatingPosition when the answer carried no standings",
                      Next(Mode.Position, Standings.Absent) == Mode.Name,
                      "next=" + Next(Mode.Position, Standings.Absent));
                Check(r, "Next skips RatingPosition before any answer has been read",
                      Next(Mode.Position, Standings.Unknown) == Mode.Name,
                      "next=" + Next(Mode.Position, Standings.Unknown));
                // the mutation: the same call with standings present
                Check(r, "the same call returns RatingPosition once standings are present",
                      Next(Mode.Position, Standings.Present) == Mode.RatingPosition,
                      "next=" + Next(Mode.Position, Standings.Present));
                Check(r, "Offers agrees with Next about what is available",
                      !Offers(Mode.RatingPosition, Standings.Absent)
                      && !Offers(Mode.RatingPosition, Standings.Unknown)
                      && Offers(Mode.RatingPosition, Standings.Present)
                      && Offers(Mode.Name, Standings.Absent),
                      "absent=" + Offers(Mode.RatingPosition, Standings.Absent)
                      + " present=" + Offers(Mode.RatingPosition, Standings.Present));
            }

            // ── T9: the cycle length comes from the enum ───────────────────
            {
                var members = (Mode[])Enum.GetValues(typeof(Mode));
                var seen = new List<Mode>();
                Mode at = Mode.Name;
                for (int i = 0; i < members.Length * 2; i++)
                {
                    at = Next(at, Standings.Present);
                    if (at == Mode.Name) break;
                    seen.Add(at);
                }
                Check(r, "the cycle visits every member and returns to Name",
                      at == Mode.Name && seen.Count == members.Length - 1,
                      "visited=" + seen.Count + " of " + (members.Length - 1) + " back-at=" + at);
                // the negative control: the "% 5" cycler this replaced, run
                // over the same enum. It can never reach the sixth member, so
                // a length taken from a literal is measurably different.
                var oldSeen = new List<Mode>();
                Mode oldAt = Mode.Name;
                for (int i = 0; i < members.Length * 2; i++)
                {
                    oldAt = NextWithHardcodedFive(oldAt);
                    if (oldAt == Mode.Name) break;
                    oldSeen.Add(oldAt);
                }
                Check(r, "a hardcoded modulus cannot reach the sixth mode (control)",
                      !oldSeen.Contains(Mode.RatingPosition) && seen.Contains(Mode.RatingPosition),
                      "old=" + oldSeen.Count + " new=" + seen.Count);
            }

            // ── T10: the deferred restore, all three standings ─────────────
            {
                Check(r, "a pending RatingPosition SURVIVES the pre-fetch paint",
                      Resolve(Mode.RatingPosition, Standings.Unknown) == Restore.Keep,
                      "resolve=" + Resolve(Mode.RatingPosition, Standings.Unknown));
                Check(r, "it applies once standings are present",
                      Resolve(Mode.RatingPosition, Standings.Present) == Restore.Apply,
                      "resolve=" + Resolve(Mode.RatingPosition, Standings.Present));
                Check(r, "it is dropped for the session when the answer carried none",
                      Resolve(Mode.RatingPosition, Standings.Absent) == Restore.DropForSession,
                      "resolve=" + Resolve(Mode.RatingPosition, Standings.Absent));
                // the negative control: a resolver that folds Unknown into
                // Absent passes the other two and reds only the first, which
                // is why all three are run.
                Check(r, "folding Unknown into Absent would change the first outcome (control)",
                      Resolve(Mode.RatingPosition, Standings.Unknown)
                      != Resolve(Mode.RatingPosition, Standings.Absent),
                      "unknown=" + Resolve(Mode.RatingPosition, Standings.Unknown)
                      + " absent=" + Resolve(Mode.RatingPosition, Standings.Absent));
                // an ungated mode never waits on an answer that may never come
                foreach (Mode m in (Mode[])Enum.GetValues(typeof(Mode)))
                {
                    if (RequiresStandings(m)) continue;
                    Check(r, "a stored " + m + " applies immediately under Unknown",
                          Resolve(m, Standings.Unknown) == Restore.Apply,
                          "resolve=" + Resolve(m, Standings.Unknown));
                }
                // no outcome writes the config: the enum has exactly the three
                // members, so a "persist the fallback" member cannot be added
                // without failing here.
                var outcomes = Enum.GetNames(typeof(Restore));
                Array.Sort(outcomes, StringComparer.Ordinal);
                Check(r, "Restore has exactly Keep/Apply/DropForSession and no write outcome",
                      outcomes.Length == 3 && outcomes[0] == "Apply"
                      && outcomes[1] == "DropForSession" && outcomes[2] == "Keep",
                      "outcomes={" + string.Join(",", outcomes) + "}");
            }

            // ── the stored name, and what an unreadable one falls back to ──
            {
                Check(r, "a stored member name round-trips",
                      Parse(NameOf(Mode.RatingPosition), Mode.Name) == Mode.RatingPosition,
                      "parsed=" + Parse(NameOf(Mode.RatingPosition), Mode.Name));
                Check(r, "an unknown name falls back",
                      Parse("Nonsense", Mode.Name) == Mode.Name
                      && Parse("", Mode.Name) == Mode.Name
                      && Parse(null, Mode.Name) == Mode.Name,
                      "nonsense=" + Parse("Nonsense", Mode.Name));
                // the mutation Enum.TryParse alone would pass: a decimal
                // string names no member, and must not become one.
                Check(r, "a numeric string is not a member name",
                      Parse("7", Mode.Name) == Mode.Name && Parse("5", Mode.Name) == Mode.Name,
                      "seven=" + Parse("7", Mode.Name) + " five=" + Parse("5", Mode.Name));
                Check(r, "the stored value is a name, never an ordinal",
                      NameOf(Mode.RatingPosition) == "RatingPosition",
                      "name=" + NameOf(Mode.RatingPosition));
            }

            // ── mixed-case subject ids only ever decide an unrated pair ────
            {
                var upper = P("p1", "AAA", 0, false, false, 0f);
                var lower = P("p2", "bbb", 0, false, false, 0f);
                Check(r, "two unrated subjects order by subject id, ordinally",
                      Sign(Compare(upper, lower, Mode.RatingPosition))
                      == Sign(string.CompareOrdinal("AAA", "bbb")),
                      "cmp=" + Compare(upper, lower, Mode.RatingPosition));
            }

            return r;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
