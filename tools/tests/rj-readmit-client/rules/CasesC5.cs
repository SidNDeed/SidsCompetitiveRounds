// C5: RJ readmission P5, the client rungs of the positive ladder (V3:309-321):
// `[FFA-RDM] offered`, `claimed`, `bound` and `entered`, each named on the
// transition into its state by FfaReadmitEntryRules.LadderRung, the line from
// LadderLine. FfaReadmit calls exactly these (Offer, the answer callback of
// Send, and LadderEntered from OnSelfKept). `held` is the server's rung.
using System.Collections.Generic;

namespace CompetitiveRounds
{
    internal static class CasesC5
    {
        private const string Lobby8 = "1a2b3c4d";
        private const string Token = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

        /// <summary>The machine as FfaReadmit drives it: each step reads the
        /// state before, applies the transition, and records the rung's line.</summary>
        private sealed class Driver
        {
            internal readonly FfaReadmitEntryRules.RdmClient C = new FfaReadmitEntryRules.RdmClient();
            internal readonly List<string> Lines = new List<string>();

            private void Note(FfaReadmitEntryRules.RdmState before, bool selfKept)
            {
                string line = FfaReadmitEntryRules.LadderLine(FfaReadmitEntryRules.LadderRung(before, C.State, selfKept), Lobby8, C);
                if (line != null) Lines.Add(line);
            }

            internal void Offer(int n, float now)
            {
                var before = C.State;
                FfaReadmitEntryRules.Offer(C, "lobbyA", 1, n, 90, now);
                Note(before, false);
            }

            internal void Accept() { C.State = FfaReadmitEntryRules.RdmState.Claiming; }

            internal FfaReadmitEntryRules.RdmNext Answer(string step, FfaReadmitEntryRules.RdmAnswer a, float now)
            {
                var before = C.State;
                var next = FfaReadmitEntryRules.OnAnswer(C, step, a, now);
                Note(before, false);
                return next;
            }

            internal void SelfKept() { Note(C.State, true); }
        }

        private static FfaReadmitEntryRules.RdmAnswer Claimed()
        {
            return new FfaReadmitEntryRules.RdmAnswer { Status = "claimed", Token = Token, Room = "roomA", Region = "eu", Slot = 1, N = 1, HoldS = 80 };
        }

        private static FfaReadmitEntryRules.RdmAnswer Admitted()
        {
            return new FfaReadmitEntryRules.RdmAnswer { Status = "admitted_late", Kind = "r", Game = 3, Actor = 42, N = 1, Slot = 1 };
        }

        private static FfaReadmitEntryRules.RdmAnswer Refused(string reason, int retry = 0)
        {
            return new FfaReadmitEntryRules.RdmAnswer { Status = "refused", Reason = reason, Retry = retry, N = 1, HoldS = 90 };
        }

        private static List<string> Rungs(List<string> lines)
        {
            var r = new List<string>();
            foreach (var l in lines) r.Add(l.Split(' ')[1]);
            return r;
        }

        internal static void Register()
        {
            RulesProgram.Add("C5.T5.ladder_each_rung_once_in_order", () =>
            {
                var d = new Driver();
                d.Offer(1, 0f);
                d.Accept();
                Check.Eq(FfaReadmitEntryRules.RdmNext.JoinRoom, d.Answer("claim", Claimed(), 10f), "claimed joins the room");
                d.C.State = FfaReadmitEntryRules.RdmState.Binding;   // the first bind sent
                Check.Eq(FfaReadmitEntryRules.RdmNext.BindAgain, d.Answer("bind", Refused("uncorroborated", 1), 15f), "uncorroborated binds again");
                Check.Eq(FfaReadmitEntryRules.RdmNext.ArmLate, d.Answer("bind", Admitted(), 20f), "admitted kind r arms the late entry");
                d.SelfKept();
                Check.Eq(FfaReadmitEntryRules.RdmNext.Done,
                         d.Answer("entered", new FfaReadmitEntryRules.RdmAnswer { Status = "entered", N = 1 }, 30f), "entered spends the token");
                Check.Seq(new[] { "offered", "claimed", "bound", "entered" }, Rungs(d.Lines), "the four client rungs, once each, in order");
                Check.Eq("[FFA-RDM] offered lobby=1a2b3c4d slot=1 n=1", d.Lines[0], "the offered line");
                Check.Eq("[FFA-RDM] claimed lobby=1a2b3c4d slot=1 n=1", d.Lines[1], "the claimed line");
                Check.Eq("[FFA-RDM] bound lobby=1a2b3c4d slot=1 n=1 game=3 actor=42", d.Lines[2], "the bound line carries g and the actor");
                Check.Eq("[FFA-RDM] entered lobby=1a2b3c4d slot=1 n=1 game=3 actor=42", d.Lines[3], "the entered line carries g and the actor");
                foreach (var l in d.Lines) Check.True(!l.Contains(Token), "no ladder line carries the token");
            });

            RulesProgram.Add("C5.T5.ladder_repeats_add_no_line", () =>
            {
                var d = new Driver();
                d.Offer(1, 0f);
                d.Offer(1, 5f);                                          // the same hold refreshed
                d.Accept();
                d.Answer("claim", Claimed(), 10f);
                d.Answer("claim", Claimed(), 11f);                       // a repeated claimed answer
                d.C.State = FfaReadmitEntryRules.RdmState.Binding;
                d.Answer("bind", Refused("uncorroborated", 1), 15f);     // a retried bind, twice
                d.Answer("bind", Refused("uncorroborated", 1), 20f);
                Check.Seq(new[] { "offered", "claimed" }, Rungs(d.Lines), "a refreshed offer, a repeated answer and a retried bind add no line");
                // A second drop after entry (step 10) is a new hold: offered again, n = 2.
                d.Answer("bind", Admitted(), 25f);
                d.SelfKept();
                d.Answer("entered", new FfaReadmitEntryRules.RdmAnswer { Status = "entered", N = 1 }, 30f);
                d.Offer(2, 100f);
                Check.Eq("[FFA-RDM] offered lobby=1a2b3c4d slot=1 n=2", d.Lines[d.Lines.Count - 1], "hold n + 1 is offered afresh");
            });

            RulesProgram.Add("C5.T5.ladder_refusals_name_no_later_rung", () =>
            {
                var d = new Driver();
                d.Offer(1, 0f);
                d.Accept();
                d.Answer("claim", Claimed(), 10f);
                d.C.State = FfaReadmitEntryRules.RdmState.Binding;
                Check.Eq(FfaReadmitEntryRules.RdmNext.Leave, d.Answer("bind", Refused("hold_lapsed"), 15f), "a refused bind leaves");
                d.SelfKept();
                Check.Seq(new[] { "offered", "claimed" }, Rungs(d.Lines), "a refused bind names neither bound nor entered");
                var e = new Driver();
                e.Offer(1, 0f);
                e.Accept();
                Check.Eq(FfaReadmitEntryRules.RdmNext.Probe, e.Answer("claim", Refused("lobby_closed"), 5f), "a refused claim probes");
                Check.Seq(new[] { "offered" }, Rungs(e.Lines), "a refused claim names no claimed rung");
            });

            // ---------------------------------------------------------- T4.13 negative control (client half)
            RulesProgram.Add("C5.T4.13.flag_false_no_rung", () =>
            {
                var d = new Driver();
                // Flag false: the offer answer is readmissible 0, so Offer is never called.
                Check.True(!FfaReadmitEntryRules.DiscoveryOffers(0, "lobbyA", 1, 90), "readmissible 0 offers nothing");
                d.SelfKept();                                            // a kind l late seat, never readmitted
                Check.Eq(0, d.Lines.Count, "no ladder line at all");
                Check.True(FfaReadmitEntryRules.LadderLine(null, Lobby8, d.C) == null, "no rung, no line");
            });
        }
    }
}
