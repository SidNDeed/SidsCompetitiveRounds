using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

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
        /// <summary>Capability key. The KEY carries the protocol version: any later
        /// SEMANTIC change to who this repair chooses takes cr_prox2, because a
        /// client advertising cr_prox1 has answered a different question. Same
        /// family and same pre-join discipline as cr_pois2 / cr_msv2.</summary>
        internal const string CapabilityProp = "cr_prox1";
        internal const int CapabilityValue = 1;

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
                    prejoin[CapabilityProp] = CapabilityValue;
                    return;
                }

                if (!_stageFailedPermanently)
                {
                    _stageFailedPermanently = true;
                    Plugin.Log.LogError("[PROX-CAP] proximity-victim patches did NOT attach ("
                        + _attached + "/" + RequiredAttachments + ") - not advertising "
                        + CapabilityProp + "; this seat stays on vanilla for the session");
                }
            }
            catch { }
        }

        // Per-room capability cache. Recomputed when the room or the fighter count
        // changes - a roster change is exactly when a previously whole-room-capable
        // room can stop being one.
        private static string _capRoom = "";
        private static int _capCount = -1;
        private static bool _capValue;

        /// <summary>True when EVERY fighter in the room advertises a build carrying
        /// this repair.
        ///
        /// Whole-room, not master-only and not self-only: the effect object runs on
        /// every client with no ownership gate, so a seat that repairs while another
        /// does not produces two different healths for the same player. A mixed room
        /// keeps vanilla on every seat, which is exactly today's shipped behaviour -
        /// no new symptom - and the room stays self-consistent.
        ///
        /// Spectators are excluded by construction: RoomActors.ActiveFighters() is
        /// the census of players who fight, and a spectator advertises no capability
        /// and must not disable the repair room-wide.</summary>
        internal static bool RoomCarriesFix()
        {
            try
            {
                if (Plugin.modDisabled) return false;
                if (!PatchesLive) return false;
                if (PhotonNetwork.OfflineMode) return true;
                if (!PhotonNetwork.InRoom) return false;

                string room = PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : "";
                var fighters = RoomActors.ActiveFighters();
                int count = fighters == null ? 0 : fighters.Length;

                if (room == _capRoom && count == _capCount) return _capValue;

                bool ok = count > 0;
                if (ok)
                {
                    foreach (var p in fighters)
                    {
                        if (p == null) { ok = false; break; }
                        var props = p.CustomProperties;
                        object v;
                        if (props == null || !props.TryGetValue(CapabilityProp, out v) || !(v is int) || ((int)v) != CapabilityValue)
                        {
                            ok = false;
                            break;
                        }
                    }
                }

                _capRoom = room;
                _capCount = count;
                _capValue = ok;
                return ok;
            }
            catch { return false; }
        }
    }

    internal static class ProximityVictimResolver
    {
        internal const string DiagKey = "ProximityVictim389";

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
        internal static Player ResolveFromTrigger(PlayerInRangeTrigger trigger)
        {
            if (trigger == null) return null;
            PlayerManager pm = PlayerManager.instance;
            if (pm == null || pm.players == null || pm.players.Count == 0) return null;

            var players = pm.players;
            var candidates = new List<ProximityCandidate>(players.Count);
            for (int i = 0; i < players.Count; i++)
            {
                Player p = players[i];
                var c = new ProximityCandidate();
                c.Id = i;
                if (p == null || p.data == null)
                {
                    c.Dead = true;
                    candidates.Add(c);
                    continue;
                }
                Vector3 pos = p.transform.position;
                c.Team = p.TeamID;
                c.X = pos.x;
                c.Y = pos.y;
                c.Z = pos.z;
                // The NearestAny selection is vanilla's GetClosestPlayer, which
                // measures data.playerVel.position and NOT transform.position
                // (PlayerManager.cs:71). Marshal both so each vanilla path is
                // reproduced against the position vanilla itself read.
                Vector2 velPos = new Vector2(pos.x, pos.y);
                try { if (p.data.playerVel != null) velPos = p.data.playerVel.position; }
                catch { }
                c.AnyX = velPos.x;
                c.AnyY = velPos.y;
                c.Dead = p.data.dead;
                candidates.Add(c);
            }

            Vector3 triggerPos = trigger.transform.position;
            Player holder = trigger.ownPlayer;

            ProximitySelection selection = trigger.targetType == PlayerInRangeTrigger.TargetType.OtherPlayer
                ? ProximitySelection.NearestEnemy
                : ProximitySelection.NearestAny;

            // OtherPlayer measures its lookup from the HOLDER (vanilla :61 passes
            // ownPlayer to GetOtherPlayer); Any measures from the TRIGGER (:65).
            Vector3 selectPos = triggerPos;
            int holderId = ProximityVictim.None;
            int holderTeam = int.MinValue;
            if (selection == ProximitySelection.NearestEnemy)
            {
                if (holder == null) return null;
                selectPos = holder.transform.position;
                holderTeam = holder.TeamID;
                for (int i = 0; i < players.Count; i++)
                    if (ReferenceEquals(players[i], holder)) { holderId = i; break; }
            }

            float effectiveRange = trigger.range * trigger.transform.root.localScale.x;
            Vector2 seeFrom = new Vector2(triggerPos.x, triggerPos.y);

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
                        if (id < 0 || id >= players.Count) return false;
                        Player p = players[id];
                        if (p == null) return false;
                        return pm.CanSeePlayer(seeFrom, p).canSee;
                    }
                    catch { return false; }
                });

            if (chosen < 0 || chosen >= players.Count) return null;
            return players[chosen];
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
        internal static void NoteRefusal(string site, string why)
        {
            VanillaFixSupport.DiagLimited(
                DiagKey,
                "[PROX-TARGET] refused site=" + site + " why=" + why,
                ProximityVictim.MaxRefusalDiagnostics);
        }
    }

    /// <summary>The reported defect. DealDamageToPlayer.cs:24,33-40.</summary>
    [HarmonyPatch(typeof(DealDamageToPlayer), "Go")]
    internal static class DealDamageToPlayerFreshVictimPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGo(DealDamageToPlayer __instance)
        {
            try
            {
                if (__instance == null) return true;
                bool targetsOther = __instance.targetPlayer == DealDamageToPlayer.TargetPlayer.Other;
                if (!ProximityVictim.ShouldRepair(ProximityVictimGate.RoomCarriesFix(), targetsOther)) return true;

                PlayerInRangeTrigger trigger = ProximityVictimResolver.OwningTrigger(__instance.transform);
                // No owning trigger, no predicate to reproduce: vanilla, untouched.
                if (trigger == null) return true;

                Player fresh = ProximityVictimResolver.ResolveFromTrigger(trigger);
                if (fresh == null)
                {
                    // A contradiction, not a routine outcome: our predicate is a
                    // strict relaxation of the one the trigger evaluated
                    // microseconds ago, in the same frame, over the same
                    // transforms.
                    ProximityVictimResolver.NoteRefusal("DealDamageToPlayer", "trigger-driven call admits nobody");
                    return false;
                }

                // Hand the answer to vanilla. Writing on EVERY call is not
                // reinstating the cache: nothing ever reads a value this prefix did
                // not just write on this call.
                __instance.target = fresh;
                return true;
            }
            catch (Exception ex)
            {
                // LogError, NOT Cleanup. Cleanup is the Harmony ATTACH reporter and
                // its first statement returns immediately on a non-null exception
                // (VanillaFixes.cs:69-72), so routing a runtime failure through it
                // emits nothing at all - the refusal below would be invisible and
                // an inert feature would be indistinguishable from one with nothing
                // to do (#438/#443). Both signals here are bounded: LogError is
                // rate-limited per name, NoteRefusal by MaxRefusalDiagnostics.
                VanillaFixSupport.LogError("DealDamageToPlayerFreshVictim", ex);
                ProximityVictimResolver.NoteRefusal("DealDamageToPlayer", "resolution threw");
                return false;   // conservative: apply nothing
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
    /// PerfPatches.StunPlayerGoNullGuard is a separate Prefix on the same method; it
    /// suppresses an NRE when the ancestor Player is gone and does not touch the
    /// cache, so the two do not overlap. Either returning false skips the original,
    /// which is the conservative direction for both, and neither can turn the
    /// other's refusal into an application.</summary>
    [HarmonyPatch(typeof(StunPlayer), "Go")]
    internal static class StunPlayerFreshVictimPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGo(StunPlayer __instance)
        {
            try
            {
                if (__instance == null) return true;
                bool targetsOther = __instance.targetPlayer == StunPlayer.TargetPlayer.OtherPlayer;
                if (!ProximityVictim.ShouldRepair(ProximityVictimGate.RoomCarriesFix(), targetsOther)) return true;

                PlayerInRangeTrigger trigger = ProximityVictimResolver.OwningTrigger(__instance.transform);
                // No owning trigger, no predicate to reproduce: vanilla, untouched.
                if (trigger == null) return true;

                Player fresh = ProximityVictimResolver.ResolveFromTrigger(trigger);
                if (fresh == null)
                {
                    ProximityVictimResolver.NoteRefusal("StunPlayer", "trigger-driven call admits nobody");
                    return false;
                }

                __instance.target = fresh;
                return true;
            }
            catch (Exception ex)
            {
                // See the note on DealDamageToPlayer's catch: Cleanup is the attach
                // reporter and logs nothing when handed an exception.
                VanillaFixSupport.LogError("StunPlayerFreshVictim", ex);
                ProximityVictimResolver.NoteRefusal("StunPlayer", "resolution threw");
                return false;
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
            try
            {
                if (__instance == null) return true;
                if (!ProximityVictim.ShouldRepair(ProximityVictimGate.RoomCarriesFix(), true)) return true;

                PlayerInRangeTrigger trigger = ProximityVictimResolver.OwningTrigger(__instance.transform);
                // No owning trigger, no predicate to reproduce: vanilla, untouched.
                if (trigger == null) return true;

                Player fresh = ProximityVictimResolver.ResolveFromTrigger(trigger);
                if (fresh == null)
                {
                    ProximityVictimResolver.NoteRefusal("TeleportToOpponent", "trigger-driven call admits nobody");
                    return false;
                }

                __instance.target = fresh;
                return true;
            }
            catch (Exception ex)
            {
                // See the note on DealDamageToPlayer's catch: Cleanup is the attach
                // reporter and logs nothing when handed an exception.
                VanillaFixSupport.LogError("TeleportToOpponentFreshVictim", ex);
                ProximityVictimResolver.NoteRefusal("TeleportToOpponent", "resolution threw");
                return false;
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
