using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Item 19 (v1.41.0, two default avatars switched by the kind of
    /// room). The DECISION half of the feature, kept free of Unity, Photon and
    /// BepInEx so tools/client-rules-harness can EXECUTE it (suite
    /// "avatardefaults", cases in the harness-only AvatarDefaultRulesSelfTest.cs).
    /// AvatarDefaults.cs reads the live game into the plain values below and
    /// applies what this file decides.
    ///
    /// The method (design revision 3, "derive, do not latch"): the face shown
    /// is a pure function f(census, setting, own selection), recomputed on
    /// every edge. The only remembered value is the pre-switch own selection
    /// ("Home", the UI/AvatarHomeSlot config int), restored when the
    /// condition that forced the switch ends. A live game is a GATE on the
    /// evaluator, never a return value of f: f has no way to say "write
    /// nothing", because every value it returns is a face and the evaluator
    /// applies it (design section 0, DEVIATION 3).
    ///
    /// The methods are instance and virtual for one reason only: the harness
    /// replaces a single method with a mutant to prove each check can go red.
    /// The class holds no field; production code makes a fresh instance per
    /// evaluation, so nothing here can carry state between edges.</summary>
    internal enum AvatarFacing { Locked, Undecided, Modded, Vanilla }

    /// <summary>Why a nominee the setting names cannot be used (case 2 of the
    /// notifications, design section 2.4). None also covers an unset nominee,
    /// which is silent.</summary>
    internal enum AvatarUnusable { None, NotClean, Unauthored }

    /// <summary>Which "switched" message an apply raises. Restore (the room
    /// ended, the setting was turned off, the nominee stopped being usable)
    /// raises none: no literal names it, and the launch restore is silent by
    /// design (section 2.10, last paragraph).</summary>
    internal enum AvatarSwitched { None, ToVanilla, ToModded }

    /// <summary>The four typed ids of one saved face. Present is false for a
    /// null playerFaces entry.</summary>
    internal struct AvatarFaceIds
    {
        internal bool Present;
        internal int Eye, Mouth, Detail, Detail2;

        internal static AvatarFaceIds Of(int eye, int mouth, int detail, int detail2)
        {
            return new AvatarFaceIds { Present = true, Eye = eye, Mouth = mouth, Detail = detail, Detail2 = detail2 };
        }

        internal bool AllZero => Eye == 0 && Mouth == 0 && Detail == 0 && Detail2 == 0;
    }

    /// <summary>The BASE loader's three arrays as "is entry i non-null". Null
    /// arrays mean the loader (or that array) could not be read.</summary>
    internal sealed class AvatarLoaderView
    {
        internal bool[] Eyes, Mouths, Accessories;
    }

    /// <summary>Input 2, read live from the config on every evaluation.</summary>
    internal struct AvatarSetting
    {
        internal bool Auto;
        internal int Modded, Vanilla;   // -1 = not set
    }

    /// <summary>Term (1) of the census: may the face move at all.</summary>
    internal struct AvatarLivenessIn
    {
        internal bool Unreadable;       // reading the game threw
        internal bool ManagerExists;    // GameManager.instance != null
        internal bool IsPlaying, BattleOngoing;
        internal bool LocalBodyExists;  // only consulted without a manager
    }

    /// <summary>Term (2) of the census: which default does this room call
    /// for. Every term is a fact every seat in the room computes identically,
    /// except the three that can only answer Undecided (design 2.2's audit).</summary>
    internal struct AvatarFacingIn
    {
        internal bool Unreadable;       // reading the room threw
        internal bool InRoom, OfflineMode, LocalIsSpectator, RoomExists;
        internal bool ModIssuedRoom;    // CompetitiveRoomDetect.IsModIssuedRoom(name, props): logged, never decides (BR-H1)
        /// <summary>One entry per OTHER active fighter: that actor's custom
        /// property keys (a null entry = an actor whose properties are null).</summary>
        internal IList<IList<string>> OtherFighterKeys;
        /// <summary>The face carrier's property key, which the per-actor test
        /// skips (supplied by AvatarDefaults from FacePublisher.PROP_FACE).</summary>
        internal string FaceKey;
    }

    /// <summary>Everything one evaluation reads.</summary>
    internal struct AvatarEvalIn
    {
        internal AvatarLivenessIn Liveness;
        internal AvatarFacingIn Facing;
        internal AvatarSetting Setting;
        internal AvatarFaceIds[] Faces;     // playerFaces, null when unreadable
        internal AvatarLoaderView Loader;
        internal int Live;                   // selectedFaceID[0]; < 0 when unreadable
        internal int Home;                   // the config int, unvalidated
    }

    /// <summary>What one evaluation decided. The caller applies Apply (when
    /// >= 0), then publishes, writes NewHome, and raises the messages.</summary>
    internal struct AvatarDecision
    {
        internal bool Gated;                 // a live game: nothing read, nothing written
        internal bool NothingToRead;         // no handler / faces: nothing written
        internal AvatarFacing Facing;
        internal int Want;
        internal int Apply;                  // -1 = no apply
        internal int NewHome;                // the value Home must hold afterwards
        internal bool HomeChanged;
        internal bool Publish;
        internal AvatarSwitched Switched;
        internal AvatarUnusable Unusable;
        internal int Nominee;                // the slot the facing names, -1 for none
    }

    internal class AvatarRules
    {
        // ---------------------------------------------------------------
        // The census
        // ---------------------------------------------------------------

        /// <summary>Term (1). A manager decides by its two flags (isPlaying is
        /// never written false, so this holds until the menu scene destroys the
        /// manager); without one, a local body means a game. Unreadable means
        /// live: the conservative answer is not to move a face.</summary>
        internal virtual bool Live(AvatarLivenessIn l)
        {
            if (l.Unreadable) return true;
            return l.ManagerExists ? (l.IsPlaying || l.BattleOngoing) : l.LocalBodyExists;
        }

        /// <summary>The per-actor test: at least one custom property key that
        /// begins "cr_", not counting the face carrier's key. Item 19's own
        /// publish writes that key on any edge in any room, so counting it would
        /// make an output of f on one seat an input of f on another (design 2.2,
        /// refuter LOW 6); it is skipped by name before the prefix test.</summary>
        internal virtual bool CarriesModSignature(IList<string> keys, string faceKey)
        {
            if (keys == null) return false;
            foreach (var k in keys)
            {
                if (k == null) continue;
                if (k == faceKey) continue;
                if (k.StartsWith("cr_", StringComparison.Ordinal)) return true;
            }
            return false;
        }

        /// <summary>The every-quantifier over the other fighters. An empty
        /// roster is not an answer (the caller maps it to Undecided).</summary>
        internal virtual bool EveryOtherFighterIsModded(IList<IList<string>> others, string faceKey)
        {
            foreach (var o in others) if (!CarriesModSignature(o, faceKey)) return false;
            return true;
        }

        /// <summary>Term (2), capability first (fix pass 1, BR-H1 and BR-M4).
        /// No online room (not in a room, or offline) is Undecided BEFORE
        /// unreadability is consulted: AvatarDefaults.ReadFacing establishes
        /// InRoom and OfflineMode in their own read, and leaves InRoom false
        /// when that read throws, so Unreadable can only mean Vanilla once a
        /// real online room is known. Inside one, unreadable is Vanilla: the
        /// plain face in a modded room costs a friend a nicer face, the modded
        /// face in a vanilla room is the complaint this item exists for.
        /// Modded is answered only by a NONEMPTY census in which every other
        /// fighter carries the mod's signature; zero others is Undecided (the
        /// own face). The room's provenance (ModIssuedRoom: a room-name prefix
        /// or cr_ff) is not read here, so it can trigger a re-evaluation (edge
        /// E12) but never decides the face (learnings #286, #301).</summary>
        internal virtual AvatarFacing FacingOf(AvatarFacingIn f)
        {
            if (!f.InRoom || f.OfflineMode) return AvatarFacing.Undecided;
            if (f.Unreadable) return AvatarFacing.Vanilla;
            if (f.LocalIsSpectator) return AvatarFacing.Undecided;
            if (!f.RoomExists) return AvatarFacing.Undecided;
            var others = f.OtherFighterKeys;
            if (others == null || others.Count == 0) return AvatarFacing.Undecided;
            return EveryOtherFighterIsModded(others, f.FaceKey) ? AvatarFacing.Modded : AvatarFacing.Vanilla;
        }

        /// <summary>A confirmed exit (the room read succeeded and says not in a
        /// room: OnLeftRoom, OnDisconnected, the menu) outranks liveness (fix
        /// pass 1, H9 and M3): GameManager's isPlaying is never written false,
        /// so the old manager can still report a game after the room is gone,
        /// and gating there would carry the remembered selection into the menu
        /// and the next room. With no room the facing is Undecided, f returns
        /// the remembered selection, and the debt is repaid; a second exit
        /// finds want == live and writes nothing. An offline room (Sandbox,
        /// local play) is still a room, so a live offline game stays Locked.
        /// An unreadable room read is not a confirmed exit.</summary>
        internal virtual AvatarFacing Census(AvatarLivenessIn l, AvatarFacingIn f)
        {
            if (!f.InRoom && !f.Unreadable) return FacingOf(f);
            if (Live(l)) return AvatarFacing.Locked;
            return FacingOf(f);
        }

        // ---------------------------------------------------------------
        // Vanilla-clean and usable
        // ---------------------------------------------------------------

        /// <summary>A seat WITHOUT the mod resolves this id: it is inside the
        /// base array and the entry there is not null. The mod never mutates
        /// the arrays (its ids >= 1000 resolve in a prefix), so the arrays a
        /// modded seat holds are the arrays an unmodded seat holds. Negative,
        /// out-of-array and every custom id are all NOT resolvable.</summary>
        internal virtual bool ResolvesOnABaseSeat(int id, bool[] arr)
        {
            return arr != null && id >= 0 && id < arr.Length && arr[id];
        }

        internal virtual bool VanillaClean(AvatarFaceIds fc, AvatarLoaderView l)
        {
            if (l == null) return false;
            return ResolvesOnABaseSeat(fc.Eye, l.Eyes)
                && ResolvesOnABaseSeat(fc.Mouth, l.Mouths)
                && ResolvesOnABaseSeat(fc.Detail, l.Accessories)
                && ResolvesOnABaseSeat(fc.Detail2, l.Accessories);
        }

        /// <summary>Why a nominee cannot be used for this facing, or None when
        /// it can. An unset nominee is reported as None by Unusable's caller
        /// (it is silent), so this is only asked of slot >= 0.</summary>
        internal virtual AvatarUnusable WhyUnusable(int slot, AvatarFacing facing, AvatarFaceIds[] faces, AvatarLoaderView l)
        {
            if (faces == null || slot < 0 || slot >= faces.Length) return AvatarUnusable.Unauthored;
            var fc = faces[slot];
            if (!fc.Present) return AvatarUnusable.Unauthored;
            if (fc.AllZero) return AvatarUnusable.Unauthored;          // never authored (LoadFace has no default)
            if (facing == AvatarFacing.Vanilla && !VanillaClean(fc, l)) return AvatarUnusable.NotClean;
            return AvatarUnusable.None;
        }

        internal virtual bool Usable(int slot, AvatarFacing facing, AvatarFaceIds[] faces, AvatarLoaderView l)
        {
            if (slot < 0) return false;                                  // not set
            return WhyUnusable(slot, facing, faces, l) == AvatarUnusable.None;
        }

        // ---------------------------------------------------------------
        // f, the remembered value, the evaluator
        // ---------------------------------------------------------------

        /// <summary>Home is valid iff 0 &lt;= home &lt; playerFaces.Length (the live
        /// face array, not the dropdowns' slot count). Anything else is empty.</summary>
        internal virtual int HomeOrEmpty(int home, int faceCount)
        {
            return (home >= 0 && home < faceCount) ? home : -1;
        }

        /// <summary>f. Its domain excludes Locked: the evaluator gated on it.
        /// Called with Locked it refuses rather than answers, so a caller that
        /// skipped the gate is caught instead of silently restoring mid-game.</summary>
        internal virtual int F(AvatarFacing c, AvatarSetting s, int own, AvatarFaceIds[] faces, AvatarLoaderView l)
        {
            if (c == AvatarFacing.Locked)
                throw new ArgumentException("f is not defined on a Locked census (the evaluator gates on it)");
            if (!s.Auto) return own;                                     // the feature is off
            if (c == AvatarFacing.Undecided) return own;                 // menu, offline, spectator, empty roster
            int nominee = c == AvatarFacing.Modded ? s.Modded : s.Vanilla;
            if (!Usable(nominee, c, faces, l)) return own;               // unset, out of domain, unauthored, not clean
            return nominee;
        }

        /// <summary>THE GATE (design section 0, DEVIATION 3).</summary>
        internal virtual bool Gate(AvatarFacing c)
        {
            return c == AvatarFacing.Locked;
        }

        /// <summary>The hand-choice rule: with a remembered value held, a live
        /// selection that is neither it nor either nominee re-bases it.</summary>
        internal virtual int Rebase(int home, int live, AvatarSetting s)
        {
            if (home >= 0 && live != home && live != s.Modded && live != s.Vanilla) return live;
            return home;
        }

        /// <summary>One evaluation, the arithmetic of design 2.3's evaluator.</summary>
        internal virtual AvatarDecision Evaluate(AvatarEvalIn x)
        {
            var d = new AvatarDecision { Apply = -1, Nominee = -1, Want = -1, NewHome = x.Home };
            var c = Census(x.Liveness, x.Facing);
            d.Facing = c;
            if (Gate(c)) { d.Gated = true; return d; }
            if (x.Faces == null || x.Live < 0) { d.NothingToRead = true; return d; }

            int live = x.Live;
            var s = x.Setting;
            int home = HomeOrEmpty(x.Home, x.Faces.Length);

            // The hand-choice rule (derived, not stored): a live selection that
            // is neither the remembered value nor either nominee was set by the
            // player, so the remembered value re-bases to it.
            home = Rebase(home, live, s);

            int own = home >= 0 ? home : live;
            int want = F(c, s, own, x.Faces, x.Loader);
            d.Want = want;

            // Case 2: the room calls for a nominee the setting NAMES but cannot
            // use. Derived from the same inputs on whatever edge reaches it.
            int nom = c == AvatarFacing.Modded ? s.Modded : c == AvatarFacing.Vanilla ? s.Vanilla : -1;
            d.Nominee = nom;
            if (s.Auto && nom >= 0) d.Unusable = WhyUnusable(nom, c, x.Faces, x.Loader);

            if (want == live)
            {
                if (want == home) home = -1;
                Finish(ref d, x.Home, home);
                return d;
            }
            if (home < 0) home = live;          // displacing the player's own choice
            d.Apply = want;
            bool restore = want == home;
            if (restore) home = -1;             // the condition ended; the debt is paid
            d.Publish = true;
            if (!restore)
                d.Switched = c == AvatarFacing.Vanilla ? AvatarSwitched.ToVanilla
                           : c == AvatarFacing.Modded ? AvatarSwitched.ToModded : AvatarSwitched.None;
            Finish(ref d, x.Home, home);
            return d;
        }

        private static void Finish(ref AvatarDecision d, int homeBefore, int homeAfter)
        {
            d.NewHome = homeAfter;
            // An out-of-domain value on disk that reads as empty is normalised to
            // -1 the first time an evaluation completes (one write, then stable).
            d.HomeChanged = homeAfter != homeBefore;
        }

        // ---------------------------------------------------------------
        // The announcer and the swap
        // ---------------------------------------------------------------

        /// <summary>Raise unless the toast surface is already showing exactly
        /// this text with time left. Remembers nothing; expires by itself.</summary>
        internal virtual bool ShouldRaise(string msg, string showingText, float timerLeft)
        {
            if (string.IsNullOrEmpty(msg)) return false;
            return !(timerLeft > 0f && showingText == msg);
        }

        /// <summary>A swap is permitted exactly where the gate is open AND f is
        /// not naming a face. The gate is read first, so f is never evaluated
        /// on a Locked census here either. (The reader of the swap key belongs
        /// to item 17's Keybinds registry, which is not on this lane; until it
        /// lands this rule has no caller in the plugin. Design section 2.5,
        /// sentence 3: no fallback binding.)</summary>
        internal virtual bool SwapPermitted(AvatarEvalIn x)
        {
            var c = Census(x.Liveness, x.Facing);
            if (Gate(c)) return false;
            if (x.Faces == null || x.Live < 0) return false;
            int home = HomeOrEmpty(x.Home, x.Faces.Length);
            int own = home >= 0 ? home : x.Live;
            try { return F(c, x.Setting, own, x.Faces, x.Loader) == own; }
            catch (ArgumentException) { return false; }
        }

        /// <summary>The OTHER configured default: the vanilla nominee when the
        /// live selection is the modded nominee, otherwise the modded one; -1
        /// (refused) when that nominee is not usable for the facing it names.</summary>
        internal virtual int SwapTarget(int live, AvatarSetting s, AvatarFaceIds[] faces, AvatarLoaderView l)
        {
            bool toVanilla = live == s.Modded;
            int target = toVanilla ? s.Vanilla : s.Modded;
            var facing = toVanilla ? AvatarFacing.Vanilla : AvatarFacing.Modded;
            return Usable(target, facing, faces, l) ? target : -1;
        }
    }
}
