using System;
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
    /// A_Lifestealer, DealDamageToPlayer and Go.
    ///
    /// WHERE THE REPAIR CAN ACTUALLY ENGAGE on this game build. Only a ring-driven
    /// call is repaired, and the content census bounds that to one card:
    /// A_Lifestealer's DealDamageToPlayer. A_DemonicPact's DealDamageToPlayer is
    /// AttackTrigger-driven, E_StunOverTime's StunPlayer is DelayEvent-driven, and
    /// TeleportToOpponent has no instances at all - each of those falls through to
    /// vanilla, untouched. The two sibling patches are kept for the reasons recorded
    /// on their own classes below.
    ///
    /// THE REPAIR, AND WHAT IT DOES NOT DO. Vanilla's effects resolve their victim
    /// once and keep it in a private field they never re-derive - `if (!target)`,
    /// DealDamageToPlayer.cs:31-40 - while the ring that fires them re-evaluates
    /// who is nearby every frame. A Prefix on each effect hands it the answer ITS
    /// OWN resolution would produce on this tick, and then lets vanilla run.
    ///
    /// That answer is not computed here. It comes from calling the very method the
    /// effect's own body calls - PlayerManager.GetOtherPlayer - with the holder
    /// that body derives, so the ranking, the roster reads and any throw are
    /// vanilla's own (#510: a prefix that samples what the original is about to
    /// read is measuring a prediction, and every round of narrowing that prediction
    /// produced another case of it). One call covers every mode: this mod prefixes
    /// GetOtherPlayer itself while the free-for-all engine is driving the room
    /// (FfaMode.cs:3752-3764) and otherwise it falls through to stock
    /// GetClosestPlayerInTeam, mis-indexed liveness gate and all - and the ring
    /// reaches its own player through that same patched method
    /// (PlayerInRangeTrigger.cs:59-61). There is no branch here to disagree with it.
    ///
    /// Nothing re-implements the damage call either: vanilla's
    /// DealDamageToPlayer.cs:41-45 still runs, including data.player as the
    /// damaging player, which is what makes the holder's own LifeSteal heal fire
    /// (#354 - a path that applies damage outside the engine's funnel silently
    /// drops every side-effect of that damage).
    ///
    /// FAILURE DIRECTION (#276/#430). Today the unhandled case fails in the worst
    /// direction: real health leaves the wrong player and can kill them. EVERY
    /// unhandled case here fails to ONE direction - vanilla, unchanged, running
    /// against its own cached field, which is exactly today's shipped behaviour and
    /// no new symptom. That covers a room that does not all carry the repair, an
    /// own-player effect, a call no ring drives, a holder that cannot be read, a
    /// vanilla resolution that answered with nobody, and a throw anywhere in the
    /// attempt.
    ///
    /// THESE PREFIXES NEVER RETURN false. The previous design re-derived vanilla's
    /// own predicate - visibility, range, liveness - and refused the call when its
    /// re-derivation disagreed, which was the one route by which a repair meant to
    /// change WHO takes damage could change WHETHER anyone does. The predicate is
    /// gone with the rest of the prediction, and with it the refusing answer: see
    /// ProximityVictim.VictimAction, which has no such value to return.
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

        /// <summary>THE ONLY PLACE IN THIS FILE THAT READS EITHER GLOBAL. What this
        /// seat will do, asked once, by the advertisement, by the gate and by the
        /// withdrawal - so a peer can never be told something this seat's own gate
        /// contradicts. The decision itself is pure and lives in the seam, where a
        /// case can execute it and a mutant can reach it; this is the one line of
        /// plumbing that hands it the two facts.
        ///
        /// A SECOND COPY IS THE DEFECT, not merely a duplication: the advert used
        /// to be staged on the attachment count alone while the gate also required
        /// the mod to be switched on, and the two answers disagreed on exactly the
        /// seat that had been disabled. Harness cases W14 and W15 hold this to one
        /// copy by requiring the mod-disabled flag to occur exactly once in this
        /// whole file - inside this member - and by forbidding both globals inside
        /// StageInto and GateState.</summary>
        internal static ProximityGateState LocalCapability()
        {
            return ProximityVictim.LocalGateState(Plugin.modDisabled, PatchesLive);
        }

        /// <summary>True once this seat has actually staged the key into a pre-join
        /// merge. A seat that never staged has nothing to withdraw.</summary>
        private static bool _advertised;

        /// <summary>Set by RepublishCapability when it withdraws. It is a SEPARATE
        /// latch from the local gate on purpose: the gate answers what is true now,
        /// and this answers what this seat has already told the room. Re-staging
        /// after a withdrawal would advertise a capability across a room boundary
        /// that peers in the previous room were told was gone, so the honest
        /// direction is to stay withdrawn for the session.</summary>
        private static bool _withdrawn;

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
        /// Why the gate has to be HERE and not only in GateState(). PatchesLive
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
                ProximityGateState local = LocalCapability();
                if (local == ProximityGateState.Capable && !_withdrawn)
                {
                    prejoin[ProximityVictim.CapabilityProp] = ProximityVictim.CapabilityValue;
                    _advertised = true;
                    return;
                }

                if (!_stageFailedPermanently)
                {
                    _stageFailedPermanently = true;
                    // The reason must be true for the branch that printed it: once
                    // withdrawn, the gate's own answer is no longer why we are
                    // declining, and printing it would name a cause that has been
                    // superseded.
                    string why = _withdrawn
                        ? "this seat withdrew the capability earlier in the session"
                        : ProximityVictim.GateReason(local);
                    Plugin.Log.LogError("[PROX-CAP] not advertising " + ProximityVictim.CapabilityProp
                        + " - " + why + " (" + _attached + "/"
                        + RequiredAttachments + " patches live); this seat stays on vanilla for the session");
                }
            }
            catch { }
        }

        /// <summary>Withdraw a staged advertisement once this seat's own gate has
        /// stopped saying Capable, so the room census re-reads it and the WHOLE
        /// room falls back to vanilla rather than half of it repairing.
        ///
        /// DRIVEN, NOT HOOKED, from the always-on persistent tick - and from a
        /// point ABOVE that tick's own modDisabled return. Below that line this
        /// member could never run on the one seat it exists for, because the
        /// condition that makes a withdrawal necessary is the condition the
        /// return covers: a guard keyed on a feature's enable-condition inherits
        /// that feature's dead zone (#272/#98). Harness case W16b is bounded to
        /// exactly that span. THE TICK IS THE TRANSITION THAT EXISTS TODAY: it is
        /// the only driver that can reach a seat which has already staged the key
        /// and has since stopped being Capable.
        ///
        /// It is also called directly from the compat check that disables the mod,
        /// beside PoisonSync.RevokeCapability and GrowNormalize.RevokeCapability -
        /// but it is NOT the same shape as those two, and saying so was wrong.
        /// PoisonSync stages at Awake and GrowNormalize stages from the tick, so
        /// their latches are already set when that check fires. This key is staged
        /// PRE-JOIN, from the queue poll, which cannot run before ApiClient
        /// .Initialize - and the compat-fail branch returns above that call
        /// (Plugin.cs, held by W18). So on a FIRST initialisation _advertised is
        /// false there by construction and this member returns on its first line:
        /// that site can only ever withdraw on a SECOND DoInitialize, after a
        /// persistent-host respawn whose compat read differs from the first. It is
        /// kept for exactly that case, and because a call that cannot do anything
        /// is cheaper than a rule nobody remembers (#275). The consequence for a
        /// reader: "[PROX-CAP] withdrew" is not a line a plain compat-disable can
        /// produce, and an acceptance check that waits for it there will wait
        /// forever (#438/#443).
        ///
        /// IT CAN ONLY WITHDRAW. ProximityVictim.ShouldRevokeCapability has no
        /// advertising direction and this member writes the value 0 and nothing
        /// else - the capable value reaches a peer through the pre-join merge in
        /// StageInto or not at all (#287, asserted by W15). Withdrawal is safe in
        /// room because the census's answer is keyed on RoomActors
        /// .RosterGeneration and Plugin.cs bumps that counter for a cr_prox1
        /// property change, so every peer re-derives on its next tick instead of
        /// holding a cached true.
        ///
        /// THE FLAGS MOVE ONLY ON A WRITE THAT WAS ACCEPTED, and acceptance has
        /// TWO channels rather than one. Player.SetCustomProperties RETURNS a bool
        /// (verified against the shipped PhotonRealtime.dll, not assumed): in room
        /// it forwards to the actor-property op, and an op the client cannot send
        /// at that instant - mid-reconnect, or a tick where this peer is no longer
        /// on the game server - comes back FALSE, having sent nothing and cached
        /// nothing, and having thrown nothing. An earlier version of this member
        /// read only the throw and cleared _advertised and latched _withdrawn
        /// regardless, which defeated the retry the tick exists to provide:
        /// cr_prox1 stayed 1 on every peer for the rest of the room while this
        /// seat ran vanilla against its stale cached target, and the log asserted
        /// a withdrawal that never left the process.
        ///
        /// So both channels are handled the same way - the flags are untouched and
        /// the next tick tries again - and the success line is printed only where
        /// the room was actually told. The same polarity the room half of this API
        /// is already read with at GameStateWatcher.cs:4706 (#276/#430).
        ///
        /// The refusal is stated through the BOUNDED sink, not Plugin.Log: the
        /// retry is per tick by design and a line per tick would bury it. Its
        /// reason is its own sentence, so it gets its own budget and cannot be
        /// silenced by another cause that spoke first (ProximityVictim
        /// .WithdrawRefusedReason, held by G8).</summary>
        internal static void RepublishCapability()
        {
            try
            {
                if (!_advertised) return;

                ProximityGateState local = LocalCapability();
                if (!ProximityVictim.ShouldRevokeCapability(local, _advertised)) return;

                var me = PhotonNetwork.LocalPlayer;
                if (me == null) return;

                bool sent = me.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { ProximityVictim.CapabilityProp, 0 }
                });
                if (!sent)
                {
                    // Nothing left this process, so nothing about what the room
                    // has been told changed. Keep the advert standing - it is
                    // still true that peers were told Capable - and retry.
                    VanillaFixSupport.DiagLimited(
                        ProximityVictim.SignalKey("withdraw", ProximityVictim.WithdrawRefusedReason),
                        "[PROX-CAP] " + ProximityVictim.WithdrawRefusedReason + " ("
                        + ProximityVictim.CapabilityProp
                        + " still stands on this seat); retrying on the next tick",
                        ProximityVictim.MaxOutcomeSignals);
                    return;
                }
                _advertised = false;
                _withdrawn = true;   // StageInto refuses for the rest of the session
                Plugin.Log.LogWarning("[PROX-CAP] withdrew " + ProximityVictim.CapabilityProp
                    + " - " + ProximityVictim.GateReason(local)
                    + "; this seat and every seat in its room stay on vanilla");
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
        /// while the actor still owns a Player the game is simulating, still runs
        /// this effect object locally, and - since nothing kicks a fighter - keeps
        /// playing. The repair would then re-resolve the victim on four seats while
        /// the fifth drained its stale cached one: the same drain tick debiting a
        /// different player's health on different screens, which is the exact state
        /// StageInto's note says this gate exists to prevent.
        ///
        /// So the census walks PhotonNetwork.PlayerList itself and excludes only a
        /// CONFIRMED spectator - the one actor class that is not simulating a
        /// fighter's effects, and which advertises no capability of its own. An
        /// actor that cannot be identified is counted and must advertise like any
        /// other; if it does not, the room stays on vanilla. That is fail-closed
        /// for the REPAIR, which is today's shipped behaviour and no new symptom
        /// (#276/#430).
        ///
        /// WHY THIS ANSWERS WITH A STATE AND NOT A BOOLEAN (#430). Five different
        /// facts refuse the repair here and only one of them is about the peers:
        /// the mod is switched off, this seat's own prefixes did not attach, there
        /// is no room, the census found a fighter without the key, or the census
        /// could not be read at all. A caller handed `false` can only guess which,
        /// and the line it printed - "the room does not all carry the repair" -
        /// pointed a reader at the other seats' builds for a patch that failed to
        /// attach locally, and printed the same sentence in the main menu, where
        /// there is no room to carry anything. Each cause now leaves here under its
        /// own name and gets its own line (ProximityVictim.GateReason). The failure
        /// DIRECTION is unchanged: anything that is not Capable refuses.</summary>
        internal static ProximityGateState GateState()
        {
            try
            {
                // The SAME answer the advertisement is staged on - one predicate,
                // never a second copy of the conjunction (see LocalCapability).
                ProximityGateState local = LocalCapability();
                if (local != ProximityGateState.Capable) return local;
                if (PhotonNetwork.OfflineMode) return ProximityGateState.Capable;
                if (!PhotonNetwork.InRoom) return ProximityGateState.NotInARoom;

                return _cap.Evaluate(Time.frameCount, RoomActors.RosterGeneration, CensusDelegate)
                    ? ProximityGateState.Capable
                    : ProximityGateState.RoomNotAllCapable;
            }
            catch { return ProximityGateState.CensusUnreadable; }
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
            // This is the ONLY thing the walk is asked. The repair does not read
            // the trigger's targetType, range, position or cached fields: the
            // defect is a victim field that survives REPEATED invocation, and what
            // this walk settles is whether anything invokes this effect
            // repeatedly. An AttackTrigger or a DelayEvent drives its own rule,
            // which this repair does not model, so those keep vanilla's answer.
            //
            // The reasoning sits HERE, inside the member that implements it,
            // rather than on the diagnostic sink it drifted onto in an earlier
            // round: a block describing a branch has to be readable from that
            // branch (#302/#351).
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

        /// <summary>The holder each effect's own body derives, derived the same
        /// way, because it is the ARGUMENT vanilla's own resolution passes.
        ///
        /// Each arm is one line of a decompiled body and must stay that way - hand
        /// GetOtherPlayer a different asker and it ranks from a different position
        /// against a different team, which is a selection of our own by the back
        /// door:
        ///   DealDamageToPlayer.cs:35   target = data.player;
        ///   StunPlayer.cs:21           target = GetComponentInParent&lt;Player&gt;();
        ///   TeleportToOpponent.cs:21   GetOtherPlayer(GetComponentInParent&lt;Player&gt;())
        /// DealDamageToPlayer caches `data` in its own Start (`:26-29`), so a call
        /// that arrives before that ran has no holder and the answer is vanilla's -
        /// which is also what vanilla would do with it, one line later, by
        /// throwing.</summary>
        internal static Player HolderOf(Component instance)
        {
            DealDamageToPlayer damage = instance as DealDamageToPlayer;
            if (damage != null) return damage.data == null ? null : damage.data.player;

            StunPlayer stun = instance as StunPlayer;
            if (stun != null) return stun.GetComponentInParent<Player>();

            TeleportToOpponent teleport = instance as TeleportToOpponent;
            if (teleport != null) return teleport.GetComponentInParent<Player>();

            return null;
        }

        /// <summary>THE VICTIM, RESOLVED BY THE GAME AND NOT BY US.
        ///
        /// One call, into the same method the effect's own body calls
        /// (DealDamageToPlayer.cs:38, StunPlayer.cs:24, TeleportToOpponent.cs:21),
        /// with the same argument. Everything that decides WHO - the candidate
        /// team, the roster order, the liveness gate and its mis-index, the
        /// comparison and its float behaviour, and the free-for-all substitution
        /// this mod itself installs on that method (FfaMode.cs:3752-3764) - happens
        /// inside vanilla IL. There is nothing here to keep equivalent to it.
        ///
        /// A throw is caught and answered with vanilla-unchanged. Letting it
        /// propagate would be a new failure: vanilla only reaches this resolution
        /// when its field is EMPTY, so on the second and every later call it cannot
        /// throw here at all, and a prefix that did would break the ring's own
        /// Update for that frame. The fallback is therefore to vanilla ITSELF - it
        /// runs and uses its own field - and never to some other selector.
        ///
        /// FOUR WAYS TO COME BACK EMPTY, FOUR ANSWERS. They used to be one null and
        /// one sentence, which told a reader that the game's targeting had answered
        /// with nobody on three paths where it was never reached at all. The
        /// `answer` parameter is what happened, never a prediction of what would
        /// have happened (#510), and the caller prints exactly it.</summary>
        private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)
        {
            try
            {
                PlayerManager pm = PlayerManager.instance;
                if (pm == null) { answer = ProximityVanillaAnswer.NoManager; return null; }

                Player holder = HolderOf(instance);
                if (holder == null) { answer = ProximityVanillaAnswer.NoHolder; return null; }

                Player victim = pm.GetOtherPlayer(holder);
                // Unity's own equality: this is also how a DESTROYED Player reads
                // as absent. Vanilla would write such a reference into its field
                // and dereference it; declining leaves the field as it found it.
                if (victim == null) { answer = ProximityVanillaAnswer.Nobody; return null; }

                answer = ProximityVanillaAnswer.Answered;
                return victim;
            }
            catch { answer = ProximityVanillaAnswer.Threw; return null; }
        }

        /// <summary>THE WHOLE PREFIX DECISION, ONCE, FOR ALL THREE EFFECTS.
        ///
        /// The defect this repair exists for is a CLASS, not a line, and the
        /// three prefixes below must take the SAME action for the same facts
        /// (#432). Three copies of an if-ladder is how they stop doing that. Each
        /// caller keeps only the one statement that is genuinely its own - writing
        /// its own field - and the mapping from facts to action lives in the pure
        /// seam, where it is tested.
        ///
        /// ORDER OF WORK, and it is load-bearing. The gate is asked first and
        /// cheaply, because an own-player effect and a room that does not all carry
        /// the repair must cost nothing per tick. Only then is the ancestor walked,
        /// and only then is the call into the game's own targeting made - so a
        /// declined call never pays for, and never reports on, a fact it did not
        /// establish.</summary>
        internal static ProximityPrefixAction DecidePrefix(
            string site, Component instance, bool targetsOther, out Player fresh)
        {
            fresh = null;
            try
            {
                if (instance == null) return ProximityPrefixAction.RunVanillaUntouched;

                // The census is not consulted for an own-player effect: that branch
                // has no cross-player lookup and no defect, so the room's answer
                // cannot change the outcome and asking would walk the PlayerList on
                // every tick. ShouldRepair still makes the whole decision - both
                // terms go into it, in one place (#432).
                ProximityGateState gate = targetsOther
                    ? ProximityVictimGate.GateState()
                    : ProximityGateState.Capable;
                if (!ProximityVictim.ShouldRepair(gate, targetsOther))
                {
                    // NOT a refusal: the repair has nothing to do here and vanilla
                    // runs untouched. It still gets a line, because a feature that
                    // is INACTIVE and a feature that is active and declining must
                    // not produce the same silence (#438/#443) - and the line names
                    // WHICH cause applied, because four of the five are local to
                    // this seat and only one is about the room. Bounded to one line
                    // per reason per session, so behaviour and log volume both stay
                    // what an unpatched seat produces.
                    NoteOutcome(site, "inactive", ProximityVictim.InactiveReason(gate, targetsOther));
                    return ProximityPrefixAction.RunVanillaUntouched;
                }

                bool ringDriven = OwningTrigger(instance.transform) != null;
                // NotAsked when no ring drives this call: the resolution is never
                // made, so the term may not carry a value describing one. It is the
                // term's honest value and not a printable reason - DeclineReason
                // answers the ring first (#351).
                ProximityVanillaAnswer vanilla = ProximityVanillaAnswer.NotAsked;
                fresh = ringDriven ? VanillaVictimFor(instance, out vanilla) : null;

                ProximityPrefixAction action = ProximityVictim.VictimAction(
                    gate, targetsOther, ringDriven, vanilla == ProximityVanillaAnswer.Answered);
                if (action != ProximityPrefixAction.WriteVictimAndRun)
                {
                    NoteOutcome(site, "defer",
                        ProximityVictim.DeclineReason(gate, targetsOther, ringDriven, vanilla));
                    fresh = null;
                }
                return action;
            }
            catch (Exception ex)
            {
                // LogError, NOT Cleanup. Cleanup is the Harmony ATTACH reporter
                // and its first statement returns immediately on a non-null
                // exception (VanillaFixes.cs:69-72), so routing a runtime failure
                // through it emits nothing at all.
                VanillaFixSupport.LogError(site + "FreshVictim", ex);
                NoteOutcome(site, "defer", "the repair could not be attempted");
                fresh = null;
                return ProximityPrefixAction.RunVanillaUntouched;   // vanilla keeps its own field
            }
        }

        /// <summary>The one bounded sink every outcome in this resolver reports
        /// through. Outcome AND reason are the budget key, and the SITE is not, so
        /// each distinct reason is stated once per session however many effects meet
        /// it - see ProximityVictim.SignalKey for why a room-wide fact charged to
        /// three separate budgets printed three times. The LINE still names the
        /// site.
        ///
        /// It builds a key and a line and decides nothing. The behaviour each line
        /// describes lives at the branch that emits it.</summary>
        internal static void NoteOutcome(string site, string outcome, string why)
        {
            VanillaFixSupport.DiagLimited(
                ProximityVictim.SignalKey(outcome, why),
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
            ProximityPrefixAction action = ProximityVictimResolver.DecidePrefix(
                "DealDamageToPlayer", __instance,
                __instance != null && __instance.targetPlayer == DealDamageToPlayer.TargetPlayer.Other,
                out fresh);
            // Hand the answer to vanilla. Writing on EVERY call is not reinstating
            // the cache: nothing ever reads a value this prefix did not just write
            // on this same call, and the value came from vanilla's own resolution a
            // few microseconds earlier. The write stays on the accepting branch, and
            // the return comes from the seam, so both prefixes on a shared method
            // answer Harmony through one tested function (#432).
            if (action == ProximityPrefixAction.WriteVictimAndRun) __instance.target = fresh;
            return ProximityVictim.PrefixReturn(action);
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
    /// therefore finds no ring on every real call and the prefix leaves vanilla
    /// untouched.
    ///
    /// It is kept deliberately. The census bounds today's CONTENT, not the code: the
    /// cache defect is in StunPlayer.Go itself, so the day a card puts this component
    /// under a ring the repair is already in place, and until then the cost is one
    /// attach signal and a branch that returns true.
    ///
    /// PerfPatches.StunPlayerGoNullGuard is a separate Prefix on the same method
    /// and neither declares a priority, so their ORDER IS UNDEFINED. What that
    /// order can and cannot reach is two different questions.
    ///
    /// It cannot change whether the original runs. THIS prefix returns true on
    /// every path - ProximityVictim.VictimAction has no refusing value - so it
    /// contributes the identity element to any conjunction and cannot turn the
    /// guard's refusal into an application. The composition itself is read from the
    /// shipped 0Harmony.dll rather than assumed, and the bound that holds without
    /// it is stated, on ProximityVictim.RunOriginalAfter. Harness case P3 composes
    /// that fold in BOTH orders over the two SHIPPED decision functions - this
    /// one's and the null guard's, which now lives in the seam as
    /// ProximityVictim.NullGuardAction - rather than over a boolean the test
    /// supplies itself.
    ///
    /// What the order could still reach is a SIDE EFFECT one prefix leaves for the
    /// other to read. This one writes __instance.target, and only on the accepting
    /// path; the null guard reads the ancestor Player and writes nothing. So today
    /// there is no shared state to order. That is a statement about today's two
    /// bodies rather than a property of the arrangement, and it is recorded as a
    /// residual: nothing in the tree stops a later edit from making either prefix
    /// read the field the other writes. The consequence to watch for is a stun
    /// applied to, or withheld from, a player the ring did not match.</summary>
    [HarmonyPatch(typeof(StunPlayer), "Go")]
    internal static class StunPlayerFreshVictimPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGo(StunPlayer __instance)
        {
            Player fresh;
            ProximityPrefixAction action = ProximityVictimResolver.DecidePrefix(
                "StunPlayer", __instance,
                __instance != null && __instance.targetPlayer == StunPlayer.TargetPlayer.OtherPlayer,
                out fresh);
            if (action == ProximityPrefixAction.WriteVictimAndRun) __instance.target = fresh;
            return ProximityVictim.PrefixReturn(action);
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
    /// StageInto states it once per session, and the substring to grep a session
    /// log for is " patches live); this seat stays on vanilla for the session".
    /// That sentence is the one StageInto actually builds; harness case W19 holds
    /// this quote and that log expression to the same text, because a comment that
    /// quotes a deleted message sends the next maintainer looking for a line no
    /// build can emit and the absence then reads as "nothing is wrong" (#306).
    /// Re-pin the census after any ROUNDS update, and if this class is gone, delete
    /// this patch and drop RequiredAttachments to 2 rather than leaving the repair
    /// inert.</summary>
    [HarmonyPatch(typeof(TeleportToOpponent), "Go")]
    internal static class TeleportToOpponentFreshVictimPatch
    {
        [HarmonyPrefix]
        private static bool BeforeGo(TeleportToOpponent __instance)
        {
            Player fresh;
            ProximityPrefixAction action = ProximityVictimResolver.DecidePrefix(
                "TeleportToOpponent", __instance, true, out fresh);
            if (action == ProximityPrefixAction.WriteVictimAndRun) __instance.target = fresh;
            return ProximityVictim.PrefixReturn(action);
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
