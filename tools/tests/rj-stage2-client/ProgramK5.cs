using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── K5: S5 client, the expiry from the cut ────────────────────────

        /// <summary>A 2v2 drop of 1001 (team 0). Each survivor decides its
        /// eligibility at the drop (the leave frame) from the census it read
        /// then; the cut latches it.</summary>
        private static Dictionary<long, R.DropCut> CutsAtDrop(bool roomWide, IList<R.DcSurvivor> census, Func<long, IEnumerable<DcReporterElection.Peer>> floor)
        {
            var cuts = new Dictionary<long, R.DropCut>();
            foreach (var me in census)
            {
                var view = census.Select(s => new R.DcSurvivor(s.Sid, s.Team, s.Sid == me.Sid, s.Actor)).ToList();
                var d = R.DecideDc(me.Sid, me.Team, 0, 1001, roomWide, roomWide ? -1 : 4, view, floor(me.Sid));
                cuts[me.Sid] = new R.DropCut { Mode = R.MODE_TEAM, Slot = 0, Team = 0, Eligibility = d.Kind };
            }
            return cuts;
        }

        private static string Reporters(Dictionary<long, R.DropCut> cuts, IList<int> presentAtExpiry)
        {
            var who = new List<string>();
            foreach (var kv in cuts.OrderBy(k => k.Key))
            {
                var ops = R.ExpiryActions(kv.Value, presentAtExpiry);
                foreach (var op in ops) if (op != R.ExpiryOp.VanillaLeave) who.Add(kv.Key + ":" + op);
                if (ops.Count == 0 || ops[ops.Count - 1] != R.ExpiryOp.VanillaLeave) who.Add(kv.Key + ":no-vanilla-leave");
            }
            return string.Join(",", who);
        }

        private static readonly List<R.DcSurvivor> CleanCensus = new List<R.DcSurvivor>
        {
            new R.DcSurvivor(1002, 0, false, 2), new R.DcSurvivor(1003, 1, false, 3), new R.DcSurvivor(1004, 1, false, 4),
        };

        private static void RegisterK5()
        {
            // T5.2: a clean census: the lower id of the team that stayed
            // reports, its partner watches, the leaver's partner stands down;
            // at x exactly that set executes, whoever is present then.
            Add("t52_clean_census", () =>
            {
                var cuts = CutsAtDrop(true, CleanCensus, sid => new List<DcReporterElection.Peer>());
                return All(Expect("at drop", string.Join(",", cuts.OrderBy(k => k.Key).Select(k => k.Key + ":" + k.Value.Eligibility)), "1002:StandDown,1003:Prompt,1004:Fallback"),
                           Expect("at x", Reporters(cuts, new[] { 2, 3 }), "1003:ReportPrompt,1004:ArmFallback"));
            });
            // T5.2: a missing capability: the floor election of today.
            Add("t52_floor", () =>
            {
                var cuts = CutsAtDrop(false, CleanCensus, sid => CleanCensus.Where(s => s.Sid != sid)
                                                                     .Select(s => new DcReporterElection.Peer(s.Sid.ToString(), s.Team)).ToList());
                string drop = string.Join(",", cuts.OrderBy(k => k.Key).Where(k => k.Value.Eligibility == R.DcKind.Floor).Select(k => k.Key.ToString()));
                string atX = string.Join(",", cuts.OrderBy(k => k.Key).Where(k => R.ExpiryActions(k.Value, new[] { 3 }).Contains(R.ExpiryOp.ReportFloor)).Select(k => k.Key.ToString()));
                return All(Expect("floor reporters", atX, drop), Expect("someone reports", drop.Length > 0, true));
            });
            // T5.2, M5.2: the leaver's partner stands down at x too.
            Add("t52_stand_down_kept", () =>
            {
                var cut = new R.DropCut { Mode = R.MODE_TEAM, Eligibility = R.DcKind.StandDown };
                return Expect("ops", string.Join(",", R.ExpiryActions(cut, new[] { 2, 3, 4 })), "VanillaLeave");
            });
            // T5.2, M5.3: a census that changed by x (one survivor left since
            // the drop) elects nothing new: the latched set runs.
            Add("t52_census_changed", () =>
            {
                var cuts = CutsAtDrop(true, CleanCensus, sid => new List<DcReporterElection.Peer>());
                return Expect("at x with one survivor gone", Reporters(cuts, new[] { 3 }), "1003:ReportPrompt,1004:ArmFallback");
            });
            // T5.6, M5.9: a 1v2 expiry reports nothing, whatever was latched.
            Add("t56_ovt_no_report", () =>
            {
                var solo = new R.DropCut { Mode = R.MODE_OVT, Slot = 0, Eligibility = R.DcKind.Floor };
                var duo = new R.DropCut { Mode = R.MODE_OVT, Slot = 2, Eligibility = R.DcKind.Prompt };
                return All(Expect("solo drop", string.Join(",", R.ExpiryActions(solo, new[] { 1, 2 })), "VanillaLeave"),
                           Expect("duo drop", string.Join(",", R.ExpiryActions(duo, new[] { 0, 1 })), "VanillaLeave"));
            });
            // T5.8 client half: flag false: nothing is held, so no cut and no
            // expiry; every departure takes the path of today.
            Add("t58_flag_false_today", () =>
            {
                R.ClearPins();
                R.PinRoom("team_ab12", false, R.MODE_TEAM, "s", new[] { "1001", "1002", "1003", "1004" });
                var i = Admitted(R.PinFor("team_ab12"));
                return All(Expect("held", R.HoldGate.Decide(i), false), Expect("expiry without a cut", R.ExpiryActions(null, null).Count, 0));
            });
        }
    }
}
