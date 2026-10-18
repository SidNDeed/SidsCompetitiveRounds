using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── KX2: live points while a hold waits (V3 S2, RJS-M5) ─────────────

        /// <summary>The team channel as the two producers drive it: a post
        /// is created by MaybeSendLivePoints (LiveGate.Create over its own
        /// reading of cr_th) and sent, first and on every retry, only when
        /// LiveGate.Dispatch admits it. Sends land at the server in any order;
        /// the server keeps the greatest pair, and two points in game 1 close
        /// the betting window.</summary>
        private sealed class LiveSim
        {
            internal readonly string Room;
            internal int Created, Dropped, ServerT1, ServerT2;
            internal readonly List<Tuple<long, int, int>> InFlight = new List<Tuple<long, int, int>>();
            internal LiveSim(string room) { Room = room; R.LiveGate.Reset(); }

            /// <summary>One MaybeSendLivePoints tick with the score (t1, t2)
            /// and the room's cr_th as this seat reads it.</summary>
            internal void Tick(int t1, int t2, string roomTh)
            {
                long stamp = R.LiveGate.Create(Room, roomTh);
                if (stamp == 0) return;
                Created++;
                InFlight.Add(Tuple.Create(stamp, t1, t2));
            }

            /// <summary>The send of the in-flight post at <paramref name="i"/>
            /// (its first send or a retry, in whatever order HTTP delivers).</summary>
            internal void Deliver(int i)
            {
                var p = InFlight[i];
                if (!R.LiveGate.Dispatch(p.Item1, Room)) { Dropped++; return; }
                ServerT1 = Math.Max(ServerT1, p.Item2); ServerT2 = Math.Max(ServerT2, p.Item3);
            }

            internal int Pair { get { return Math.Max(ServerT1, ServerT2); } }
        }

        private static string HoldTh(char state, int slot = 1, string g = "g-7")
        {
            return new R.HoldKey { HoldId = state == 'p' ? "" : "h1", Slot = slot, Team = slot / 2, G = g, State = state, Seq = 1, HoldS = 110, Writer = 2 }.Format();
        }

        private static void RegisterKX2()
        {
            // T2.7: the open is delayed beyond the point result. The writer
            // wrote p (its compare-and-set not yet echoed, so the room still
            // reads no hold) and the drop's point result raises the score to
            // 2-1: the post created after the writer's observation never
            // dispatches; the 1-1 post created before it, delivered late
            // (HTTP reordered), is sent as today. The server's pair stays at 1.
            Add("t27_open_delayed_reordered", () =>
            {
                var s = new LiveSim("team_ab12");
                s.Tick(1, 1, null);                       // post A, before the hold
                R.LiveGate.Observe(s.Room, HoldTh('p'));  // the writer's own write
                s.Tick(2, 1, null);                       // the point result; the room has no echo yet
                s.Deliver(1);                             // post B first ...
                s.Deliver(0);                             // ... and A after it
                return All(Expect("created", s.Created, 2), Expect("dropped", s.Dropped, 1),
                           Expect("server pair", s.Pair, 1), Expect("server t2", s.ServerT2, 1));
            });
            // T2.7: a post is never created while the room reads p (nor o, c,
            // b), the 20 s refresh included; the retry of a post created
            // before the hold still goes.
            Add("t27_no_post_while_held", () =>
            {
                var s = new LiveSim("team_ab12");
                s.Tick(1, 0, null);
                foreach (var st in new[] { 'p', 'o', 'c', 'b' }) { s.Tick(2, 0, HoldTh(st)); s.Tick(2, 0, HoldTh(st)); }
                s.Deliver(0); s.Deliver(0);
                return All(Expect("created", s.Created, 1), Expect("dropped", s.Dropped, 0),
                           Expect("server pair", s.Pair, 1), Expect("held", R.LiveGate.Held(s.Room), true));
            });
            // The observation lifts at the same hold's x and the channel runs
            // as today; an older hold's x left in the room does not lift a
            // newer hold; another room is never held.
            Add("t27_lift_and_rooms", () =>
            {
                var s = new LiveSim("team_ab12");
                R.LiveGate.Observe(s.Room, HoldTh('p', 1, "g-8"));
                s.Tick(2, 0, HoldTh('x', 1, "g-7"));      // the older game's x
                s.Deliver(0);
                bool heldAfterOld = R.LiveGate.Held(s.Room);
                bool otherRoom = R.LiveGate.Dispatch(99, "team_other");
                s.Tick(2, 0, HoldTh('x', 1, "g-8"));      // this hold ended
                s.Deliver(1);
                return All(Expect("old x lifts", heldAfterOld, true), Expect("first dropped", s.Dropped, 1),
                           Expect("other room", otherRoom, true), Expect("held after x", R.LiveGate.Held(s.Room), false),
                           Expect("server pair", s.Pair, 2), Expect("unstamped", R.LiveGate.Dispatch(0, s.Room), true));
            });
        }
    }
}
