using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Item 19's executable checks (design section 5.1), run by
    /// tools/client-rules-harness as suite "avatardefaults". Harness-only: the
    /// mutants below never ship in the plugin.
    ///
    /// Every check is THREE case lines: the claim against the real rules, the
    /// claim against ONE mutant (that line passes only when the claim goes
    /// red), and the claim against a negative control (a runnable change to
    /// the same method that keeps its meaning; that line passes only when the
    /// claim stays green). A check whose mutant line fails is a check that
    /// cannot fail (#342/#391). The design's separators (the input a mutant
    /// is told apart by) live inside each claim and are printed in got=.</summary>
    internal static class AvatarDefaultRulesCases
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private const string FaceKey = "cr_face";

        // ---- fixtures ---------------------------------------------------

        private static AvatarFaceIds[] Faces()
        {
            var f = new AvatarFaceIds[10];
            f[0] = AvatarFaceIds.Of(0, 0, 0, 0);          // never authored
            f[1] = AvatarFaceIds.Of(1, 1, 1, 1);          // clean
            f[2] = AvatarFaceIds.Of(1001, 2, 2, 2);       // a custom eye: not clean
            f[3] = AvatarFaceIds.Of(3, 3, 3, 3);
            f[4] = AvatarFaceIds.Of(4, 4, 4, 4);
            f[5] = AvatarFaceIds.Of(5, 5, 5, 5);
            f[6] = new AvatarFaceIds();                   // a null playerFaces entry
            f[7] = AvatarFaceIds.Of(7, 7, 7, 7);
            f[8] = AvatarFaceIds.Of(8, 8, 8, 8);
            f[9] = AvatarFaceIds.Of(9, 9, 9, 9);
            return f;
        }

        private static bool[] All(int n) { var a = new bool[n]; for (int i = 0; i < n; i++) a[i] = true; return a; }

        private static AvatarLoaderView Loader()
        {
            var acc = All(20);
            acc[15] = false;                              // a null hole in the base array
            return new AvatarLoaderView { Eyes = All(20), Mouths = All(20), Accessories = acc };
        }

        private static AvatarLivenessIn NotLive() => new AvatarLivenessIn { ManagerExists = true };
        private static AvatarLivenessIn Live() => new AvatarLivenessIn { ManagerExists = true, IsPlaying = true };

        private static IList<string> Modded() => new List<string> { "cr_trail_sku", "cr_pcolor_sku" };
        private static IList<string> Unmodded() => new List<string> { "pid" };
        private static IList<string> FaceOnly() => new List<string> { FaceKey };

        private static AvatarFacingIn Room(bool modIssued, params IList<string>[] others)
        {
            return new AvatarFacingIn
            {
                InRoom = true, RoomExists = true, ModIssuedRoom = modIssued,
                OtherFighterKeys = new List<IList<string>>(others), FaceKey = FaceKey,
            };
        }

        private static AvatarFacingIn Menu() => new AvatarFacingIn { FaceKey = FaceKey };

        private static AvatarSetting Set(bool auto, int modded, int vanilla)
            => new AvatarSetting { Auto = auto, Modded = modded, Vanilla = vanilla };

        private static AvatarEvalIn In(AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s, int live, int home)
        {
            return new AvatarEvalIn { Liveness = l, Facing = f, Setting = s, Faces = Faces(), Loader = Loader(), Live = live, Home = home };
        }

        /// <summary>A seat: the live selection and the remembered value, moved
        /// by each decision exactly as AvatarDefaults moves them.</summary>
        private sealed class Seat
        {
            internal int Live, Home = -1, Applies, Switches, Publishes;
            internal Seat(int live) { Live = live; }
            internal AvatarDecision Step(AvatarRules r, AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s)
            {
                var d = r.Evaluate(In(l, f, s, Live, Home));
                if (d.Gated || d.NothingToRead) return d;
                if (d.Apply >= 0) { Live = d.Apply; Applies++; }
                if (d.Publish) Publishes++;
                if (d.Switched != AvatarSwitched.None) Switches++;
                Home = d.NewHome;
                return d;
            }
        }

        private static readonly AvatarFacing[] Decided = { AvatarFacing.Undecided, AvatarFacing.Modded, AvatarFacing.Vanilla };
        private static readonly int[] Slots = { -1, 0, 1, 2, 3, 6, 9, 12 };

        // ---- the checks ---------------------------------------------------

        private delegate bool Claim(AvatarRules r, out string got);

        private static bool T1(AvatarRules r, out string got)
        {
            var l = Loader();
            bool m1 = r.VanillaClean(AvatarFaceIds.Of(-1, 1, 1, 1), l);
            bool e20 = r.VanillaClean(AvatarFaceIds.Of(20, 1, 1, 1), l);
            bool e999 = r.VanillaClean(AvatarFaceIds.Of(999, 1, 1, 1), l);
            bool e19 = r.VanillaClean(AvatarFaceIds.Of(19, 1, 1, 1), l);
            bool hole = r.VanillaClean(AvatarFaceIds.Of(1, 1, 1, 15), l);
            bool custom = r.VanillaClean(AvatarFaceIds.Of(1001, 1, 1, 1), l);
            got = "clean(-1)=" + m1 + " clean(20)=" + e20 + " clean(999)=" + e999 + " clean(19)=" + e19
                + " clean(detail2 on a null hole)=" + hole + " clean(1001)=" + custom;
            return !m1 && !e20 && !e999 && e19 && !hole && !custom;
        }

        private static bool T2(AvatarRules r, out string got)
        {
            var all = r.FacingOf(Room(false, Modded(), Modded(), Modded()));
            var one = r.FacingOf(Room(false, Modded(), Unmodded(), Unmodded()));
            got = "3-of-3 modded=" + all + " 1-of-3 modded=" + one;
            return all == AvatarFacing.Modded && one == AvatarFacing.Vanilla;
        }

        private static bool T3(AvatarRules r, out string got)
        {
            var zero = r.FacingOf(Room(false));
            var two = r.FacingOf(Room(false, Modded(), Modded()));
            int own = r.F(zero == AvatarFacing.Locked ? AvatarFacing.Undecided : zero, Set(true, 3, 1), 5, Faces(), Loader());
            got = "zero others=" + zero + " f(own=5)=" + own + " 2-of-2 modded=" + two;
            return zero == AvatarFacing.Undecided && own == 5 && two == AvatarFacing.Modded;
        }

        private static bool T4a(AvatarRules r, out string got)
        {
            var c = r.Census(new AvatarLivenessIn { Unreadable = true }, Room(false, Modded()));
            got = "unreadable liveness, modded room -> " + c;
            return c == AvatarFacing.Locked;
        }

        private static bool T4b(AvatarRules r, out string got)
        {
            var c = r.Census(NotLive(), new AvatarFacingIn { Unreadable = true, FaceKey = FaceKey });
            got = "unreadable facing inside a room -> " + c;
            return c == AvatarFacing.Vanilla;
        }

        private static bool T5(AvatarRules r, out string got)
        {
            int n = 0, bad = 0; string first = null;
            var faces = Faces(); var l = Loader();
            foreach (var c in Decided)
                foreach (bool auto in new[] { true, false })
                    foreach (int m in Slots)
                        foreach (int v in Slots)
                            for (int o = 0; o < 10; o++)
                            {
                                var s = Set(auto, m, v);
                                int once = r.F(c, s, o, faces, l);
                                int twice = r.F(c, s, once, faces, l);
                                n++;
                                if (once != twice) { bad++; if (first == null) first = c + " m=" + m + " v=" + v + " o=" + o + ": " + once + "->" + twice; }
                            }
            int single = r.F(AvatarFacing.Modded, Set(true, 3, 1), 5, faces, l);
            got = "points=" + n + " non-idempotent=" + bad + (first != null ? " first=" + first : "") + " single(modded 3, own 5)=" + single;
            return bad == 0 && n > 0 && single == 3;
        }

        private static bool T6(AvatarRules r, out string got)
        {
            var faces = Faces(); var l = Loader();
            int unset = r.F(AvatarFacing.Modded, Set(true, -1, 1), 5, faces, l);
            int past = r.F(AvatarFacing.Modded, Set(true, 12, 1), 5, faces, l);
            int nul = r.F(AvatarFacing.Modded, Set(true, 6, 1), 5, faces, l);
            int zero = r.F(AvatarFacing.Modded, Set(true, 0, 1), 5, faces, l);
            int zeroV = r.F(AvatarFacing.Vanilla, Set(true, 3, 0), 5, faces, l);
            int ok = r.F(AvatarFacing.Modded, Set(true, 3, 1), 5, faces, l);
            got = "unset=" + unset + " >=Length=" + past + " null=" + nul + " all-zero(modded)=" + zero
                + " all-zero(vanilla)=" + zeroV + " usable=" + ok;
            return unset == 5 && past == 5 && nul == 5 && zero == 5 && zeroV == 5 && ok == 3;
        }

        private static bool T7(AvatarRules r, out string got)
        {
            int combos = 0, wrote = 0;
            foreach (bool auto in new[] { true, false })
                foreach (int m in Slots)
                    foreach (int v in Slots)
                        foreach (var f in new[] { Room(true, Modded()), Room(false, Unmodded()), Room(false), Menu() })
                        {
                            var d = r.Evaluate(In(Live(), f, Set(auto, m, v), 2, 7));
                            combos++;
                            if (!d.Gated || d.Apply >= 0 || d.Publish || d.Switched != AvatarSwitched.None
                                || d.NewHome != 7 || d.HomeChanged) wrote++;
                        }
            // the same inputs with liveness FALSE must still switch, so a
            // feature that never switches cannot pass
            var open = r.Evaluate(In(NotLive(), Room(true, Modded()), Set(true, 3, 1), 2, -1));
            got = "locked combos=" + combos + " that wrote anything=" + wrote + " | not live: apply=" + open.Apply;
            return combos > 0 && wrote == 0 && open.Apply == 3;
        }

        private static bool T8(AvatarRules r, out string got)
        {
            int n = 0, bad = 0, writes = 0; string first = null;
            var faces = Faces(); var l = Loader();
            foreach (var f in new[] { Room(true, Modded()), Room(false, Unmodded()), Room(false), Menu() })
                foreach (bool auto in new[] { true, false })
                    foreach (int m in Slots)
                        foreach (int v in Slots)
                            foreach (int home in new[] { -1, 4, 7 })
                                for (int live = 0; live < 10; live++)
                                {
                                    var x = In(NotLive(), f, Set(auto, m, v), live, home);
                                    var d = r.Evaluate(x);
                                    n++;
                                    var c = r.Census(x.Liveness, x.Facing);
                                    int nom = c == AvatarFacing.Modded ? m : c == AvatarFacing.Vanilla ? v : -1;
                                    bool named = auto && nom >= 0 && r.Usable(nom, c, faces, l);
                                    bool ok = !(d.NewHome >= 0) || named;
                                    // written exactly when f displaces a live selection with Home empty
                                    if (home < 0 && d.Apply >= 0)
                                    {
                                        writes++;
                                        if (d.NewHome != live) ok = false;
                                    }
                                    if (!ok) { bad++; if (first == null) first = c + " auto=" + auto + " m=" + m + " v=" + v + " home=" + home + " live=" + live + " -> home " + d.NewHome; }
                                }
            got = "points=" + n + " displacing writes=" + writes + " violations=" + bad + (first != null ? " first=" + first : "");
            return bad == 0 && writes > 0;
        }

        private static bool T9(AvatarRules r, out string got)
        {
            var two = new Seat(3);
            two.Step(r, NotLive(), Room(false, Unmodded()), Set(true, 2, 1));   // Vanilla -> 1
            two.Step(r, NotLive(), Room(true, Modded()), Set(true, 2, 1));      // Modded  -> 2
            two.Step(r, NotLive(), Menu(), Set(true, 2, 1));                    // Undecided -> restore
            var one = new Seat(3);
            one.Step(r, NotLive(), Room(false, Unmodded()), Set(true, 2, 1));
            one.Step(r, NotLive(), Menu(), Set(true, 2, 1));
            got = "two-switch 3->1->2->Undecided ends live=" + two.Live + " home=" + two.Home
                + " | one-switch 3->1->Undecided ends live=" + one.Live + " home=" + one.Home;
            return two.Live == 3 && two.Home == -1 && one.Live == 3 && one.Home == -1;
        }

        private static bool T10(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            // Home 3 held by an earlier switch; the player picked 4 by hand
            var d = r.Evaluate(In(NotLive(), Room(true, Modded()), s, 4, 3));
            var seat = new Seat(d.Apply >= 0 ? d.Apply : 4) { Home = d.NewHome };
            seat.Step(r, NotLive(), Menu(), s);
            int keep = r.Rebase(3, 3, s);
            got = "hand pick 4 under home 3: home->" + d.NewHome + " applied=" + d.Apply
                + " | after the room: live=" + seat.Live + " | live==home keeps " + keep;
            return d.NewHome == 4 && d.Apply == 2 && seat.Live == 4 && keep == 3;
        }

        private static bool T11(AvatarRules r, out string got)
        {
            int a = r.HomeOrEmpty(-1, 10), b = r.HomeOrEmpty(-7, 10), c = r.HomeOrEmpty(10, 10),
                d9 = r.HomeOrEmpty(9, 10), d7 = r.HomeOrEmpty(7, 10);
            got = "-1->" + a + " -7->" + b + " 10->" + c + " 9->" + d9 + " 7->" + d7;
            return a == -1 && b == -1 && c == -1 && d9 == 9 && d7 == 7;
        }

        private static bool T12(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new Seat(3);
            for (int i = 0; i < 120; i++) seat.Step(r, NotLive(), Room(true, Modded()), s);
            int roomApplies = seat.Applies, roomSwitches = seat.Switches;
            seat.Step(r, NotLive(), Menu(), s);                                  // leave: the restore
            int afterLeave = seat.Applies;
            for (int i = 0; i < 120; i++) seat.Step(r, NotLive(), Room(true, Modded()), s);
            got = "one room x120: applies=" + roomApplies + " switches=" + roomSwitches
                + " | leave restore applies=" + (afterLeave - roomApplies)
                + " | rejoin x120: total switches=" + seat.Switches + " total applies=" + seat.Applies;
            return roomApplies == 1 && roomSwitches == 1 && afterLeave == 2 && seat.Switches == 2 && seat.Applies == 3;
        }

        private static bool T13(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            bool menu = r.SwapPermitted(In(NotLive(), Menu(), s, 3, -1));
            bool forced = r.SwapPermitted(In(NotLive(), Room(true, Modded()), s, 2, 3));
            bool live = r.SwapPermitted(In(Live(), Menu(), s, 3, -1));
            bool unset = r.SwapPermitted(In(NotLive(), Room(true, Modded()), Set(true, -1, 1), 3, -1));
            bool off = r.SwapPermitted(In(NotLive(), Room(true, Modded()), Set(false, 2, 1), 3, -1));
            got = "menu=" + menu + " room naming a face=" + forced + " live game=" + live
                + " nominee unset=" + unset + " auto off=" + off;
            return menu && !forced && !live && unset && off;
        }

        private static bool T14(AvatarRules r, out string got)
        {
            var faces = Faces(); var l = Loader();
            int fromM = r.SwapTarget(3, Set(true, 3, 1), faces, l);    // live = modded -> vanilla 1
            int fromV = r.SwapTarget(1, Set(true, 3, 1), faces, l);    // live = vanilla -> modded 3
            int dirty = r.SwapTarget(3, Set(true, 3, 2), faces, l);    // vanilla nominee 2 is not clean
            int blank = r.SwapTarget(1, Set(true, 0, 1), faces, l);    // modded nominee 0 never authored
            got = "from modded=" + fromM + " from vanilla=" + fromV + " to a dirty vanilla=" + dirty + " to an unauthored modded=" + blank;
            return fromM == 1 && fromV == 3 && dirty == -1 && blank == -1;
        }

        private static bool T15(AvatarRules r, out string got)
        {
            int moved = 0, n = 0; var faces = Faces(); var l = Loader();
            foreach (var roster in new[] { Room(true, Modded()), Room(false, Unmodded()), Room(false, Modded(), Modded()) })
            {
                var room = roster;   // AvatarFacingIn is a struct: a foreach variable is read-only
                room.OfflineMode = true;
                foreach (int m in Slots) foreach (int v in Slots)
                    {
                        var c = r.Census(NotLive(), room);
                        int w = c == AvatarFacing.Locked ? 5 : r.F(c, Set(true, m, v), 5, faces, l);
                        n++; if (w != 5) moved++;
                    }
            }
            var online = Room(false, Unmodded());
            int sw = r.F(r.Census(NotLive(), online), Set(true, 3, 1), 5, faces, l);
            got = "offline points=" + n + " moved=" + moved + " | the same roster online -> " + sw;
            return n > 0 && moved == 0 && sw == 1;
        }

        private static bool T16(AvatarRules r, out string got)
        {
            var a = r.FacingOf(Room(false, Modded(), Modded()));
            var b = r.FacingOf(Room(false, Modded(), Modded(), Unmodded()));
            var c = r.FacingOf(Room(false, Modded(), Modded()));
            got = "modded roster=" + a + " + an unmodded entrant=" + b + " entrant left=" + c;
            return a == AvatarFacing.Modded && b == AvatarFacing.Vanilla && c == AvatarFacing.Modded;
        }

        private static bool T17(AvatarRules r, out string got)
        {
            var spec = Room(true, Modded()); spec.LocalIsSpectator = true;
            var a = r.FacingOf(spec);
            var b = r.FacingOf(Room(true, Modded()));
            got = "spectator=" + a + " fighter in the same room=" + b;
            return a == AvatarFacing.Undecided && b == AvatarFacing.Modded;
        }

        private static bool T18(AvatarRules r, out string got)
        {
            bool only = r.CarriesModSignature(FaceOnly(), FaceKey);
            var room = r.FacingOf(Room(false, FaceOnly(), FaceOnly()));
            bool both = r.CarriesModSignature(new List<string> { FaceKey, "cr_trail_sku" }, FaceKey);
            got = "cr_face only reads modded=" + only + " room of two such=" + room + " cr_face+cr_trail reads modded=" + both;
            return !only && room == AvatarFacing.Vanilla && both;
        }

        /// <summary>The toast surface: one slot, latest wins, a timer.</summary>
        private sealed class Surface
        {
            internal string Text = ""; internal float Timer; internal int Raised;
            internal void Ask(AvatarRules r, string msg)
            {
                if (r.ShouldRaise(msg, Text, Timer)) { Text = msg; Timer = 5f; Raised++; }
            }
            internal void Advance(float dt) { Timer -= dt; }
        }

        private static bool T19(AvatarRules r, out string got)
        {
            const string dirty = "Your vanilla avatar preset has items an unmodded player cannot see, so your avatar was not switched.";
            const string other = "That preset has never been customised, so your avatar was not switched.";
            var s = Set(true, 3, 2);                                   // vanilla nominee 2 is not clean
            var surf = new Surface();
            int unusable = 0;
            for (int i = 0; i < 120; i++)
            {
                var d = r.Evaluate(In(NotLive(), Room(false, Unmodded()), s, 3, -1));
                if (d.Unusable == AvatarUnusable.NotClean) { unusable++; surf.Ask(r, dirty); }
                surf.Advance(1f / 60f);
            }
            int inWindow = surf.Raised;
            surf.Advance(6f);
            surf.Ask(r, dirty);
            int afterExpiry = surf.Raised;
            var two = new Surface();
            two.Ask(r, dirty); two.Ask(r, other);
            got = "120 evaluations, unusable=" + unusable + " raised=" + inWindow + " | after expiry raised=" + afterExpiry
                + " | two different messages raised=" + two.Raised;
            return unusable == 120 && inWindow == 1 && afterExpiry == 2 && two.Raised == 2;
        }

        // ---- the mutants and the controls -------------------------------

        private sealed class M_T1 : AvatarRules { internal override bool ResolvesOnABaseSeat(int id, bool[] arr) => id < 1000; }
        private sealed class K_T1 : AvatarRules { internal override bool ResolvesOnABaseSeat(int id, bool[] arr) => arr != null && (uint)id < (uint)arr.Length && arr[id]; }

        private sealed class M_T2 : AvatarRules
        {
            internal override bool EveryOtherFighterIsModded(IList<IList<string>> others, string faceKey)
            { foreach (var o in others) if (CarriesModSignature(o, faceKey)) return true; return false; }
        }
        private sealed class K_T2 : AvatarRules
        {
            internal override bool EveryOtherFighterIsModded(IList<IList<string>> others, string faceKey)
            { for (int i = others.Count - 1; i >= 0; i--) if (!CarriesModSignature(others[i], faceKey)) return false; return true; }
        }

        private sealed class M_T3 : AvatarRules
        {
            internal override AvatarFacing FacingOf(AvatarFacingIn f)
            { var c = base.FacingOf(f); return (c == AvatarFacing.Undecided && f.InRoom && f.RoomExists && !f.OfflineMode && !f.LocalIsSpectator && !f.ModIssuedRoom && (f.OtherFighterKeys == null || f.OtherFighterKeys.Count == 0)) ? AvatarFacing.Vanilla : c; }
        }
        private sealed class K_FacingSame : AvatarRules
        {
            internal override AvatarFacing FacingOf(AvatarFacingIn f) { var c = base.FacingOf(f); return c; }
        }

        private sealed class M_T4a : AvatarRules { internal override bool Live(AvatarLivenessIn l) => l.Unreadable ? false : base.Live(l); }
        private sealed class M_T4b : AvatarRules
        {
            internal override AvatarFacing FacingOf(AvatarFacingIn f) => f.Unreadable ? AvatarFacing.Undecided : base.FacingOf(f);
        }

        private sealed class M_T5 : AvatarRules
        {
            internal override int F(AvatarFacing c, AvatarSetting s, int own, AvatarFaceIds[] faces, AvatarLoaderView l)
            {
                int w = base.F(c, s, own, faces, l);
                if (c == AvatarFacing.Modded && s.Auto && own == s.Modded && s.Vanilla >= 0) return s.Vanilla;
                return w;
            }
        }
        private sealed class K_F : AvatarRules
        {
            internal override int F(AvatarFacing c, AvatarSetting s, int own, AvatarFaceIds[] faces, AvatarLoaderView l)
            { int w = base.F(c, s, own, faces, l); return w == own ? own : w; }
        }

        private sealed class M_T6 : AvatarRules
        {
            internal override AvatarUnusable WhyUnusable(int slot, AvatarFacing facing, AvatarFaceIds[] faces, AvatarLoaderView l)
            {
                if (faces == null || slot < 0 || slot >= faces.Length || !faces[slot].Present) return AvatarUnusable.Unauthored;
                if (facing == AvatarFacing.Vanilla && !VanillaClean(faces[slot], l)) return AvatarUnusable.NotClean;
                return AvatarUnusable.None;                    // the authored term dropped
            }
        }
        private sealed class K_T6 : AvatarRules
        {
            internal override AvatarUnusable WhyUnusable(int slot, AvatarFacing facing, AvatarFaceIds[] faces, AvatarLoaderView l)
            {
                if (faces == null || slot < 0 || slot >= faces.Length || !faces[slot].Present) return AvatarUnusable.Unauthored;
                if (faces[slot].AllZero) return AvatarUnusable.Unauthored;
                return AvatarUnusable.None;                    // the cleanliness term dropped instead
            }
        }

        /// <summary>Revision 3's defect restored: no gate, and f answers a
        /// Locked census with own.</summary>
        private sealed class M_T7 : AvatarRules
        {
            internal override bool Gate(AvatarFacing c) => false;
            internal override int F(AvatarFacing c, AvatarSetting s, int own, AvatarFaceIds[] faces, AvatarLoaderView l)
                => c == AvatarFacing.Locked ? own : base.F(c, s, own, faces, l);
        }
        private sealed class K_Gate : AvatarRules { internal override bool Gate(AvatarFacing c) => c.Equals(AvatarFacing.Locked); }

        private sealed class M_T8 : AvatarRules
        {
            internal override AvatarDecision Evaluate(AvatarEvalIn x)
            {
                var d = base.Evaluate(x);
                if (d.Apply >= 0) { d.NewHome = x.Live; d.HomeChanged = d.NewHome != x.Home; }   // written on EVERY apply
                return d;
            }
        }
        private sealed class K_Eval : AvatarRules
        {
            internal override AvatarDecision Evaluate(AvatarEvalIn x) { var d = base.Evaluate(x); var e = d; return e; }
        }

        private sealed class M_T9 : AvatarRules
        {
            internal override AvatarDecision Evaluate(AvatarEvalIn x)
            {
                var d = base.Evaluate(x);
                bool restore = d.Apply >= 0 && d.Switched == AvatarSwitched.None;
                if (d.Apply >= 0 && !restore && x.Home >= 0) { d.NewHome = x.Live; }   // overwritten on the second apply
                return d;
            }
        }

        private sealed class M_T10 : AvatarRules { internal override int Rebase(int home, int live, AvatarSetting s) => home; }
        private sealed class K_T10 : AvatarRules
        {
            internal override int Rebase(int home, int live, AvatarSetting s)
            { if (home < 0 || live == home || live == s.Modded || live == s.Vanilla) return home; return live; }
        }

        private sealed class M_T11 : AvatarRules { internal override int HomeOrEmpty(int home, int faceCount) => (home >= 0 && home < 8) ? home : -1; }
        private sealed class K_T11 : AvatarRules { internal override int HomeOrEmpty(int home, int faceCount) => (uint)home < (uint)faceCount ? home : -1; }

        private sealed class M_T12 : AvatarRules
        {
            internal override AvatarDecision Evaluate(AvatarEvalIn x)
            {
                var d = base.Evaluate(x);
                if (!d.Gated && !d.NothingToRead && d.Apply < 0 && d.Want >= 0)
                {   // the want != live gate removed: apply and announce anyway
                    d.Apply = d.Want; d.Publish = true;
                    d.Switched = d.Facing == AvatarFacing.Vanilla ? AvatarSwitched.ToVanilla
                               : d.Facing == AvatarFacing.Modded ? AvatarSwitched.ToModded : AvatarSwitched.None;
                }
                return d;
            }
        }

        private sealed class M_T13 : AvatarRules
        {
            internal override bool SwapPermitted(AvatarEvalIn x) => !Gate(Census(x.Liveness, x.Facing));   // f == own dropped
        }
        private sealed class K_T13 : AvatarRules
        {
            internal override bool SwapPermitted(AvatarEvalIn x)
            {   // the GATE term dropped instead: f is reached on a Locked census and refuses
                var c = Census(x.Liveness, x.Facing);
                if (x.Faces == null || x.Live < 0) return false;
                int home = HomeOrEmpty(x.Home, x.Faces.Length);
                int own = home >= 0 ? home : x.Live;
                try { return F(c, x.Setting, own, x.Faces, x.Loader) == own; }
                catch (ArgumentException) { PreconditionTrips++; return false; }
            }
            internal int PreconditionTrips;
        }

        private sealed class M_T14 : AvatarRules
        {
            internal override int SwapTarget(int live, AvatarSetting s, AvatarFaceIds[] faces, AvatarLoaderView l)
                => live == s.Modded ? s.Vanilla : s.Modded;
        }
        private sealed class K_T14 : AvatarRules
        {
            internal override int SwapTarget(int live, AvatarSetting s, AvatarFaceIds[] faces, AvatarLoaderView l)
            {
                if (live == s.Modded) return Usable(s.Vanilla, AvatarFacing.Vanilla, faces, l) ? s.Vanilla : -1;
                return Usable(s.Modded, AvatarFacing.Modded, faces, l) ? s.Modded : -1;
            }
        }

        private sealed class M_T15 : AvatarRules
        {
            internal override AvatarFacing FacingOf(AvatarFacingIn f) { f.OfflineMode = false; return base.FacingOf(f); }
        }

        private sealed class M_T16 : AvatarRules
        {
            private bool _wasVanilla;   // harness-only mutant state: the sticky facing
            internal override AvatarFacing FacingOf(AvatarFacingIn f)
            {
                var c = base.FacingOf(f);
                if (c == AvatarFacing.Vanilla) _wasVanilla = true;
                return _wasVanilla && c == AvatarFacing.Modded ? AvatarFacing.Vanilla : c;
            }
        }

        private sealed class M_T17 : AvatarRules
        {
            internal override AvatarFacing FacingOf(AvatarFacingIn f) { f.LocalIsSpectator = false; return base.FacingOf(f); }
        }

        private sealed class M_T18 : AvatarRules
        {
            internal override bool CarriesModSignature(IList<string> keys, string faceKey)
            {
                if (keys == null) return false;
                foreach (var k in keys) if (k != null && k.StartsWith("cr_", StringComparison.Ordinal)) return true;
                return false;
            }
        }
        private sealed class K_T18 : AvatarRules
        {
            internal override bool CarriesModSignature(IList<string> keys, string faceKey)
            {
                if (keys == null) return false;
                foreach (var k in keys)
                    if (k != null && !string.Equals(k, faceKey, StringComparison.Ordinal)
                        && string.CompareOrdinal(k, 0, "cr_", 0, 3) == 0) return true;
                return false;
            }
        }

        private sealed class M_T19 : AvatarRules { internal override bool ShouldRaise(string msg, string showingText, float timerLeft) => !string.IsNullOrEmpty(msg); }
        private sealed class K_T19 : AvatarRules
        {
            internal override bool ShouldRaise(string msg, string showingText, float timerLeft)
                => !string.IsNullOrEmpty(msg) && (timerLeft <= 0f || !string.Equals(showingText, msg, StringComparison.Ordinal));
        }

        // ---- the runner -------------------------------------------------

        private static bool Run(Claim c, AvatarRules r, out string got)
        {
            try { return c(r, out got); }
            catch (Exception ex) { got = "THREW " + ex.GetType().Name + ": " + ex.Message; return false; }
        }

        private static void Pair(SelfTestResult res, string id, string claim, Claim c, AvatarRules mutant, AvatarRules control)
        {
            string g;
            bool real = Run(c, new AvatarRules(), out g);
            Check(res, id + " " + claim, real, g);
            bool mut = Run(c, mutant, out g);
            Check(res, id + " mutation reds", !mut, (mut ? "STAYED GREEN " : "red as required ") + g);
            bool ctl = Run(c, control, out g);
            Check(res, id + " control stays green", ctl, g);
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            Pair(r, "T1", "vanilla-clean is base-loader resolvability (-1, 20, 999, a null hole and a custom id are not clean; 19 is)", T1, new M_T1(), new K_T1());
            Pair(r, "T2", "the facing is an every-quantifier, not an any", T2, new M_T2(), new K_T2());
            Pair(r, "T3", "zero other fighters is Undecided and f returns own", T3, new M_T3(), new K_FacingSame());
            Pair(r, "T4a", "an unreadable liveness term is Locked", T4a, new M_T4a(), new M_T4b());
            Pair(r, "T4b", "an unreadable facing inside a real room is Vanilla", T4b, new M_T4b(), new M_T4a());
            Pair(r, "T5", "f is idempotent over the enumerated input space", T5, new M_T5(), new K_F());
            Pair(r, "T6", "f returns own for every unusable nominee (unset, past the array, null, all-zero)", T6, new M_T6(), new K_T6());
            Pair(r, "T7", "the gate writes nothing: Home 7 and live 2 on a Locked census", T7, new M_T7(), new K_Gate());
            Pair(r, "T8", "Home is non-empty only where f names a face, and is written exactly when f displaces", T8, new M_T8(), new K_Eval());
            Pair(r, "T9", "two switches preserve the original selection", T9, new M_T9(), new K_Eval());
            Pair(r, "T10", "a hand choice re-bases the remembered value", T10, new M_T10(), new K_T10());
            Pair(r, "T11", "the remembered value's domain is playerFaces.Length (slot 9 of 10 is valid)", T11, new M_T11(), new K_T11());
            Pair(r, "T12", "120 evaluations in one room apply once; leave then rejoin applies again", T12, new M_T12(), new K_Eval());
            var k13 = new K_T13();
            Pair(r, "T13", "a swap is permitted exactly where the gate is open and f names no face", T13, new M_T13(), k13);
            Check(r, "T13 the gate-less control reached f on a Locked census and f refused",
                  k13.PreconditionTrips > 0, "precondition trips=" + k13.PreconditionTrips);
            Pair(r, "T14", "the swap selects the other nominee and refuses an unusable one", T14, new M_T14(), new K_T14());
            Pair(r, "T15", "the feature is inert offline", T15, new M_T15(), new K_FacingSame());
            Pair(r, "T16", "the facing moves both ways on a live roster", T16, new M_T16(), new K_FacingSame());
            Pair(r, "T17", "a spectator seat's facing is Undecided", T17, new M_T17(), new K_FacingSame());
            Pair(r, "T18", "the per-actor test excludes cr_face", T18, new M_T18(), new K_T18());
            Pair(r, "T19", "the announcer is bounded by the surface, not by a counter", T19, new M_T19(), new K_T19());
            return r;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
