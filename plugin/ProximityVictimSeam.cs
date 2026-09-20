using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Bug 389 - the PURE half of the proximity-victim repair.
    ///
    /// References nothing from Unity, Harmony or Photon, so the victim choice,
    /// the capability gate, its cache key and the outcome signals can be compiled
    /// and EXECUTED by a plain console harness (#340/#465).
    /// ProximityVictimPatches.cs marshals real players into these structs and
    /// calls in here, so the shipped path IS the tested path - a seam that only
    /// the tests use would prove nothing about what runs in a match.
    ///
    /// WHAT IT REPRODUCES. Vanilla PlayerInRangeTrigger.Update re-evaluates who is
    /// nearby every frame (PlayerInRangeTrigger.cs:58-67) and then invokes a
    /// parameterless UnityEvent, which cannot hand the effect the player it just
    /// matched. DealDamageToPlayer.Go therefore resolves its own victim, once, and
    /// keeps it (DealDamageToPlayer.cs:24,33-40). With more than one opponent the
    /// two halves disagree by construction.
    ///
    /// The rule is taken from the trigger's INPUTS - targetType, ownPlayer, range,
    /// transform - never from its OUTPUT fields. UnityEvent.Invoke() is
    /// synchronous, so Go() runs inside PlayerInRangeTrigger.cs:70, after the clear
    /// at :52-53 and before the assignment at :71-72: inside Go(), trigger.target
    /// is always null and trigger.inRange is always false. A design or a gate
    /// written on those fields reads cleared state and cannot fail (#342).
    ///
    /// ONE SELECTION RULE PER MODE, because vanilla has more than one. The trigger's
    /// OtherPlayer branch calls PlayerManager.GetOtherPlayer, and this mod prefixes
    /// that method in FFA only (FfaMode.cs:3752-3763, gated on EngineActive()). So
    /// the function the trigger actually evaluated is FfaTargeting.NearestOpponent
    /// in FFA and the stock PlayerManager.GetClosestPlayerInTeam in 2v2, 1v2, 1v1
    /// and offline play - and those two do NOT agree. Reproducing one of them in
    /// both modes makes the seam choose a player the trigger could not have chosen,
    /// which is the whole failure this seam exists to avoid. The enum below names
    /// the vanilla function each branch reproduces; keep them separate.
    ///
    /// AN INPUT THE SEAM COULD NOT READ IS NOT AN INPUT. Every field marshalled
    /// here is one the vanilla rule reads, so a field that cannot be read leaves
    /// the seam unable to show that its candidate set is the set vanilla built.
    /// The answer is then Defer - vanilla resolves its own victim, exactly as an
    /// unpatched build would - and never a partial set, a default team or a
    /// guess. That is a BOUND rather than a per-branch mechanism (#310): it costs
    /// one deferred tick, which is today's shipped behaviour and no new symptom,
    /// and it cannot be defeated by a later branch reading a field this one did
    /// not think about.</summary>
    internal struct ProximityCandidate
    {
        /// <summary>Caller-assigned identity, and LOAD-BEARING: it must be the
        /// candidate's index into PlayerManager.instance.players, and the list
        /// handed to Choose must be the COMPLETE roster in roster order.
        ///
        /// The NearestEnemyTeam branch reproduces a vanilla loop that reads the
        /// global roster positionally (PlayerManager.cs:113), so a filtered,
        /// reordered or re-numbered list silently changes which candidate that loop
        /// admits. ProximityVictimResolver builds the list that way; a future caller
        /// that does not must not use that branch.</summary>
        public int Id;

        /// <summary>TeamID. In FFA every player is their own team, so an
        /// own-team exclusion collapses to a self exclusion; in 2v2 and 1v2 it
        /// names the friendly team, which the enemy-team branch excludes by
        /// selecting GetOtherTeam(holderTeam) instead.</summary>
        public int Team;

        /// <summary>transform.position. Used by BOTH enemy SELECTION branches -
        /// GetClosestPlayerInTeam measures it (PlayerManager.cs:115) and so does
        /// FfaTargeting.NearestOpponent (FfaMode.cs:3815) - and by the PREDICATE,
        /// which is what PlayerInRangeTrigger.cs:67 measures.</summary>
        public float X;
        public float Y;

        /// <summary>transform.position.z. The predicate is a Vector3.Distance in
        /// vanilla, so z is part of it. Dropping z can only SHORTEN the measured
        /// distance, which admits candidates vanilla's own predicate rejects -
        /// the one direction a repair that changes who takes damage must not move
        /// in.</summary>
        public float Z;

        /// <summary>data.playerVel.position. Vanilla's GetClosestPlayer measures
        /// the NearestAny selection against THIS and not against transform.position
        /// (PlayerManager.cs:71). The two differ: playerVel is the rigidbody the
        /// movement code drives. Keeping both means each vanilla path is
        /// reproduced against the position vanilla actually used, rather than
        /// against one position chosen for convenience.</summary>
        public float AnyX;
        public float AnyY;

        /// <summary>data.dead. Which branches consult it differs by mode and is
        /// part of the fidelity - see Choose.</summary>
        public bool Dead;

        /// <summary>At least one field above could not be read from this roster
        /// entry - a destroyed Player, a missing CharacterData, a missing
        /// rigidbody, or a property access that threw.
        ///
        /// It is a FLAG rather than an omission on purpose. The roster handed to
        /// Choose must keep its length and its order, because the NearestEnemyTeam
        /// branch indexes it positionally; dropping the entry would renumber every
        /// later one. Choose refuses the whole resolution when any entry carries
        /// this, so the unread Team, X, Y, Z, AnyX, AnyY and Dead of such an entry
        /// are never consulted - which is what stops a default team of zero from
        /// deciding who the enemy subset contains.</summary>
        public bool Unreadable;
    }

    /// <summary>Each value names the ONE vanilla function it reproduces. The
    /// mapping from a trigger to a value is made by the marshalling half, which is
    /// the only place that can see whether the FFA engine is driving the room.</summary>
    internal enum ProximitySelection
    {
        /// <summary>PlayerManager.GetClosestPlayerInTeam (PlayerManager.cs:106-124),
        /// reached through GetOtherPlayer (:58-61) whenever FfaMode.EngineActive()
        /// is false - i.e. 2v2, 1v2, 1v1 and offline. Measured from the HOLDER's
        /// transform.position against each enemy's transform.position.</summary>
        NearestEnemyTeam,

        /// <summary>FfaTargeting.NearestOpponent (FfaMode.cs:3805-3826), which this
        /// mod substitutes for GetOtherPlayer while the FFA engine is active
        /// (FfaMode.cs:3752-3763). Measured from the HOLDER's transform.position
        /// against each candidate's transform.position.</summary>
        NearestEnemyFfa,

        /// <summary>PlayerManager.GetClosestPlayer (PlayerManager.cs:63-78) -
        /// PlayerInRangeTrigger.cs:65. Measured from the TRIGGER's position against
        /// each candidate's data.playerVel.position, and vanilla excludes nobody
        /// here: it skips only the dead. The repair must not quietly narrow that.
        /// No FFA substitution exists for this one.</summary>
        NearestAny
    }

    /// <summary>The vision term of vanilla's predicate, with the case vanilla does
    /// not have: the answer could not be obtained. PlayerManager.CanSeePlayer is a
    /// live scene query, so "it threw" is a different fact from "it said no", and
    /// folding the two together would turn an unreadable input into a suppressed
    /// tick. See Choose for which outcome each one produces.</summary>
    internal enum ProximityVision
    {
        /// <summary>CanSeePlayer(...).canSee was true.</summary>
        Visible,

        /// <summary>CanSeePlayer(...).canSee was false - vanilla's own predicate
        /// rejects this candidate.</summary>
        Blocked,

        /// <summary>The query could not be answered.</summary>
        Unreadable
    }

    /// <summary>What the resolver concluded. Three outcomes, because two would
    /// force a genuinely different case into one of the others: Refuse means the
    /// trigger's own rule admitted nobody and nothing should be applied, while
    /// Defer means this seam has no standing to answer and an unpatched build's
    /// behaviour is the correct one. Folding Defer into Refuse would drop ticks
    /// vanilla applies; folding it into Victim would require inventing a victim.</summary>
    internal enum ProximityResolution
    {
        /// <summary>A victim was resolved and is handed back.</summary>
        Victim,

        /// <summary>The trigger's own rule admits nobody - a contradiction on a
        /// trigger-driven call, so the effect applies nothing and says so.</summary>
        Refuse,

        /// <summary>Not this seam's question: run vanilla untouched.</summary>
        Defer
    }

    /// <summary>What a prefix does with a resolution. Named as an action rather
    /// than left as three copies of an if-ladder because all three prefixes must
    /// take the SAME action for the same resolution (#432), and because the
    /// relationship between "wrote vanilla's field" and "let the original run" is
    /// the half of the sibling-ordering claim that can be tested here - see
    /// PrefixAction.</summary>
    internal enum ProximityPrefixAction
    {
        /// <summary>Return true without touching anything.</summary>
        RunVanillaUntouched,

        /// <summary>Write the resolved victim into vanilla's own field, then
        /// return true so vanilla runs with it.</summary>
        WriteVictimAndRun,

        /// <summary>Return false. Nothing is written and nothing is applied.</summary>
        SkipOriginal
    }

    internal static class ProximityVictim
    {
        /// <summary>No victim: the trigger's own rule admits nobody. The repair
        /// refuses rather than guesses.</summary>
        internal const int None = -1;

        /// <summary>Not this seam's question - leave vanilla alone and let it
        /// resolve its own victim. Distinct from None because the two ask the
        /// caller for opposite things: None means "apply nothing", Defer means
        /// "apply exactly what an unpatched build would". Collapsing them would
        /// either drop damage vanilla applies or apply damage it does not.</summary>
        internal const int Defer = -2;

        /// <summary>Positional self-exclusion. This belongs to the FFA rule ONLY:
        /// FfaTargeting.NearestOpponent skips a candidate standing where the lookup
        /// is measured from (FfaMode.cs:3816), on the premise that it is the asker.
        /// Stock GetClosestPlayerInTeam has no such term, so applying it outside FFA
        /// would NARROW the candidate set relative to the set the trigger
        /// evaluated.</summary>
        internal const float SelfEpsilon = 0.01f;

        /// <summary>Bound on the once-per-reason outcome signals below. One line
        /// is the whole point: a second one carries no information the first did
        /// not, and this runs inside a per-tick effect.</summary>
        internal const int MaxOutcomeSignals = 1;

        /// <summary>Capability key. The KEY carries the protocol version: any later
        /// SEMANTIC change to who this repair chooses takes cr_prox2, because a
        /// client advertising cr_prox1 has answered a different question. Same
        /// family and same pre-join discipline as cr_pois2 / cr_msv2.
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

        /// <summary>Root of the bounded-diagnostic budget keys. One root, three
        /// outcomes, one reason each - see SignalKey.</summary>
        internal const string DiagKeyRoot = "ProximityVictim389";

        /// <summary>The budget key a single outcome signal is charged to.
        ///
        /// Site, outcome AND reason are all in the key, so "the room does not all
        /// carry the repair", "this call has no owning trigger", "the roster could
        /// not be read" and "the trigger's own rule admits nobody" each get their
        /// own line. That is the whole requirement: a feature that is INACTIVE and
        /// a feature that is active and declining must not produce the same
        /// silence, or a stale answer reads exactly like a feature with nothing to
        /// do (#438/#443). Charged against MaxOutcomeSignals, so each distinct
        /// reason is stated once per session and never repeats per tick.</summary>
        internal static string SignalKey(string site, string outcome, string reason)
        {
            return DiagKeyRoot + "/" + site + "/" + outcome + "/" + reason;
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
        /// roomCapable: EVERY seat in the room that can simulate this effect
        /// advertises a build carrying this repair. This changes who takes damage in
        /// a shared simulation, so it is whole-room or nothing - never a room-name
        /// prefix (#286: the prefix set misses most rated play) and never
        /// mod_version (#301: a locally built DLL reports the last shipped version,
        /// so it lies on exactly the seat that tests it).
        ///
        /// targetsOther: the effect resolves a player OTHER than its holder. The
        /// own-player branch caches data.player (DealDamageToPlayer.cs:35), which is
        /// not a cross-player lookup and has no defect, so it stays vanilla. Because
        /// this term is required, every call that reaches Choose belongs to an
        /// effect whose own rule is to act on someone other than its holder - which
        /// is why Choose may never answer with the holder.
        ///
        /// Both false-directions fall through to vanilla unchanged, which preserves
        /// today's behaviour rather than inventing a third one (#276/#430).</summary>
        internal static bool ShouldRepair(bool roomCapable, bool targetsOther)
        {
            return roomCapable && targetsOther;
        }

        /// <summary>One resolution, one action, for all three prefixes.
        ///
        /// THE WRITE AND THE RUN ARE THE SAME DECISION. Vanilla's field is written
        /// only by WriteVictimAndRun, which also lets the original run; every
        /// declining action leaves the field exactly as it found it. That matters
        /// beyond tidiness: StunPlayer.Go carries a second, unrelated prefix
        /// (PerfPatches.StunPlayerGoNullGuard) and neither declares a priority, so
        /// their order is undefined. HarmonyX calls EVERY prefix regardless of what
        /// a sibling returned and ANDs the returns into __runOriginal (#352), so
        /// the run decision is a conjunction and is order-independent by
        /// construction; what the order could still expose is a SIDE EFFECT one
        /// prefix leaves behind for the other to read. Keeping the only write on
        /// the accepting path - and asserting it here - closes that half. The
        /// other half is recorded as a residual: nothing in the tree stops a future
        /// edit from making either prefix read the field the other writes.</summary>
        internal static ProximityPrefixAction PrefixAction(ProximityResolution outcome, bool victimKnown)
        {
            if (outcome == ProximityResolution.Defer) return ProximityPrefixAction.RunVanillaUntouched;
            if (outcome != ProximityResolution.Victim || !victimKnown) return ProximityPrefixAction.SkipOriginal;
            return ProximityPrefixAction.WriteVictimAndRun;
        }

        /// <summary>Planar squared distance, for the SELECTION only. All three
        /// vanilla selectors are Vector2.Distance (PlayerManager.cs:71 and :115,
        /// FfaMode.cs:3815) and each is used only to rank candidates against one
        /// another, so squaring is order-preserving there and changes no answer.
        /// The PREDICATE is a different matter - see Distance3D.</summary>
        private static float DistanceSquared(float ax, float ay, float bx, float by)
        {
            float dx = ax - bx;
            float dy = ay - by;
            return (dx * dx) + (dy * dy);
        }

        /// <summary>Distance in THREE dimensions, in the DOMAIN vanilla compares
        /// in. PlayerInRangeTrigger.cs:67 is `Vector3.Distance(...) < range *
        /// root.localScale.x`, and Vector3.Distance is Mathf.Sqrt of the squared
        /// sum, so this is that expression.
        ///
        /// Comparing squares instead is not the same test. Squaring is monotonic in
        /// exact arithmetic but not in float: for a small positive range the
        /// product underflows to zero, and `0 >= 0` then REFUSES a candidate
        /// standing exactly on the trigger while vanilla's `0 < range` arms. A
        /// repair that decides who takes damage has to answer the question vanilla
        /// asked, in vanilla's own domain and with vanilla's own operator, rather
        /// than one that agrees with it almost everywhere.
        ///
        /// Three dimensions, not two: planar distance is less than or equal to its
        /// 3D counterpart, so a planar range test admits every candidate vanilla
        /// admits AND some it rejects - the widening direction, which is the one
        /// that costs another player the match (#276/#430).</summary>
        private static float Distance3D(float ax, float ay, float az, float bx, float by, float bz)
        {
            float dx = ax - bx;
            float dy = ay - by;
            float dz = az - bz;
            return (float)Math.Sqrt((dx * dx) + (dy * dy) + (dz * dz));
        }

        /// <summary>Re-execute the trigger's own selection and its own predicate,
        /// from the trigger's inputs.
        ///
        /// ONE candidate is selected and then tested. If it fails the test the
        /// answer is None - the search does NOT continue to the next-nearest.
        /// Vanilla evaluates exactly one candidate at PlayerInRangeTrigger.cs:59-67
        /// and declines; searching past it would silently widen the card, draining
        /// an opponent that vanilla's own CanSeePlayer excluded.
        ///
        /// WHY A None IS A CONTRADICTION, and what that rests on. The predicate is
        /// vanilla's at :67 minus the `counter >= cooldown` term: vanilla zeroes
        /// counter at :69, one line before the invoke, so that term is unreadable
        /// from inside Go(). Dropping a term only RELAXES the predicate - but a
        /// relaxed predicate only guarantees a pass when it is applied to the SAME
        /// candidate vanilla selected. Two things deliver that premise and both are
        /// below: every branch reproduces one named vanilla selector exactly,
        /// including a mis-indexed liveness test that a "tidier" loop would quietly
        /// repair; and a roster this seam could not read completely is refused
        /// outright rather than selected from, because a candidate set built on a
        /// default team is not the set vanilla built. Break either one and the
        /// relaxation argument no longer holds: a None would then mean nothing
        /// worse than "our candidate failed a test vanilla's candidate passed", and
        /// the caller's refusal - and the refusal diagnostic that names it a
        /// contradiction - would both be wrong (#351).
        ///
        /// SELECTION and PREDICATE measure different things, and each is matched to
        /// the vanilla call it reproduces: the selection is planar and ranks
        /// candidates against the position the corresponding vanilla selector
        /// reads; the predicate is 3D, against transform.position, and is compared
        /// in vanilla's own domain with vanilla's own operator. Do not unify
        /// them.</summary>
        internal static int Choose(
            IList<ProximityCandidate> candidates,
            int holderId,
            int holderTeam,
            ProximitySelection selection,
            float selectX, float selectY,
            float triggerX, float triggerY, float triggerZ,
            float effectiveRange,
            Func<int, ProximityVision> canSee)
        {
            if (candidates == null || candidates.Count == 0) return None;

            // A ROSTER WITH AN UNREADABLE ENTRY IS NOT THE ROSTER VANILLA READ.
            // Vanilla's own loops read players[i].data.dead, the team subset's
            // transform.position and, on the Any path, data.playerVel.position
            // (PlayerManager.cs:69-71, :113-115); an entry whose fields could not
            // be obtained would have thrown there, and cannot be stood in for by
            // defaults. A defaulted Team is the sharpest case: team zero puts the
            // entry into whichever subset the enemy-team branch walks, so ONE
            // unread entry changes which candidates that branch even considers.
            // Deferring costs a vanilla tick and one log line; guessing costs
            // another player the health that left them.
            for (int i = 0; i < candidates.Count; i++)
                if (candidates[i].Unreadable) return Defer;

            // Every caller is an effect whose own rule acts on someone other than
            // its holder (see ShouldRepair). Identifying the holder is therefore a
            // precondition, not a convenience: without it the answer cannot be
            // shown to be someone else, and an unproven answer goes to vanilla
            // rather than into vanilla's field.
            if (holderId == None) return Defer;

            int bestIndex = -1;
            float bestDistanceSquared = float.PositiveInfinity;

            if (selection == ProximitySelection.NearestEnemyTeam)
            {
                // PlayerManager.GetClosestPlayerInTeam, reproduced AS IT IS.
                //
                // Vanilla walks the enemy-team subset but reads its liveness test
                // from the GLOBAL roster at the same ordinal:
                //
                //     playersInTeam = GetPlayersInTeam(team);          // :109
                //     for (i = 0; i < playersInTeam.Length; i++)       // :111
                //         if (!players[i].data.dead)                   // :113  global
                //             d = Distance(position, playersInTeam[i]  // :115  subset
                //                              .transform.position);
                //
                // So the k-th enemy is considered only when the k-th entry of the
                // GLOBAL roster is alive, whoever that is, and a dead enemy IS
                // considered when the k-th global entry happens to be alive. That
                // is not a rule anyone would write, and it is the rule the trigger
                // evaluated; this seam exists to answer with the player the trigger
                // matched, so it reproduces the loop rather than the intent.
                // Writing `!c.Dead` here instead is the whole defect class this
                // branch guards against: it admits enemies the trigger never looked
                // at, and the repair then drains one of them.
                //
                // Team choice is vanilla's too: GetOtherPlayer passes
                // GetOtherTeam(holderTeam), which is 1 for team 0 and 0 for every
                // other team (PlayerManager.cs:339-346) - a specific team, not
                // "anyone not mine".
                int enemyTeam = holderTeam == 0 ? 1 : 0;
                int teamIndex = 0;
                for (int i = 0; i < candidates.Count; i++)
                {
                    ProximityCandidate c = candidates[i];
                    if (c.Team != enemyTeam) continue;

                    // The mis-indexed gate, read positionally from the roster.
                    // Every entry is readable by the time control reaches here, so
                    // this consults the same Dead flag vanilla's :113 consulted.
                    bool gateAlive = teamIndex < candidates.Count && !candidates[teamIndex].Dead;
                    teamIndex++;
                    if (!gateAlive) continue;

                    float d2t = DistanceSquared(selectX, selectY, c.X, c.Y);
                    if (d2t >= bestDistanceSquared) continue;
                    bestDistanceSquared = d2t;
                    bestIndex = i;
                }
            }
            else if (selection == ProximitySelection.NearestEnemyFfa)
            {
                // FfaTargeting.NearestOpponent (FfaMode.cs:3805-3826): skip the
                // dead, skip the asker's own team - which in FFA is the asker alone
                // - and skip anything standing on the lookup position. Order
                // matters only in that the epsilon test precedes the
                // nearest-so-far test, as it does in the original.
                for (int i = 0; i < candidates.Count; i++)
                {
                    ProximityCandidate c = candidates[i];
                    if (c.Dead) continue;
                    if (c.Team == holderTeam) continue;

                    float d2f = DistanceSquared(selectX, selectY, c.X, c.Y);
                    if (d2f < SelfEpsilon * SelfEpsilon) continue;
                    if (d2f >= bestDistanceSquared) continue;
                    bestDistanceSquared = d2f;
                    bestIndex = i;
                }
            }
            else
            {
                // PlayerManager.GetClosestPlayer (PlayerManager.cs:63-78): skip the
                // dead and nobody else, measured against the rigidbody position.
                // No self-exclusion of any kind, positional or by identity - adding
                // one here would narrow a set vanilla leaves open.
                for (int i = 0; i < candidates.Count; i++)
                {
                    ProximityCandidate c = candidates[i];
                    if (c.Dead) continue;

                    float d2a = DistanceSquared(selectX, selectY, c.AnyX, c.AnyY);
                    if (d2a >= bestDistanceSquared) continue;
                    bestDistanceSquared = d2a;
                    bestIndex = i;
                }
            }

            if (bestIndex < 0) return None;

            ProximityCandidate chosen = candidates[bestIndex];

            // THE HOLDER IS NEVER AN ANSWER, and the check is here rather than in
            // the selection because only the NearestAny branch can produce it:
            // that branch is vanilla's own open set, and the trigger sits on the
            // holder's subtree, so the holder is very nearly always the nearest
            // candidate to it. Every caller is an effect that acts on someone
            // other than its holder (ShouldRepair), and writing the holder into
            // such an effect's victim field inverts it - DealDamageToPlayer then
            // drains the holder with data.player as the damaging player, which is
            // self-damage, and LifeSteal does not fire on it (#354).
            //
            // Defer, not None: vanilla's own rule for these effects resolves an
            // opponent (DealDamageToPlayer.cs:33-38), so falling through produces
            // the right polarity, while refusing would drop a tick vanilla applies.
            // The stale-cache defect remains on that path, which is today's
            // behaviour and no new symptom - recorded as a deviation rather than
            // papered over (#327).
            if (chosen.Id == holderId) return Defer;

            // Vanilla's predicate (PlayerInRangeTrigger.cs:67), evaluated from the
            // TRIGGER's position - not from the position the selection was measured
            // from - and in vanilla's own term ORDER: CanSeePlayer first, then the
            // range test, then the dead flag. The order changes no boolean, but it
            // decides WHICH term is reported as the reason, and reporting a term
            // vanilla never reached would be a false statement about the call.
            if (canSee != null)
            {
                ProximityVision sight = canSee(chosen.Id);
                // An unanswerable vision query is an unreadable input, not a
                // negative answer: vanilla would have thrown out of Update rather
                // than declined. Defer hands the call back to vanilla; None would
                // suppress a tick vanilla applies and log it as a contradiction.
                if (sight == ProximityVision.Unreadable) return Defer;
                if (sight != ProximityVision.Visible) return None;
            }
            if (!(Distance3D(triggerX, triggerY, triggerZ, chosen.X, chosen.Y, chosen.Z) < effectiveRange)) return None;
            if (chosen.Dead) return None;

            return chosen.Id;
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
