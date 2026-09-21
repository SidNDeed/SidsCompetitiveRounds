using System;

namespace CompetitiveRounds
{
    /// <summary>Bug 389 - the PURE half of the proximity-victim repair.
    ///
    /// References nothing from Unity, Harmony or Photon, so the gate, its cache
    /// key, the prefix decision and the outcome signals can be compiled and
    /// EXECUTED by a plain console harness (#340/#465). ProximityVictimPatches.cs
    /// calls in here, so the shipped path IS the tested path - a seam that only
    /// the tests use would prove nothing about what runs in a match.
    ///
    /// WHAT THE DEFECT IS, AND WHERE IT IS NOT. Vanilla PlayerInRangeTrigger
    /// .Update re-evaluates who is nearby every frame and then invokes a
    /// parameterless UnityEvent (PlayerInRangeTrigger.cs:49-78), which cannot hand
    /// the effect the player it just matched. The effect therefore resolves its own
    /// victim - and caches it in a private field it never re-derives:
    /// `if (!target) { ... target = PlayerManager.instance.GetOtherPlayer(target); }`
    /// (DealDamageToPlayer.cs:31-40, StunPlayer.cs:17-26,
    /// TeleportToOpponent.cs:17-22). The defect is that `if`, not the ranking
    /// behind it.
    ///
    /// SO THIS SEAM AUTHORS NO SELECTION SEMANTICS. It does not rank, compare,
    /// marshal a roster or reproduce a predicate. It decides only WHEN the
    /// effect's own resolution is allowed to run again; the victim comes from
    /// calling the very method the effect's own body calls, so vanilla IL does the
    /// ranking, the reads and the throwing. A prefix that samples the fields the
    /// original is about to read is measuring a PREDICTION (#510), and three
    /// rounds of narrowing that prediction produced three more cases of it. When
    /// the deleted mechanisms outnumber the surviving ones the model is wrong
    /// (#310/#389/#473).
    ///
    /// WHAT WAS DELETED AND WHAT REPLACED IT, so the tally is not a silent drop:
    /// the squared candidate ranking, the three-dimensional predicate, the roster
    /// marshalling and its unreadable-entry flag, the per-mode selection enum, the
    /// FFA branch, the vision tri-state and the Refuse outcome are all GONE,
    /// replaced by one call into PlayerManager.GetOtherPlayer made by the
    /// marshalling half. Nothing here is left unreachable: a branch no case can
    /// assert is decoration (#342/#431).</summary>

    /// <summary>What a prefix on one of these methods does. Three values because
    /// two prefixes with different jobs answer Harmony through this one shape
    /// (#432): the victim repair, which may never suppress anything, and
    /// PerfPatches.StunPlayerGoNullGuard, whose whole job is to suppress.</summary>
    internal enum ProximityPrefixAction
    {
        /// <summary>Return true without touching anything.</summary>
        RunVanillaUntouched,

        /// <summary>Write the resolved victim into vanilla's own field, then
        /// return true so vanilla runs with it.</summary>
        WriteVictimAndRun,

        /// <summary>Return false, so the original does not run. NOT reachable from
        /// the victim repair - see VictimAction - and reached only by the sibling
        /// null guard, whose ancestor Player is missing.</summary>
        SkipOriginal
    }

    /// <summary>Whether this seat is in a position to repair the victim, and when
    /// it is not, WHICH of the reasons applies.
    ///
    /// A BOOLEAN HERE MEANS FIVE DIFFERENT THINGS AT ONCE (#430). The gate answers
    /// no when the mod is switched off, when this seat's own prefixes did not
    /// attach, when there is no room to take a census of, when a fighter in the
    /// room does not advertise the repair, and when the census itself could not be
    /// read. "The room does not all carry the repair" is a true statement about
    /// exactly one of those; printed for the other four it points the reader at
    /// the peers' builds while the cause is local, or at a room that does not
    /// exist. One value per cause, one reason line each, so this gate never has to
    /// say both "the room said no" and "we declined locally".</summary>
    internal enum ProximityGateState
    {
        /// <summary>Every seat in the room that simulates these effects advertises
        /// the repair - or there are no peers at all (offline play).</summary>
        Capable,

        /// <summary>The mod is switched off on this seat.</summary>
        ModDisabled,

        /// <summary>This seat's own Harmony prefixes are not all attached, so it
        /// cannot perform the repair - and does not advertise it (#83).</summary>
        PatchesNotAttached,

        /// <summary>Not in a Photon room, so there is no roster to take a census
        /// of. The main menu and every pre-join state land here.</summary>
        NotInARoom,

        /// <summary>The census ran and found a fighter that does not advertise the
        /// capability. This is the one state that IS about the peers.</summary>
        RoomNotAllCapable,

        /// <summary>The census could not be taken - a Photon or roster read threw.
        /// An unreadable input, not an answer.</summary>
        CensusUnreadable
    }

    internal static class ProximityVictim
    {
        /// <summary>Bound on the once-per-reason outcome signals below. One line
        /// is the whole point: a second one carries no information the first did
        /// not, and this runs inside a per-tick effect.</summary>
        internal const int MaxOutcomeSignals = 1;

        /// <summary>Capability key. The KEY carries the protocol version: any later
        /// SEMANTIC change to who this repair chooses takes cr_prox2, because a
        /// client advertising cr_prox1 has answered a different question. Same
        /// family and same pre-join discipline as cr_pois2 / cr_msv2.
        ///
        /// Round 3 did NOT take a new key, and the reason is NOT that the two
        /// builds choose alike. They do not. Round 2 ranked the candidates with a
        /// selector of its own and deferred entirely on an Any-target ring, where
        /// this build re-runs PlayerManager.GetOtherPlayer unconditionally; a room
        /// holding one seat of each could drain different players on different
        /// screens. Measured against the rule above, that is a cr_prox2 change.
        ///
        /// What makes cr_prox1 correct here is narrower and checkable: no
        /// released build advertises it at all. The key is absent from the base
        /// release v1.40.3 and from every earlier tag - it exists only on the
        /// unreleased tips of this branch, none of which reached a player - so
        /// there is no cr_prox1 population for a census to be wrong about. The
        /// rotation rule binds from the FIRST RELEASE that ships the key onward,
        /// and this paragraph is the last point at which it can be waived.
        /// Harness case K3 holds the argument to that fact, and the runner checks
        /// the absence at the base tag against a key that did ship.
        ///
        /// It lives in the pure half because three different places have to agree
        /// on it - the staging call, the census, and the spectator staging that
        /// must stop advertising it - and a key that three files spell for
        /// themselves is a key that can drift.</summary>
        internal const string CapabilityProp = "cr_prox1";
        internal const int CapabilityValue = 1;

        /// <summary>The capability keys that describe a FIGHTER and must therefore
        /// be cleared when a seat stages as a spectator.
        ///
        /// Photon player properties persist across rooms (#182), so a seat that
        /// fought a match and then joins one to watch still carries whatever it
        /// last advertised. A spectator does not simulate these effects and is not
        /// counted by the census, so a key left behind describes a role the actor
        /// is not filling. SpectatorSession.StagePreJoinProperties nulls every key
        /// in this array in the same pre-join merge that sets the role, beside the
        /// fighter-only keys it already cleared.</summary>
        internal static readonly string[] FighterCapabilityKeys = new string[] { CapabilityProp };

        /// <summary>Root of the bounded-diagnostic budget keys.</summary>
        internal const string DiagKeyRoot = "ProximityVictim389";

        /// <summary>The budget key a single outcome signal is charged to.
        ///
        /// THE SITE IS DELIBERATELY NOT IN THE KEY. Outcome and reason are, and
        /// nothing else, so each distinct reason is stated ONCE PER SESSION however
        /// many effects meet it. With the site in the key, "the room does not all
        /// carry the repair" - one fact about one room - was charged to three
        /// separate budgets and could print three times; the same held for every
        /// local cause, none of which is a statement about the effect that happened
        /// to reach it first. The LINE still names the site (see SignalText), so the
        /// reader loses nothing: the first effect to meet a reason reports it, and
        /// the reason is what the reader acts on.
        ///
        /// Charged against MaxOutcomeSignals, so a per-tick effect can never repeat
        /// itself. The separation it must preserve is between an INACTIVE feature
        /// and an active one with nothing to do: those have different reasons, so
        /// they have different keys and both get their line (#438/#443).</summary>
        internal static string SignalKey(string outcome, string reason)
        {
            return DiagKeyRoot + "/" + outcome + "/" + reason;
        }

        /// <summary>The line itself. Reads as a sentence in the log and names the
        /// three things a reader needs: which effect, what this seam did, and
        /// why.</summary>
        internal static string SignalText(string site, string outcome, string reason)
        {
            return "[PROX-TARGET] " + outcome + " site=" + site + " why=" + reason;
        }

        /// <summary>The capability gate, as a pure predicate so the inert case is
        /// testable.
        ///
        /// state: what this seat's census concluded. Capable means EVERY seat in
        /// the room that can simulate this effect advertises a build carrying this
        /// repair, or that there are no peers at all. This changes who takes damage
        /// in a shared simulation, so it is whole-room or nothing - never a room-name
        /// prefix (#286: the prefix set misses most rated play) and never
        /// mod_version (#301: a locally built DLL reports the last shipped version,
        /// so it lies on exactly the seat that tests it). Every other state refuses,
        /// and each of them names its own cause - see ProximityGateState.
        ///
        /// targetsOther: the effect's own rule resolves a player OTHER than its
        /// holder. The own-player branch caches data.player (DealDamageToPlayer
        /// .cs:35) without ever calling GetOtherPlayer, so re-running that
        /// resolution would hand back the player it already holds - nothing to
        /// repair, and no reason to walk the room census on every tick for it.
        ///
        /// Both false-directions fall through to vanilla unchanged, which preserves
        /// today's behaviour rather than inventing a third one (#276/#430).</summary>
        internal static bool ShouldRepair(ProximityGateState state, bool targetsOther)
        {
            return state == ProximityGateState.Capable && targetsOther;
        }

        /// <summary>THE WHOLE PREFIX DECISION FOR THE VICTIM REPAIR, in one pure
        /// function, for all three effects (#432).
        ///
        /// EVERY TERM IS A FACT ALREADY IN HAND, never a prediction about what the
        /// original is going to do (#510):
        ///   gate            - what this seat's census concluded.
        ///   targetsOther    - the effect's own rule acts on someone else.
        ///   ringDriven      - a PlayerInRangeTrigger owns this call. The defect is
        ///                     a field that survives REPEATED invocation, and only a
        ///                     ring invokes these effects repeatedly; an
        ///                     AttackTrigger or a DelayEvent has its own rule that
        ///                     this repair does not model, so it keeps vanilla's.
        ///   vanillaAnswered - the call into PlayerManager.GetOtherPlayer returned a
        ///                     usable player. NOT "we think it would": the caller
        ///                     has already made that call and reports its result.
        ///
        /// THERE IS NO REFUSING ANSWER HERE, and that is the point. Every path that
        /// is not a repair returns RunVanillaUntouched, so this prefix cannot
        /// suppress a tick vanilla applies - it cannot suppress anything at all.
        /// The previous seam re-derived vanilla's own predicate and returned false
        /// when its re-derivation disagreed; that was the only route by which a
        /// repair meant to change WHO takes damage could change WHETHER anyone
        /// does. Deleting the predicate deletes the route (#276/#430).</summary>
        internal static ProximityPrefixAction VictimAction(
            ProximityGateState gate, bool targetsOther, bool ringDriven, bool vanillaAnswered)
        {
            if (!ShouldRepair(gate, targetsOther)) return ProximityPrefixAction.RunVanillaUntouched;
            if (!ringDriven) return ProximityPrefixAction.RunVanillaUntouched;
            if (!vanillaAnswered) return ProximityPrefixAction.RunVanillaUntouched;
            return ProximityPrefixAction.WriteVictimAndRun;
        }

        /// <summary>Why a call was left to vanilla, in the order VictimAction
        /// decides them, so a line can never name a cause the decision did not
        /// reach.
        ///
        /// The polarity is first because it is the permanent answer: an own-player
        /// effect is never repaired whatever the room does, and saying anything
        /// about the room for it would be a statement the reader cannot act on.
        /// Then the gate's own state, then the two facts about this call.</summary>
        internal static string DeclineReason(
            ProximityGateState gate, bool targetsOther, bool ringDriven, bool vanillaAnswered)
        {
            if (!targetsOther) return "the effect targets its own player";
            if (gate != ProximityGateState.Capable) return GateReason(gate);
            if (!ringDriven) return "no proximity ring drives this call";
            if (!vanillaAnswered) return "the game's own targeting answered with nobody";
            return "the repair is active";
        }

        /// <summary>The reason line for an inactive call, from the gate alone. Kept
        /// separate from DeclineReason because the marshalling half asks the gate
        /// BEFORE it does any work: on an own-player or non-Capable call it never
        /// walks for a ring and never makes the vanilla call, so those two terms
        /// are not yet facts and DeclineReason may not be asked about them.</summary>
        internal static string InactiveReason(ProximityGateState state, bool targetsOther)
        {
            if (!targetsOther) return "the effect targets its own player";
            return GateReason(state);
        }

        /// <summary>One line per gate state. They must stay DISTINCT: the line is
        /// also the budget key (see SignalKey), so two states sharing a line means
        /// the second cause is never printed at all, and the reader is told the
        /// first one instead.</summary>
        internal static string GateReason(ProximityGateState state)
        {
            switch (state)
            {
                case ProximityGateState.Capable: return "the repair is active";
                case ProximityGateState.ModDisabled: return "the mod is disabled on this seat";
                case ProximityGateState.PatchesNotAttached: return "this seat's repair patches are not attached";
                case ProximityGateState.NotInARoom: return "this seat is not in a room";
                case ProximityGateState.RoomNotAllCapable: return "the room does not all carry the repair";
                case ProximityGateState.CensusUnreadable: return "the room census could not be read";
                default: return "the gate state is not one this build names";
            }
        }

        /// <summary>The sibling prefix on StunPlayer.Go, as a pure function.
        ///
        /// PerfPatches.StunPlayerGoNullGuard exists because vanilla's StunPlayer.Go
        /// walks GetComponentInParent&lt;Player&gt;() and dereferences it with no
        /// null check, so a player destroyed between the stun being queued and Go()
        /// running produces an exception every frame the coroutine ticks. Its
        /// decision lives here, behind the same shape the victim repair uses, for
        /// two reasons. Both prefixes on that one method then answer Harmony
        /// through ONE function (#432) rather than one of them returning a bare
        /// bool. And the ordering case below can compose the SHIPPED sibling
        /// decision instead of a boolean the test supplies itself, which is the
        /// difference between a test of the arrangement and a test of the test
        /// (#441/#431).
        ///
        /// guardEnabled: the perf gate for this fix is on. Off, the guard declines
        /// to act at all and vanilla runs exactly as it would unpatched.</summary>
        internal static ProximityPrefixAction NullGuardAction(
            bool guardEnabled, bool instancePresent, bool ancestorPresent)
        {
            if (!guardEnabled) return ProximityPrefixAction.RunVanillaUntouched;
            if (instancePresent && ancestorPresent) return ProximityPrefixAction.RunVanillaUntouched;
            return ProximityPrefixAction.SkipOriginal;
        }

        /// <summary>What a prefix hands back to Harmony for a given action. One
        /// function, so the two prefixes on StunPlayer.Go cannot drift apart on it -
        /// and so the ordering claim below is composed from the SAME function both
        /// shipped bodies return through, rather than from a restatement of
        /// it.</summary>
        internal static bool PrefixReturn(ProximityPrefixAction action)
        {
            return action != ProximityPrefixAction.SkipOriginal;
        }

        /// <summary>HarmonyX's composition of prefix returns, SOURCED rather than
        /// assumed.
        ///
        /// Read from the shipped BepInEx/core/0Harmony.dll, FileVersion 2.9.0.0,
        /// sha256 1A21CC03...C1031, decompiled: HarmonyLib.Public.Patching
        /// .HarmonyManipulator.WritePrefixes initialises __runOriginal to true
        /// (Ldc_I4_1, Stloc), then walks `foreach (PatchContext prefix in prefixes)`
        /// emitting a Call to EVERY prefix with no branch around it, folding each
        /// bool return in with `Ldloc __runOriginal; And; Stloc __runOriginal`, and
        /// only AFTER the loop tests the accumulated value (`Ldloc; Brfalse`) to
        /// skip the original. Both halves of the claim are in the emitted IL: every
        /// prefix runs whatever a sibling returned, and the returns are ANDed. Same
        /// finding as #352, which reached it from the other direction - a
        /// `return false` that failed to gate a sibling in production.
        ///
        /// This is a MODEL of that fold, not a call the shipped prefixes make;
        /// Harmony performs the conjunction itself. It lives here so the ordering
        /// claim on StunPlayer.Go - which carries two prefixes with no priority
        /// declared on either - can be MEASURED over the two real decision
        /// functions. Make it return `prefixReturn` alone, last prefix wins, and
        /// the two orders disagree, which is what P3 asserts.
        ///
        /// WHAT THIS CANNOT PROVE, and what carries it instead. That the decompiled
        /// emitter is the code path this game build actually takes is a claim about
        /// a running process, and only the game can answer it (#83/#405).
        ///
        /// The bound that does NOT depend on it is scoped to the two methods this
        /// repair patches ALONE - DealDamageToPlayer.Go and TeleportToOpponent.Go.
        /// There this is the only prefix, it returns true on every path (V5), and
        /// the worst a foreign fold could do is fail to run it: the repair goes
        /// inert and the seat keeps vanilla, which is today's shipped behaviour.
        ///
        /// StunPlayer.Go is NOT covered by that bound, and the wording this
        /// paragraph used to carry - "any composition" - was wrong about it. That
        /// method also carries PerfPatches.StunPlayerGoNullGuard, whose whole job
        /// is to answer false when the ancestor Player is gone. An unconditional
        /// true is the identity element of a CONJUNCTION and of nothing else: fold
        /// the answers some other way, with this prefix last, and the guard's
        /// refusal is lost, vanilla dereferences the missing ancestor, and the
        /// seat is left WORSE than today rather than equal to it. Harness case P5
        /// measures both halves - that the conjunction preserves the refusal, and
        /// that the two shipped prefixes really do disagree somewhere, which is
        /// what makes the scoping matter. On that one method the claim therefore
        /// rests on the conjunction being real: read from the shipped 0Harmony.dll
        /// above, matched by #352, which reached the same fold from a production
        /// failure. The witness carries the rest.</summary>
        internal static bool RunOriginalAfter(bool runSoFar, bool prefixReturn)
        {
            return runSoFar && prefixReturn;
        }
    }

    /// <summary>The capability census answer, cached under a key that moves
    /// whenever the answer can.
    ///
    /// The frame alone is NOT that key. A census taken early in a frame can be
    /// overtaken inside the same frame by an actor joining, an actor leaving, or a
    /// property delivery, and one PUN Dispatch can drain several of those with no
    /// frame boundary between them. A cached TRUE that survives such a change says
    /// "every seat in this room carries the repair" about a room that has since
    /// changed - and this gate decides whether seats re-resolve the victim, so two
    /// seats disagreeing on it is the same drain tick debiting different players
    /// on different screens. A cached FALSE that survives one costs a tick of
    /// vanilla, which is today's shipped behaviour.
    ///
    /// So the key is the frame AND a change stamp the caller derives from the
    /// room callbacks. Both terms are required: the stamp catches a same-frame
    /// change, and the frame bounds any change the stamp's callback set does not
    /// name to a single frame. There is no separate invalidation call, because
    /// there is no edge that would need one: the room teardown and the room
    /// change move the stamp themselves (RoomActors.Reset and EnsureCacheRoom),
    /// so an answer cached in one room cannot be read in another.</summary>
    internal sealed class ProximityCapabilityCache
    {
        private bool _has;
        private int _frame;
        private long _stamp;
        private bool _value;

        /// <summary>Re-derive unless BOTH key terms are unchanged.</summary>
        internal bool Evaluate(int frame, long stamp, Func<bool> census)
        {
            if (census == null) return false;
            if (_has && frame == _frame && stamp == _stamp) return _value;
            bool value = census();
            _has = true;
            _frame = frame;
            _stamp = stamp;
            _value = value;
            return value;
        }
    }
}
