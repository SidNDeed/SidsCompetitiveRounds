using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── KX4: registration after the purge, the returner's seeding ────────

        private sealed class Pl
        {
            internal int Id; internal bool Dead;
            internal Pl(int id, bool dead = false) { Id = id; Dead = dead; }
        }

        /// <summary>The prefix then vanilla RegisterPlayer(forceIndex):
        /// vanilla pads with nulls up to the index and assigns
        /// players[forceIndex] (V:PlayerManager.cs:227-240). Returns false
        /// when the prefix refused.</summary>
        private static bool Register(List<Pl> list, Pl p, bool sorted)
        {
            int force = p.Id;
            if (sorted)
            {
                int at = R.PlaceRegistration(list, x => x.Dead, x => x.Id, p.Id, FfaReadmitEntryRules.RegisterIndex);
                if (at < 0) return false;
                force = at;
            }
            while (list.Count <= force) list.Add(null);
            list[force] = p;
            return true;
        }

        /// <summary>The positional consumers (ApplyCardStats.Pick, the
        /// RoundTransition pickers, RevivePlayers, MovePlayers) read a list
        /// with no hole, sorted by PlayerID, every live fighter once.</summary>
        private static string Consumers(List<Pl> list, params int[] want)
        {
            if (list.Any(x => x == null)) return "a null hole at " + list.FindIndex(x => x == null);
            var ids = list.Select(x => x.Id).ToArray();
            return Expect("ids", string.Join(",", ids), string.Join(",", want));
        }

        private static void RegisterKX4()
        {
            // T3.4: a returning high slot after the purge: the list compacted
            // to 0,1 and seat 3 returns; it lands at its sorted index, no hole.
            Add("t34_high_slot", () =>
            {
                R.ClearPins(); R.PinRoom("team_ab12", true, R.MODE_TEAM, "series-1", new[] { "1001", "1002", "1003", "1004" });
                var list = new List<Pl> { new Pl(0), new Pl(1) };
                bool sorted = R.SortedRegistration(false, "team_ab12");
                bool ok = Register(list, new Pl(3), sorted);
                return All(Expect("sorted", sorted, true), Expect("registered", ok, true), Consumers(list, 0, 1, 3));
            });
            // T3.4: a returning low slot against an occupied compacted
            // position: seat 1 returns to 0,2,3 and never replaces seat 2.
            Add("t34_low_slot", () =>
            {
                R.ClearPins(); R.PinRoom("ovt_ef56", true, R.MODE_OVT, "series-3", new[] { "1001", "1002", "1003" });
                var list = new List<Pl> { new Pl(0), new Pl(2), new Pl(3, dead: true) };
                bool ok = Register(list, new Pl(1), R.SortedRegistration(false, "ovt_ef56"));
                return All(Expect("registered", ok, true), Consumers(list, 0, 1, 2));
            });
            // A duplicate PlayerID is refused and the list is unchanged; a
            // room not flagged registers as vanilla does.
            Add("t34_duplicate_and_today", () =>
            {
                R.ClearPins();
                var list = new List<Pl> { new Pl(0), new Pl(1), new Pl(2) };
                bool dup = R.PlaceRegistration(list, x => x.Dead, x => x.Id, 1, FfaReadmitEntryRules.RegisterIndex) >= 0;
                bool today = R.SortedRegistration(false, "team_other");
                bool ffa = R.SortedRegistration(true, "ffa_room");
                return All(Expect("duplicate", dup, false), Consumers(list, 0, 1, 2), Expect("today", today, false), Expect("ffa", ffa, true));
            });
            // S3 step 8: the returner's seeding plan from the snapshot: the
            // score, its draw index = its slot's deals, its cr_cards value.
            Add("tx4_seed_plan", () =>
            {
                var s = new R.Snapshot { HoldId = "h1", G = "g-8", R0 = 1, R1 = 2, P0 = 1, P1 = 0 };
                s.Slots.Add(new R.SlotState { Slot = 0, Deals = 3, Deaths = 1, Names = new List<string> { "A", "B", "C" } });
                s.Slots.Add(new R.SlotState { Slot = 1, Deals = 4, Deaths = 2, Names = new List<string> { "Big Bullet", "Leech", "Bombs Away", "Pristine" } });
                var p = R.PlanSeed(s, 1);
                return All(Expect("score", p.R0 + "-" + p.R1 + " " + p.P0 + "-" + p.P1, "1-2 1-0"), Expect("draw index", p.DrawIndex, 4),
                           Expect("cards", p.Cards, "Big Bullet|Leech|Bombs Away|Pristine"), Expect("names", p.Names.Count, 4));
            });
        }
    }
}
