using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;
using PhotonPlayer = Photon.Realtime.Player;

namespace CompetitiveRounds
{
    /// <summary>Bug 389 - the Unity/Photon half of the proximity-victim repair.
    ///
    /// GATE 0. The mechanism rests on A_Lifestealer's prefab wiring
    /// PlayerInRangeTrigger.triggerEvent to DealDamageToPlayer.Go. That wiring is
    /// settled from the shipped assets - BUG389-GATE0-OFFLINE.md, CONFIRMED by two
    /// independent passes: trigger path id 10029 on A_Lifestealer carries persistent
    /// call [6] to DealDamageToPlayer path id 10015, method Go, Void, RuntimeOnly.
    /// What an asset read cannot show is REACHABILITY on the seat that reports the
    /// bug (#405/#286/#83); that is what Gate0TriggerWiringProbe.cs measures in a
    /// running game, and its acceptance is a SCR_GATE0_389=1 line naming
    /// A_Lifestealer, DealDamageToPlayer and Go. The in-game witness run is still
    /// wanted; it confirms reachability rather than re-proving the wiring.
    ///
    /// WHERE THE REPAIR CAN ACTUALLY ENGAGE on this game build. Only a ring-driven
    /// call is repaired, and the content census bounds that to one card:
    /// A_Lifestealer's DealDamageToPlayer. A_DemonicPact's DealDamageToPlayer is
    /// AttackTrigger-driven, E_StunOverTime's StunPlayer is DelayEvent-driven, and
    /// TeleportToOpponent has no instances at all - each of those falls through to
    /// vanilla, untouched. The two sibling patches are kept for the reasons recorded
    /// on their own classes below.
    ///
    /// THE REPAIR. A Prefix on each cached-victim effect re-resolves the victim on
    /// every call from the owning trigger's INPUTS, writes it into vanilla's own
    /// field, and lets vanilla run unchanged. Nothing re-implements the damage
    /// call: vanilla's DealDamageToPlayer.cs:41-45 still runs, including
    /// data.player as the damaging player, which is what makes the holder's own
    /// LifeSteal heal fire (#354 - a path that applies damage outside the engine's
    /// funnel silently drops every side-effect of that damage).
    ///
    /// FAILURE DIRECTION (#276/#430). Today the unhandled case fails in the worst
    /// direction: real health leaves the wrong player and can kill them. The repair
    /// fails in two conservative directions instead.
    ///   * Resolution fails on a TRIGGER-DRIVEN call - the trigger's own rule
    ///     admits nobody, or the attempt throws: return false, so the original
    ///     never runs and NOTHING is applied. Returning true here would run vanilla
    ///     against the stale field, which is the defect. Refusing also removes a
    ///     latent crash on that path: vanilla dereferences the field with no null
    ///     guard (DealDamageToPlayer.cs:45, StunPlayer.cs:27,
    ///     TeleportToOpponent.cs:24).
    ///   * No owning trigger: fall through to vanilla unchanged. There is no
    ///     predicate to reproduce, so there is no repair to make and no licence to
    ///     invent a selection rule of our own.
    ///   * Capability unknown or partial: fall through to vanilla unchanged.
    /// A refused drain tick costs the holder a small heal. A wrongly applied one
    /// costs another player the game - that is the asymmetry the guard is judged
    /// by.
    ///
    /// NOT INCLUDED. BeamAttack freezes the DAMAGER rather than the victim
    /// (BeamAttack.cs:30,52), so repairing it changes who is credited with a kill
    /// and who is healed. That is balance-visible in a way this is not, and it is
    /// Sid's call - it is question 5 of the diagnosis and is deliberately absent
    /// here.
    /// </summary>
    internal static class ProximityVictimGate
    {
        /// <summary>Set by the Harmony cleanup of each patch below, and only when
        /// that patch actually attached. A patch can silently fail to attach and
        /// produce nothing for release cycles (#83); advertising a repair we cannot
        /// perform would make every peer believe the room is consistent while this
        /// seat still runs vanilla - the one state this gate exists to prevent.
        /// All three must be live before the key is staged.</summary>
        private static int _attached;

        internal const int RequiredAttachments = 3;

        internal static bool PatchesLive { get { return _attached >= RequiredAttachments; } }

        internal static void MarkAttached(string which)
        {
            _attached++;
            try { Plugin.Log.LogInfo("[PROX-CAP] patch live: " + which + " (" + _attached + "/" + RequiredAttachments + ")"); }
            catch { }
        }

        /// <summary>Once we have declined to advertise, we never advertise later in
        /// the session. Harmony patching is finished before anything can connect, so
        /// a false PatchesLive at the first staging attempt is the final answer, and
        /// a key that appeared on a later join would describe a seat that still runs
        /// vanilla.</summary>
        private static bool _stageFailedPermanently;

        /// <summary>THE ONLY way this key reaches a peer. Staging is gated on
        /// attachment, exactly as PoisonSync.StageCapability gates cr_pois2
        /// (PoisonSync.cs:236-242) and as Plugin.cs:1114-1116 states the rule:
        /// advertising an authority we cannot deliver is worse than not advertising
        /// at all.
        ///
        /// Why the gate has to be HERE and not only in RoomCarriesFix(). PatchesLive
        /// read at the census only suppresses THIS seat's own repair. The key is
        /// what every OTHER seat reads. A seat whose patches failed would keep
        /// advertising, its peers' census would find the key on every fighter and
        /// return true, and they would re-resolve the victim each tick while this
        /// seat kept draining the stale cached one: the same drain tick debiting a
        /// different player's health on different seats, in a shared simulation.
        /// That is precisely the state a whole-room gate exists to prevent, and it
        /// decides the placement and the rating.</summary>
        internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)
        {
            if (prejoin == null) return;
            try
            {
                if (PatchesLive)
                {
                    prejoin[ProximityVictim.CapabilityProp] = ProximityVictim.CapabilityValue;
                    return;
                }

                if (!_stageFailedPermanently)
                {
                    _stageFailedPermanently = true;
                    Plugin.Log.LogError("[PROX-CAP] proximity-victim patches did NOT attach ("
                        + _attached + "/" + RequiredAttachments + ") - not advertising "
                        + ProximityVictim.CapabilityProp + "; this seat stays on vanilla for the session");
                }
            }
            catch { }
        }

        // THE FRAME ALONE IS NOT A KEY FOR THIS ANSWER. An actor can join, an
        // actor can leave, and a property delivery can land, all inside one frame
        // - one PUN Dispatch drains several with no frame boundary between them -
        // so a census taken early in a frame and reused for the rest of it can
        // describe a room that has since changed. The direction that matters is a
        // stale TRUE: this gate decides whether a seat re-resolves the victim, so
        // two seats disagreeing on it is the same damage tick debiting different
        // players on different screens. A stale FALSE costs a tick of vanilla,
        // which is today's shipped behaviour.
        //
        // So the key is the frame AND RoomActors.RosterGeneration, the monotonic
        // counter the room callbacks already bump: Plugin.cs:3714
        // (OnPlayerEnteredRoom) and :3830 (OnPlayerLeftRoom) through
        // InvalidateFighterCache, and Plugin.cs:3974 (OnPlayerPropertiesUpdate)
        // through NoteRosterIdentityChange for the properties this answer reads -
        // u_id and the spectator keys, which decide the denominator, and
        // cr_prox1, which is the answer itself. A counter rather than a flag on
        // purpose: a change that lands and reverts between two reads leaves
        // nothing behind in the room state, and the counter is the trace that
        // survives it (the same reasoning RoomActors states on its own key).
        private static readonly ProximityCapabilityCache _cap = new ProximityCapabilityCache();

        /// <summary>Cached delegate so the per-tick census path allocates
        /// nothing.</summary>
        private static readonly Func<bool> CensusDelegate = Census;

        /// <summary>The census itself: every actor that can simulate the effect
        /// must advertise the key. Split out so the cache above holds the ONLY
        /// copy of the staleness rule.</summary>
        private static bool Census()
        {
            PhotonPlayer[] actors = PhotonNetwork.PlayerList;
            if (actors == null || actors.Length == 0) return false;
            foreach (var p in actors)
            {
                // An unreadable actor is not a reason to stop looking at it: it
                // may still be simulating. Treat it as a seat that does not
                // advertise.
                if (p == null) return false;
                if (RoomActors.IsSpectator(p)) continue;

                var props = p.CustomProperties;
                object v;
                if (props == null
                    || !props.TryGetValue(ProximityVictim.CapabilityProp, out v)
                    || !(v is int)
                    || ((int)v) != ProximityVictim.CapabilityValue)
                    return false;
            }
            return true;
        }

        /// <summary>True when EVERY fighter in the room advertises a build carrying
        /// this repair.
        ///
        /// Whole-room, not master-only and not self-only: the effect object runs on
        /// every client with no ownership gate, so a seat that repairs while another
        /// does not produces two different healths for the same player. A mixed room
        /// keeps vanilla on every seat, which is exactly today's shipped behaviour -
        /// no new symptom - and the room stays self-consistent.
        ///
        /// THE DENOMINATOR IS EVERY ACTOR THAT CAN SIMULATE THE EFFECT, which is
        /// NOT RoomActors.ActiveFighters(). That helper is the rating-bearing
        /// roster, and it is deliberately fail-CLOSED: once FreezeFighterRoster has
        /// run - and it does run, from GameStateWatcher.cs:1564, :4965 and :6351 -
        /// it drops any actor that is off the frozen steam-id roster, whose u_id
        /// cannot be read, or that was ever cached as rejected. Dropping an actor
        /// from a ROSTER is the safe direction. Dropping it from a CAPABILITY
        /// CENSUS is the unsafe one, and reusing a fail-soft helper under the
        /// opposite polarity is its own defect class (#412): the census would
        /// answer "every fighter advertises" without having looked at that actor,
        /// while the actor still owns a Player in PlayerManager.instance.players,
        /// still runs this effect object locally, and - since nothing kicks a
        /// fighter - keeps playing. The repair would then re-resolve the victim on
        /// four seats while the fifth drained its stale cached one: the same drain
        /// tick debiting a different player's health on different screens, which is
        /// the exact state StageInto's note says this gate exists to prevent.
        ///
        /// So the census walks PhotonNetwork.PlayerList itself and excludes only a
        /// CONFIRMED spectator - the one actor class that is not simulating a
        /// fighter's effects, and which advertises no capability of its own. An
        /// actor that cannot be identified is counted and must advertise like any
        /// other; if it does not, the room stays on vanilla. That is fail-closed
        /// for the REPAIR, which is today's shipped behaviour and no new symptom
        /// (#276/#430).</summary>
        internal static bool RoomCarriesFix()
        {
            try
            {
                if (Plugin.modDisabled) return false;
                if (!PatchesLive) return false;
                if (PhotonNetwork.OfflineMode) return true;
                if (!PhotonNetwork.InRoom) return false;

                return _cap.Evaluate(Time.frameCount, RoomActors.RosterGeneration, CensusDelegate);
            }
            catch { return false; }
        }
    }

    internal static class ProximityVictimResolver
    {

        /// <summary>Nearest-ancestor PlayerInRangeTrigger, the association vanilla
        /// itself uses to decide which trigger a subtree belongs to. Two triggers on
        /// one object read as not-ours: the subtree cannot be attributed, and
        /// guessing would attribute the damage to the wrong ring. Same walk shape as
        /// the bug 369 indicator-radius patch.</summary>
        internal static PlayerInRangeTrigger OwningTrigger(Transform start)
        {
            Transform t = start;
            for (int guard = 0; t != null && guard < 64; guard++)
            {
                var owners = t.GetComponents<PlayerInRangeTrigger>();
                if (owners != null && owners.Length > 0)
                    return owners.Length == 1 ? owners[0] : null;
                t = t.parent;
            }
            return null;
        }

        /// <summary>Re-execute the trigger's own selection and predicate through the
        /// pure seam. Returns null when the trigger's own rule admits nobody.</summary>
        internal static ProximityResolution ResolveFromTrigger(PlayerInRangeTrigger trigger, string site, out Player victim)
        {
            victim = null;
            if (trigger == null) { NoteOutcome(site, "defer", "no owning trigger"); return ProximityResolution.Defer; }
            PlayerManager pm = PlayerManager.instance;
            if (pm == null || pm.players == null || pm.players.Count == 0)
            {
                NoteOutcome(site, "defer", "the player roster is unavailable");
                return ProximityResolution.Defer;
            }

            var players = pm.players;
            var candidates = new List<ProximityCandidate>(players.Count);
            bool rosterUnreadable = false;
            for (int i = 0; i < players.Count; i++)
            {
                Player p = players[i];
                var c = new ProximityCandidate();
                c.Id = i;
                // EVERY FIELD SET HERE IS ONE THE VANILLA RULE READS
                // (PlayerManager.cs:69-71 and :113-115), so a field that cannot
                // be read leaves this seam unable to show that its candidate set
                // is the set vanilla built. The entry keeps its SLOT and its
                // order - the team branch indexes the roster positionally, so
                // dropping one would renumber every later entry - and carries a
                // flag that makes Choose defer the WHOLE resolution rather than
                // select from a set with a defaulted team in it.
                bool readable = false;
                try
                {
                    // The NearestAny selection is vanilla's GetClosestPlayer,
                    // which measures data.playerVel.position and NOT
                    // transform.position (PlayerManager.cs:71). Marshal both, so
                    // each vanilla path is reproduced against the position
                    // vanilla itself read. A null playerVel is UNREADABLE rather
                    // than a reason to substitute the transform: vanilla
                    // dereferences it and would have thrown, and standing a
                    // different position in its place would rank candidates
                    // vanilla's own loop never measured.
                    if (p != null && p.data != null && p.data.playerVel != null)
                    {
                        Vector3 pos = p.transform.position;
                        Vector2 velPos = p.data.playerVel.position;
                        c.Team = p.TeamID;
                        c.X = pos.x;
                        c.Y = pos.y;
                        c.Z = pos.z;
                        c.AnyX = velPos.x;
                        c.AnyY = velPos.y;
                        c.Dead = p.data.dead;
                        readable = true;
                    }
                }
                catch { readable = false; }
                if (!readable)
                {
                    // Discard whatever was written before the read failed: a
                    // half-filled entry is exactly the partial candidate this
                    // flag exists to keep out of the selection.
                    c = new ProximityCandidate();
                    c.Id = i;
                    c.Unreadable = true;
                    rosterUnreadable = true;
                }
                candidates.Add(c);
            }

            Vector3 triggerPos = trigger.transform.position;
            Player holder = trigger.ownPlayer;

            // THE HOLDER IS REQUIRED ON EVERY PATH, not only on the enemy ones.
            // The seam may never answer with the holder (every caller is an effect
            // that acts on someone else), and the only way to honour that is to
            // know which candidate the holder is. Without it, vanilla's own rule
            // is the honest answer.
            if (holder == null)
            {
                NoteOutcome(site, "defer", "the trigger has no owning player");
                return ProximityResolution.Defer;
            }
            int holderId = ProximityVictim.None;
            for (int i = 0; i < players.Count; i++)
                if (ReferenceEquals(players[i], holder)) { holderId = i; break; }
            if (holderId == ProximityVictim.None)
            {
                NoteOutcome(site, "defer", "the holder is not on the roster");
                return ProximityResolution.Defer;
            }
            int holderTeam = holder.TeamID;

            // WHICH vanilla selector the trigger actually evaluated. GetOtherPlayer
            // is prefixed to FfaTargeting.NearestOpponent while the FFA engine is
            // active and runs stock GetClosestPlayerInTeam otherwise
            // (FfaMode.cs:3752-3763), and the two disagree - so reading the mode is
            // part of reproducing the selection, not a detail. If the mode cannot
            // be read there is no selector to reproduce and vanilla keeps the call.
            bool ffa;
            try { ffa = FfaMode.EngineActive(); }
            catch
            {
                NoteOutcome(site, "defer", "the game mode could not be read");
                return ProximityResolution.Defer;
            }

            ProximitySelection selection;
            if (trigger.targetType == PlayerInRangeTrigger.TargetType.OtherPlayer)
                selection = ffa ? ProximitySelection.NearestEnemyFfa : ProximitySelection.NearestEnemyTeam;
            else
                selection = ProximitySelection.NearestAny;

            // OtherPlayer measures its lookup from the HOLDER (vanilla :61 passes
            // ownPlayer to GetOtherPlayer); Any measures from the TRIGGER (:65).
            Vector3 selectPos = selection == ProximitySelection.NearestAny
                ? triggerPos
                : holder.transform.position;

            float effectiveRange = trigger.range * trigger.transform.root.localScale.x;
            Vector2 seeFrom = new Vector2(triggerPos.x, triggerPos.y);

            // PlayerManager.CanSeePlayer is a live scene query, so "it threw"
            // is a different fact from "it said no". Folding the two together
            // would turn an unreadable input into a suppressed tick, which is
            // the direction that costs a player health vanilla would not have
            // taken; the seam defers on Unreadable instead.
            bool visionUnreadable = false;
            int chosen = ProximityVictim.Choose(
                candidates,
                holderId,
                holderTeam,
                selection,
                selectPos.x, selectPos.y,
                triggerPos.x, triggerPos.y, triggerPos.z,
                effectiveRange,
                delegate (int id)
                {
                    try
                    {
                        if (id < 0 || id >= players.Count) { visionUnreadable = true; return ProximityVision.Unreadable; }
                        Player p = players[id];
                        if (p == null) { visionUnreadable = true; return ProximityVision.Unreadable; }
                        return pm.CanSeePlayer(seeFrom, p).canSee
                            ? ProximityVision.Visible
                            : ProximityVision.Blocked;
                    }
                    catch { visionUnreadable = true; return ProximityVision.Unreadable; }
                });

            if (chosen == ProximityVictim.Defer)
            {
                // Which unreadable input produced the deferral, in the order the
                // seam consults them: the roster is read before anything is
                // selected, the vision query only for the candidate selected,
                // and a deferral with neither means the trigger's own rule
                // resolved the holder for an effect that acts on someone else.
                NoteOutcome(site, "defer",
                    rosterUnreadable ? "a roster entry could not be read"
                    : visionUnreadable ? "the vision query could not be answered"
                    : "the trigger's own rule resolves the holder");
                return ProximityResolution.Defer;
            }
            if (chosen < 0 || chosen >= players.Count) return ProximityResolution.Refuse;
            Player resolved = players[chosen];
            if (resolved == null) return ProximityResolution.Refuse;
            victim = resolved;
            return ProximityResolution.Victim;
        }

        /// <summary>THE WHOLE PREFIX DECISION, ONCE, FOR ALL THREE EFFECTS.
        ///
        /// The defect this repair exists for is a CLASS, not a line, and the
        /// three prefixes below must take the SAME action for the same
        /// resolution (#432). Three copies of an if-ladder is how they stop
        /// doing that. Each caller keeps only the one statement that is genuinely
        /// its own - writing its own field - and the mapping from resolution to
        /// action lives in the pure seam, where it is tested.</summary>
        internal static ProximityPrefixAction DecidePrefix(
            string site, Component instance, bool targetsOther, out Player fresh)
        {
            fresh = null;
            try
            {
                if (instance == null) return ProximityPrefixAction.RunVanillaUntouched;
                if (!ProximityVictim.ShouldRepair(ProximityVictimGate.RoomCarriesFix(), targetsOther))
                {
                    // NOT a refusal and not a deferral: the repair has nothing to
                    // do here. It still gets a line, because a feature that is
                    // INACTIVE and a feature that is active and declining must
                    // not produce the same silence (#438/#443). Bounded to one
                    // line per reason per session, so behaviour and log volume
                    // both stay what an unpatched seat produces.
                    NoteOutcome(site, "inactive", targetsOther
                        ? "the room does not all carry the repair"
                        : "the effect targets its own player");
                    return ProximityPrefixAction.RunVanillaUntouched;
                }

                PlayerInRangeTrigger trigger = OwningTrigger(instance.transform);
                ProximityResolution outcome = ResolveFromTrigger(trigger, site, out fresh);
                ProximityPrefixAction action = ProximityVictim.PrefixAction(outcome, fresh != null);
                if (action == ProximityPrefixAction.SkipOriginal)
                    NoteOutcome(site, "refuse", "trigger-driven call admits nobody");
                return action;
            }
            catch (Exception ex)
            {
                // LogError, NOT Cleanup. Cleanup is the Harmony ATTACH reporter
                // and its first statement returns immediately on a non-null
                // exception (VanillaFixes.cs:69-72), so routing a runtime failure
                // through it emits nothing at all.
                VanillaFixSupport.LogError(site + "FreshVictim", ex);
                NoteOutcome(site, "refuse", "resolution threw");
                fresh = null;
                return ProximityPrefixAction.SkipOriginal;   // conservative: apply nothing
            }
        }

        /// <summary>NO OWNING TRIGGER - and therefore no repair. The effect is
        /// driven by something other than a PlayerInRangeTrigger, so this seam has
        /// no predicate to reproduce and leaves vanilla exactly as it is.
        ///
        /// An earlier draft called PlayerManager.GetOtherPlayer here and argued in
        /// a comment that this was deliberately NOT FfaTargeting.NearestOpponent,
        /// "which defaults needVision to false and applies no range bound at all".
        /// In FFA that distinction does not exist: this mod's own
        /// PlayerManager_GetOtherPlayer_Ffa_Patch prefixes GetOtherPlayer to
        /// exactly FfaTargeting.NearestOpponent whenever FfaMode.EngineActive()
        /// (FfaMode.cs:3754-3763), with needVision omitted and no range term in the
        /// helper (FfaMode.cs:3805-3826). So on this path, in the very mode the bug
        /// was reported in, the draft selected with neither a range bound nor a
        /// vision test and then wrote that answer into vanilla's field - which can
        /// drain a player standing behind a wall on the far side of the map. That
        /// is the reported symptom, reproduced by the repair.
        ///
        /// Falling through is also the RIGHT scope. The only other vanilla caller
        /// of DealDamageToPlayer.Go is A_DemonicPact, driven by an AttackTrigger
        /// (measured in BUG389-GATE0-OFFLINE.md: exactly three persistent calls in
        /// the whole game name a DealDamageToPlayer, one from the Lifestealer ring
        /// and two from that AttackTrigger). AttackTrigger has its own selection
        /// rule that this seam does not model, so the honest answer for it is
        /// vanilla's, unchanged. Whether that card carries the same victim-cache
        /// defect is a separate question and is flagged rather than guessed.</summary>
        internal static void NoteOutcome(string site, string outcome, string why)
        {
            VanillaFixSupport.DiagLimited(
                ProximityVictim.SignalKey(site, outcome, why),
                ProximityVictim.SignalText(site, outcome, why),
                ProximityVictim.MaxOutcomeSignals);
        }
    }

    /// <summary>The reported defect. DealDamageToPlayer.cs:24,33-40.</summary>
    [HarmonyPatch(typeof(DealDamageToPlayer), "Go")]
    internal static class DealDamageToPlayerFreshVictimPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGo(DealDamageToPlayer __instance)
        {
            Player fresh;
            // A contradiction, not a routine outcome, is what SkipOriginal means
            // here - and it is that only because the seam reproduces the SAME
            // selector the trigger evaluated, then applies a predicate that is
            // vanilla's minus one unreadable term, microseconds later, in the
            // same frame, over the same transforms. The selection fidelity is
            // what carries that claim; see the seam's note on Choose.
            switch (ProximityVictimResolver.DecidePrefix(
                "DealDamageToPlayer", __instance,
                __instance != null && __instance.targetPlayer == DealDamageToPlayer.TargetPlayer.Other,
                out fresh))
            {
                case ProximityPrefixAction.WriteVictimAndRun:
                    // Hand the answer to vanilla. Writing on EVERY call is not
                    // reinstating the cache: nothing ever reads a value this
                    // prefix did not just write on this call.
                    __instance.target = fresh;
                    return true;
                case ProximityPrefixAction.SkipOriginal:
                    return false;
                default:
                    return true;
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) ProximityVictimGate.MarkAttached("DealDamageToPlayer.Go");
            return exception;
        }
    }

    /// <summary>Sibling victim-cache. StunPlayer.cs:15,19-26.
    ///
    /// NO RING DRIVES THIS ONE IN TODAY'S CONTENT, so on this game build the patch
    /// is inert by construction rather than by accident. The only shipped instance
    /// is StunPlayer path id 10653 on E_StunOverTime, and its driver is a DelayEvent
    /// (path id 10547, delayedEvent[0] -> StunPlayer.Go, Void, RuntimeOnly), not a
    /// PlayerInRangeTrigger - measured in BUG389-GATE0-OFFLINE.md. The ancestor walk
    /// therefore returns null on every real call and the prefix returns true before
    /// resolving anything, leaving vanilla untouched.
    ///
    /// It is kept deliberately. The census bounds today's CONTENT, not the code: the
    /// cache defect is in StunPlayer.Go itself, so the day a card puts this component
    /// under a ring the repair is already in place, and until then the cost is one
    /// attach signal and a branch that returns true. What is NOT acceptable is a
    /// version of this patch that invents a selection rule when no trigger owns the
    /// call - see the resolver's note on why the no-trigger path falls through.
    ///
    /// PerfPatches.StunPlayerGoNullGuard is a separate Prefix on the same method
    /// and neither declares a priority, so their ORDER IS UNDEFINED. What that
    /// order can and cannot reach is two different questions.
    ///
    /// It cannot change whether the original runs. HarmonyX calls every prefix on
    /// a method regardless of what a sibling returned and ANDs the returns into
    /// __runOriginal (#352 - verified there from the shipped 0Harmony.dll:
    /// WritePrefixes emits every prefix call unconditionally). A conjunction is
    /// order-independent, so either prefix refusing suppresses the original
    /// whichever ran first, and neither can turn the other's refusal into an
    /// application. Both halves of that are exercised by the harness case
    /// P1/P2, over both orders.
    ///
    /// What it could still reach is a SIDE EFFECT one prefix leaves for the other
    /// to read. This one writes __instance.target, and only on the accepting
    /// path; the null guard reads the ancestor Player and writes nothing. So
    /// today there is no shared state to order. That is a statement about
    /// today's two bodies rather than a property of the arrangement, and it is
    /// recorded as a residual: nothing in the tree stops a later edit from making
    /// either prefix read the field the other writes. The consequence to watch
    /// for is a stun applied to, or withheld from, a player the ring did not
    /// match.</summary>
    [HarmonyPatch(typeof(StunPlayer), "Go")]
    internal static class StunPlayerFreshVictimPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGo(StunPlayer __instance)
        {
            Player fresh;
            switch (ProximityVictimResolver.DecidePrefix(
                "StunPlayer", __instance,
                __instance != null && __instance.targetPlayer == StunPlayer.TargetPlayer.OtherPlayer,
                out fresh))
            {
                case ProximityPrefixAction.WriteVictimAndRun:
                    __instance.target = fresh;
                    return true;
                case ProximityPrefixAction.SkipOriginal:
                    return false;
                default:
                    return true;
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) ProximityVictimGate.MarkAttached("StunPlayer.Go");
            return exception;
        }
    }

    /// <summary>Sibling victim-cache. TeleportToOpponent.cs:11,19-22. This one has no
    /// own-player branch: it always resolves an opponent, so targetsOther is
    /// unconditionally true.
    ///
    /// NOTHING IN THE SHIPPED CONTENT CARRIES THIS COMPONENT. The census in
    /// BUG389-GATE0-OFFLINE.md found zero MonoBehaviour instances of it across 146
    /// serialized files, 120,229 objects and the 23 StreamingAssets bundles; only the
    /// MonoScript exists (globalgamemanagers.assets, path id 437). Go() is therefore
    /// never invoked on this game build and this prefix never runs at all.
    ///
    /// Kept on the same reasoning as StunPlayer above, with one failure mode written
    /// down rather than left to be discovered: it occupies one of the
    /// RequiredAttachments slots, so if a later game build drops this unused class the
    /// patch will not attach and the count will never complete, which takes the
    /// DealDamageToPlayer repair down with it. That direction is safe - no advert, so
    /// every seat stays on vanilla, which is today's behaviour - and it is loud:
    /// StageInto logs "patches did NOT attach (2/3)" once per session. Re-pin the
    /// census after any ROUNDS update, and if this class is gone, delete this patch
    /// and drop RequiredAttachments to 2 rather than leaving the repair inert.</summary>
    [HarmonyPatch(typeof(TeleportToOpponent), "Go")]
    internal static class TeleportToOpponentFreshVictimPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGo(TeleportToOpponent __instance)
        {
            Player fresh;
            switch (ProximityVictimResolver.DecidePrefix(
                "TeleportToOpponent", __instance, true, out fresh))
            {
                case ProximityPrefixAction.WriteVictimAndRun:
                    __instance.target = fresh;
                    return true;
                case ProximityPrefixAction.SkipOriginal:
                    return false;
                default:
                    return true;
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) ProximityVictimGate.MarkAttached("TeleportToOpponent.Go");
            return exception;
        }
    }
}
