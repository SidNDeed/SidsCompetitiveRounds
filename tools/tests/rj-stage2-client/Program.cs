using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    /// <summary>Scripted fixtures over the REAL Stage 2 rules files. One case
    /// per process: `Stage2Tests &lt;case&gt;` prints PASS or FAIL with the reason
    /// and exits 0 only on PASS. `--list` prints every case name. Each case is
    /// a falsifiable sentence of the design (V3 test ids in the names).</summary>
    internal static partial class Program
    {
        private static readonly Dictionary<string, Func<string>> Cases = new Dictionary<string, Func<string>>(StringComparer.Ordinal);

        private static void Add(string name, Func<string> body) { Cases[name] = body; }

        private static int Main(string[] args)
        {
            RegisterK0();
            RegisterLater();
            if (args.Length == 1 && args[0] == "--list")
            {
                foreach (var k in Cases.Keys) Console.WriteLine(k);
                return 0;
            }
            if (args.Length != 1 || !Cases.ContainsKey(args[0]))
            {
                Console.WriteLine("usage: Stage2Tests <case> | --list");
                return 2;
            }
            string why;
            try { why = Cases[args[0]](); }
            catch (Exception ex) { why = "threw " + ex.GetType().Name + ": " + ex.Message; }
            Console.WriteLine(why == null ? "PASS " + args[0] : "FAIL " + args[0] + ": " + why);
            return why == null ? 0 : 1;
        }

        /// <summary>The fixtures of the pieces after K0.</summary>
        private static void RegisterLater()
        {
            RegisterK1();
            RegisterK1Equiv();
            RegisterK2();
            RegisterK3();
            RegisterK4();
            RegisterK5();
            RegisterK6();
            RegisterKX1();
            RegisterKX2();
            RegisterKX3();
            RegisterKX4();
        }

        // ── helpers ─────────────────────────────────────────────────────────

        private static string Names(int slot)
        {
            SeatDeckLog.Seat s;
            if (!SeatDeckLog.TryGetSeat(slot, out s)) return "";
            return string.Join(",", s.Names);
        }

        private static int Deals(int slot)
        {
            SeatDeckLog.Seat s;
            return SeatDeckLog.TryGetSeat(slot, out s) ? s.Deals : 0;
        }

        private static int Deaths(int slot)
        {
            SeatDeckLog.Seat s;
            return SeatDeckLog.TryGetSeat(slot, out s) ? s.Deaths : 0;
        }

        /// <summary>One RPCA_Pick as the seam sees it: intent, original,
        /// postfix (only when the original returned), finalizer.</summary>
        private static void Apply(int viewId, string card, int[] slots, bool throws = false, bool runOriginal = true)
        {
            SeatDeckLog.PickIntent(viewId, card, slots);
            if (!throws) SeatDeckLog.PickCommit(runOriginal);
            SeatDeckLog.PickEnd();
        }

        private static string Expect(string what, object got, object want)
        {
            return Equals(got, want) ? null : what + " was " + (got ?? "null") + ", expected " + (want ?? "null");
        }

        private static string All(params string[] checks)
        {
            foreach (var c in checks) if (c != null) return c;
            return null;
        }

        // ── K0: S0, the seat deck log and the accepted-death ledger ────────

        private static void RegisterK0()
        {
            // T0.1: the opening pick of DoStartGame applies by RPCA_Pick with
            // no end-pick event; every slot logs its card, deals 1.
            Add("t01_opening_2v2", () =>
            {
                SeatDeckLog.OnGameStart();
                for (int i = 0; i < 4; i++) Apply(100 + i, "Card" + i, new[] { i });
                return All(Expect("slot 0", Names(0), "Card0"), Expect("slot 3", Names(3), "Card3"),
                           Expect("deals 2", Deals(2), 1));
            });
            // T0.1: a round pick: the application commits; the end-pick hook
            // observes the same card and writes nothing.
            Add("t01_round_pick", () =>
            {
                SeatDeckLog.OnGameStart();
                for (int i = 0; i < 4; i++) Apply(100 + i, "Card" + i, new[] { i });
                Apply(200, "Round", new[] { 2 });
                SeatDeckLog.ObserveEndPick(2, "Round");
                return All(Expect("slot 2", Names(2), "Card2,Round"), Expect("deals 2", Deals(2), 2),
                           Expect("deals 1", Deals(1), 1));
            });
            // T0.1: the 1v2 solo extra initial pick: two deals in one phase.
            Add("t01_ovt_solo_two", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(100, "SoloA", new[] { 0 });
                Apply(101, "SoloB", new[] { 0 });
                Apply(102, "DuoA", new[] { 1 });
                Apply(103, "DuoB", new[] { 2 });
                return All(Expect("solo", Names(0), "SoloA,SoloB"), Expect("solo deals", Deals(0), 2),
                           Expect("duo deals", Deals(2), 1));
            });
            // T0.1: a team-target application with two actor ids commits one
            // name to each target slot.
            Add("t01_team_target", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(300, "TeamCard", new[] { 2, 3 });
                return All(Expect("slot 2", Names(2), "TeamCard"), Expect("slot 3", Names(3), "TeamCard"),
                           Expect("slot 0", Names(0), ""));
            });
            // T0.1: an application that throws writes nothing and marks the slot.
            Add("t01_throw", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(400, "Boom", new[] { 1 }, throws: true);
                Apply(401, "Fine", new[] { 0 });
                return All(Expect("slot 1", Names(1), ""), Expect("marked", SeatDeckLog.Marked(1), true),
                           Expect("slot 0", Names(0), "Fine"), Expect("slot 0 marked", SeatDeckLog.Marked(0), false));
            });
            // T0.1: a sibling prefix skipped the original: nothing written, no mark.
            Add("t01_skipped", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(450, "Skipped", new[] { 1 }, runOriginal: false);
                return All(Expect("slot 1", Names(1), ""), Expect("marked", SeatDeckLog.Marked(1), false));
            });
            // T0.1: a duplicate observer: the same application delivered twice
            // and the end-pick hook: one entry.
            Add("t01_duplicate", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(500, "Dup", new[] { 1 });
                Apply(500, "Dup", new[] { 1 });
                SeatDeckLog.ObserveEndPick(1, "Dup");
                return All(Expect("slot 1", Names(1), "Dup"), Expect("deals", Deals(1), 1));
            });
            // T0.1: a local replay through OFFLINE_Pick never appends.
            Add("t01_replay", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(600, "A", new[] { 0 });
                Apply(601, "B", new[] { 0 });
                SeatDeckLog.ObserveOfflinePick(0, "A");
                SeatDeckLog.ObserveOfflinePick(0, "B");
                return All(Expect("slot 0", Names(0), "A,B"), Expect("replays", SeatDeckLog.Replays, 2));
            });
            // T0.1: a new game resets the log; the grant is the one logical
            // writer keyed on (k, slot), superseded when the deal already ran.
            Add("t01_reset_and_grant", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(700, "Old", new[] { 1 });
                SeatDeckLog.OnGameStart();
                bool sup;
                bool g0 = SeatDeckLog.CommitGrant(0, 1, "Granted", out sup);
                bool again = SeatDeckLog.CommitGrant(0, 1, "Granted", out sup);
                return All(Expect("slot 1", Names(1), "Granted"), Expect("first", g0, true),
                           Expect("again", again, false), Expect("superseded", sup, true));
            });
            // T0.2: leave before death, then a late RPCA_Die: one death.
            Add("t02_leave_then_die", () =>
            {
                SeatDeckLog.OnGameStart();
                string t = SeatDeckLog.Tuple(0, 0, 1, 0);
                var a = SeatDeckLog.ClaimDeparture(1, t);
                var b = SeatDeckLog.ClaimDie(1, t);
                return All(Expect("departure", a, SeatDeckLog.Claim.Won), Expect("die", b, SeatDeckLog.Claim.Lost),
                           Expect("deaths", Deaths(1), 1));
            });
            // T0.2: death and leave together: one death.
            Add("t02_die_and_leave", () =>
            {
                SeatDeckLog.OnGameStart();
                string t = SeatDeckLog.Tuple(0, 0, 1, 0);
                var a = SeatDeckLog.ClaimDie(1, t);
                var b = SeatDeckLog.ClaimDeparture(1, t);
                return All(Expect("die", a, SeatDeckLog.Claim.Won), Expect("departure", b, SeatDeckLog.Claim.Lost),
                           Expect("deaths", Deaths(1), 1));
            });
            // T0.2: a duplicate RPCA_Die: one death.
            Add("t02_dup_die", () =>
            {
                SeatDeckLog.OnGameStart();
                string t = SeatDeckLog.Tuple(1, 0, 0, 0);
                SeatDeckLog.ClaimDie(2, t);
                SeatDeckLog.ClaimDie(2, t);
                return Expect("deaths", Deaths(2), 1);
            });
            // T0.2: a Phoenix death then a leave during the charge: today
            // counts no death and neither does the ledger.
            Add("t02_phoenix_then_leave", () =>
            {
                SeatDeckLog.OnGameStart();
                string t = SeatDeckLog.Tuple(0, 0, 0, 0);
                SeatDeckLog.ClaimPhoenix(3, t);
                var b = SeatDeckLog.ClaimDeparture(3, t);
                return All(Expect("departure", b, SeatDeckLog.Claim.Lost), Expect("deaths", Deaths(3), 0));
            });
            // T0.2: a Phoenix revive then a real death: one death.
            Add("t02_phoenix_revive_then_die", () =>
            {
                SeatDeckLog.OnGameStart();
                string t = SeatDeckLog.Tuple(0, 0, 0, 0);
                SeatDeckLog.ClaimPhoenix(3, t);
                SeatDeckLog.AdvanceLife(3);
                var b = SeatDeckLog.ClaimDie(3, t);
                return All(Expect("die", b, SeatDeckLog.Claim.Won), Expect("deaths", Deaths(3), 1));
            });
            // T0.2: deaths in two points count twice.
            Add("t02_two_points", () =>
            {
                SeatDeckLog.OnGameStart();
                SeatDeckLog.ClaimDie(0, SeatDeckLog.Tuple(0, 0, 0, 0));
                SeatDeckLog.ClaimDie(0, SeatDeckLog.Tuple(0, 0, 0, 1));
                return Expect("deaths", Deaths(0), 2);
            });
            // S0 step 4: the drift probe: equal is silent; a mismatch marks the
            // slot and is reported once per game.
            Add("t0_drift", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(800, "A", new[] { 1 });
                bool same = SeatDeckLog.DriftCheck(1, new List<string> { "A" });
                bool first = SeatDeckLog.DriftCheck(1, new List<string> { "A", "B" });
                bool second = SeatDeckLog.DriftCheck(1, new List<string> { "A", "B" });
                return All(Expect("same", same, false), Expect("first", first, true), Expect("second", second, false),
                           Expect("marked", SeatDeckLog.Marked(1), true));
            });
        }
    }
}
