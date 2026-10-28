using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;
    using N = TeamHoldNet;
    using Stage = TeamHoldRules.ReturnRoute.Stage;

    internal static partial class Program
    {
        // ── K3: S3 client, the snapshot gate, the token check, the route ───

        /// <summary>The honest snapshot of a 2v2 hold of slot 1: team 0 won the
        /// point in flight after the drop (points 0-0 to 1-0).</summary>
        private static R.Snapshot Snap()
        {
            var s = new R.Snapshot { HoldId = "h1", G = "g-7", R0 = 1, R1 = 0, P0 = 1, P1 = 0, W0 = 1, W1 = 0, Ledger = "0123456789abcdef",
                                     BR0 = 1, BR1 = 0, BP0 = 0, BP1 = 0 };
            s.BNames.AddRange(new[] { "Barrage", "Leech" });
            s.BDeals = 2;
            string[][] decks = { new[] { "Bomb", "Spray", "Grow" }, new[] { "Barrage", "Leech" }, new[] { "Shield", "Fast" }, new[] { "Spray" } };
            for (int i = 0; i < 4; i++)
            {
                var st = new R.SlotState { Slot = i, Deaths = i == 1 ? 3 : 2 };
                st.Names.AddRange(decks[i]);
                st.Deals = st.Names.Count;
                s.Slots.Add(st);
            }
            return s;
        }

        private static string HeldCheckpoint(R.Snapshot s) { return R.BoundaryDigest(s.BR0, s.BR1, s.BP0, s.BP1, s.BNames); }

        /// <summary>The returner's gate with the server's own facts taken from
        /// the HONEST snapshot (tally, checkpoint, G) and the remaining seats'
        /// digests given.</summary>
        private static string Gate(string tsn, IList<string> digests, int expected, R.Snapshot honest)
        {
            R.Snapshot snap;
            return R.CheckSnapshot(tsn, digests, expected, honest.G, honest.W0, honest.W1, HeldCheckpoint(honest), 1, 2, out snap);
        }

        private static string Sha256Hex(string t)
        {
            using (var sha = System.Security.Cryptography.SHA256.Create())
            {
                var sb = new StringBuilder();
                foreach (var b in sha.ComputeHash(Encoding.UTF8.GetBytes(t))) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        /// <summary>Drives a return route through its stages with a stub
        /// per stage; a stage whose stub is false never completes. Answers
        /// the route after <paramref name="until"/> seconds.</summary>
        private static R.ReturnRoute Drive(Func<Stage, bool> stub, double until)
        {
            var route = new R.ReturnRoute();
            for (int i = 0; i <= (int)(until * 10); i++)
            {
                double t = i / 10.0;
                route.Tick(t);
                var s = route.S;
                if (s == Stage.Ended || s == Stage.Released) break;
                if (stub(s)) route.Done(s, true, t);
            }
            return route;
        }

        private static void ReplaySetup()
        {
            var r = new R.ReturnRoute { S = Stage.Activate, ClaimedAt = 0, Slot = 1 };
            Stage2Replay.TeamHoldReturn.Setup(r);
            Stage2Replay.TeamHoldLoop._survivorReplay = null;
            Stage2Replay.TeamHoldLoop.Releases = 0;
            Stage2Replay.PlayerManager.instance = new Stage2Replay.PlayerManager();
            Stage2Replay.PlayerManager.instance.players.Add(new Stage2Replay.Player { PlayerID = 1 });
        }

        private static R.DropCut ReplayCut() { return new R.DropCut { Slot = 1, G = "g1" }; }
        private static R.HoldKey ReplayKey(char state) { return new R.HoldKey { Slot = 1, HoldId = "h1", State = state, BoundActor = 12 }; }

        private static void RegisterReplayControls()
        {
            Add("t3_replay_skipped_bound", () =>
            {
                ReplaySetup();
                var cut = ReplayCut(); var key = ReplayKey('e');
                if (!Stage2Replay.TeamHoldLoop.SurvivorWired) return "Tick bypasses survivor gate";
                if (Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key)) return "released on launch";
                Stage2Replay.TeamHoldReturn.Frame();
                if (Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key)) return "released before final yield";
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("release after last yield", Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key), true),
                    Expect("one replay", Stage2Replay.TeamHoldReturn.Starts, 1),
                    Expect("card order", string.Join(",", Stage2Replay.TeamHoldReturn.Applied), "A,B"));
            });
            Add("t3_replay_bound_then_entered", () =>
            {
                ReplaySetup(); var cut = ReplayCut(); var key = ReplayKey('b');
                Stage2Replay.TeamHoldLoop.SurvivorReplay(cut, key);
                Stage2Replay.TeamHoldReturn.Frame(); Stage2Replay.TeamHoldReturn.Frame();
                key.State = 'e';
                return All(Expect("released", Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key), true),
                    Expect("one replay", Stage2Replay.TeamHoldReturn.Starts, 1));
            });
            Add("t3_replay_missing", () =>
            {
                ReplaySetup(); Stage2Replay.TeamHoldReturn.FailCard = "B";
                var cut = ReplayCut(); var key = ReplayKey('e');
                Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key);
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("failed", Stage2Replay.TeamHoldLoop._survivorReplay.State, Stage2Replay.TeamHoldReturn.ReplayState.Failed),
                    Expect("no release", Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key), false));
            });
            Add("t3_replay_throw", () =>
            {
                ReplaySetup(); Stage2Replay.TeamHoldReturn.ThrowCard = "B";
                var cut = ReplayCut(); var key = ReplayKey('e');
                Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key);
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("failed", Stage2Replay.TeamHoldLoop._survivorReplay.State, Stage2Replay.TeamHoldReturn.ReplayState.Failed),
                    Expect("no release", Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key), false));
            });
            Add("t3_replay_room_change", () =>
            {
                ReplaySetup(); var cut = ReplayCut(); var key = ReplayKey('e');
                Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key);
                Stage2Replay.TeamHoldReturn.LiveRoom = new object();
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("failed stale room", Stage2Replay.TeamHoldLoop._survivorReplay.State, Stage2Replay.TeamHoldReturn.ReplayState.Failed),
                    Expect("stale result rejected", Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key), false),
                    Expect("no stale apply", Stage2Replay.TeamHoldReturn.Applied.Count, 1));
            });
            Add("t3_replay_deck_changed", () =>
            {
                ReplaySetup(); var cut = ReplayCut(); var key = ReplayKey('e');
                Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key);
                SeatDeckLog.Seed(1, new List<string> { "A", "B", "C" }, 0);
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("changed snapshot fails", Stage2Replay.TeamHoldLoop._survivorReplay.State, Stage2Replay.TeamHoldReturn.ReplayState.Failed),
                    Expect("no release", Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key), false));
            });
            Add("t3_replay_body_replaced", () =>
            {
                ReplaySetup(); var cut = ReplayCut(); var key = ReplayKey('e');
                Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key);
                Stage2Replay.PlayerManager.instance.players[0] = new Stage2Replay.Player { PlayerID = 1 };
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("replaced body fails", Stage2Replay.TeamHoldLoop._survivorReplay.State, Stage2Replay.TeamHoldReturn.ReplayState.Failed),
                    Expect("no release", Stage2Replay.TeamHoldLoop.SurvivorEntered(cut, key), false),
                    Expect("no extra apply", Stage2Replay.TeamHoldReturn.Applied.Count, 1));
            });
            Add("t3_replay_invalidation", () =>
            {
                ReplaySetup(); var work = Stage2Replay.TeamHoldReturn.Replay(false, 1, "h1", 12);
                var old = work;
                Stage2Replay.TeamHoldReturn.InvalidateReplay(ref work);
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("cleared", work, null), Expect("late work failed", old.State, Stage2Replay.TeamHoldReturn.ReplayState.Failed),
                    Expect("no stale apply", Stage2Replay.TeamHoldReturn.Applied.Count, 1));
            });
            Add("t3_replay_returner", () =>
            {
                ReplaySetup(); var route = Stage2Replay.TeamHoldReturn._route; var claim = Stage2Replay.TeamHoldReturn.Claim;
                if (!Stage2Replay.TeamHoldReturn.ActivationWired) return "Tick bypasses activation gate";
                Stage2Replay.TeamHoldReturn.ActivateReplay(route, claim, 1);
                Stage2Replay.TeamHoldReturn.PostEntered(route, claim);
                if (route.S != Stage.Activate || Stage2Replay.TeamHoldReturn.EnteredPosts != 0) return "entered on replay launch";
                Stage2Replay.TeamHoldReturn.Frame();
                Stage2Replay.TeamHoldReturn.ActivateReplay(route, claim, 2);
                Stage2Replay.TeamHoldReturn.PostEntered(route, claim);
                if (route.S != Stage.Activate || Stage2Replay.TeamHoldReturn.EnteredPosts != 0) return "entered before final yield";
                Stage2Replay.TeamHoldReturn.Frame();
                Stage2Replay.TeamHoldReturn.ActivateReplay(route, claim, 3);
                Stage2Replay.TeamHoldReturn.PostEntered(route, claim);
                return All(Expect("one entered post", Stage2Replay.TeamHoldReturn.EnteredPosts, 1),
                    Expect("entered stage", route.S, Stage.Entered));
            });
            Add("t3_replay_returner_failure", () =>
            {
                ReplaySetup(); Stage2Replay.TeamHoldReturn.FailCard = "A";
                var route = Stage2Replay.TeamHoldReturn._route; var claim = Stage2Replay.TeamHoldReturn.Claim;
                Stage2Replay.TeamHoldReturn.ActivateReplay(route, claim, 1);
                Stage2Replay.TeamHoldReturn.PostEntered(route, claim);
                return All(Expect("route ended", route.S, Stage.Ended), Expect("no entered", Stage2Replay.TeamHoldReturn.EnteredPosts, 0));
            });
            Add("t3_replay_route_left", () =>
            {
                ReplaySetup(); var route = Stage2Replay.TeamHoldReturn._route;
                Stage2Replay.TeamHoldReturn.ActivateReplay(route, Stage2Replay.TeamHoldReturn.Claim, 1);
                var work = Stage2Replay.TeamHoldReturn._returnReplay;
                Stage2Replay.TeamHoldReturn.OnRoomLeft();
                Stage2Replay.TeamHoldReturn.Frame();
                return All(Expect("route cleared", Stage2Replay.TeamHoldReturn._route, null),
                    Expect("work invalidated", work.State, Stage2Replay.TeamHoldReturn.ReplayState.Failed),
                    Expect("no late apply", Stage2Replay.TeamHoldReturn.Applied.Count, 1));
            });
            Add("t3_replay_completed_exit", () =>
            {
                ReplaySetup(); Stage2Replay.TeamHoldReturn._route.S = Stage.Released;
                Stage2Replay.TeamHoldReturn.OnRoomLeft();
                return All(Expect("completed route retired", Stage2Replay.TeamHoldReturn._route, null),
                    Expect("no abort after entry", Stage2Replay.TeamHoldReturn.EndCalls, 0));
            });
            Add("t3_replay_body_wait", () =>
            {
                ReplaySetup(); Stage2Replay.PlayerManager.instance.players.Clear();
                return All(Expect("missing body fences", Stage2Replay.TeamHoldLoop.SurvivorEntered(ReplayCut(), ReplayKey('e')), false),
                    Expect("no premature replay", Stage2Replay.TeamHoldReturn.Starts, 0));
            });
            Add("t3_bound_entered", () =>
            {
                var writer = new R.Writer(); writer.OnDrop(0, 1, 0, "g1", 10, "request1");
                writer.OnOpen(1, 200, new N.OpenAnswer { Opened = true, HoldId = "h1", HoldS = 30, Seq = 1 });
                writer.OnState(2, new N.StateAnswer { HoldId = "h1", G = "g1", State = 'e', Seq = 4, BoundActor = 12 });
                var pending = new R.Writer(); pending.OnDrop(0, 1, 0, "g1", 10, "request1");
                pending.OnByRoom(2, 200, new N.StateAnswer { HoldId = "h1", G = "g1", State = 'e', Seq = 4, BoundActor = 12 });
                return All(Expect("state e actor", writer.Key.BoundActor, 12), Expect("by-room e actor", pending.Key.BoundActor, 12));
            });
        }

        private static void RegisterK3()
        {
            RegisterReplayControls();
            // T3.3: the honest snapshot passes with every remaining digest.
            Add("t33_honest", () =>
            {
                var s = Snap();
                string d = R.SnapshotDigest(s);
                return All(Expect("2v2", Gate(s.Format(), new[] { d, d }, 2, s), null),
                           Expect("1v2", Gate(s.Format(), new[] { d }, 1, s), null),
                           Expect("round trip", R.TryParseSnapshot(s.Format(), out R.Snapshot back) && back.Format() == s.Format(), true));
            });
            // T3.3: one mutation each in the master's cr_tsn; the remaining
            // seats publish the honest digest.
            Add("t33_mutations", () =>
            {
                var honest = Snap();
                string d = R.SnapshotDigest(honest);
                var muts = new List<KeyValuePair<string, Action<R.Snapshot>>>
                {
                    new KeyValuePair<string, Action<R.Snapshot>>("rounds", s => s.R1 = 1),
                    new KeyValuePair<string, Action<R.Snapshot>>("points", s => s.P1 = 1),
                    new KeyValuePair<string, Action<R.Snapshot>>("wins", s => s.W1 = 1),
                    new KeyValuePair<string, Action<R.Snapshot>>("another slot deck", s => s.Slots[2].Names[1] = "Grow"),
                    new KeyValuePair<string, Action<R.Snapshot>>("deals", s => { s.Slots[3].Names.Add("Spray"); s.Slots[3].Deals = 2; }),
                    new KeyValuePair<string, Action<R.Snapshot>>("deaths", s => s.Slots[0].Deaths = 1),
                    new KeyValuePair<string, Action<R.Snapshot>>("ledger", s => s.Ledger = "fedcba9876543210"),
                    new KeyValuePair<string, Action<R.Snapshot>>("G", s => s.G = "g-8"),
                    new KeyValuePair<string, Action<R.Snapshot>>("boundary", s => s.BP1 = 1),
                };
                foreach (var m in muts)
                {
                    var s = Snap();
                    m.Value(s);
                    if (Gate(s.Format(), new[] { d, d }, 2, honest) == null) return "accepted a falsified " + m.Key;
                }
                return null;
            });
            // T3.3, M3.7: the 1v2 duo colluding (master and the other remaining
            // seat agree on the falsified values): the server checkpoint of the
            // held solo's own boundary refuses.
            Add("t33_colluding_duo", () =>
            {
                var honest = Snap();
                var deck = Snap();
                deck.BNames.RemoveAt(1); deck.BDeals = 1;
                deck.Slots[1].Names.RemoveAt(1); deck.Slots[1].Deals = 1;
                var pts = Snap();
                pts.BP1 = 1; pts.P1 = 2; pts.P0 = 0; pts.BP0 = 0; pts.R0 = 1;
                string a = Gate(deck.Format(), new[] { R.SnapshotDigest(deck) }, 1, honest);
                string b = Gate(pts.Format(), new[] { R.SnapshotDigest(pts) }, 1, honest);
                return All(Expect("shed card", a, "boundary checkpoint mismatch"), Expect("moved points", b, "boundary checkpoint mismatch"));
            });
            // T3.3, M3.6: in 1v2 the one other remaining seat's digest must be present.
            Add("t33_ovt_digest_absent", () =>
            {
                var s = Snap();
                return All(Expect("absent", Gate(s.Format(), new string[] { null }, 1, s), "digest missing"),
                           Expect("2v2 one absent", Gate(s.Format(), new[] { R.SnapshotDigest(s), null }, 2, s), "digest missing"));
            });
            Add("t33_delta_legal", () =>
            {
                var round = Snap();
                round.BP0 = 1; round.P0 = 0; round.R0 = 2; round.BR0 = 1;
                var two = Snap();
                two.P0 = 2;
                return All(Expect("round transition", R.DeltaLegal(round, 2), true), Expect("two points", R.DeltaLegal(two, 2), false));
            });

            // T3.7 client half: the master's token check. Session A binds
            // actor B advertising A without T: refused; genuine A with T passes.
            Add("t37_token", () =>
            {
                string verifier = Sha256Hex("tok-genuine");
                return All(Expect("no cr_rdt", R.TokenOk(null, "h1", verifier), false),
                           Expect("other hold", R.TokenOk("h0:tok-genuine", "h1", verifier), false),
                           Expect("guessed T", R.TokenOk("h1:tok-guess", "h1", verifier), false),
                           Expect("empty T", R.TokenOk("h1:", "h1", verifier), false));
            });
            Add("t37_genuine", () => Expect("genuine", R.TokenOk("h1:tok-genuine", "h1", Sha256Hex("tok-genuine")), true));

            // T3.8: the U2 route over stubs. Complete, then each missing stage:
            // the route ends at the entry bound and the boundary stays closed.
            Add("t38_route_complete", () =>
            {
                var r = Drive(s => true, 10);
                return All(Expect("released", r.BoundaryReleased, true), Expect("stage", r.S, Stage.Released));
            });
            Add("t38_route_missing", () =>
            {
                foreach (var missing in new[] { Stage.Bind, Stage.Token, Stage.Latch, Stage.Snapshot, Stage.Register, Stage.Activate, Stage.Entered })
                {
                    var r = Drive(s => s != missing, 120);
                    if (r.BoundaryReleased) return "released without " + missing;
                    if (r.S != Stage.Ended || r.EndReason != "entry bound") return "missing " + missing + " left the route at " + r.S + " (" + r.EndReason + ")";
                }
                var outOfOrder = new R.ReturnRoute();
                outOfOrder.Done(Stage.Claim, true, 0);
                outOfOrder.Done(Stage.Snapshot, true, 1);
                return All(Expect("out of order", outOfOrder.S, Stage.Ended), Expect("released", outOfOrder.BoundaryReleased, false));
            });
            Add("t38_route_refused", () =>
            {
                var r = new R.ReturnRoute();
                r.Done(Stage.Claim, true, 0);
                r.Done(Stage.Join, true, 1);
                r.Done(Stage.Bind, false, 2, "actor_conflict");
                return All(Expect("ended", r.S, Stage.Ended), Expect("reason", r.EndReason, "actor_conflict"), Expect("released", r.BoundaryReleased, false));
            });

            // T3.9: no hold row, readmissible 0: nothing shown.
            Add("t39_nothing_shown", () =>
            {
                N.MineAnswer a, b, c;
                N.TryParseMine(200, "{\"readmissible\":0}", out a);
                N.TryParseMine(404, "{\"detail\":\"Not Found\"}", out b);
                N.TryParseMine(200, "{\"readmissible\":1,\"hold_id\":\"h1\",\"mode\":\"team\",\"room_name\":\"team_x\",\"slot\":1,\"team\":0,\"hold_s\":100,\"series_tally\":[1, 0]}", out c);
                return All(Expect("zero", R.DiscoveryShows(a), false), Expect("404", R.DiscoveryShows(b), false),
                           Expect("live", R.DiscoveryShows(c), true));
            });
        }
    }
}

// Engine/transport stubs only. ReplayRun, its outcome predicates and the
// release/entered/activation dispatch methods are extracted by run_stage2.py.
namespace CompetitiveRounds.Stage2Replay
{
    internal static partial class TeamHoldReturn
    {
        internal static ReplayWork _returnReplay;
        internal static TeamHoldRules.ReturnRoute _route;
        internal static TeamHoldNet.MineAnswer _claimed;
        internal static TeamHoldNet.ClaimAnswer Claim;
        internal static bool _enteredPosted;
        internal static string _snapWrittenFor, _tbdFor;
        internal static int EndCalls;
        internal static void End(string why, string reason) { EndCalls++; InvalidateReplay(ref _returnReplay); _route = null; }
        internal static void Finish() { _route = null; }
        internal static double Now { get { return 1; } }
        internal static object LiveRoom { get { return PhotonNetwork.CurrentRoom; } set { PhotonNetwork.CurrentRoom = value; } }
        internal static int _replayGeneration, Starts, EnteredPosts;
        internal static string FailCard, ThrowCard;
        internal static readonly List<string> Applied = new List<string>();
        internal static System.Collections.IEnumerator Pending;
        internal static bool Activated() { return true; }
        internal static void Fail(TeamHoldRules.ReturnRoute.Stage stage, string reason) { _route.Done(stage, false, 1, reason); }
        internal static void Setup(TeamHoldRules.ReturnRoute route)
        {
            _returnReplay = null; _route = route; _enteredPosted = false; EndCalls = 0;
            _claimed = new TeamHoldNet.MineAnswer { HoldId = "h1" };
            Claim = new TeamHoldNet.ClaimAnswer { Slot = 1, G = "g1" };
            LiveRoom = new object(); PhotonNetwork.InRoom = true; _replayGeneration = 1; Starts = EnteredPosts = 0;
            SeatDeckLog.OnGameStart(); SeatDeckLog.Seed(1, new List<string> { "A", "B" }, 0);
            FailCard = ThrowCard = null; Applied.Clear(); Pending = null;
            TeamHoldNet.Send = (method, path, body, done) => { EnteredPosts++; };
        }
        internal static CardInfo ResolveCard(string name) { return name == FailCard ? null : new CardInfo { Name = name }; }
        internal static void Frame() { if (Pending != null) Pending.MoveNext(); }
    }
    internal static partial class TeamHoldLoop
    {
        internal static TeamHoldReturn.ReplayWork _survivorReplay;
        internal static int Releases;
        internal static void Release(TeamHoldRules.DropCut cut) { Releases++; }
    }
    internal static class PhotonNetwork
    {
        internal static Peer LocalPlayer = new Peer();
        internal static object CurrentRoom;
        internal static bool InRoom;
        internal sealed class Peer { internal int ActorNumber = 12; }
    }
    internal static class MatchTracker { internal static string LocalSteamId = "1001"; }
    internal sealed class Player
    {
        internal int PlayerID;
        internal object gameObject = new object();
        internal Data data = new Data();
        internal sealed class Data { internal View view = new View(); }
        internal sealed class View { internal int OwnerActorNr = 12; }
    }
    internal sealed class CardInfo { internal string Name; }
    internal static class FfaMode
    {
        internal static bool SpectatorApplyCard(Player body, CardInfo card)
        {
            if (card.Name == TeamHoldReturn.ThrowCard) throw new InvalidOperationException("apply failed");
            TeamHoldReturn.Applied.Add(card.Name); return true;
        }
    }
    internal sealed class GM_ArmsRace
    {
        internal static GM_ArmsRace instance = new GM_ArmsRace();
        internal void StartCoroutine(System.Collections.IEnumerator run)
        {
            TeamHoldReturn.Starts++;
            TeamHoldReturn.Pending = run;
            run.MoveNext();
        }
    }
    internal sealed class PlayerManager
    {
        internal static PlayerManager instance;
        internal List<Player> players = new List<Player>();
        internal Player GetPlayerWithActorID(int actor) { return players.Find(p => p.data.view.OwnerActorNr == actor); }
    }
}
