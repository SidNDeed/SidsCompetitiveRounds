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
