using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── K4: S4 client, the absent picker and the grant ────────────────

        private static string LiveTh(int slot, char state = 'o')
        {
            return new R.HoldKey { HoldId = "h1", Slot = slot, Team = slot / 2, G = "g-7", State = state, Seq = 1, HoldS = 120, Writer = 2 }.Format();
        }

        /// <summary>Real picks of a slot, committed as the RPCA_Pick seam
        /// commits them (keyed by the card's view).</summary>
        private static void DeckOf(int slot, params string[] names)
        {
            SeatDeckLog.OnGameStart();
            for (int i = 0; i < names.Length; i++) SeatDeckLog.Commit(SeatDeckLog.ViewKey(100 + i), slot, names[i]);
        }

        private static void RegisterK4()
        {
            // T4.3: the drop comes before the phase: the held slot's deal is
            // skipped on every client, the others deal as today.
            Add("t43_before_phase", () =>
            {
                string th = LiveTh(1);
                var set = R.PickerSet(R.MODE_TEAM, false, 0, new[] { 0, 2, 3 }, new[] { 1 }, false);
                return All(Expect("pickers", string.Join(",", set.Select(e => e.Key + "x" + e.Value)), "0x1,1x1"),
                           Expect("skip held", R.SkipDeal(1, th, false), true),
                           Expect("present deals", R.SkipDeal(0, th, true), false));
            });
            // T4.3, M4.5: delayed delivery: the purge has not run yet, so the
            // body still resolves; cr_th decides, never the body.
            Add("t43_delayed_purge", () => All(
                Expect("skip with a body", R.SkipDeal(1, LiveTh(1), true), true),
                Expect("no hold, no body", R.SkipDeal(1, "", false), false),
                Expect("ended hold", R.SkipDeal(1, LiveTh(1, 'x'), false), false)));
            // T4.3: the drop comes during the own deal: every client ends the
            // pick locally on reading the hold.
            Add("t43_during_own_deal", () => All(
                Expect("picking the held slot", R.DonePickingLocally(true, 1, LiveTh(1)), true),
                Expect("picking another slot", R.DonePickingLocally(true, 0, LiveTh(1)), false),
                Expect("not picking", R.DonePickingLocally(false, 1, LiveTh(1)), false)));
            // T4.3, M4.6: the own pick was sent before the leave: received
            // first, it is kept and the grant for that deal is ignored.
            Add("t43_after_own_pick", () =>
            {
                DeckOf(1, "Barrage", "Leech", "Bomb");
                var o = R.ApplyGrant("g-7", "g-7", 1, 2, "Shield");
                SeatDeckLog.Seat seat; SeatDeckLog.TryGetSeat(1, out seat);
                return All(Expect("outcome", o, R.GrantOutcome.Superseded), Expect("deck", string.Join(",", seat.Names), "Barrage,Leech,Bomb"));
            });
            Add("t43_grant_applies", () =>
            {
                DeckOf(1, "Barrage", "Leech");
                var o = R.ApplyGrant("g-7", "g-7", 1, 2, "Shield");
                var again = R.ApplyGrant("g-7", "g-7", 1, 2, "Shield");
                var other = R.ApplyGrant("g-6", "g-7", 1, 3, "Bomb");
                SeatDeckLog.Seat seat; SeatDeckLog.TryGetSeat(1, out seat);
                return All(Expect("applied", o, R.GrantOutcome.Applied), Expect("repeat", again, R.GrantOutcome.Superseded),
                           Expect("another game", other, R.GrantOutcome.Refused), Expect("deck", string.Join(",", seat.Names), "Barrage,Leech,Shield"));
            });
            // No record, no card.
            Add("t43_no_record", () =>
            {
                R.RecordEntry0 = null;
                return All(Expect("entry", R.Entry0("g-7", 1, 2), null), Expect("late", R.RecordLate(0, 4.0, false), true),
                           Expect("in time", R.RecordLate(0, 3.9, false), false), Expect("arrived", R.RecordLate(0, 9, true), false));
            });
            Add("t43_tap_codec", () =>
            {
                string g, card; int slot, k;
                bool ok = R.TryParseTap(R.TapFormat("g-7", 1, 2, "Shield"), out g, out slot, out k, out card);
                return All(Expect("parsed", ok, true), Expect("fields", g + "|" + slot + "|" + k + "|" + card, "g-7|1|2|Shield"),
                           Expect("malformed", R.TryParseTap("g-7:1:x:Shield", out g, out slot, out k, out card), false));
            });
            // T4.5: the 1v2 solo with two initial deals: both entries recorded
            // and granted in order.
            Add("t45_ovt_two_initial", () =>
            {
                var set = R.PickerSet(R.MODE_OVT, true, -1, new[] { 1, 2 }, new[] { 0 }, true);
                string pickers = string.Join(",", set.Select(e => e.Key + "x" + e.Value));
                SeatDeckLog.OnGameStart();
                var rec = new Dictionary<string, string> { { "g-7|0|0", "Barrage" }, { "g-7|0|1", "Leech" } };
                R.RecordEntry0 = (g, s, k) => { string c; return rec.TryGetValue(g + "|" + s + "|" + k, out c) ? c : null; };
                var outcomes = new List<R.GrantOutcome>();
                for (int k = 0; k < set.First(e => e.Key == 0).Value; k++) outcomes.Add(R.ApplyGrant("g-7", "g-7", 0, k, R.Entry0("g-7", 0, k)));
                R.RecordEntry0 = null;
                SeatDeckLog.Seat seat; SeatDeckLog.TryGetSeat(0, out seat);
                return All(Expect("pickers", pickers, "0x2,1x1,2x1"), Expect("outcomes", string.Join(",", outcomes), "Applied,Applied"),
                           Expect("deck", seat != null ? string.Join(",", seat.Names) : "", "Barrage,Leech"));
            });
        }
    }
}
