using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Item 19 fix pass 1: the behaviour controls, compiled against a
    /// TREE's plugin/AvatarDefaultRules.cs (item19_controls.py copies that one
    /// file next to this one), so the same scenarios run against the build
    /// round 1 tree and the fix tip. It uses only the API both trees have.
    /// Fix pass 4 (H9loop) adds the debt order of fix pass 3
    /// (HomeBeforeApply, HomeAfterApply: on the round 4 tree b963d618 and
    /// later) and reaches the fix pass 4 rule DefersSelectEdge by reflection,
    /// so the same probe runs on the round 4 tree and the fix tip.
    /// Each line is "PROBE id PASS|FAIL | detail"; PASS means the required
    /// behaviour holds on that tree. Exit 0 always: the verdicts are the
    /// output, read by the runner.</summary>
    internal static class Probe
    {
        private const string FaceKey = "cr_face";

        private static AvatarFaceIds[] Faces()
        {
            var f = new AvatarFaceIds[10];
            f[0] = AvatarFaceIds.Of(0, 0, 0, 0);
            for (int i = 1; i < 10; i++) f[i] = AvatarFaceIds.Of(i, i, i, i);
            return f;
        }

        private static AvatarLoaderView Loader()
        {
            var a = new bool[20];
            for (int i = 0; i < 20; i++) a[i] = true;
            return new AvatarLoaderView { Eyes = a, Mouths = a, Accessories = a };
        }

        private static AvatarLivenessIn NotLive() => new AvatarLivenessIn { ManagerExists = true };
        private static AvatarLivenessIn Live() => new AvatarLivenessIn { ManagerExists = true, IsPlaying = true };
        private static IList<string> Modded() => new List<string> { "cr_trail_sku" };
        private static IList<string> Unmodded() => new List<string> { "pid" };

        private static AvatarFacingIn Room(bool issued, params IList<string>[] others) => new AvatarFacingIn
        {
            InRoom = true, RoomExists = true, ModIssuedRoom = issued,
            OtherFighterKeys = new List<IList<string>>(others), FaceKey = FaceKey,
        };

        private static AvatarFacingIn Menu() => new AvatarFacingIn { FaceKey = FaceKey };

        private static AvatarSetting Set(int m, int v) => new AvatarSetting { Auto = true, Modded = m, Vanilla = v };

        private sealed class Seat
        {
            internal int Live, Home = -1, Applies;
            internal Seat(int live) { Live = live; }
            internal AvatarDecision Step(AvatarRules r, AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s)
            {
                var d = r.Evaluate(new AvatarEvalIn { Liveness = l, Facing = f, Setting = s, Faces = Faces(), Loader = Loader(), Live = Live, Home = Home });
                if (d.Gated || d.NothingToRead) return d;
                if (d.Apply >= 0) { Live = d.Apply; Applies++; }
                Home = d.NewHome;
                return d;
            }
        }

        private static void Line(string id, bool ok, string detail)
        {
            Console.WriteLine("PROBE " + id + " " + (ok ? "PASS" : "FAIL") + " | " + detail);
        }

        /// <summary>Item 19 fix pass 4 (H9, M3): a seat moved as AvatarDefaults
        /// moves it since fix pass 3 (HomeBeforeApply, the apply, the
        /// read-back, HomeAfterApply), whose apply is the owned select with the
        /// SelectFace postfix (E9) Harmony runs on every normal return. The
        /// postfix defers when the tree's rules have DefersSelectEdge and it
        /// says so (reflection: a tree without the rule never defers), else it
        /// evaluates again, one select deeper. A select nested past Bound gives
        /// up, so a re-entry without a bound ends instead of overflowing the
        /// stack. NoOp: every select returns normally without committing.</summary>
        private sealed class ReentrantSeat
        {
            internal const int Bound = 8;
            internal int Live, Home = -1, Selects, Depth, Deepest;
            internal bool NoOp;
            private readonly AvatarRules r;
            private readonly System.Reflection.MethodInfo defers;

            internal ReentrantSeat(AvatarRules rules, int live)
            {
                r = rules;
                Live = live;
                defers = typeof(AvatarRules).GetMethod("DefersSelectEdge",
                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public);
            }

            internal bool HasGuard => defers != null;

            internal void Evaluate(AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s)
            {
                var d = r.Evaluate(new AvatarEvalIn { Liveness = l, Facing = f, Setting = s, Faces = Faces(), Loader = Loader(), Live = Live, Home = Home });
                if (d.Gated || d.NothingToRead) return;
                int held = r.HomeBeforeApply(Home, d);
                Home = held;
                int after = d.Apply >= 0 ? Apply(d.Apply, l, f, s) : Live;
                Home = r.HomeAfterApply(held, d, after);
            }

            private int Apply(int slot, AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s)
            {
                Selects++;
                Depth++;
                if (Depth > Deepest) Deepest = Depth;
                try
                {
                    if (Depth > Bound) return Live;
                    if (!NoOp) Live = slot;
                    bool defer = defers != null && (bool)defers.Invoke(r, new object[] { Depth });
                    if (!defer) Evaluate(l, f, s);
                }
                finally { Depth--; }
                return Live;
            }
        }

        private static int Main()
        {
            var r = new AvatarRules();

            // BR-H1: an issued room with zero other fighters keeps the own face.
            var solo = new Seat(3);
            var ds = solo.Step(r, NotLive(), Room(true), Set(2, 1));
            Line("BRH1", ds.Apply < 0 && solo.Live == 3,
                 "issued room, zero others: facing=" + ds.Facing + " apply=" + ds.Apply + " live=" + solo.Live);

            // H8 / BR-H1: an issued room containing an unmodded fighter is Vanilla.
            var mixed = r.FacingOf(Room(true, Modded(), Unmodded()));
            Line("H8", mixed == AvatarFacing.Vanilla, "issued room + an unmodded fighter: facing=" + mixed);

            // H9: leave while the old manager still reports a live game.
            var h9 = new Seat(3);
            h9.Step(r, NotLive(), Room(false, Unmodded()), Set(2, 1));
            int forced = h9.Live;
            h9.Step(r, Live(), Room(false, Unmodded()), Set(2, 1));
            var d9 = h9.Step(r, Live(), Menu(), Set(2, 1));
            Line("H9", forced == 1 && h9.Live == 3 && h9.Home == -1,
                 "forced=" + forced + " | leave, live manager: census=" + d9.Facing + " live=" + h9.Live + " home=" + h9.Home);

            // M3: a disconnect alone (no OnLeftRoom) restores; a repeated exit writes nothing.
            var m3 = new Seat(3);
            m3.Step(r, NotLive(), Room(false, Modded()), Set(2, 1));
            m3.Step(r, Live(), Room(false, Modded()), Set(2, 1));
            m3.Step(r, Live(), Menu(), Set(2, 1));
            int one = m3.Applies, liveOne = m3.Live;
            m3.Step(r, Live(), Menu(), Set(2, 1));
            Line("M3", liveOne == 3 && one == 2 && m3.Applies == 2 && m3.Home == -1,
                 "disconnect alone: applies=" + one + " live=" + liveOne + " | repeated exit: applies=" + m3.Applies + " home=" + m3.Home);

            // BR-M3: one preset slot set changes nothing.
            var b3 = new Seat(5);
            var d3 = b3.Step(r, NotLive(), Room(false, Modded()), Set(3, -1));
            var b3v = new Seat(5);
            var d3v = b3v.Step(r, NotLive(), Room(false, Unmodded()), Set(-1, 1));
            Line("BRM3", d3.Apply < 0 && d3v.Apply < 0,
                 "only modded set, modded room: apply=" + d3.Apply + " | only vanilla set, vanilla room: apply=" + d3v.Apply);

            // BR-M4: an unreadable facing with no established room is not Vanilla.
            var c4 = r.Census(NotLive(), new AvatarFacingIn { Unreadable = true, FaceKey = FaceKey });
            Line("BRM4", c4 != AvatarFacing.Vanilla, "unreadable, InRoom never established: census=" + c4);

            // H9 (fix pass 4): a persistent no-op select is bounded: one select
            // per trigger, the one debt kept, no nesting; repaid once the select works.
            var rs = new ReentrantSeat(r, 3);
            rs.Evaluate(NotLive(), Room(false, Unmodded()), Set(2, 1));      // 3 -> 1, home 3
            int forcedR = rs.Live, heldR = rs.Home;
            rs.NoOp = true;
            int s0 = rs.Selects;
            rs.Evaluate(NotLive(), Menu(), Set(2, 1));                       // E6
            int e6 = rs.Selects - s0, h6 = rs.Home;
            rs.Evaluate(NotLive(), Menu(), Set(2, 1));                       // E7
            int e7 = rs.Selects - s0 - e6, h7 = rs.Home, deep = rs.Deepest;
            rs.NoOp = false;
            rs.Evaluate(NotLive(), Menu(), Set(2, 1));                       // a later trigger, the select working
            Line("H9loop", forcedR == 1 && heldR == 3 && e6 == 1 && e7 == 1 && deep == 1 && h6 == 3 && h7 == 3 && rs.Live == 3 && rs.Home == -1,
                 "the rules have DefersSelectEdge=" + rs.HasGuard + " | a no-op select: E6 selects " + e6 + " home " + h6
                 + " | E7 selects " + e7 + " home " + h7 + " | deepest nesting " + deep + " (bound " + ReentrantSeat.Bound + ")"
                 + " | the select works again: live " + rs.Live + " home " + rs.Home);
            return 0;
        }
    }
}
