// C3: RJ readmission P3, the client half (V3:101-112): every present kept seat
// files in a readmission lobby; elsewhere the client election is unchanged.
using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds
{
    internal static class CasesC3
    {
        /// <summary>One client's view at the game-over edge.</summary>
        private sealed class Seat
        {
            internal int Actor;
            internal string Sid;
            internal int LocalLagGame;                       // FfaLateEntry.LagGame on this client
            internal HashSet<int> SeesLagged = new HashSet<int>();  // peers whose cr_lag this client read
            internal HashSet<int> SeesLate = new HashSet<int>();
        }

        /// <summary>What GameStateWatcher does with the two rules: the lag skip
        /// first, then the filer; it files when the filer is its own id.</summary>
        private static bool Files(bool readmit, int game, Seat self, IList<Seat> present, out bool selfLag)
        {
            selfLag = FfaReportRules.SelfLag(readmit, game, self.LocalLagGame);
            if (FfaReportRules.LagSkipsReport(readmit, game, self.LocalLagGame)) return false;
            var sorted = present.OrderBy(s => long.Parse(s.Sid)).ToList();
            var actors = sorted.Select(s => s.Actor).ToList();
            var sidOf = sorted.ToDictionary(s => s.Actor, s => s.Sid);
            Func<int, bool> lagged = a => a == self.Actor ? self.LocalLagGame == game && game > 0 : self.SeesLagged.Contains(a);
            Func<int, bool> late = a => self.SeesLate.Contains(a);
            string filer = FfaReportRules.FilerOf(readmit, self.Sid, self.Actor, actors, sidOf, lagged, late,
                                                  FfaLateRules.ElectReporter, false, null);
            return filer == self.Sid;
        }

        /// <summary>The election as it stood inline in GameStateWatcher at the
        /// lane base (B:plugin/GameStateWatcher.cs:7861-7880), transcribed
        /// statement for statement: the reference T3.6 compares against.</summary>
        private static string BaseElection(string localSid, int ownActor, IList<int> candActors,
                                           IDictionary<int, string> sidOfActor, Func<int, bool> lagged,
                                           Func<int, bool> late, bool noneParse, Func<string> ordinal)
        {
            int elected = FfaLateRules.ElectReporter(candActors, lagged, late);
            string lowest = null;
            if (elected >= 0) sidOfActor.TryGetValue(elected, out lowest);
            else if (noneParse) lowest = ordinal();
            bool selfBarred = late(ownActor) || lagged(ownActor);
            if (lowest == null && !selfBarred) lowest = localSid;
            return lowest;
        }

        internal static void Register()
        {
            // T3.2 client half (RJ2-H4): the lowest seat A lagged, its cr_lag
            // never published, so B does not see it; both file.
            RulesProgram.Add("C3.T3.2.lag_publication_lost_both_file", () =>
            {
                var a = new Seat { Actor = 1, Sid = "100", LocalLagGame = 3 };
                var b = new Seat { Actor = 2, Sid = "200" };
                var present = new List<Seat> { a, b };
                bool aLag, bLag;
                Check.True(Files(true, 3, a, present, out aLag), "the lagged lowest seat files in a readmission lobby");
                Check.True(Files(true, 3, b, present, out bLag), "the other seat files in a readmission lobby");
                Check.True(aLag, "the lagged seat marks its own report self_lag");
                Check.True(!bLag, "a seat with no lag record carries no self_lag mark");
            });
            // The same fixture with the flag false: today's outcome (nobody
            // files), the defect V3 P3 answers in readmission lobbies only.
            RulesProgram.Add("C3.T3.6.flag_false_two_clients_today", () =>
            {
                var a = new Seat { Actor = 1, Sid = "100", LocalLagGame = 3 };
                var b = new Seat { Actor = 2, Sid = "200" };
                var present = new List<Seat> { a, b };
                bool aLag, bLag;
                Check.True(!Files(false, 3, a, present, out aLag), "flag false: the lagged seat skips (lag_out), as today");
                Check.True(!Files(false, 3, b, present, out bLag), "flag false: the peer defers to the lowest seat, as today");
                Check.True(!aLag && !bLag, "flag false: no self_lag mark is ever set");
            });
            // T3.6 client half (#391 negative control): with the flag false the
            // election and its outputs are the base election's, for every
            // assignment of late and lag bars over three seats, every own seat,
            // and the no-parse ordinal fallback.
            RulesProgram.Add("C3.T3.6.flag_false_matrix_equals_base", () =>
            {
                var actors = new List<int> { 4, 7, 9 };
                var sidOf = new Dictionary<int, string> { { 4, "11" }, { 7, "22" }, { 9, "33" } };
                int checkedN = 0;
                for (int bits = 0; bits < 64; bits++)
                    foreach (int own in actors)
                        foreach (bool noneParse in new[] { false, true })
                            foreach (string ord in new[] { null, "22" })
                            {
                                int b = bits;
                                Func<int, bool> lagged = x => (b >> actors.IndexOf(x) & 1) == 1;
                                Func<int, bool> late = x => (b >> (3 + actors.IndexOf(x)) & 1) == 1;
                                var cand = noneParse ? new List<int>() : actors;
                                string want = BaseElection(sidOf[own], own, cand, sidOf, lagged, late, noneParse, () => ord);
                                string got = FfaReportRules.FilerOf(false, sidOf[own], own, cand, sidOf, lagged, late,
                                                                    FfaLateRules.ElectReporter, noneParse, () => ord);
                                Check.Eq(want, got, "flag false filer, bits=" + bits + " own=" + own + " noneParse=" + noneParse);
                                checkedN++;
                            }
                foreach (int lagGame in new[] { 0, 2, 3 })
                    foreach (int game in new[] { 0, 3 })
                    {
                        bool baseSkip = game > 0 && lagGame == game;
                        Check.Eq(baseSkip, FfaReportRules.LagSkipsReport(false, game, lagGame), "flag false lag skip");
                        Check.True(!FfaReportRules.SelfLag(false, game, lagGame), "flag false never marks self_lag");
                    }
                Check.True(checkedN == 64 * 3 * 2 * 2, "the matrix ran");
            });
            // In a readmission lobby the filer is always the seat itself, and
            // the lag skip never fires.
            RulesProgram.Add("C3.readmit_always_self", () =>
            {
                var actors = new List<int> { 4, 7 };
                var sidOf = new Dictionary<int, string> { { 4, "11" }, { 7, "22" } };
                string got = FfaReportRules.FilerOf(true, "22", 7, actors, sidOf, x => true, x => true,
                                                    FfaLateRules.ElectReporter, false, null);
                Check.Eq("22", got, "readmission lobby: the barred seat still names itself");
                Check.True(!FfaReportRules.LagSkipsReport(true, 3, 3), "readmission lobby: the lag record does not skip");
            });
        }
    }
}
