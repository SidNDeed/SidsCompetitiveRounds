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

        private static AvatarFacingIn OfflineRoom()
        {
            var f = Room(false, Modded());
            f.OfflineMode = true;
            return f;
        }

        private static AvatarSetting Set(bool auto, int modded, int vanilla)
            => new AvatarSetting { Auto = auto, Modded = modded, Vanilla = vanilla };

        private static AvatarEvalIn In(AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s, int live, int home)
        {
            return new AvatarEvalIn { Liveness = l, Facing = f, Setting = s, Faces = Faces(), Loader = Loader(), Live = live, Home = home };
        }

        /// <summary>How the next apply of a seat ends (fix pass 3, H9 and M3).
        /// Commit: the selection moves. Throw: an exception leaves the
        /// evaluator before the selection moves, so nothing after the apply
        /// runs. NoCommit: the apply returns and the read-back shows the
        /// selection unmoved.</summary>
        private enum ApplyOutcome { Commit, Throw, NoCommit }

        /// <summary>A seat: the live selection and the remembered value, moved
        /// by each decision exactly as AvatarDefaults moves them.</summary>
        private sealed class Seat
        {
            internal int Live, Home = -1, Applies, Switches, Publishes;
            internal ApplyOutcome Next = ApplyOutcome.Commit;
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

            /// <summary>Fix pass 3 (H9, M3): the same evaluation moved in the
            /// order AvatarDefaults.Evaluate moves it since fix pass 3: Home as
            /// AvatarRules.HomeBeforeApply holds it, then the apply (ending as
            /// Next says, once), then Home as AvatarRules.HomeAfterApply reads
            /// it from the selection read back. A Throw leaves the evaluator
            /// with Home as it was held. Step above keeps the decision-only
            /// model the fix pass 1 and 2 cases were written against.</summary>
            internal AvatarDecision StepThrough(AvatarRules r, AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s, AvatarFaceIds[] faces = null, bool facesMissing = false)
            {
                var x = In(l, f, s, Live, Home);
                if (facesMissing) { x.Faces = null; }
                else if (faces != null) x.Faces = faces;
                var d = r.Evaluate(x);
                if (d.Gated || d.NothingToRead) return d;
                int held = r.HomeBeforeApply(Home, d);
                Home = held;
                int after = Live;
                if (d.Apply >= 0)
                {
                    var how = Next;
                    Next = ApplyOutcome.Commit;
                    if (how == ApplyOutcome.Throw) return d;
                    if (how == ApplyOutcome.Commit) { Live = d.Apply; Applies++; }
                    after = Live;
                }
                Home = r.HomeAfterApply(held, d, after);
                if (d.Apply >= 0 && after != d.Apply) return d;
                if (d.Publish) Publishes++;
                if (d.Switched != AvatarSwitched.None) Switches++;
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
            // fix pass 1 (BR-M4): the room is a REAL online room here, as the
            // claim says; the no-room half is case BRM4.
            var c = r.Census(NotLive(), new AvatarFacingIn { Unreadable = true, InRoom = true, RoomExists = true, FaceKey = FaceKey });
            got = "unreadable facing inside a real online room -> " + c;
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
                        // in-room facings only: a confirmed no-room outranks a
                        // live manager (fix pass 1, H9), which cases H9 and M3 pin
                        foreach (var f in new[] { Room(true, Modded()), Room(false, Unmodded()), Room(false), OfflineRoom() })
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
            bool live = r.SwapPermitted(In(Live(), Room(false), s, 3, -1));   // f names no face here: only the gate refuses
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

        // ---- fix pass 1 (Codex BUILD round 1), one case per finding -------

        private static AvatarLivenessIn PlayingOnly() => new AvatarLivenessIn { ManagerExists = true, IsPlaying = true };
        private static AvatarLivenessIn BattleOnly() => new AvatarLivenessIn { ManagerExists = true, BattleOngoing = true };
        private static AvatarLivenessIn BodyOnly() => new AvatarLivenessIn { ManagerExists = false, LocalBodyExists = true };

        /// <summary>One liveness term alone, the other two false: the face
        /// must not move. The separator is the same room with every term false,
        /// which must switch, so a feature that never switches cannot pass.</summary>
        private static bool LiveTermBlocks(AvatarRules r, AvatarLivenessIn term, string name, out string got)
        {
            var room = Room(false, Unmodded());
            var locked = r.Evaluate(In(term, room, Set(true, 3, 1), 5, -1));
            var open = r.Evaluate(In(new AvatarLivenessIn { ManagerExists = term.ManagerExists }, room, Set(true, 3, 1), 5, -1));
            got = name + " alone: census=" + locked.Facing + " apply=" + locked.Apply
                + " | every term false: census=" + open.Facing + " apply=" + open.Apply;
            return locked.Gated && locked.Apply < 0 && !open.Gated && open.Apply == 1;
        }

        private static bool H6a(AvatarRules r, out string got) => LiveTermBlocks(r, PlayingOnly(), "isPlaying", out got);
        private static bool H6b(AvatarRules r, out string got) => LiveTermBlocks(r, BattleOnly(), "battleOngoing", out got);
        private static bool H6c(AvatarRules r, out string got) => LiveTermBlocks(r, BodyOnly(), "no manager, a local body", out got);

        private static bool H8(AvatarRules r, out string got)
        {
            var entrant = r.FacingOf(Room(true, Modded(), Unmodded()));
            var gone = r.FacingOf(Room(true, Modded()));
            var plain = r.FacingOf(Room(false, Modded(), Unmodded()));
            int w = r.F(entrant == AvatarFacing.Locked ? AvatarFacing.Undecided : entrant, Set(true, 3, 1), 5, Faces(), Loader());
            got = "issued room + an unmodded entrant=" + entrant + " (f(own 5)=" + w + ") | entrant left=" + gone
                + " | the same roster unissued=" + plain;
            return entrant == AvatarFacing.Vanilla && w == 1 && gone == AvatarFacing.Modded && plain == AvatarFacing.Vanilla;
        }

        private static bool BRH1(AvatarRules r, out string got)
        {
            var solo = r.Evaluate(In(NotLive(), Room(true), Set(true, 2, 1), 3, -1));
            var issued = r.FacingOf(Room(true, Modded()));
            var census = r.FacingOf(Room(false, Modded(), Modded()));
            var faceOnly = r.FacingOf(Room(true, FaceOnly()));
            got = "issued room, zero others: facing=" + solo.Facing + " apply=" + solo.Apply
                + " | issued + one modded=" + issued + " | unissued, all modded=" + census
                + " | issued + one cr_face-only actor=" + faceOnly;
            return solo.Facing == AvatarFacing.Undecided && solo.Apply < 0 && issued == AvatarFacing.Modded
                && census == AvatarFacing.Modded && faceOnly == AvatarFacing.Vanilla;
        }

        private static bool H9(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new Seat(3);
            seat.Step(r, NotLive(), Room(false, Unmodded()), s);                  // Vanilla: 3 -> 1, home 3
            int forced = seat.Live, held = seat.Home;
            seat.Step(r, Live(), Room(false, Unmodded()), s);                     // the game: locked
            int inGame = seat.Live;
            var d = seat.Step(r, Live(), Menu(), s);                              // leave, the old manager still live
            got = "forced live=" + forced + " home=" + held + " | in game live=" + inGame
                + " | leave with a live manager: census=" + d.Facing + " live=" + seat.Live + " home=" + seat.Home;
            return forced == 1 && held == 3 && inGame == 1 && seat.Live == 3 && seat.Home == -1;
        }

        private static bool M3(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new Seat(3);
            seat.Step(r, NotLive(), Room(true, Modded()), s);                     // Modded: 3 -> 2, home 3
            seat.Step(r, Live(), Room(true, Modded()), s);                        // the game
            seat.Step(r, Live(), Menu(), s);                                      // E7 alone (no OnLeftRoom)
            int afterOne = seat.Applies, liveOne = seat.Live, homeOne = seat.Home;
            seat.Step(r, Live(), Menu(), s);                                      // a second exit edge
            seat.Step(r, NotLive(), Menu(), s);                                   // and a third, manager gone
            var unreadable = r.Census(Live(), new AvatarFacingIn { Unreadable = true, FaceKey = FaceKey });
            got = "disconnect alone: applies=" + afterOne + " live=" + liveOne + " home=" + homeOne
                + " | two more exits: applies=" + seat.Applies + " live=" + seat.Live
                + " | unreadable room read, live manager: " + unreadable;
            return afterOne == 2 && liveOne == 3 && homeOne == -1 && seat.Applies == 2 && seat.Live == 3
                && unreadable == AvatarFacing.Locked;
        }

        private static bool BRM3(AvatarRules r, out string got)
        {
            var faces = Faces(); var l = Loader();
            int onlyM = r.F(AvatarFacing.Modded, Set(true, 3, -1), 5, faces, l);
            int onlyV = r.F(AvatarFacing.Vanilla, Set(true, -1, 1), 5, faces, l);
            int both = r.F(AvatarFacing.Modded, Set(true, 3, 1), 5, faces, l);
            var dOne = r.Evaluate(In(NotLive(), Room(true, Modded()), Set(true, 3, -1), 5, -1));
            var dRestore = r.Evaluate(In(NotLive(), Room(false, Unmodded()), Set(true, -1, 1), 1, 4));   // a debt from before
            got = "only modded set, modded room: f=" + onlyM + " | only vanilla set, vanilla room: f=" + onlyV
                + " | both set: f=" + both + " | one set, evaluator: apply=" + dOne.Apply + " unusable=" + dOne.Unusable
                + " | one set, remembered 4: apply=" + dRestore.Apply + " home->" + dRestore.NewHome;
            return onlyM == 5 && onlyV == 5 && both == 3 && dOne.Apply < 0 && dOne.Unusable == AvatarUnusable.None
                && dRestore.Apply == 4 && dRestore.NewHome == -1;
        }

        private static bool BRM4(AvatarRules r, out string got)
        {
            var noRoom = r.FacingOf(new AvatarFacingIn { Unreadable = true, FaceKey = FaceKey });
            var offline = r.FacingOf(new AvatarFacingIn { Unreadable = true, InRoom = true, OfflineMode = true, FaceKey = FaceKey });
            var real = r.FacingOf(new AvatarFacingIn { Unreadable = true, InRoom = true, RoomExists = true, FaceKey = FaceKey });
            var census = r.Census(NotLive(), new AvatarFacingIn { Unreadable = true, FaceKey = FaceKey });
            got = "unreadable, no room established=" + noRoom + " | unreadable, offline room=" + offline
                + " | unreadable, real online room=" + real + " | census at the menu, unreadable=" + census;
            return noRoom == AvatarFacing.Undecided && offline == AvatarFacing.Undecided
                && real == AvatarFacing.Vanilla && census == AvatarFacing.Undecided;
        }

        /// <summary>The carrier as the popup sees it: the last value written,
        /// or none.</summary>
        private static string Carry(FaceCarrierAction a, string carrier, string current)
        {
            return a == FaceCarrierAction.Publish ? current : a == FaceCarrierAction.Clear ? null : carrier;
        }

        private static bool H3(AvatarRules r, out string got)
        {
            var valid = AvatarFaceIds.Of(3, 3, 3, 3);
            var zero = AvatarFaceIds.Of(0, 0, 0, 0);
            var none = new AvatarFaceIds();
            string carrier = null;
            carrier = Carry(r.CarrierAction(false, true, true, true, valid), carrier, "face-3");
            string afterValid = carrier;
            carrier = Carry(r.CarrierAction(false, true, true, true, zero), carrier, "face-0");
            string afterZero = carrier;
            carrier = Carry(r.CarrierAction(false, true, true, true, valid), carrier, "face-3");
            carrier = Carry(r.CarrierAction(false, true, true, true, none), carrier, "null");
            string afterNull = carrier;
            carrier = Carry(r.CarrierAction(false, true, true, true, valid), carrier, "face-3");
            carrier = Carry(r.CarrierAction(false, true, true, false, none), carrier, "empty");
            string afterEmpty = carrier;
            var spec = r.CarrierAction(true, true, true, true, valid);
            var noHandler = r.CarrierAction(false, false, true, false, none);
            var noPlayer = r.CarrierAction(false, true, false, true, valid);
            got = "valid -> carrier " + (afterValid ?? "none") + " | then all-zero -> " + (afterZero ?? "none")
                + " | then a null face -> " + (afterNull ?? "none") + " | then an empty list -> " + (afterEmpty ?? "none")
                + " | spectator=" + spec + " no handler=" + noHandler + " no local player=" + noPlayer;
            return afterValid == "face-3" && afterZero == null && afterNull == null && afterEmpty == null
                && spec == FaceCarrierAction.Keep && noHandler == FaceCarrierAction.Keep && noPlayer == FaceCarrierAction.Keep;
        }

        /// <summary>The capture replay (M8): the exact line AvatarDefaults.Evaluate
        /// logs, for the issued, vanilla, census-Modded, entrant and departure
        /// rooms, each driven through a seat.</summary>
        private static bool M8(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var sb = new StringBuilder();
            bool ok = true;
            Func<Seat, string, AvatarFacingIn, AvatarFacing, int, int, bool> step = (seat, tag, room, wantFacing, wantNominee, wantOthers) =>
            {
                int was = seat.Live, home = seat.Home;
                var d = seat.Step(r, NotLive(), room, s);
                int n = room.OtherFighterKeys != null ? room.OtherFighterKeys.Count : 0;
                string line = r.LogsClassification(tag) || d.Apply >= 0 ? r.ClassificationLine(tag, d, n, room.ModIssuedRoom, was, home) : "(no line)";
                sb.Append(" || ").Append(line);
                return line.Contains("(facing " + wantFacing + ",") && line.Contains(", nominee " + wantNominee + ",")
                    && line.Contains(", other fighters " + wantOthers + ",");
            };
            ok &= step(new Seat(3), "E2-joined", Room(true, Modded()), AvatarFacing.Modded, 2, 1);
            ok &= step(new Seat(3), "E2-joined", Room(false, Unmodded()), AvatarFacing.Vanilla, 1, 1);
            var c = new Seat(3);
            ok &= step(c, "E2-joined", Room(false, Modded(), Modded()), AvatarFacing.Modded, 2, 2);
            ok &= step(c, "E3-entered", Room(false, Modded(), Modded(), Unmodded()), AvatarFacing.Vanilla, 1, 3);
            ok &= step(c, "E11-left", Room(false, Modded(), Modded()), AvatarFacing.Modded, 2, 2);
            var kept = new Seat(2);
            ok &= step(kept, "E2-joined", Room(true, Modded()), AvatarFacing.Modded, 2, 1);      // nothing moves: a kept line
            bool quiet = !r.LogsClassification("E5-spawn") && !r.LogsClassification("E4-props")
                && !r.LogsClassification("E9-select") && !r.LogsClassification("E12-roomprops");
            got = "per-frame and property edges log no kept line=" + quiet + sb;
            return ok && quiet;
        }

        // ---- fix pass 2 (Codex BUILD round 2) ------------------------------

        /// <summary>H3: an ASYNCHRONOUS model of a seat's own property cache.
        /// PUN's SetCustomProperties on the local player in a room changes
        /// nothing locally; the cache takes the value on the server's echo.
        /// Publish stores into a pending slot, Read returns the cached (old)
        /// value until Echo moves the pending one in. Read counts every call,
        /// so a pass that rereads the cache is seen even when it is lucky.</summary>
        private sealed class AsyncCarrierStore
        {
            private string cached, pending;
            private bool hasPending;
            internal int Reads;
            internal AsyncCarrierStore(string echoed) { cached = echoed; }
            internal void Publish(FaceCarrierAction a, string value)
            {
                if (a == FaceCarrierAction.Keep) return;
                pending = a == FaceCarrierAction.Publish ? value : null;
                hasPending = true;
            }
            internal string Read() { Reads++; return cached; }
            internal void Echo() { if (hasPending) { cached = pending; hasPending = false; } }
        }

        /// <summary>One card-pick Show pass for the LOCAL picker in the order
        /// the postfix runs it: the publish attempt (into the pending slot),
        /// the popup's face from the rule, then the server's echo.</summary>
        private static string LocalPass(AvatarRules r, AsyncCarrierStore st, AvatarFaceIds face, string serialized, out int reads)
        {
            var a = r.CarrierAction(false, true, true, true, face);
            string fresh = a == FaceCarrierAction.Publish ? serialized : null;
            st.Publish(a, fresh);
            int before = st.Reads;
            string shown = r.PopupFace(true, a, fresh, st.Read);
            reads = st.Reads - before;
            st.Echo();
            return shown;
        }

        private static bool H3Async(AvatarRules r, out string got)
        {
            var st = new AsyncCarrierStore("face-old");                       // an earlier pass's carrier, echoed
            int r1, r2, r3;
            string first = LocalPass(r, st, AvatarFaceIds.Of(3, 3, 3, 3), "face-new", out r1);
            string cleared = LocalPass(r, st, AvatarFaceIds.Of(0, 0, 0, 0), null, out r2);   // a definitive no-face attempt
            string again = LocalPass(r, st, AvatarFaceIds.Of(4, 4, 4, 4), "face-4", out r3);
            // Fix pass 3 (H3, the remote arm): a REMOTE seat whose settled copy
            // of the picker's carrier is stale (face 1: an earlier publish that
            // arrived and settled) raises the popup and applies, and only then
            // receives the echo of the picker's publish for this pick (face 4,
            // bound to this pick since fix pass 4).
            var remote = new RemoteSeat(r);
            remote.Arrive(7, Wire(1));                                        // the settled, stale copy
            remote.Show(7);                                                   // raise the popup and apply
            int atShow = remote.Equipped.Count;
            remote.Now = 0.3;
            remote.Arrive(7, Bd(Wire(4), 1, 0));                              // the echo, late
            string onEcho = remote.Equipped.Count > 0 ? remote.Equipped[remote.Equipped.Count - 1] : null;
            got = "publish, read, echo (cache still face-old at the read): shown=" + (first ?? "none") + " cache reads=" + r1
                + " | then a clear (cache still face-new at the read): shown=" + (cleared ?? "none") + " reads=" + r2
                + " | then face-4: shown=" + (again ?? "none") + " reads=" + r3
                + " | a remote picker, settled copy " + Short(Wire(1)) + ": faces equipped at the popup " + atShow
                + ", on the late echo " + Short(onEcho) + ", equipped in all " + remote.Faces() + ", reads of the settled copy " + remote.Reads;
            return first == "face-new" && r1 == 0 && cleared == null && r2 == 0 && again == "face-4" && r3 == 0
                && atShow == 0 && onEcho == Bd(Wire(4), 1, 0) && remote.Equipped.Count == 1 && remote.Reads == 0;
        }

        // ---- fix pass 3 (Codex BUILD round 3) ------------------------------

        /// <summary>A carrier value in the wire format (cr_face: twelve '|'
        /// fields), named by the id it carries in all four item slots.</summary>
        private static string Wire(int id)
        {
            string n = id.ToString(System.Globalization.CultureInfo.InvariantCulture), z = "0.000";
            return string.Join("|", new[] { n, z, z, n, z, z, n, z, z, n, z, z });
        }

        /// <summary>A carrier value as got= prints it: "face N" plus the pick
        /// it is bound to, or the clear tombstone with its pick.</summary>
        private static string Short(string v)
        {
            if (v == null) return "none";
            var p = v.Split('|');
            if (p.Length == 2) return "clear " + p[1];
            return "face " + p[0] + (p.Length == 13 ? " " + p[12] : p.Length == 12 ? " (unbound)" : " (?)");
        }

        /// <summary>Fix pass 4 (H3): a pick identity as both seats derive it
        /// ("pick" + the game this seat saw start + "." + the rounds completed).</summary>
        private static string Pk(int game, int rounds)
            => PopupCarrierLedger.PickPrefix + game.ToString(System.Globalization.CultureInfo.InvariantCulture)
               + "." + rounds.ToString(System.Globalization.CultureInfo.InvariantCulture);

        /// <summary>Fix pass 4 (H3): a face bound to a pick, as its picker
        /// publishes it at its own card-pick Show.</summary>
        private static string Bd(string face, int game, int rounds) => PopupCarrierLedger.BoundFace(face, Pk(game, rounds));

        /// <summary>H3, the remote arm (fix pass 3): a REMOTE seat as PUN feeds
        /// it. A carrier update ARRIVES (OnPlayerPropertiesUpdate) and is from
        /// then on this seat's settled copy: the copy the round 3 popup read.
        /// The popup's remote arm is the rule's reader wired as production
        /// wires it (PopupCarriers.ForShow: the ledger); arrival and the tick
        /// apply what the ledger hands back, and every outcome is reported to
        /// it (Applied), as PopupCarriers does. Every face equipped on the
        /// popup is recorded in order, with the ledger's notes. Fix pass 4
        /// (H3): the seat derives the pick identity as production does
        /// (PopupCarriers.PickNow: the games it saw start in the room, from
        /// GameStart, and Rounds), hands it to every Show and Arrived, and a
        /// seat built with started false has seen no game start in its room.</summary>
        private sealed class RemoteSeat
        {
            internal readonly Dictionary<int, string> Settled = new Dictionary<int, string>();
            internal readonly List<string> Equipped = new List<string>();
            internal readonly List<double> Attempts = new List<double>();
            internal readonly List<string> Notes = new List<string>();
            internal readonly PopupCarrierLedger Ledger;
            internal object Room = new object();
            internal double Now;
            internal int Rounds;                  // the rounds completed in the current game on this seat
            internal int Reads;                   // reads of the settled copy: the popup makes none
            internal int FailNext;                // the next N equips fail (no visualizer to equip)
            private readonly AvatarRules rules;

            internal RemoteSeat(AvatarRules r, bool started = true)
            {
                rules = r;
                Ledger = new PopupCarrierLedger(r);
                if (started) GameStart();
            }

            internal string ReadSettled(int actor) { Reads++; string v; return Settled.TryGetValue(actor, out v) ? v : null; }

            private void Note() { if (Ledger.Note != null) Notes.Add(Ledger.Note); }

            /// <summary>GM_ArmsRace.DoStartGame on this seat: a game starts in
            /// its room, with no rounds completed.</summary>
            internal void GameStart() { Ledger.GameStarted(Room); Note(); Rounds = 0; }

            /// <summary>The identity of a popup opening now (PopupCarriers.PickNow).</summary>
            internal string PickNow() { string p = Ledger.PopupPick(Room, Rounds); Note(); return p; }

            internal void Arrive(int actor, string value)
            {
                Settled[actor] = value;
                string pick = PickNow();
                string v = Ledger.Arrived(Room, actor, value, pick, Now);
                Note();
                if (v != null) Equip(actor, v);
            }

            internal void Show(int actor)
            {
                string v = rules.PopupFace(false, FaceCarrierAction.Keep, null, () =>
                {
                    string pick = PickNow();
                    string h = Ledger.Show(Room, actor, pick, Now);
                    Note();
                    return h;
                });
                if (v != null) Equip(actor, v);
            }

            internal void Hide() { Ledger.EndSession(Room); Note(); }

            internal void Tick()
            {
                string v = Ledger.Tick(Room, Now);
                Note();
                if (v != null) Equip(Ledger.Shown, v);
            }

            private void Equip(int actor, string v)
            {
                Attempts.Add(Now);
                bool ok = FailNext <= 0;
                if (ok) Equipped.Add(v); else FailNext--;
                Ledger.Applied(actor, ok, Now);
                Note();
            }

            internal string Faces() => Equipped.Count == 0 ? "none" : string.Join(", ", Equipped.ConvertAll(Short));

            internal int NotesWith(string s) => Notes.FindAll(n => n.Contains(s)).Count;
        }

        /// <summary>H3 (fix pass 3; bound in fix pass 4), what the popup's
        /// remote arm applies: never the settled copy, only a value its picker
        /// published bound to the pick that raised the popup, completed on
        /// arrival when it comes late; nothing on a seat with no pick identity.</summary>
        private static bool H3Remote(AvatarRules r, out string got)
        {
            const int P = 7;
            string old = Wire(1), face = Wire(3);
            // A: an unbound publish arrived earlier and settled; popup, apply, then the late echo
            var a = new RemoteSeat(r);
            a.Arrive(P, old);
            a.Show(P);
            int aShow = a.Equipped.Count;
            a.Now = 0.4;
            a.Arrive(P, Bd(face, 1, 0));
            bool okA = aShow == 0 && a.Equipped.Count == 1 && a.Equipped[0] == Bd(face, 1, 0) && a.Reads == 0
                && a.NotesWith("stale") == 1;
            // B: the picker's previous pick applied; its next popup is raised before that pick's echo
            var b = new RemoteSeat(r);
            b.Show(P);
            b.Arrive(P, Bd(old, 1, 0));                                       // pick1.0, applied on arrival
            b.Hide();
            b.Rounds = 1;
            b.Now = 6;
            b.Show(P);                                                        // pick1.1: nothing bound to it yet
            int bShow = b.Equipped.Count;
            b.Now = 6.3;
            b.Arrive(P, Bd(face, 1, 1));
            bool okB = bShow == 1 && b.Equipped.Count == 2 && b.Equipped[1] == Bd(face, 1, 1);
            // C: a seat that has seen no game start in its room (a spectator,
            // a seat that joined a running game) applies no carrier at all
            var c = new RemoteSeat(r, started: false);
            c.Arrive(P, Bd(face, 1, 0));
            c.Show(P);
            c.Now = 0.5;
            c.Arrive(P, Bd(face, 1, 0));
            bool okC = c.Equipped.Count == 0 && c.NotesWith("no pick identity") == 1;
            got = "A settled unbound " + Short(old) + ", popup, late echo: equipped at the popup " + aShow + ", in all " + a.Faces()
                + ", settled reads " + a.Reads + ", stale lines " + a.NotesWith("stale")
                + " | B the previous pick's value applied: equipped at the popup of pick1.1 " + (bShow - 1) + " new, in all " + b.Faces()
                + " | C no game start seen: " + c.Faces() + ", no-identity lines " + c.NotesWith("no pick identity");
            return okA && okB && okC;
        }

        /// <summary>H3 (fix pass 4), what is held for a picker whose popup is
        /// not open: a value is applied at the popup of the pick it is bound to
        /// (the picker's seat can be ahead), never at another pick's popup
        /// however long it waited; an unbound publish changes nothing held;
        /// another room drops what was held.</summary>
        private static bool H3Hold(AvatarRules r, out string got)
        {
            const int P = 7, Q = 8;
            string f3 = Wire(3), f4 = Wire(4);
            // D: the picker's seat is ahead: its value lands while this seat shows another picker
            var d = new RemoteSeat(r);
            d.Show(Q);
            d.Arrive(P, Bd(f3, 1, 0));
            d.Now = 0.5;
            d.Hide();
            d.Show(P);
            bool okD = d.Equipped.Count == 1 && d.Equipped[0] == Bd(f3, 1, 0);
            // E: a value bound to the previous pick is held; the next pick's
            // popup opens long after, before its own value
            var e = new RemoteSeat(r);
            e.Arrive(P, Bd(f3, 1, 0));
            e.Rounds = 1;
            e.Now = 3 * PopupCarrierLedger.DeferralBoundSeconds;
            e.Show(P);
            int eShow = e.Equipped.Count;
            e.Now += 0.2;
            e.Arrive(P, Bd(f4, 1, 1));
            bool okE = eShow == 0 && e.Equipped.Count == 1 && e.Equipped[0] == Bd(f4, 1, 1);
            // F: an unbound publish after a held bound value changes nothing held
            var f = new RemoteSeat(r);
            f.Arrive(P, Bd(f3, 1, 0));
            f.Arrive(P, f4);
            f.Show(P);
            bool okF = f.Equipped.Count == 1 && f.Equipped[0] == Bd(f3, 1, 0);
            // G: a new room drops what was held in the old one (its first game is game 1 again)
            var g = new RemoteSeat(r);
            g.Arrive(P, Bd(f3, 1, 0));
            g.Room = new object();
            g.GameStart();
            g.Show(P);
            bool okG = g.Equipped.Count == 0;
            got = "D early arrival under another popup: " + d.Faces()
                + " | E bound to pick1.0, the popup of pick1.1 at " + e.Now.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)
                + " s: at the popup " + eShow + ", in all " + e.Faces()
                + " | F held, then an unbound publish: " + f.Faces() + " | G held, then another room: " + g.Faces();
            return okD && okE && okF && okG;
        }

        /// <summary>H3 (fix pass 3), the owed apply follows E13's debt rules:
        /// recorded once however often the popup is re-shown, cleared only by
        /// an apply observed to complete, retried on the tick after a failure,
        /// and dropped with a line at the bound when nothing completes.</summary>
        private static bool H3Owed(AvatarRules r, out string got)
        {
            const int P = 7;
            string f3 = Wire(3);
            // H: re-shown twice before the value arrives; the first equip fails, the tick completes it
            var h = new RemoteSeat(r);
            h.Show(P);
            h.Show(P);
            h.Show(P);
            int deferrals = h.NotesWith("deferred");
            h.FailNext = 1;
            h.Now = 0.3;
            h.Arrive(P, Bd(f3, 1, 0));
            int afterFail = h.Equipped.Count;
            h.Now = 0.6;
            h.Tick();
            int afterRetry = h.Equipped.Count;
            h.Now = 0.9;
            h.Tick();
            bool okH = deferrals == 1 && afterFail == 0 && afterRetry == 1 && h.Equipped.Count == 1;
            // I: the equip keeps failing: retried on the tick until the bound, then dropped with a line
            var i = new RemoteSeat(r);
            i.Show(P);
            i.FailNext = 1000;
            i.Now = 0.2;
            i.Arrive(P, Bd(f3, 1, 0));
            for (int k = 1; k <= 60; k++) { i.Now = 0.2 + k * 0.25; i.Tick(); }
            double last = i.Attempts.Count > 0 ? i.Attempts[i.Attempts.Count - 1] : -1;
            bool okI = i.Attempts.Count > 2 && last <= PopupCarrierLedger.DeferralBoundSeconds && i.NotesWith("no longer owed") == 1;
            got = "H deferral lines over three shows " + deferrals + ", equipped after a failed arrival " + afterFail
                + ", after the tick " + afterRetry + ", after a second tick " + h.Equipped.Count
                + " | I attempts " + i.Attempts.Count + ", the last at " + last.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture)
                + " s, bound lines " + i.NotesWith("no longer owed");
            return okH && okI;
        }

        /// <summary>H9 (fix pass 3): a restoration whose apply does not commit
        /// keeps the debt, and the next retry restores the remembered face.</summary>
        private static bool Uncommitted(AvatarRules r, ApplyOutcome how, string what, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new Seat(3);
            seat.StepThrough(r, NotLive(), Room(false, Unmodded()), s);       // 3 -> 1, home 3
            int forced = seat.Live, held = seat.Home;
            seat.Next = how;
            var e6 = seat.StepThrough(r, NotLive(), Menu(), s);               // E6: the restoration does not commit
            int liveFail = seat.Live, homeFail = seat.Home;
            bool owed = r.RestorationOwed(seat.Home, true);                   // what E13 asks
            var retry = seat.StepThrough(r, NotLive(), Menu(), s);            // E13 (or a later E6, E7)
            got = what + ": forced live=" + forced + " home=" + held
                + " | the restoration (apply " + e6.Apply + ") did not commit: live " + liveFail + " home " + homeFail
                + " | owed to the tick=" + owed + " | the retry: apply " + retry.Apply + " live " + seat.Live + " home " + seat.Home;
            return forced == 1 && held == 3 && e6.Apply == 3 && liveFail == 1 && homeFail == 3 && owed
                && retry.Apply == 3 && seat.Live == 3 && seat.Home == -1;
        }

        private static bool H9Throw(AvatarRules r, out string got) => Uncommitted(r, ApplyOutcome.Throw, "the select throws before it commits", out got);
        private static bool H9Readback(AvatarRules r, out string got) => Uncommitted(r, ApplyOutcome.NoCommit, "the read-back shows the selection unmoved", out got);

        /// <summary>M3 (fix pass 3): repeated confirmed exits, the first with the
        /// character data missing and the next two with applies that do not
        /// commit, keep the one debt record until a restoration commits.</summary>
        private static bool M3Repeat(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new Seat(3);
            seat.StepThrough(r, NotLive(), Room(false, Unmodded()), s);       // 3 -> 1, home 3
            var e1 = seat.StepThrough(r, Live(), Menu(), s, facesMissing: true); // E6, the data missing
            int h1 = seat.Home;
            seat.Next = ApplyOutcome.Throw;
            var e2 = seat.StepThrough(r, Live(), Menu(), s);                  // E7, the select throws
            int h2 = seat.Home;
            seat.Next = ApplyOutcome.NoCommit;
            var e3 = seat.StepThrough(r, NotLive(), Menu(), s);               // E6 again, nothing commits
            int h3 = seat.Home;
            var e13 = seat.StepThrough(r, NotLive(), Menu(), s);              // the deferred edge, which commits
            got = "exit with the data missing: deferred=" + e1.RestorationDeferred + " home " + h1
                + " | exit, the select throws: apply " + e2.Apply + " home " + h2
                + " | exit, no commit: apply " + e3.Apply + " home " + h3
                + " | the deferred edge: apply " + e13.Apply + " live " + seat.Live + " home " + seat.Home + " applies " + seat.Applies;
            return e1.NothingToRead && e1.RestorationDeferred && h1 == 3 && e2.Apply == 3 && h2 == 3 && e3.Apply == 3 && h3 == 3
                && e13.Apply == 3 && seat.Live == 3 && seat.Home == -1 && seat.Applies == 2;
        }

        // ---- fix pass 4 (Codex BUILD round 4) ------------------------------

        /// <summary>H3 (fix pass 4, build round 4): the popup of a picker's
        /// pick N opens, then the carrier that picker published at pick N-1
        /// arrives LATE, after every earlier one (the newest arrival). It is
        /// never applied (logged stale) and nothing owed changes; the carrier
        /// bound to pick N completes the owed apply when it arrives.</summary>
        private static bool H3Late(AvatarRules r, out string got)
        {
            const int P = 7;
            var s = new RemoteSeat(r);
            s.Arrive(P, Bd(Wire(2), 1, 0));                                   // pick N-2 (pick1.0), in time
            s.Show(P);
            s.Hide();
            s.Rounds = 1;                                                     // pick N-1 (pick1.1): its carrier is late
            s.Now = 5;
            s.Show(P);
            s.Now = 9;
            s.Hide();
            s.Rounds = 2;                                                     // pick N (pick1.2)
            s.Now = 12;
            s.Show(P);
            int atShow = s.Equipped.Count;
            s.Now = 12.5;
            s.Arrive(P, Bd(Wire(3), 1, 1));                                   // pick N-1's carrier, the newest arrival
            int afterLate = s.Equipped.Count, stale = s.NotesWith("stale");
            s.Now = 13;
            s.Tick();
            int afterTick = s.Equipped.Count;
            s.Now = 13.2;
            s.Arrive(P, Bd(Wire(4), 1, 2));                                   // pick N's own carrier
            int completed = s.NotesWith("owed popup face applied");
            got = "pick1.0 in time: " + Short(Bd(Wire(2), 1, 0)) + " | the popup of pick1.2 opens: equipped " + (atShow - 1)
                + " new | pick1.1's carrier arrives late: equipped " + (afterLate - atShow) + " new, stale lines " + stale
                + " | the tick: " + (afterTick - afterLate) + " new | pick1.2's own carrier: in all " + s.Faces()
                + ", owed applies completed " + completed;
            return atShow == 1 && afterLate == 1 && stale == 1 && afterTick == 1 && s.Equipped.Count == 2
                && s.Equipped[1] == Bd(Wire(4), 1, 2) && completed == 1;
        }

        /// <summary>H3 (fix pass 4): a bound carrier arriving AFTER its popup
        /// opened: the apply is deferred (one line), then completed on
        /// arrival; at the next pick's popup the value bound to the previous
        /// pick is not applied, and a clear bound to that popup's pick settles
        /// what is owed with nothing applied.</summary>
        private static bool H3After(AvatarRules r, out string got)
        {
            const int P = 7;
            var s = new RemoteSeat(r);
            s.Show(P);                                                        // the popup of pick1.0: nothing bound to it yet
            int atShow = s.Equipped.Count, deferred = s.NotesWith("deferred");
            s.Now = 0.4;
            s.Arrive(P, Bd(Wire(4), 1, 0));                                   // its bound carrier
            int onArrival = s.Equipped.Count, completed = s.NotesWith("owed popup face applied");
            s.Hide();
            s.Rounds = 1;
            s.Now = 6;
            s.Show(P);                                                        // the popup of pick1.1
            int atShow2 = s.Equipped.Count;
            s.Now = 6.2;
            s.Arrive(P, PopupCarrierLedger.BoundClear(Pk(1, 1)));             // the picker cleared its carrier for pick1.1
            int settled = s.NotesWith("cleared its carrier for " + Pk(1, 1) + ": no longer owed");
            s.Now = 7;
            s.Tick();
            got = "the popup of pick1.0 opens first: equipped " + atShow + ", deferral lines " + deferred
                + " | its bound carrier arrives: equipped " + onArrival + " (" + s.Faces() + "), owed applies completed " + completed
                + " | the popup of pick1.1: equipped " + (atShow2 - onArrival) + " new | the clear bound to pick1.1: settled lines " + settled
                + ", equipped in all " + s.Equipped.Count;
            return atShow == 0 && deferred == 1 && onArrival == 1 && s.Equipped[0] == Bd(Wire(4), 1, 0) && completed == 1
                && atShow2 == 1 && settled == 1 && s.Equipped.Count == 1;
        }

        /// <summary>H3 (fix pass 4): a bound carrier arriving BEFORE its popup
        /// opens is applied at once when it opens, with no deferral; also when
        /// the picker's seat is ahead and its value, bound to a pick this seat
        /// has not reached yet, lands first.</summary>
        private static bool H3Before(AvatarRules r, out string got)
        {
            const int P = 7;
            var s = new RemoteSeat(r);
            s.Arrive(P, Bd(Wire(4), 1, 0));                                   // before the popup of pick1.0
            int onArrival = s.Equipped.Count;
            s.Now = 0.5;
            s.Show(P);
            int atShow = s.Equipped.Count;
            s.Hide();
            s.Now = 3;
            s.Arrive(P, Bd(Wire(6), 1, 1));                                   // the picker ahead: bound to pick1.1, this seat at pick1.0
            int ahead = s.Equipped.Count;
            s.Rounds = 1;
            s.Now = 4;
            s.Show(P);
            got = "arrived first: equipped on arrival " + onArrival + " | the popup of pick1.0: equipped " + atShow
                + " | the picker ahead, bound to pick1.1: equipped on arrival " + (ahead - atShow)
                + " | the popup of pick1.1: in all " + s.Faces() + ", deferral lines " + s.NotesWith("deferred");
            return onArrival == 0 && atShow == 1 && s.Equipped[0] == Bd(Wire(4), 1, 0) && ahead == 1
                && s.Equipped.Count == 2 && s.Equipped[1] == Bd(Wire(6), 1, 1) && s.NotesWith("deferred") == 0;
        }

        /// <summary>H9 and M3 (fix pass 4): a seat moved as AvatarDefaults moves
        /// it, whose apply is the OWNED select with the SelectFace postfix (E9)
        /// that Harmony runs on every normal return of the select. The postfix
        /// defers when AvatarRules.DefersSelectEdge says so (the select's depth
        /// is held around it, as AvatarDefaults.Apply holds it), else it
        /// evaluates again, one select deeper. A select nested past Bound gives
        /// up (the harness's depth bound: in production the stand-in throws and
        /// Apply catches it), so a re-entry without a bound ends here instead of
        /// overflowing the stack, and Deepest shows it. NoOp: every select
        /// returns normally without committing (a persistent no-op);
        /// NoCommitOnce: the next one does; ThrowOnce: the next one throws
        /// before it commits (no postfix runs).</summary>
        private sealed class ReentrantSeat
        {
            internal const int Bound = 8;
            internal int Live, Home = -1, Selects, Depth, Deepest, Deferred;
            internal bool NoOp;
            internal int NoCommitOnce, ThrowOnce;
            private readonly AvatarRules rules;

            internal ReentrantSeat(AvatarRules r, int live) { rules = r; Live = live; }

            internal AvatarDecision Evaluate(AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s, bool facesMissing = false)
            {
                var x = In(l, f, s, Live, Home);
                if (facesMissing) x.Faces = null;
                var d = rules.Evaluate(x);
                if (d.Gated || d.NothingToRead) return d;
                int held = rules.HomeBeforeApply(Home, d);
                Home = held;
                int after = d.Apply >= 0 ? Apply(d.Apply, l, f, s) : Live;
                Home = rules.HomeAfterApply(held, d, after);
                return d;
            }

            private int Apply(int slot, AvatarLivenessIn l, AvatarFacingIn f, AvatarSetting s)
            {
                Selects++;
                Depth++;
                if (Depth > Deepest) Deepest = Depth;
                try
                {
                    if (Depth > Bound) return Live;                    // the bound: this select gives up
                    if (ThrowOnce > 0) { ThrowOnce--; return Live; }  // threw before committing: no postfix
                    bool commit = !NoOp;
                    if (commit && NoCommitOnce > 0) { NoCommitOnce--; commit = false; }
                    if (commit) Live = slot;
                    if (rules.DefersSelectEdge(Depth)) Deferred++;     // E9 inside the owned apply
                    else Evaluate(l, f, s);                            // E9 re-entering the evaluator
                }
                finally { Depth--; }
                return Live;                                           // the read-back
            }
        }

        /// <summary>H9 (fix pass 4): a persistent no-op select. Each confirmed
        /// exit (E6, E7) and the deferred edge (E13) makes ONE select and keeps
        /// the one debt; nothing nests; the first trigger after the select
        /// works again repays it.</summary>
        private static bool H9Loop(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new ReentrantSeat(r, 3);
            seat.Evaluate(NotLive(), Room(false, Unmodded()), s);             // 3 -> 1, home 3
            int forced = seat.Live, held = seat.Home;
            seat.NoOp = true;
            int s0 = seat.Selects;
            seat.Evaluate(NotLive(), Menu(), s);                              // E6
            int e6 = seat.Selects - s0, deep6 = seat.Deepest, h6 = seat.Home;
            seat.Evaluate(NotLive(), Menu(), s);                              // E7
            int e7 = seat.Selects - s0 - e6, h7 = seat.Home;
            seat.Evaluate(NotLive(), Menu(), s);                              // E13
            int e13 = seat.Selects - s0 - e6 - e7, h13 = seat.Home, deep = seat.Deepest;
            seat.NoOp = false;
            seat.Evaluate(NotLive(), Menu(), s);                              // the next trigger, the select working
            got = "forced live=" + forced + " home=" + held + " | a no-op select: E6 selects " + e6 + " (deepest " + deep6
                + ", bound " + ReentrantSeat.Bound + ") home " + h6 + " | E7 selects " + e7 + " home " + h7
                + " | E13 selects " + e13 + " home " + h13 + " | deepest overall " + deep
                + " | the select works again: live " + seat.Live + " home " + seat.Home + ", E9 deferrals " + seat.Deferred;
            return forced == 1 && held == 3 && e6 == 1 && e7 == 1 && e13 == 1 && deep6 == 1 && deep == 1
                && h6 == 3 && h7 == 3 && h13 == 3 && seat.Live == 3 && seat.Home == -1;
        }

        /// <summary>H9 (fix pass 4): the E9 postfix fires inside the owned apply
        /// of a confirmed exit whose select returns without committing: it
        /// defers, the read-back keeps the debt, and a LATER confirmed exit
        /// (E7) retries and commits.</summary>
        private static bool H9Defer(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new ReentrantSeat(r, 3);
            seat.Evaluate(NotLive(), Room(false, Unmodded()), s);             // 3 -> 1, home 3
            seat.NoCommitOnce = 1;
            int s0 = seat.Selects, d0 = seat.Deferred;
            seat.Evaluate(NotLive(), Menu(), s);                              // E6: not committed
            int e6 = seat.Selects - s0, deferred = seat.Deferred - d0, l6 = seat.Live, h6 = seat.Home;
            seat.Evaluate(NotLive(), Menu(), s);                              // E7, the later trigger
            int e7 = seat.Selects - s0 - e6;
            got = "E6 whose select does not commit: selects " + e6 + ", E9 deferred " + deferred + ", live " + l6 + " home " + h6
                + " | E7 retries: selects " + e7 + ", live " + seat.Live + " home " + seat.Home;
            return e6 == 1 && deferred == 1 && l6 == 1 && h6 == 3 && e7 == 1 && seat.Live == 3 && seat.Home == -1;
        }

        /// <summary>M3 (fix pass 4, the fix pass 3 M3x re-run with the E9
        /// postfix): repeated confirmed exits, the first with the character
        /// data missing, the second whose select throws before it commits, the
        /// third whose select returns normally without committing (the postfix
        /// runs), keep the one debt until a later trigger commits it.</summary>
        private static bool M3Reentry(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new ReentrantSeat(r, 3);
            seat.Evaluate(NotLive(), Room(false, Unmodded()), s);             // 3 -> 1, home 3
            var e1 = seat.Evaluate(Live(), Menu(), s, facesMissing: true);    // E6, the data missing
            int h1 = seat.Home;
            seat.ThrowOnce = 1;
            seat.Evaluate(Live(), Menu(), s);                                 // E7, the select throws
            int h2 = seat.Home, l2 = seat.Live;
            seat.NoCommitOnce = 1;
            int s0 = seat.Selects;
            seat.Evaluate(NotLive(), Menu(), s);                              // E6 again: no commit, the postfix runs
            int e3 = seat.Selects - s0, h3 = seat.Home, l3 = seat.Live;
            seat.Evaluate(NotLive(), Menu(), s);                              // E13, which commits
            got = "exit with the data missing: deferred=" + e1.RestorationDeferred + " home " + h1
                + " | exit, the select throws: live " + l2 + " home " + h2
                + " | exit, no commit with the postfix: selects " + e3 + " live " + l3 + " home " + h3
                + " | the deferred edge: live " + seat.Live + " home " + seat.Home + ", deepest " + seat.Deepest;
            return e1.NothingToRead && e1.RestorationDeferred && h1 == 3 && h2 == 3 && l2 == 1 && e3 == 1 && h3 == 3 && l3 == 1
                && seat.Live == 3 && seat.Home == -1 && seat.Deepest == 1;
        }

        /// <summary>M8 (fix pass 3): the line of every exit, as
        /// AvatarDefaults.Evaluate writes it before any fallible work
        /// (ClassificationLine, then MissingDataNote): E2 and E3 with the
        /// character data missing, the deferred exit, and an applied change.
        /// Each names the facing, the nominee and the other-fighter count.</summary>
        private static bool M8Exits(AvatarRules r, out string got)
        {
            var s = Set(true, 2, 1);
            var sb = new StringBuilder();
            Func<string, AvatarEvalIn, string, string> line = (tag, x, missing) =>
            {
                var d = r.Evaluate(x);
                int n = x.Facing.OtherFighterKeys != null ? x.Facing.OtherFighterKeys.Count : 0;
                string l = r.LogsClassification(tag) || d.Apply >= 0
                    ? r.ClassificationLine(tag, d, n, x.Facing.ModIssuedRoom, x.Live, x.Home) + r.MissingDataNote(d, d.NothingToRead ? missing : null, x.Home)
                    : "(no line)";
                sb.Append(" || ").Append(l);
                return l;
            };
            var e2x = In(NotLive(), Room(false, Unmodded()), s, -1, -1);
            e2x.Faces = null;
            string e2 = line("E2-joined", e2x, "no character controller");
            string e3 = line("E3-entered", In(NotLive(), Room(true, Modded()), s, -1, -1), "no selected face");
            var defx = In(Live(), Menu(), s, 1, 3);
            defx.Faces = null;
            string def = line("E6-left", defx, "no face table");
            string app = line("E2-joined", In(NotLive(), Room(false, Unmodded()), s, 3, -1), null);
            bool ok = e2.Contains("(facing Vanilla, nominee 1, other fighters 1,") && e2.EndsWith(": nothing applied (no character controller)")
                && e3.Contains("(facing Modded, nominee 2, other fighters 1,") && e3.EndsWith(": nothing applied (no selected face)")
                && def.Contains("(facing Undecided, nominee -1, other fighters 0,") && def.Contains(": restoration deferred (no face table), home 3 kept")
                && app.StartsWith("[AVATAR] E2-joined applied slot 1 (facing Vanilla, nominee 1, other fighters 1,") && app.EndsWith(")");
            got = "E2 and E3 with the data missing, the deferred exit, an applied change" + sb;
            return ok;
        }

        /// <summary>H9 and M3: a seat forced 3 -> 1 in a vanilla room (home 3),
        /// then a confirmed exit while the character data is missing, twice
        /// (the repeated exit edge), then the deferred edge with the data back.</summary>
        private static bool MissingData(AvatarRules r, AvatarFaceIds[] faces, int live, string what, out string got)
        {
            var s = Set(true, 2, 1);
            var seat = new Seat(3);
            seat.Step(r, NotLive(), Room(false, Unmodded()), s);                  // 3 -> 1, home 3
            int forced = seat.Live, held = seat.Home;
            var x = new AvatarEvalIn { Liveness = Live(), Facing = Menu(), Setting = s, Faces = faces, Loader = Loader(), Live = live, Home = seat.Home };
            var e1 = r.Evaluate(x);                                               // E6, the data gone
            var e2 = r.Evaluate(x);                                               // E7, a repeated exit edge
            bool kept = e1.NothingToRead && e2.NothingToRead && e1.NewHome == held && e2.NewHome == held && !e1.HomeChanged && !e2.HomeChanged;
            bool deferred = e1.RestorationDeferred && e2.RestorationDeferred;
            bool owed = r.RestorationOwed(e2.NewHome, true);
            bool notInRoom = !r.RestorationOwed(e2.NewHome, false);
            seat.Home = e2.NewHome;
            var e13 = seat.Step(r, NotLive(), Menu(), s);                         // E13, the data back
            bool quiet = !r.RestorationOwed(seat.Home, true);
            got = what + ": forced live=" + forced + " home=" + held + " | exit x2 with the data missing: home kept=" + kept
                + " deferred=" + deferred + " owed=" + owed + " owed in a room=" + !notInRoom
                + " | the deferred edge: apply=" + e13.Apply + " live=" + seat.Live + " home=" + seat.Home + " then owed=" + !quiet;
            return forced == 1 && held == 3 && kept && deferred && owed && notInRoom && e13.Apply == 3 && seat.Live == 3
                && seat.Home == -1 && quiet;
        }

        private static bool H9Controller(AvatarRules r, out string got) => MissingData(r, null, -1, "no controller", out got);
        private static bool H9Selected(AvatarRules r, out string got) => MissingData(r, Faces(), -1, "no selected face", out got);
        private static bool M3Table(AvatarRules r, out string got) => MissingData(r, null, 1, "no face table", out got);

        // ---- the mutants and the controls -------------------------------

        // fix pass 1 mutants: each restores the build-round-1 behaviour (or
        // drops exactly the term its case is about); each control is the same
        // method rewritten with its meaning unchanged.
        private sealed class M_H6a : AvatarRules
        {
            internal override bool Live(AvatarLivenessIn l) { if (l.Unreadable) return true; return l.ManagerExists ? l.BattleOngoing : l.LocalBodyExists; }
        }
        private sealed class M_H6b : AvatarRules
        {
            internal override bool Live(AvatarLivenessIn l) { if (l.Unreadable) return true; return l.ManagerExists ? l.IsPlaying : l.LocalBodyExists; }
        }
        private sealed class M_H6c : AvatarRules
        {
            internal override bool Live(AvatarLivenessIn l) { if (l.Unreadable) return true; return l.ManagerExists && (l.IsPlaying || l.BattleOngoing); }
        }

        private sealed class M_ProvenanceDecides : AvatarRules
        {   // build round 1's FacingOf: provenance before the roster
            internal override AvatarFacing FacingOf(AvatarFacingIn f)
            {
                if (f.InRoom && !f.OfflineMode && !f.Unreadable && !f.LocalIsSpectator && f.RoomExists && f.ModIssuedRoom) return AvatarFacing.Modded;
                return base.FacingOf(f);
            }
        }
        private sealed class M_SoloIssued : AvatarRules
        {   // provenance answers only the empty roster
            internal override AvatarFacing FacingOf(AvatarFacingIn f)
            {
                var c = base.FacingOf(f);
                bool empty = f.OtherFighterKeys == null || f.OtherFighterKeys.Count == 0;
                return c == AvatarFacing.Undecided && f.InRoom && f.RoomExists && !f.OfflineMode && !f.LocalIsSpectator && f.ModIssuedRoom && empty
                    ? AvatarFacing.Modded : c;
            }
        }

        private sealed class M_LivenessFirst : AvatarRules
        {   // build round 1's Census: liveness before the confirmed exit
            internal override AvatarFacing Census(AvatarLivenessIn l, AvatarFacingIn f) => Live(l) ? AvatarFacing.Locked : FacingOf(f);
        }
        private sealed class M_AnyNoRoomIsExit : AvatarRules
        {   // an unreadable room read counted as a confirmed exit
            internal override AvatarFacing Census(AvatarLivenessIn l, AvatarFacingIn f)
            {
                if (!f.InRoom) return FacingOf(f);
                return Live(l) ? AvatarFacing.Locked : FacingOf(f);
            }
        }
        private sealed class K_Census : AvatarRules
        {
            internal override AvatarFacing Census(AvatarLivenessIn l, AvatarFacingIn f)
            {
                bool confirmedExit = f.InRoom == false && f.Unreadable == false;
                if (!confirmedExit && Live(l)) return AvatarFacing.Locked;
                return FacingOf(f);
            }
        }

        private sealed class M_OnePresetEnough : AvatarRules { internal override bool BothPresetsSet(AvatarSetting s) => true; }
        private sealed class K_BothPresets : AvatarRules { internal override bool BothPresetsSet(AvatarSetting s) => !(s.Modded < 0 || s.Vanilla < 0); }

        private sealed class M_UnreadableFirst : AvatarRules
        {   // build round 1's FacingOf order: unreadability before the room
            internal override AvatarFacing FacingOf(AvatarFacingIn f) => f.Unreadable ? AvatarFacing.Vanilla : base.FacingOf(f);
        }

        private sealed class M_H3 : AvatarRules
        {   // build round 1's publisher: a definitive decline writes nothing
            internal override FaceCarrierAction CarrierAction(bool spectator, bool handlerReady, bool localPlayerReady, bool facesListed, AvatarFaceIds face0)
            {
                var a = base.CarrierAction(spectator, handlerReady, localPlayerReady, facesListed, face0);
                return a == FaceCarrierAction.Clear ? FaceCarrierAction.Keep : a;
            }
        }
        private sealed class K_H3 : AvatarRules
        {
            internal override FaceCarrierAction CarrierAction(bool spectator, bool handlerReady, bool localPlayerReady, bool facesListed, AvatarFaceIds face0)
            {
                if (!(handlerReady && localPlayerReady) || spectator) return FaceCarrierAction.Keep;
                bool valid = facesListed && face0.Present && !face0.AllZero;
                return valid ? FaceCarrierAction.Publish : FaceCarrierAction.Clear;
            }
        }

        private sealed class M_M8 : AvatarRules
        {   // the capture loses the other-fighter count
            internal override string ClassificationLine(string tag, AvatarDecision d, int otherFighters, bool issuedRoom, int was, int homeBefore)
                => base.ClassificationLine(tag, d, -1, issuedRoom, was, homeBefore);
        }
        private sealed class K_M8 : AvatarRules
        {
            internal override string ClassificationLine(string tag, AvatarDecision d, int otherFighters, bool issuedRoom, int was, int homeBefore)
                => string.Concat(base.ClassificationLine(tag, d, otherFighters, issuedRoom, was, homeBefore), "");
        }

        // fix pass 2 mutants and controls
        private sealed class M_H3Reread : AvatarRules
        {   // the round 2 postfix: the pass rereads the cache it has just published to
            internal override string PopupFace(bool pickerIsLocal, FaceCarrierAction published, string publishedValue, Func<string> readCarrier)
                => readCarrier != null ? readCarrier() : null;
        }
        private sealed class K_H3Pop : AvatarRules
        {
            internal override string PopupFace(bool pickerIsLocal, FaceCarrierAction published, string publishedValue, Func<string> readCarrier)
            {
                if (!pickerIsLocal) return readCarrier == null ? null : readCarrier();
                return published != FaceCarrierAction.Publish ? null : publishedValue;
            }
        }
        private sealed class M_ClearOnMissing : AvatarRules
        {   // a missing read "settles" the debt by forgetting it
            internal override AvatarDecision Evaluate(AvatarEvalIn x)
            {
                var d = base.Evaluate(x);
                if (d.NothingToRead) { d.NewHome = -1; d.HomeChanged = x.Home != -1; d.RestorationDeferred = false; }
                return d;
            }
        }
        private sealed class M_NoDeferral : AvatarRules
        {   // the round 2 shape: nothing records that a restoration is owed
            internal override AvatarDecision Evaluate(AvatarEvalIn x) { var d = base.Evaluate(x); d.RestorationDeferred = false; return d; }
        }
        private sealed class M_NeverOwed : AvatarRules { internal override bool RestorationOwed(int home, bool confirmedNoRoom) => false; }
        private sealed class K_Owed : AvatarRules
        {
            internal override bool RestorationOwed(int home, bool confirmedNoRoom) { if (!confirmedNoRoom) return false; return home > -1; }
        }

        // fix pass 3 mutants and controls (fix pass 4 replaced the provenance
        // and hold mutants with the binding's, below: their rules are gone)
        private sealed class M_H3OwedForever : AvatarRules
        {   // the deferral never ends
            internal override bool OwedWithin(double deferredSince, double now) => true;
        }
        private sealed class K_H3Owed : AvatarRules
        {
            internal override bool OwedWithin(double deferredSince, double now)
                => !(now - deferredSince > PopupCarrierLedger.DeferralBoundSeconds);
        }
        private sealed class M_PayBeforeCommit : AvatarRules
        {   // the round 3 order: the debt is cleared before the apply runs
            internal override int HomeBeforeApply(int homeBefore, AvatarDecision d) => d.HomeChanged ? d.NewHome : homeBefore;
        }
        private sealed class M_IgnoreReadback : AvatarRules
        {   // the debt is cleared after the apply whatever the read-back shows
            internal override int HomeAfterApply(int homeHeld, AvatarDecision d, int liveAfter) => d.HomeChanged ? d.NewHome : homeHeld;
        }
        private sealed class K_HomeOrder : AvatarRules
        {
            internal override int HomeBeforeApply(int homeBefore, AvatarDecision d)
            {
                if (!d.HomeChanged) return homeBefore;
                return d.NewHome < 0 ? homeBefore : d.NewHome;
            }
            internal override int HomeAfterApply(int homeHeld, AvatarDecision d, int liveAfter)
            {
                if (d.HomeChanged && d.NewHome < 0 && liveAfter == (d.Apply >= 0 ? d.Apply : d.Want)) return d.NewHome;
                return homeHeld;
            }
        }
        // fix pass 4 mutants and controls
        private sealed class M_H3NoBinding : AvatarRules
        {   // the binding check dropped: a value bound to any pick is taken for the popup's
            internal override bool BoundToPopup(string pick, string popupPick) => popupPick != null;
        }
        private sealed class M_H3NeverBound : AvatarRules
        {   // no value is ever bound to the popup's pick
            internal override bool BoundToPopup(string pick, string popupPick) => false;
        }
        private sealed class K_H3Binding : AvatarRules
        {
            internal override bool BoundToPopup(string pick, string popupPick)
                => popupPick != null && string.Equals(popupPick, pick, StringComparison.Ordinal);
        }
        private sealed class M_NoDepthGuard : AvatarRules
        {   // the depth guard removed: the E9 postfix re-enters the evaluator inside the owned apply
            internal override bool DefersSelectEdge(int ownedApplyDepth) => false;
        }
        private sealed class K_DepthGuard : AvatarRules
        {
            internal override bool DefersSelectEdge(int ownedApplyDepth) => !(ownedApplyDepth <= 0);
        }

        private sealed class M_M8NomineeLate : AvatarRules
        {   // the round 3 rules: the nominee is read only after the missing-data exit
            internal override AvatarDecision Evaluate(AvatarEvalIn x)
            {
                var d = base.Evaluate(x);
                if (d.NothingToRead) d.Nominee = -1;
                return d;
            }
        }
        private sealed class K_M8Note : AvatarRules
        {
            internal override string MissingDataNote(AvatarDecision d, string missing, int home)
            {
                if (d.NothingToRead == false) return string.Empty;
                return base.MissingDataNote(d, missing, home);
            }
        }

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

        // ---- bug 444 (the night of 2026-10-19) ---------------------------

        /// <summary>Bug 444. The night's sequence: modded default 5, vanilla
        /// default 4, live 4, a private 1v2 room whose two other fighters both
        /// carry the mod. The rules apply the authored nominee 5. The menu
        /// portrait for slot 5 has not started in this scene, so it holds an
        /// all-zero default face that is not the preset: the apply must take the
        /// direct select, which writes playerFaces[5], and the carrier rule
        /// publishes that face. A started portrait (it holds the preset) keeps
        /// the portrait route; zero or two portraits take the direct select.
        /// An unauthored nominee in the same room keeps the own face and is
        /// reported Unauthored (design 2.4), and the carrier rule still clears
        /// an all-zero selected face (A-H3, unchanged).</summary>
        private static bool B444(AvatarRules r, out string got)
        {
            var s = Set(true, 5, 4);
            var room = Room(true, Modded(), Modded());
            var d = r.Evaluate(In(NotLive(), room, s, 4, -1));
            bool unstarted = r.SelectsThroughPortrait(1, false);
            bool started = r.SelectsThroughPortrait(1, true);
            bool none = r.SelectsThroughPortrait(0, false);
            bool two = r.SelectsThroughPortrait(2, true);
            var faces = Faces();
            var written = unstarted ? AvatarFaceIds.Of(0, 0, 0, 0) : faces[5];   // the face the select writes
            var carrier = r.CarrierAction(false, true, true, true, written);
            var zero = r.CarrierAction(false, true, true, true, AvatarFaceIds.Of(0, 0, 0, 0));
            var u = r.Evaluate(In(NotLive(), room, Set(true, 0, 4), 4, -1));
            got = "facing=" + d.Facing + " apply=" + d.Apply + " | portrait route: unstarted=" + unstarted + " started=" + started
                + " none=" + none + " two=" + two + " | carrier on the written face=" + carrier + " on all-zero=" + zero
                + " | unauthored nominee 0: apply=" + u.Apply + " want=" + u.Want + " unusable=" + u.Unusable;
            return d.Facing == AvatarFacing.Modded && d.Apply == 5
                && !unstarted && started && !none && !two
                && carrier == FaceCarrierAction.Publish && zero == FaceCarrierAction.Clear
                && u.Apply == -1 && u.Want == 4 && u.Unusable == AvatarUnusable.Unauthored;
        }

        /// <summary>The route before the fix: one portrait is enough, whatever
        /// face it holds.</summary>
        private sealed class M_B444 : AvatarRules
        {
            internal override bool SelectsThroughPortrait(int hits, bool portraitHoldsSlotFace) => hits == 1;
        }

        private sealed class K_B444 : AvatarRules
        {
            internal override bool SelectsThroughPortrait(int hits, bool portraitHoldsSlotFace) => portraitHoldsSlotFace && hits == 1;
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

            // fix pass 1 (Codex BUILD round 1), one case per finding. The H6
            // controls are each other's mutants: dropping a DIFFERENT liveness
            // term must leave the case green, so no term masks another.
            Pair(r, "H6a", "isPlaying alone blocks a face change", H6a, new M_H6a(), new M_H6b());
            Pair(r, "H6b", "battleOngoing alone blocks a face change", H6b, new M_H6b(), new M_H6c());
            Pair(r, "H6c", "a local body without a manager blocks a face change", H6c, new M_H6c(), new M_H6a());
            Pair(r, "H8", "an issued room with an unmodded entrant is Vanilla; its departure is Modded", H8, new M_ProvenanceDecides(), new K_FacingSame());
            Pair(r, "BRH1", "Modded only from a nonempty every-modded census; an issued room with zero others keeps the own face", BRH1, new M_SoloIssued(), new K_FacingSame());
            Pair(r, "H9", "a leave while the old manager reports live repays the remembered selection", H9, new M_LivenessFirst(), new K_Census());
            Pair(r, "M3", "a disconnect alone restores once, repeated exits write nothing, an unreadable room read stays locked", M3, new M_AnyNoRoomIsExit(), new K_Census());
            Pair(r, "BRM3", "automatic switching needs both preset slots set; a remembered selection is still given back", BRM3, new M_OnePresetEnough(), new K_BothPresets());
            Pair(r, "BRM4", "an unreadable facing is Vanilla only inside an established online room", BRM4, new M_UnreadableFirst(), new K_FacingSame());
            Pair(r, "H3", "a definitive no-face publish attempt clears the carrier", H3, new M_H3(), new K_H3());
            Pair(r, "M8", "the classification line names facing, nominee and other fighters for the five room cases", M8, new M_M8(), new K_M8());

            // fix pass 2 (Codex BUILD round 2). The production bindings of H6,
            // M8, BR-M4 and L1, and the production half of H9 and M3, are
            // executed by tools/item19-controls/prodprobe (pytest S35), which
            // compiles plugin/AvatarDefaults.cs itself.
            Pair(r, "H3async", "the local picker's popup uses the value it published: publish, read, echo over an asynchronous cache; a remote popup raised over a stale settled copy applies the late echo, never the copy", H3Async, new M_H3Reread(), new K_H3Pop());
            Pair(r, "H9c", "a confirmed exit with no character controller keeps the debt, defers it, and the deferred edge repays it", H9Controller, new M_ClearOnMissing(), new K_Eval());
            Pair(r, "H9s", "a confirmed exit with no selected face keeps the debt, defers it, and the deferred edge repays it", H9Selected, new M_NoDeferral(), new K_Eval());
            Pair(r, "M3t", "a confirmed exit with no face table keeps the debt, defers it, and the deferred edge repays it", M3Table, new M_NeverOwed(), new K_Owed());

            // fix pass 3 (Codex BUILD round 3). The production order of H9, M3
            // and M8 (the debt cleared after the read-back, the line written
            // before the apply) is executed by tools/item19-controls/prodprobe
            // (pytest S35) over plugin/AvatarDefaults.cs itself.
            // Fix pass 4 rebuilt H3remote and H3hold on the pick binding.
            Pair(r, "H3remote", "a remote popup applies only a value bound to the pick it shows: never a settled unbound copy, never the previous pick's, nothing on a seat with no pick identity", H3Remote, new M_H3NoBinding(), new K_H3Binding());
            Pair(r, "H3hold", "a held value is applied at the popup of the pick it is bound to (the picker ahead), never at another pick's however long it waited; an unbound publish changes nothing held; another room drops it", H3Hold, new M_H3NoBinding(), new K_H3Binding());
            Pair(r, "H3owed", "the owed popup face: recorded once, cleared only by a completed apply, retried on the tick, dropped with a line at the bound", H3Owed, new M_H3OwedForever(), new K_H3Owed());
            Pair(r, "H9t", "a restoration whose select throws before it commits keeps the debt, and the retry restores", H9Throw, new M_PayBeforeCommit(), new K_HomeOrder());
            Pair(r, "H9r", "a restoration whose read-back shows the selection unmoved keeps the debt, and the retry restores", H9Readback, new M_IgnoreReadback(), new K_HomeOrder());
            Pair(r, "M3x", "repeated confirmed exits (data missing, a throw, no commit) keep the one debt record until a restoration commits", M3Repeat, new M_PayBeforeCommit(), new K_HomeOrder());
            Pair(r, "M8x", "every exit's line names facing, nominee and other fighters: E2 and E3 with the data missing, the deferred exit, an applied change", M8Exits, new M_M8NomineeLate(), new K_M8Note());

            // fix pass 4 (Codex BUILD round 4). H3: the carrier is bound to
            // the pick its popup shows (the asynchronous remote-seat model);
            // H9 and M3: the E9 postfix Harmony runs inside the owned apply
            // defers to its read-back (the re-entrant seat model). The
            // production halves are executed by tools/item19-controls/prodprobe
            // (pytest S35: H3late, H3after, H3before, H9loop, H9defer, M3x).
            Pair(r, "H3late", "the popup of pick N never applies the late carrier of pick N-1 (logged stale, nothing owed changes); pick N's own carrier completes it", H3Late, new M_H3NoBinding(), new K_H3Binding());
            Pair(r, "H3after", "a bound carrier arriving after its popup opened is deferred, then applied on arrival; the next pick's popup is not given it; a clear bound to that pick settles what is owed", H3After, new M_H3NoBinding(), new K_H3Binding());
            Pair(r, "H3before", "a bound carrier arriving before its popup opens (also from a picker ahead) is applied at once, with no deferral", H3Before, new M_H3NeverBound(), new K_H3Binding());
            Pair(r, "H9loop", "a persistent no-op select is bounded: one select per trigger, one debt kept, no nesting, repaid when the select works", H9Loop, new M_NoDepthGuard(), new K_DepthGuard());
            Pair(r, "H9defer", "the E9 postfix inside an owned apply that does not commit defers; the debt is kept and a later E7 retries it", H9Defer, new M_NoDepthGuard(), new K_DepthGuard());
            Pair(r, "M3e9", "repeated confirmed exits with the E9 postfix run (data missing, a throw, a normal return without commit) keep the one debt until a later trigger commits", M3Reentry, new M_NoDepthGuard(), new K_DepthGuard());

            // bug 444: the apply selects through a portrait only when it holds
            // the slot's preset (an unstarted portrait holds an all-zero default)
            Pair(r, "B444", "the night's 1v2 sequence applies authored slot 5 by the direct select when its portrait has not started, and the carrier publishes it; an unauthored nominee keeps the own face", B444, new M_B444(), new K_B444());
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
