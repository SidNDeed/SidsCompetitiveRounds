using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── K1: S1 client, the classifier, convergence, the point in flight ─

        private static R.Pin TeamPin(string room = "team_ab12", bool hold = true, string mode = R.MODE_TEAM)
        {
            R.ClearPins();
            R.PinRoom(room, hold, mode, "series-1", new[] { "1001", "1002", "1003", "1004" });
            return R.PinFor(room);
        }

        /// <summary>A departure every condition of S1 step 5 admits.</summary>
        private static R.GateInputs Admitted(R.Pin pin)
        {
            return new R.GateInputs
            {
                Pin = pin, IsSpec = false, Uid = "1002", Slot = 1, Tgid = R.GidValue("g-7", true), Trd = "",
                Th = "", VLeave = false, SlotMarked = false,
                QuorumCapable = true, LocalUnauthorized = false, LocalInMatch = true, RoomName = pin != null ? pin.Room : "",
            };
        }

        /// <summary>The point model of T1.5: two teams, a purge, vanilla's
        /// RPCA_NextRound fence (isTransitioning) and PlayerDied's master arm.</summary>
        private sealed class PointSim
        {
            internal sealed class P { public int Slot, Team; public bool Alive = true, Present = true, Body = true; }
            internal readonly List<P> Players = new List<P>();
            internal bool Battle = true, Transitioning, Hung;
            internal int NextRounds, Winner = -1;
            internal bool Purged;

            internal PointSim(params int[] teams) { for (int i = 0; i < teams.Length; i++) Players.Add(new P { Slot = i, Team = teams[i] }); }

            private IEnumerable<P> List() { return Purged ? Players.Where(p => p.Present) : Players; }

            internal int TeamsAlive()
            {
                var alive = new HashSet<int>();
                foreach (var p in List()) if (p.Alive && (p.Present || !Purged)) if (p.Team == 0 || p.Team == 1) alive.Add(p.Team);
                return alive.Count;
            }

            private int LastTeamAlive() { foreach (var p in List()) if (p.Alive) return p.Team; return -1; }

            internal void RpcaNextRound(int losing, int winning)
            {
                if (Transitioning) return;
                Battle = false;
                Transitioning = true;
                NextRounds++;
                Winner = winning;
            }

            /// <summary>Vanilla PlayerDied: its first statement reads the
            /// killed body's owner; a departed body throws there.</summary>
            internal void VanillaPlayerDied(P killed)
            {
                if (killed == null || !killed.Body) { Hung = true; throw new NullReferenceException("killedPlayer.data.view.Owner"); }
                if (TeamsAlive() < 2) { int l, w; R.MasterArm(LastTeamAlive(), out l, out w); RpcaNextRound(l, w); }
            }

            internal void Leave(int slot) { var p = Players[slot]; p.Present = false; p.Body = false; p.Alive = false; }

            internal void RealDeath(int slot) { var p = Players[slot]; p.Alive = false; try { VanillaPlayerDied(p); } catch { } }

            /// <summary>One resolver tick on the master after the purge.</summary>
            internal R.Resolve Tick(double since, char observed, int leaverSlot)
            {
                if (since >= R.PurgeDelay) Purged = true;
                var a = R.PointAfterLeave(since, observed, Battle, TeamsAlive());
                if (a != R.Resolve.NextRound) return a;
                if (R.ViaMasterArm) { int l, w; R.MasterArm(LastTeamAlive(), out l, out w); RpcaNextRound(l, w); }
                else { try { VanillaPlayerDied(Players[leaverSlot]); } catch { } }
                return a;
            }
        }

        private enum Seat { Normal, Detached, Throws }

        /// <summary>T1.2: every survivor either suppresses or runs today; a
        /// client running today leaves, which every suppressing client sees as
        /// a second fighter departure and expires. Answers null when the room
        /// converged and the hold ended at that second departure.</summary>
        private static string Converge(Seat[] survivors)
        {
            var pin = TeamPin();
            var suppressing = new List<int>();
            var today = new List<int>();
            for (int i = 0; i < survivors.Length; i++)
            {
                R.HoldGate.Clear();   // each client keeps its own memo
                bool s;
                if (survivors[i] == Seat.Detached) s = false;
                else if (survivors[i] == Seat.Throws) s = R.HoldGate.DecideOnce(7, () => { throw new InvalidOperationException("classifier"); });
                else s = R.HoldGate.DecideOnce(7, () => Admitted(pin));
                (s ? suppressing : today).Add(i);
            }
            if (today.Count == 0 && survivors.Any(x => x != Seat.Normal))
                return "every client suppresses although one could not classify; no client leaves, the hold never ends at a departure";
            foreach (var c in suppressing)
                if (!R.SecondDepartureEnds(true, true)) return "client " + c + " kept holding after a second departure";
            return null;
        }

        private static void RegisterK1()
        {
            // T1.1: the gate is true only when every condition holds.
            Add("t11_gate_all_true", () => Expect("decide", R.HoldGate.Decide(Admitted(TeamPin())), true));
            Add("t11_gate_each_false", () =>
            {
                var pin = TeamPin();
                var cases = new List<KeyValuePair<string, Action<R.GateInputs>>>
                {
                    new KeyValuePair<string, Action<R.GateInputs>>("flag false", i => { R.ClearPins(); R.PinRoom("team_ab12", false, R.MODE_TEAM, "s", new[] { "1002" }); i.Pin = R.PinFor("team_ab12"); }),
                    new KeyValuePair<string, Action<R.GateInputs>>("no pin", i => i.Pin = null),
                    new KeyValuePair<string, Action<R.GateInputs>>("not on roster", i => i.Uid = "9999"),
                    new KeyValuePair<string, Action<R.GateInputs>>("spectator", i => i.IsSpec = true),
                    new KeyValuePair<string, Action<R.GateInputs>>("no started G", i => i.Tgid = R.GidValue("g-7", false)),
                    new KeyValuePair<string, Action<R.GateInputs>>("no G", i => i.Tgid = ""),
                    new KeyValuePair<string, Action<R.GateInputs>>("voluntary", i => i.VLeave = true),
                    new KeyValuePair<string, Action<R.GateInputs>>("held before in G", i => i.Trd = R.TrdAppend("", "g-7", 1, 'h')),
                    new KeyValuePair<string, Action<R.GateInputs>>("live hold", i => i.Th = new R.HoldKey { HoldId = "h1", Slot = 3, Team = 1, G = "g-7", State = 'o', Seq = 1 }.Format()),
                    new KeyValuePair<string, Action<R.GateInputs>>("drift", i => i.SlotMarked = true),
                };
                foreach (var c in cases)
                {
                    var i = Admitted(pin);
                    c.Value(i);
                    if (R.HoldGate.Decide(i)) return "suppressed with " + c.Key;
                    pin = TeamPin();
                }
                // an earlier hold of ANOTHER slot, or of this slot in another game, does not refuse
                var j = Admitted(pin);
                j.Trd = R.TrdAppend(R.TrdAppend("", "g-7", 2, 'h'), "g-6", 1, 'r');
                return Expect("other slot or game", R.HoldGate.Decide(j), true);
            });
            // T1.1, M1.1: a quorum of in-room capabilities is not the flag. The
            // member without the build already left, so every present actor
            // advertises; the server latched false at the issue.
            Add("t11_quorum_not_flag", () =>
            {
                R.ClearPins();
                R.PinRoom("team_ab12", false, R.MODE_TEAM, "s", new[] { "1001", "1002", "1003", "1004" });
                var i = Admitted(R.PinFor("team_ab12"));
                i.QuorumCapable = true;
                return Expect("decide", R.HoldGate.Decide(i), false);
            });
            // T1.1, M1.2: a stale local authorization cache is no input.
            Add("t11_stale_cache", () =>
            {
                var i = Admitted(TeamPin());
                i.LocalUnauthorized = true;
                i.LocalInMatch = false;
                return Expect("decide", R.HoldGate.Decide(i), true);
            });
            // T1.1, M1.3: the mode is the pinned one; a hosted lobby room name
            // carries no mode prefix.
            Add("t11_hosted_lobby", () =>
            {
                var pin = TeamPin("lobby_3f2a9c", true, R.MODE_OVT);
                var i = Admitted(pin);
                i.Slot = 2;
                return Expect("decide", R.HoldGate.Decide(i), true);
            });
            // S1 step 5: memoised per actor; a throwing read answers today.
            Add("t11_memo", () =>
            {
                R.HoldGate.Clear();
                var pin = TeamPin();
                bool a = R.HoldGate.DecideOnce(5, () => Admitted(pin));
                bool b = R.HoldGate.DecideOnce(5, () => { var i = Admitted(pin); i.VLeave = true; return i; });
                bool c = R.HoldGate.DecideOnce(6, () => { throw new Exception("read"); });
                return All(Expect("first", a, true), Expect("memo", b, true), Expect("throw", c, false));
            });
            // T1.2: four-client model: one detached, one throwing, one normal.
            Add("t12_four_clients", () => Converge(new[] { Seat.Normal, Seat.Detached, Seat.Throws }));
            // T1.2: three-client model (1v2): the other survivor's classifier throws.
            Add("t12_three_clients_throw", () => Converge(new[] { Seat.Normal, Seat.Throws }));
            // T1.5: 2v2 with the partner alive: the point continues two against one.
            Add("t15_2v2_partner_alive", () =>
            {
                var sim = new PointSim(0, 0, 1, 1);
                sim.Leave(0);
                var a = sim.Tick(0.8, 'p', 0);
                return All(Expect("action", a, R.Resolve.Nothing), Expect("rounds", sim.NextRounds, 0), Expect("battle", sim.Battle, true));
            });
            // T1.5: 2v2 whole team down: the other team takes the point, once.
            Add("t15_2v2_team_down", () =>
            {
                var sim = new PointSim(0, 0, 1, 1);
                sim.RealDeath(1);
                sim.Leave(0);
                sim.Tick(0.8, 'o', 0);
                sim.Tick(1.2, 'o', 0);
                return All(Expect("hung", sim.Hung, false), Expect("rounds", sim.NextRounds, 1), Expect("winner", sim.Winner, 1));
            });
            // T1.5: 1v2 solo drop: the duo takes the point.
            Add("t15_ovt_solo_drop", () =>
            {
                var sim = new PointSim(0, 1, 1);
                sim.Leave(0);
                sim.Tick(0.9, 'p', 0);
                return All(Expect("hung", sim.Hung, false), Expect("rounds", sim.NextRounds, 1), Expect("winner", sim.Winner, 1));
            });
            // T1.5: 1v2 duo drop with the partner alive, then dead.
            Add("t15_ovt_duo_partner", () =>
            {
                var sim = new PointSim(0, 1, 1);
                sim.Leave(1);
                var a = sim.Tick(0.9, 'x', 1);
                if (a != R.Resolve.Nothing || sim.NextRounds != 0) return "the point did not continue one against one";
                sim.RealDeath(2);
                return All(Expect("rounds", sim.NextRounds, 1), Expect("winner", sim.Winner, 0));
            });
            // T1.5: a real death and the resolver in the same frame, both orders:
            // exactly one RPCA_NextRound takes effect.
            Add("t15_same_frame", () =>
            {
                var a = new PointSim(0, 0, 1, 1);
                a.Leave(0);
                a.Purged = true;
                a.RealDeath(1);
                a.Tick(0.8, 'p', 0);
                var b = new PointSim(0, 0, 1, 1);
                b.Leave(0);
                b.Purged = true;
                b.Players[1].Alive = false;
                b.Tick(0.8, 'p', 0);
                try { b.VanillaPlayerDied(b.Players[1]); } catch { }
                return All(Expect("death first", a.NextRounds, 1), Expect("resolver first", b.NextRounds, 1),
                           Expect("winner a", a.Winner, 1), Expect("winner b", b.Winner, 1));
            });
            // T1.5 with T2.4's handover shape, M1.10: nothing resolves before
            // the hold state for this drop is observed, whatever the timer.
            Add("t15_handover_wait", () =>
            {
                var sim = new PointSim(0, 0, 1, 1);
                sim.RealDeath(1);
                sim.Leave(0);
                var early = sim.Tick(0.9, '\0', 0);
                int before = sim.NextRounds;
                var late = sim.Tick(1.6, 'p', 0);
                return All(Expect("before p", early, R.Resolve.Wait), Expect("rounds before p", before, 0),
                           Expect("after p", late, R.Resolve.NextRound), Expect("rounds", sim.NextRounds, 1));
            });
            // T1.6 client half: no pin (the server latched nothing or the
            // capability is unsent): no room is flagged and no departure is
            // suppressed: the cascade of today.
            Add("t16_unpinned_today", () =>
            {
                R.ClearPins();
                R.HoldGate.Clear();
                var i = Admitted(null);
                bool any = false;
                for (int actor = 1; actor <= 4; actor++) any |= R.HoldGate.DecideOnce(actor, () => i);
                return All(Expect("flagged", R.Flagged("team_ab12"), false), Expect("suppressed", any, false));
            });
            // S1 step 7: the election of today as a pure rule, unchanged.
            Add("t1_dc_today", () =>
            {
                var census = new List<DcReporterElection.Peer>();
                // me 1003 team 1, leaver 1001 team 0; survivors 1002 (t0), 1003 (t1, me), 1004 (t1)
                var surv = new List<R.DcSurvivor> { new R.DcSurvivor(1002, 0, false, 2), new R.DcSurvivor(1003, 1, true, 3), new R.DcSurvivor(1004, 1, false, 4) };
                var prompt = R.DecideDc(1003, 1, 0, 1001, true, -1, surv, census);
                var watch = R.DecideDc(1004, 1, 0, 1001, true, -1, new List<R.DcSurvivor> { surv[0], new R.DcSurvivor(1003, 1, false, 3), new R.DcSurvivor(1004, 1, true, 4) }, census);
                var down = R.DecideDc(1002, 0, 0, 1001, true, -1, new List<R.DcSurvivor> { new R.DcSurvivor(1002, 0, true, 2), new R.DcSurvivor(1003, 1, false, 3), surv[2] }, census);
                var floor = R.DecideDc(1003, 1, 0, 1001, false, 4, surv, new List<DcReporterElection.Peer> { new DcReporterElection.Peer("1002", 0), new DcReporterElection.Peer("1004", 1) });
                return All(Expect("prompt", prompt.Kind, R.DcKind.Prompt), Expect("watch", watch.Kind, R.DcKind.Fallback),
                           Expect("elected", watch.ElectedActor, 3), Expect("stand down", down.Kind, R.DcKind.StandDown),
                           Expect("floor unique", floor.Unique, false), Expect("floor", floor.Kind, R.DcKind.Floor));
            });
        }
    }
}
