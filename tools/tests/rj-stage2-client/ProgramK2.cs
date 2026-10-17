using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;
    using N = TeamHoldNet;

    internal static partial class Program
    {
        // ── K2: S2 client, envelope, writer, ceilings, fence ───────────────

        private static R.HoldKey Room(char state, int seq, string holdId = "h1", string g = "g-7")
        {
            return new R.HoldKey { HoldId = holdId, Slot = 1, Team = 0, G = g, State = state, Seq = seq, HoldS = 120, Writer = 2 };
        }

        private static N.StateAnswer Server(char state, int seq, string holdId = "h1", string g = "g-7", bool closed = false)
        {
            return new N.StateAnswer { HoldId = holdId, G = g, State = state, Seq = seq, DeadlineS = 100, Closed = closed || state == 'x' };
        }

        /// <summary>A scripted server for the writer: each call is answered
        /// at once from the script (status, answer), or never (null entry).</summary>
        private sealed class WriterRig
        {
            internal readonly R.Writer W = new R.Writer();
            internal readonly List<string> Th = new List<string>();
            internal readonly List<R.Writer.Op> Calls = new List<R.Writer.Op>();
            internal Func<R.Writer.Op, Tuple<int, object>> Answer = op => null;
            internal double DoneAt = -1;

            internal void Run(double now, List<R.Writer.Action> acts)
            {
                foreach (var a in acts)
                {
                    Calls.Add(a.Op);
                    if (a.Op == R.Writer.Op.WriteTh) { Th.Add(a.Key.Format()); if (a.Key.State == 'x' && DoneAt < 0) DoneAt = now; continue; }
                    if (a.Op == R.Writer.Op.AppendTrd) continue;
                    var ans = Answer(a.Op);
                    if (ans == null) continue;
                    switch (a.Op)
                    {
                        case R.Writer.Op.PostOpen: Run(now, W.OnOpen(now, ans.Item1, ans.Item2 as N.OpenAnswer)); break;
                        case R.Writer.Op.GetByRoom: Run(now, W.OnByRoom(now, ans.Item1, ans.Item2 as N.StateAnswer)); break;
                        case R.Writer.Op.GetState: Run(now, W.OnState(now, ans.Item2 as N.StateAnswer)); break;
                        case R.Writer.Op.PostEnd: Run(now, W.OnEndAnswer(now)); break;
                    }
                }
            }

            internal void TickUntil(double from, double to)
            {
                int n = (int)Math.Round((to - from) * 10);
                for (int i = 0; i <= n; i++) { double t = from + i / 10.0; Run(t, W.Tick(t)); }
            }

            internal char LastState() { R.HoldKey k; return Th.Count > 0 && R.TryParseHold(Th[Th.Count - 1], out k) ? k.State : '\0'; }
        }

        /// <summary>A client's local end time under the ceilings, given the
        /// room states it reads over time and its own server reads.</summary>
        private static double ClientEnds(double dropAt, Func<double, R.HoldKey> room, Func<double, N.StateAnswer> server, double until)
        {
            var c = new R.Ceilings();
            c.SawP(dropAt);
            int n = (int)Math.Round((until - dropAt) * 10);
            for (int i = 0; i <= n; i++)
            {
                double t = dropAt + i / 10.0;
                var k = room(t);
                if (k != null)
                {
                    if (k.State == 'p') c.SawP(t);
                    var v = R.Verify(k, server(t));
                    if (v == R.Verdict.End) return t;
                    if (v == R.Verdict.Act)
                    {
                        if (k.State == 'x' || k.State == 'e') return t;
                        if (k.State == 'o') c.SawO(t, k.HoldS);
                        if (k.State == 'c' || k.State == 'b') c.SawC(t);
                    }
                }
                if (c.Passed(t)) return t;
            }
            return -1;
        }

        /// <summary>The fence model (T2.6): executes a transition table step
        /// by step; the fence step waits while the hold is held. Answers the
        /// steps executed before the hold is released.</summary>
        private static List<R.Step> RunWhileHeld(R.Step[] steps, bool pickDue)
        {
            var done = new List<R.Step>();
            foreach (var s in steps)
            {
                if (s == R.Step.Fence) break;   // held: the coroutine waits here
                if (s == R.Step.PickPhase && !pickDue) continue;
                done.Add(s);
            }
            return done;
        }

        private static void RegisterK2()
        {
            // T2.3: the envelope. A verified state acts; forged, replayed and
            // cross-hold states are inert or end toward today.
            Add("t23_verified_o", () => All(
                Expect("o", R.Verify(Room('o', 1), Server('o', 1)), R.Verdict.Act),
                Expect("c later on server", R.Verify(Room('c', 2), Server('b', 3)), R.Verdict.Act),
                Expect("x closed", R.Verify(Room('x', 4), Server('x', 4)), R.Verdict.Act),
                Expect("p", R.Verify(Room('p', 0, ""), null), R.Verdict.Act)));
            Add("t23_forged_b_e_x", () => All(
                Expect("b no read", R.Verify(Room('b', 3), null), R.Verdict.Inert),
                Expect("b server o", R.Verify(Room('b', 3), Server('o', 1)), R.Verdict.Inert),
                Expect("e server b", R.Verify(Room('e', 4), Server('b', 3)), R.Verdict.Inert),
                Expect("x server open", R.Verify(Room('x', 2), Server('o', 1)), R.Verdict.Inert),
                Expect("x no read", R.Verify(Room('x', 2), null), R.Verdict.Inert)));
            Add("t23_replayed_cross_hold", () => All(
                Expect("o of another hold", R.Verify(Room('o', 1, "h0"), Server('o', 1)), R.Verdict.End),
                Expect("c of another game", R.Verify(Room('c', 2, "h1", "g-6"), Server('c', 2)), R.Verdict.End),
                Expect("e replayed at a later seq", R.Verify(Room('e', 9), Server('e', 4)), R.Verdict.Inert),
                Expect("x of another hold", R.Verify(Room('x', 5, "h0"), Server('x', 5)), R.Verdict.Inert)));
            // T2.3, lane-added: until this client's own read answers, a state
            // after p is pending (inert, bounded by the ceilings); an answered
            // read with nothing parsable shows nothing, so o or c ends.
            Add("t23_read_pending", () => All(
                Expect("o before the read answers", R.Verify(Room('o', 1), null), R.Verdict.Inert),
                Expect("c before the read answers", R.Verify(Room('c', 2), null), R.Verdict.Inert),
                Expect("o read answered empty", R.Verify(Room('o', 1), new N.StateAnswer()), R.Verdict.End),
                Expect("c read answered empty", R.Verify(Room('c', 2), new N.StateAnswer()), R.Verdict.End),
                Expect("b read answered empty", R.Verify(Room('b', 3), new N.StateAnswer()), R.Verdict.Inert)));
            // T2.3: a withholding master (writes o and never mirrors): every
            // client ends at hold_s + 20 s from its verified o.
            Add("t23_withholding", () =>
            {
                double end = ClientEnds(0, t => t < 1 ? Room('p', 0, "") : Room('o', 1), t => Server('o', 1), 400);
                return Expect("ends at hold_s + 20 after o", end >= 140.95 && end <= 141.05, true);
            });

            // T2.4: handover. Promotion before p: the promoted master writes p
            // and appends h, then posts the open.
            Add("t24_promote_before_p", () =>
            {
                var rig = new WriterRig { Answer = op => op == R.Writer.Op.PostOpen ? Tuple.Create(200, (object)new N.OpenAnswer { Opened = true, HoldId = "h1", Seq = 1, HoldS = 120 }) : null };
                rig.Run(0, rig.W.OnDrop(0, 1, 0, "g-7", 2, "req-1"));
                return All(Expect("calls", string.Join(",", rig.Calls.Take(3)), "WriteTh,AppendTrd,PostOpen"),
                           Expect("state", rig.LastState(), 'o'), Expect("phase", rig.W.P, R.Writer.Phase.Mirroring));
            });
            // After p, before the POST: by-room answers 404; the open is
            // reposted with the request key, and the answer resumes step 2.
            Add("t24_after_p_404_repost", () =>
            {
                var rig = new WriterRig
                {
                    Answer = op => op == R.Writer.Op.GetByRoom ? Tuple.Create(404, (object)null)
                                 : op == R.Writer.Op.PostOpen ? Tuple.Create(200, (object)new N.OpenAnswer { Opened = true, HoldId = "h1", Seq = 1, HoldS = 120 }) : null,
                };
                rig.Run(0, rig.W.OnPromoted(0, Room('p', 0, ""), "req-2"));
                return All(Expect("calls", string.Join(",", rig.Calls.Take(2)), "GetByRoom,PostOpen"), Expect("state", rig.LastState(), 'o'));
            });
            // During the POST: by-room finds the row and mirrors it.
            Add("t24_during_post", () =>
            {
                var rig = new WriterRig { Answer = op => op == R.Writer.Op.GetByRoom ? Tuple.Create(200, (object)Server('o', 1)) : null };
                rig.Run(0, rig.W.OnPromoted(0, Room('p', 0, ""), "req-3"));
                return All(Expect("state", rig.LastState(), 'o'), Expect("phase", rig.W.P, R.Writer.Phase.Mirroring));
            });
            // M2.10: a 404 by-room whose repost is never answered ends at the
            // pending bound (10 s), never stalls.
            Add("t24_404_by_room_ends", () =>
            {
                var rig = new WriterRig { Answer = op => op == R.Writer.Op.GetByRoom ? Tuple.Create(404, (object)null) : null };
                rig.Run(0, rig.W.OnPromoted(0, Room('p', 0, ""), "req-4"));
                rig.TickUntil(0, 30);
                return All(Expect("state", rig.LastState(), 'x'), Expect("ended by", rig.DoneAt <= 10.05 && rig.DoneAt >= 0, true));
            });
            // M2.9: point resolution on a promoted master waits for an
            // observed p, o or x, never on the timer alone.
            Add("t24_resolve_waits", () => All(
                Expect("no state", R.PointAfterLeave(5.0, '\0', true, 1), R.Resolve.Wait),
                Expect("p", R.PointAfterLeave(5.0, 'p', true, 1), R.Resolve.NextRound),
                Expect("x", R.PointAfterLeave(5.0, 'x', true, 1), R.Resolve.NextRound)));

            // T2.5: the master writes p and stops: every client ends within 10 s.
            Add("t25_pending_ceiling", () =>
            {
                double end = ClientEnds(0, t => Room('p', 0, ""), t => null, 60);
                return All(Expect("ends", end >= 0, true), Expect("within 10 s", end <= 10.05, true));
            });
            Add("t25_bind_ceiling", () =>
            {
                double end = ClientEnds(0, t => t < 2 ? Room('o', 1) : Room('c', 2), t => t < 2 ? Server('o', 1) : Server('c', 2), 400);
                return Expect("ends 60 s after c", end >= 61.95 && end <= 62.05, true);
            });

            // T2.6: the fence. A point boundary waits before the sync, after
            // every pick, never before the result.
            Add("t26_point_fenced", () =>
            {
                var ran = RunWhileHeld(R.PointSteps, false);
                return All(Expect("battle on while held", ran.Contains(R.Step.BattleOn), false),
                           Expect("sync while held", ran.Contains(R.Step.SyncUp), false),
                           Expect("result shown", ran.Contains(R.Step.Visualize), true),
                           Expect("one fence", R.PointSteps.Count(s => s == R.Step.Fence), 1),
                           Expect("fence before sync", Array.IndexOf(R.PointSteps, R.Step.Fence) + 1, Array.IndexOf(R.PointSteps, R.Step.SyncUp)));
            });
            Add("t26_round_pick_inside", () =>
            {
                var ran = RunWhileHeld(R.RoundSteps, true);
                return All(Expect("pick completes inside the hold", ran.Contains(R.Step.PickPhase), true),
                           Expect("battle on while held", ran.Contains(R.Step.BattleOn), false),
                           Expect("one fence", R.RoundSteps.Count(s => s == R.Step.Fence), 1),
                           Expect("fence before sync", Array.IndexOf(R.RoundSteps, R.Step.Fence) + 1, Array.IndexOf(R.RoundSteps, R.Step.SyncUp)));
            });
            Add("t26_round_no_pick", () =>
            {
                var ran = RunWhileHeld(R.RoundSteps, false);
                return All(Expect("no pick", ran.Contains(R.Step.PickPhase), false), Expect("battle on while held", ran.Contains(R.Step.BattleOn), false));
            });
            // The vanilla statements, in order, with only the fence inserted.
            Add("t26_tables_vanilla", () =>
            {
                string p = string.Join(",", R.PointSteps.Where(s => s != R.Step.Fence));
                string r = string.Join(",", R.RoundSteps.Where(s => s != R.Step.Fence));
                return All(Expect("point", p, "Visualize,Wait1,LoadNext,Wait05,SyncUp,CallInMove,Revive,Wait03,SpeedUp,BattleOn,TransitionOff"),
                           Expect("round", r, "WinVisualize,Wait1,LoadNext,Wait03,Wait1,SpeedUp,PickPhase,SyncUp,SlowDown,CallInMove,Revive,Wait03,SpeedUp,TransitionOff,BattleOn,ShowCounter"));
            });
            Add("t26_fence_states", () => All(
                Expect("p", R.FenceWaits(Room('p', 0, "").Format()), true), Expect("o", R.FenceWaits(Room('o', 1).Format()), true),
                Expect("c", R.FenceWaits(Room('c', 2).Format()), true), Expect("b", R.FenceWaits(Room('b', 3).Format()), true),
                Expect("e", R.FenceWaits(Room('e', 4).Format()), false), Expect("x", R.FenceWaits(Room('x', 5).Format()), false),
                Expect("none", R.FenceWaits(""), false)));

            // T2.9: an unbound transport, and an old box answering 404 to every
            // hold route: the writer ends at once and every client by 10 s.
            Add("t29_unbound_transport", () =>
            {
                N.Send = null;
                var rig = new WriterRig();
                rig.Answer = op =>
                {
                    int st = 0; string body = null;
                    N.Call("POST", N.PathOpen, "{}", (s, b) => { st = s; body = b; });
                    N.OpenAnswer oa; N.TryParseOpen(st, body, out oa);
                    return Tuple.Create(st, (object)oa);
                };
                rig.Run(0, rig.W.OnDrop(0, 1, 0, "g-7", 2, "req-5"));
                var finalRoom = rig.Th.Count > 0 ? rig.Th[rig.Th.Count - 1] : "";
                R.HoldKey fk; R.TryParseHold(finalRoom, out fk);
                double end = ClientEnds(0, t => fk, t => null, 60);
                return All(Expect("writer x", rig.LastState(), 'x'), Expect("writer at once", rig.DoneAt, 0.0),
                           Expect("client within 10 s", end >= 0 && end <= 10.05, true));
            });
            Add("t29_old_box_404", () =>
            {
                var rig = new WriterRig();
                rig.Answer = op =>
                {
                    N.OpenAnswer oa; N.TryParseOpen(404, "{\"detail\":\"Not Found\"}", out oa);
                    return Tuple.Create(404, (object)oa);
                };
                rig.Run(0, rig.W.OnDrop(0, 1, 0, "g-7", 2, "req-6"));
                N.StateAnswer sa;
                bool parsed = N.TryParseState(404, "{\"detail\":\"Not Found\"}", out sa);
                R.HoldKey fk; R.TryParseHold(rig.Th[rig.Th.Count - 1], out fk);
                double end = ClientEnds(0, t => fk, t => sa, 60);
                return All(Expect("writer x", rig.LastState(), 'x'), Expect("state read", parsed, false),
                           Expect("client within 10 s", end >= 0 && end <= 10.05, true));
            });
        }
    }
}
