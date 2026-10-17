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

        private static void RegisterK3()
        {
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
                N.TryParseMine(200, "{\"readmissible\":1,\"hold_id\":\"h1\",\"mode\":\"team\",\"room_name\":\"team_x\",\"slot\":1,\"team\":0,\"hold_s\":100,\"series_tally\":\"1:0\"}", out c);
                return All(Expect("zero", R.DiscoveryShows(a), false), Expect("404", R.DiscoveryShows(b), false),
                           Expect("live", R.DiscoveryShows(c), true));
            });
        }
    }
}
