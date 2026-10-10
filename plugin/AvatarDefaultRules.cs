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
    /// evaluation, so nothing here can carry state between edges.
    ///
    /// The one class in this file that keeps state is PopupCarrierLedger (fix
    /// pass 3, H3; rebuilt on a pick binding by fix pass 4): what this seat
    /// has RECEIVED from remote pickers' face carriers, each bound to the pick
    /// it was published for, and the games this seat has seen start. It never
    /// holds this seat's own face and never decides it; it decides only which
    /// received value the card-pick popup may show for a remote picker.</summary>
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

    /// <summary>What FacePublisher.PublishLocal does with the face carrier on
    /// one attempt (fix pass 1, H3). Publish: the current face is valid and
    /// is written. Clear: the attempt reached a DEFINITIVE answer that there
    /// is no valid face to publish (no face list, a null face, an all-zero
    /// face), so any carrier an earlier attempt left is removed: once the
    /// delete reaches a remote seat, its PopupCarrierLedger drops what it
    /// held for that picker and vanilla's RPC stays in charge; the pass that
    /// made the write applies nothing at all (PopupFace, fix pass 2, H3). Keep:
    /// nothing is known or nothing can be written (a spectator, whose carrier
    /// no reader consults; no handler yet; no local player).</summary>
    internal enum FaceCarrierAction { Publish, Clear, Keep }

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
        /// <summary>Fix pass 2 (H9, M3): a confirmed exit found a remembered
        /// selection but no character data to restore it with (no controller,
        /// no selected face, no face table). Home is KEPT as written (it is
        /// the durable record of the debt, a config int that outlives every
        /// scene and the process), and the E13 tick repays it as soon as the
        /// data reads again; a relaunch repays it at E1.</summary>
        internal bool RestorationDeferred;
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

        /// <summary>Both preset slots are set (fix pass 1, BR-M3): the switch
        /// ships on but is inert until the player has named BOTH defaults
        /// (design section 8). With one slot set, f returns the own face for
        /// either facing, so a remembered selection is still given back.</summary>
        internal virtual bool BothPresetsSet(AvatarSetting s)
        {
            return s.Modded >= 0 && s.Vanilla >= 0;
        }

        /// <summary>f. Its domain excludes Locked: the evaluator gated on it.
        /// Called with Locked it refuses rather than answers, so a caller that
        /// skipped the gate is caught instead of silently restoring mid-game.</summary>
        internal virtual int F(AvatarFacing c, AvatarSetting s, int own, AvatarFaceIds[] faces, AvatarLoaderView l)
        {
            if (c == AvatarFacing.Locked)
                throw new ArgumentException("f is not defined on a Locked census (the evaluator gates on it)");
            if (!s.Auto) return own;                                     // the feature is off
            if (!BothPresetsSet(s)) return own;                          // inert until both defaults are named
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
            // The nominee the facing names, read before the missing-data exit
            // (fix pass 3, M8): the line that exit writes names it as well.
            int nom = c == AvatarFacing.Modded ? x.Setting.Modded : c == AvatarFacing.Vanilla ? x.Setting.Vanilla : -1;
            d.Nominee = nom;
            if (x.Faces == null || x.Live < 0)
            {
                // Nothing to apply with. Home is left exactly as it is (NewHome
                // is x.Home, HomeChanged false): never cleared on a missing
                // read, so the debt survives until a readable evaluation pays
                // it (fix pass 2, H9 and M3).
                d.NothingToRead = true;
                d.RestorationDeferred = RestorationOwed(x.Home, !x.Facing.InRoom && !x.Facing.Unreadable);
                return d;
            }

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
            if (s.Auto && BothPresetsSet(s) && nom >= 0) d.Unusable = WhyUnusable(nom, c, x.Faces, x.Loader);

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

        /// <summary>Fix pass 2 (H9, M3): a restoration is owed while a
        /// remembered selection is held and the room read CONFIRMS there is
        /// no room (it succeeded and says not in a room). Both inputs survive
        /// every teardown: Home is a config int, the room read is Photon's own
        /// state. No character data is consulted, so the debt cannot be lost
        /// to a controller, a selected face or a face table that has gone; the
        /// E13 tick (AvatarDefaults.Tick) asks this on every throttled frame
        /// and re-runs the evaluator, which repays it the first time the data
        /// reads. An unreadable room read is not a confirmed exit.</summary>
        internal virtual bool RestorationOwed(int home, bool confirmedNoRoom)
        {
            return home >= 0 && confirmedNoRoom;
        }

        /// <summary>Fix pass 3 (H9, M3): the value Home holds while the apply
        /// runs. A debt the decision RECORDS or re-bases (NewHome >= 0) is
        /// written first, before the selection moves, so an apply that throws
        /// after displacing the player's own choice still leaves the record of
        /// it. A debt the decision PAYS (NewHome -1) is not touched here: only
        /// HomeAfterApply clears it, on a read-back of the restored selection.</summary>
        internal virtual int HomeBeforeApply(int homeBefore, AvatarDecision d)
        {
            return d.HomeChanged && d.NewHome >= 0 ? d.NewHome : homeBefore;
        }

        /// <summary>Fix pass 3 (H9, M3): the value Home holds after the apply,
        /// given the selection READ BACK from the character controller once
        /// the apply returned (liveAfter; for a decision that applies nothing,
        /// the selection the evaluation itself read). A debt is paid only when
        /// that read shows the slot the decision restores. Any other read (the
        /// select threw before it committed, the controller is gone, the
        /// selection did not move) keeps the debt exactly as it was, so the
        /// next E6, E7 or E13 retries it; an apply that throws out of the
        /// evaluator never reaches this method, which keeps it the same way.</summary>
        internal virtual int HomeAfterApply(int homeHeld, AvatarDecision d, int liveAfter)
        {
            if (!d.HomeChanged || d.NewHome >= 0) return homeHeld;   // nothing to pay (a record was written before)
            int restored = d.Apply >= 0 ? d.Apply : d.Want;
            if (liveAfter != restored) return homeHeld;              // not committed: the debt stays
            return d.NewHome;                                        // the read-back shows it: paid
        }

        /// <summary>The face the card-pick popup applies for one Show pass.
        ///
        /// Local picker (fix pass 2, H3): the pass has just published (or
        /// cleared, or kept) its own carrier, and PUN updates the local
        /// player's cached properties only on the server's echo, so a reread
        /// of the cache in the same pass returns the PREVIOUS value. The local
        /// picker uses the value it published, or nothing when the attempt
        /// cleared or kept the carrier (vanilla's RPC stays in charge), and
        /// never calls the reader.
        ///
        /// Remote picker (fix pass 3, H3; fix pass 4): the same defect from
        /// the other side. This seat's copy of a remote carrier is the last
        /// update it received, which can belong to an earlier pick, so the
        /// reader handed in answers only with a value BOUND to the pick this
        /// popup shows (PopupCarrierLedger.Show, through PopupCarriers.ForShow
        /// in Plugin.cs; the binding check is BoundToPopup), and with null
        /// while that value has not arrived. It is never a read of the cache.</summary>
        internal virtual string PopupFace(bool pickerIsLocal, FaceCarrierAction published, string publishedValue, Func<string> remoteForThisPick)
        {
            if (pickerIsLocal) return published == FaceCarrierAction.Publish ? publishedValue : null;
            return remoteForThisPick != null ? remoteForThisPick() : null;
        }

        /// <summary>Fix pass 4 (H3): the identity of the pick a card-pick popup
        /// shows, as every seat derives it from the same two events: the games
        /// this seat has seen start in the room (GM_ArmsRace.DoStartGame,
        /// counted by PopupCarrierLedger.GameStarted) and the rounds completed
        /// in the current game (GM_ArmsRace.p1Rounds + p2Rounds: zero for the
        /// game-start picks, and set on every seat by the master's
        /// RPCA_NextRound before any pick of that round's phase). Each player
        /// picks at most once per phase, so (game, rounds) names one pick of
        /// any one actor, and every Show of that actor inside the phase is the
        /// popup of that pick. Null when this seat has seen no game start in
        /// this room (a spectator, which the DoStartGame prefix never counts,
        /// or a seat that joined a game already running) or the rounds are
        /// unreadable: no carrier can be bound to its popups.</summary>
        internal virtual string PopupPick(int game, int rounds)
        {
            if (game <= 0 || rounds < 0) return null;
            return PopupCarrierLedger.PickPrefix + game.ToString(System.Globalization.CultureInfo.InvariantCulture)
                + "." + rounds.ToString(System.Globalization.CultureInfo.InvariantCulture);
        }

        /// <summary>Fix pass 4 (H3): the pick a carrier value is bound to, as
        /// it ARRIVES on a remote seat (PopupCarrierLedger.Arrived). True, with
        /// the pick, only for a value its picker published at its own card-pick
        /// Show with that popup's identity (PopupCarrierLedger.BoundFace, a 13th
        /// field; or PopupCarrierLedger.BoundClear, the clear tombstone, for
        /// which clear is true). False for an unbound value: a 1.40.3 client's
        /// 12 fields, a publish outside a pick, a removed key.</summary>
        internal virtual bool PickBinding(string value, out string pick, out bool clear)
        {
            return PopupCarrierLedger.TryReadBinding(value, out pick, out clear);
        }

        /// <summary>Fix pass 4 (H3): THE binding check. A carrier value, face or
        /// clear, is applied to a popup only when the pick it is bound to is
        /// exactly the pick that popup shows; a popup with no identity on this
        /// seat (popupPick null) applies nothing. Every value the ledger hands
        /// to an apply, or takes as a clear, passes here (Show, Arrived, Tick).</summary>
        internal virtual bool BoundToPopup(string pick, string popupPick)
        {
            return popupPick != null && pick == popupPick;
        }

        /// <summary>Fix pass 3 (H3): whether a popup face the ledger owes is
        /// still owed (the deferral is bounded; past the bound vanilla's face
        /// stands and the ledger says so).</summary>
        internal virtual bool OwedWithin(double deferredSince, double now)
        {
            return now - deferredSince <= PopupCarrierLedger.DeferralBoundSeconds;
        }

        // ---------------------------------------------------------------
        // The face carrier and the classification line
        // ---------------------------------------------------------------

        /// <summary>The one decision behind every FacePublisher.PublishLocal
        /// attempt (fix pass 1, H3; all four callers reach it through that one
        /// method). A definitive "no valid face" clears the carrier instead of
        /// returning with the previous value still published.</summary>
        internal virtual FaceCarrierAction CarrierAction(bool spectator, bool handlerReady, bool localPlayerReady,
                                                         bool facesListed, AvatarFaceIds face0)
        {
            if (spectator || !handlerReady || !localPlayerReady) return FaceCarrierAction.Keep;
            if (!facesListed || !face0.Present || face0.AllZero) return FaceCarrierAction.Clear;
            return FaceCarrierAction.Publish;
        }

        /// <summary>The edges whose classification is logged even when nothing
        /// is applied (fix pass 1, M8): the room edges a classification claim
        /// is made about (join, entrant, departure, leave, disconnect). The
        /// per-frame spawn prefix, the property and room-property edges, the
        /// selection and settings edges log only an applied change.</summary>
        internal virtual bool LogsClassification(string tag)
        {
            if (tag == null) return false;
            return tag.StartsWith("E2-", StringComparison.Ordinal) || tag.StartsWith("E3-", StringComparison.Ordinal)
                || tag.StartsWith("E6-", StringComparison.Ordinal) || tag.StartsWith("E7-", StringComparison.Ordinal)
                || tag.StartsWith("E11-", StringComparison.Ordinal);
        }

        /// <summary>The one [AVATAR] classification line (fix pass 1, M8):
        /// names the edge, what was applied or kept, the facing read, the
        /// nominee the facing names, the other-fighter count, the room's
        /// provenance (shown, not deciding), the selection before and the
        /// remembered value before and after. AvatarDefaults.Evaluate logs
        /// this string followed by MissingDataNote, BEFORE any fallible work
        /// (fix pass 3, M8), so "applied" records the decision; an apply that
        /// does not commit adds NotCommittedLine. The harness replays both.</summary>
        internal virtual string ClassificationLine(string tag, AvatarDecision d, int otherFighters, bool issuedRoom, int was, int homeBefore)
        {
            string head = d.Apply >= 0 ? " applied slot " + d.Apply : " kept slot " + was;
            return "[AVATAR] " + tag + head + " (facing " + d.Facing + ", nominee " + d.Nominee
                + ", other fighters " + otherFighters + ", issued room " + (issuedRoom ? "yes" : "no")
                + ", want " + d.Want + ", was " + was + ", home " + homeBefore + "->" + d.NewHome + ")";
        }

        /// <summary>Fix pass 3 (M8): the tail of the classification line on a
        /// missing-data exit, naming what could not be read; on a confirmed
        /// exit with a debt held it names the deferral E13 repays. Empty on
        /// every other exit.</summary>
        internal virtual string MissingDataNote(AvatarDecision d, string missing, int home)
        {
            if (!d.NothingToRead) return "";
            string what = string.IsNullOrEmpty(missing) ? "character data unreadable" : missing;
            return d.RestorationDeferred
                ? ": restoration deferred (" + what + "), home " + home + " kept, the E13 tick repays it once the character data reads"
                : ": nothing applied (" + what + ")";
        }

        /// <summary>Fix pass 3 (H9, M3): the line for an apply whose read-back
        /// does not show the slot it was to select (why: what went wrong, or
        /// null). The debt it names is the one still held.</summary>
        internal virtual string NotCommittedLine(string tag, int slot, int readBack, int homeHeld, string why)
        {
            return "[AVATAR] " + tag + " slot " + slot + " not committed (the selection reads " + readBack
                + (why != null ? "; " + why : "") + "): home " + homeHeld
                + " kept, a later E6, E7 or E13 retries it";
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

    /// <summary>Item 19 fix pass 3 (H3, the remote arm), rebuilt by fix pass 4
    /// on a PICK BINDING: which received carrier value the card-pick popup
    /// may apply for a REMOTE picker.
    ///
    /// The carrier (cr_face) is a Photon player property, and this seat's
    /// copy of a remote picker's carrier is whatever update it received
    /// last, which can be an earlier pick's face; so the popup never reads
    /// the copy. Fix pass 3 tagged the picker's card-pick publish with a
    /// sequence and took the newest tagged arrival by age, which a late
    /// carrier of the picker's previous show also satisfied (build round 4,
    /// H3). Fix pass 4 binds the value to the pick instead. The picker
    /// publishes at its own card-pick Show with the identity of the popup it
    /// shows (AvatarRules.PopupPick: the game this seat saw start in the room
    /// and the rounds completed in it, which every seat derives from the same
    /// DoStartGame and RPCA_NextRound), as a 13th field after the face
    /// (BoundFace) or, when it has no valid face, as the clear tombstone
    /// (BoundClear). This seat derives the identity of the popup it shows
    /// from the same events, and applies a face, or takes a clear, only when
    /// the two are equal (AvatarRules.BoundToPopup). Nothing else decides:
    /// not the order of arrival, not the age of a value.
    ///
    /// Per remote actor the ledger keeps the one value most recently received
    /// bound to a pick no older than this seat's own: the picker's seat can be
    /// ahead, so its publish for a pick can arrive before this seat's popup of
    /// that pick opens, and is applied when it does. A value bound to an older
    /// pick than this seat has reached, or than the one held, is STALE: it is
    /// logged, never applied, and nothing held or owed changes. An unbound
    /// value (a 1.40.3 client's 12 fields, a publish outside a pick, a removed
    /// key) is logged as stale and changes nothing either. A seat that has
    /// seen no game start in this room (a spectator, which the DoStartGame
    /// prefix never counts; a seat that joined a running game) has no
    /// identity to bind to: it holds nothing, applies no carrier, and
    /// vanilla's face stands. Two seats whose game counts differ (one joined
    /// or rejoined the room after a game had started in it) never derive the
    /// same identity, so neither applies the other's carrier: each deferral
    /// ends at the bound with its line, and vanilla's face stands.
    ///
    /// When the popup opens and nothing bound to its pick has arrived, the
    /// apply is OWED and the arrival completes it, with the restoration-debt
    /// rules of E13: cleared only when the apply is observed to complete
    /// (ApplySerialized returned true) or a clear bound to the pick arrives,
    /// kept when the apply throws or finds no visualizer to equip, retried on
    /// the throttled tick, recorded once however often the popup is re-shown
    /// while it is owed, and dropped only when the popup ends or shows another
    /// pick, the room changes, or DeferralBoundSeconds pass, each with a line.
    ///
    /// Pure (no Unity, no Photon): the caller passes the room object, the
    /// rounds and the clock, and logs Note after each call. Main thread only.</summary>
    internal sealed class PopupCarrierLedger
    {
        /// <summary>How long the popup waits for a remote picker's carrier
        /// for the pick before it stops waiting (vanilla's face stands).</summary>
        internal const double DeferralBoundSeconds = 10.0;

        /// <summary>The binding field's prefix ("pick" + game + "." + rounds)
        /// and the clear tombstone's first field (fix pass 4, H3).</summary>
        internal const string PickPrefix = "pick";
        internal const string ClearMark = "clear";

        /// <summary>One remote actor's record, for the room it was made in.</summary>
        private sealed class Entry
        {
            internal string Pick;                // the pick the held value is bound to ("pick<game>.<rounds>")
            internal string Value;               // the held value: a face bound to Pick, or the clear tombstone
            internal bool Clear;                 // Value is the clear tombstone
            internal double DeferredSince = -1;  // >= 0: the popup shows this actor and still owes it its pick's value
        }

        private readonly AvatarRules rules;      // the decisions: the identity, the binding, the binding check, the owed bound
        private readonly Dictionary<int, Entry> entries = new Dictionary<int, Entry>();
        private object room;                     // the room incarnation the entries belong to (Photon's Room object)
        private int game;                        // the games this seat has seen start in that room (DoStartGame)
        private int shown = -1;                  // the remote actor the popup shows; -1 for none or the local picker
        private string shownPick;                // the pick that popup shows; null when this seat has no identity for it
        private string note;                     // what the last call decided, for the log

        /// <summary>The ledger asks its rules (AvatarRules.PopupPick,
        /// PickBinding, BoundToPopup, OwedWithin) and keeps the rest itself.</summary>
        internal PopupCarrierLedger(AvatarRules rules)
        {
            this.rules = rules ?? new AvatarRules();
        }

        /// <summary>The remote actor the popup shows, or -1.</summary>
        internal int Shown => shown;

        /// <summary>What the last call decided; null when nothing is worth a line.</summary>
        internal string Note => note;

        /// <summary>The value a picker publishes at its own card-pick Show
        /// (fix pass 4, H3): the 12 face fields and a 13th, the pick of the
        /// popup it shows. A 1.40.3 reader takes fields 0 to 11.</summary>
        internal static string BoundFace(string face, string pick)
        {
            return face + "|" + pick;
        }

        /// <summary>The clear tombstone a picker publishes at its own card-pick
        /// Show when it has no valid face (fix pass 4, H3): "clear|" + the
        /// popup's pick. Two fields, so a reader that needs 12 (a 1.40.3 seat)
        /// refuses it and applies nothing, as for a removed carrier.</summary>
        internal static string BoundClear(string pick)
        {
            return ClearMark + "|" + pick;
        }

        /// <summary>The pick a carrier value is bound to, and whether it is the
        /// clear tombstone; false for an unbound value (12 fields: a 1.40.3
        /// client, or a publish outside a pick; a removed key; anything else).</summary>
        internal static bool TryReadBinding(string value, out string pick, out bool clear)
        {
            pick = null;
            clear = false;
            if (string.IsNullOrEmpty(value)) return false;
            var parts = value.Split('|');
            string last;
            bool tomb;
            if (parts.Length == 13) { last = parts[12]; tomb = false; }
            else if (parts.Length == 2 && parts[0] == ClearMark) { last = parts[1]; tomb = true; }
            else return false;
            int g, r;
            if (!TryParsePick(last, out g, out r)) return false;
            pick = last;
            clear = tomb;
            return true;
        }

        /// <summary>"pick" + game + "." + rounds, each a plain decimal.</summary>
        private static bool TryParsePick(string s, out int game, out int rounds)
        {
            game = -1;
            rounds = -1;
            if (s == null || !s.StartsWith(PickPrefix, StringComparison.Ordinal)) return false;
            string rest = s.Substring(PickPrefix.Length);
            int dot = rest.IndexOf('.');
            if (dot <= 0 || dot == rest.Length - 1) return false;
            var ns = System.Globalization.NumberStyles.None;
            var ic = System.Globalization.CultureInfo.InvariantCulture;
            return int.TryParse(rest.Substring(0, dot), ns, ic, out game) && int.TryParse(rest.Substring(dot + 1), ns, ic, out rounds);
        }

        /// <summary>Orders two well-formed picks: the game first, then the
        /// rounds. It decides only whether a value is held or stale, never
        /// whether one is applied (that is AvatarRules.BoundToPopup alone).</summary>
        private static int ComparePicks(string a, string b)
        {
            int ga, ra, gb, rb;
            TryParsePick(a, out ga, out ra);
            TryParsePick(b, out gb, out rb);
            return ga != gb ? ga.CompareTo(gb) : ra.CompareTo(rb);
        }

        private void Say(string s)
        {
            note = note == null ? s : note + "; " + s;
        }

        private Entry Get(int actor)
        {
            Entry e;
            if (!entries.TryGetValue(actor, out e)) { e = new Entry(); entries[actor] = e; }
            return e;
        }

        /// <summary>Every entry point binds the room first: a different room
        /// object (another room, a rejoin, or none) drops everything, the game
        /// count included, since nothing received or counted in one room
        /// belongs to another.</summary>
        private void BindRoom(object currentRoom)
        {
            if (ReferenceEquals(currentRoom, room)) return;
            Entry e;
            if (shown >= 0 && entries.TryGetValue(shown, out e) && e.DeferredSince >= 0)
                Say("actor " + shown + "'s popup face is no longer owed: the room changed before its carrier arrived");
            entries.Clear();
            shown = -1;
            shownPick = null;
            game = 0;
            room = currentRoom;
        }

        /// <summary>Ends the popup's session with the actor it shows: an owed
        /// apply is dropped. What is held stays: it is bound to its pick, so it
        /// can only ever be taken by a popup of that same pick (a re-Show).</summary>
        private void EndShown()
        {
            if (shown < 0) return;
            var e = Get(shown);
            if (e.DeferredSince >= 0)
                Say("actor " + shown + "'s popup of " + shownPick + " ended before a carrier bound to it arrived: vanilla's face stood");
            e.DeferredSince = -1;
            shown = -1;
            shownPick = null;
        }

        /// <summary>GM_ArmsRace.DoStartGame on this seat (a prefix, so it runs
        /// on every seat that starts the game whatever a sibling prefix
        /// decides, #352): the picks of the game starting now are bound to the
        /// new count.</summary>
        internal void GameStarted(object currentRoom)
        {
            note = null;
            BindRoom(currentRoom);
            EndShown();
            game++;
            Say("game " + game + " started in this room on this seat: its card-pick popups are bound to "
                + PickPrefix + game + ".<rounds completed>");
        }

        /// <summary>The identity of the pick a popup opening now shows, from the
        /// rounds completed in the current game (AvatarRules.PopupPick); null
        /// when this seat has no identity to give.</summary>
        internal string PopupPick(object currentRoom, int rounds)
        {
            note = null;
            BindRoom(currentRoom);
            return rules.PopupPick(game, rounds);
        }

        /// <summary>The popup now shows a REMOTE picker (the Show postfix,
        /// through AvatarRules.PopupFace), for the pick popupPick (PopupPick at
        /// that Show). Returns the value to apply now: the held value, when it
        /// is a face bound to exactly that pick. Otherwise null: a clear bound
        /// to the pick (nothing to apply, vanilla's face stands), no identity
        /// on this seat, or nothing bound to the pick has arrived, so the apply
        /// is owed and Arrived completes it. A re-Show of the same pick hands
        /// the same value back (the skin is new) and never opens a second debt.</summary>
        internal string Show(object currentRoom, int actor, string popupPick, double now)
        {
            note = null;
            BindRoom(currentRoom);
            var e = Get(actor);
            bool opened = shown != actor || shownPick != popupPick;
            if (opened)
            {
                EndShown();
                shown = actor;
                shownPick = popupPick;
            }
            if (popupPick == null)
            {
                if (opened)
                    Say("actor " + actor + "'s popup has no pick identity on this seat (no game start seen in this room):"
                        + " no carrier can be bound to it, vanilla's face stands");
                return null;
            }
            if (e.Value != null && rules.BoundToPopup(e.Pick, popupPick))
            {
                if (!e.Clear) return e.Value;             // the caller reports the outcome through Applied
                if (opened) Say("actor " + actor + " cleared its carrier for " + popupPick + ": nothing is applied, vanilla's face stands");
                return null;
            }
            if (e.DeferredSince < 0)
            {
                e.DeferredSince = now;
                Say("actor " + actor + "'s popup face for " + popupPick + " deferred: no carrier bound to that pick has arrived"
                    + (e.Value != null ? " (the value held is bound to " + e.Pick + ")" : "") + ", so none is applied until it does");
            }
            return null;
        }

        /// <summary>The caller applied a value this ledger handed it: committed
        /// when the apply was observed to complete. Only that clears what is
        /// owed; a failure keeps it owed for the tick to retry.</summary>
        internal void Applied(int actor, bool committed, double now)
        {
            note = null;
            var e = Get(actor);
            if (committed)
            {
                if (e.DeferredSince >= 0) Say("actor " + actor + "'s owed popup face applied (bound to " + e.Pick + ")");
                e.DeferredSince = -1;
                return;
            }
            if (actor != shown || e.DeferredSince >= 0) return;
            e.DeferredSince = now;
            Say("actor " + actor + "'s popup face did not apply (no visualizer to equip, or the equip failed): still owed, the tick retries it");
        }

        /// <summary>A carrier update ARRIVED for a remote actor: the property
        /// callback's changed value (a removed key arrives as null). currentPick
        /// is the identity a popup opening on this seat now would show
        /// (PopupPick). Returns the value to apply now: a face bound to exactly
        /// the pick of the popup showing this actor. Otherwise null: a clear
        /// bound to that pick (it settles what is owed), a value held for a
        /// later popup of this actor, or a value never applied (unbound, or
        /// bound to an older pick: stale, and nothing held or owed changes).</summary>
        internal string Arrived(object currentRoom, int actor, string value, string currentPick, double now)
        {
            note = null;
            BindRoom(currentRoom);
            string pick;
            bool clear;
            if (!rules.PickBinding(value, out pick, out clear))
            {
                Say((value == null ? "actor " + actor + " removed its carrier" : "an unbound carrier arrived from actor " + actor)
                    + " (a 1.40.3 client's publish, or one made outside a pick): bound to no pick, stale, never applied to a"
                    + " popup; nothing held or owed changes");
                return null;
            }
            var e = Get(actor);
            if (actor == shown && rules.BoundToPopup(pick, shownPick))
            {
                e.Pick = pick;
                e.Value = value;
                e.Clear = clear;
                if (!clear) return value;                 // the caller applies it and reports through Applied
                Say("actor " + actor + " cleared its carrier for " + pick + (e.DeferredSince >= 0 ? ": no longer owed" : "")
                    + ", vanilla's face stands");
                e.DeferredSince = -1;
                return null;
            }
            if (currentPick == null)
            {
                Say("a carrier bound to " + pick + " arrived from actor " + actor + ", and this seat has seen no game start in"
                    + " this room: none of its popups is bound to a pick, so it is never applied and not held");
                return null;
            }
            string reached = e.Value != null && ComparePicks(e.Pick, currentPick) > 0 ? e.Pick : currentPick;
            if (ComparePicks(pick, reached) < 0)
            {
                Say("a carrier bound to " + pick + " arrived from actor " + actor + " after this seat reached " + reached
                    + ": stale, never applied; nothing held or owed changes");
                return null;
            }
            e.Pick = pick;                                // held for this actor's popup of that pick
            e.Value = value;
            e.Clear = clear;
            return null;
        }

        /// <summary>The popup was hidden, or moved to the local picker.</summary>
        internal void EndSession(object currentRoom)
        {
            note = null;
            BindRoom(currentRoom);
            EndShown();
        }

        /// <summary>The throttled tick: drops an owed apply past the bound;
        /// otherwise returns the held face bound to the shown popup's pick
        /// whose apply has not completed (the retry), or null.</summary>
        internal string Tick(object currentRoom, double now)
        {
            note = null;
            BindRoom(currentRoom);
            if (shown < 0) return null;
            var e = Get(shown);
            if (e.DeferredSince < 0) return null;
            if (!rules.OwedWithin(e.DeferredSince, now))
            {
                e.DeferredSince = -1;
                Say("actor " + shown + "'s popup face for " + shownPick + " is no longer owed: nothing bound to that pick completed within "
                    + DeferralBoundSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture) + " s, vanilla's face stands");
                return null;
            }
            return e.Value != null && !e.Clear && rules.BoundToPopup(e.Pick, shownPick) ? e.Value : null;
        }
    }
}
