using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Bug 389 - the PURE half of the proximity-victim repair.
    ///
    /// References nothing from Unity, Harmony or Photon, so the victim choice and
    /// the capability gate can be compiled and EXECUTED by a plain console harness
    /// (#340/#465). ProximityVictimPatches.cs marshals real players into these
    /// structs and calls in here, so the shipped path IS the tested path - a seam
    /// that only the tests use would prove nothing about what runs in a match.
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
    /// the vanilla function each branch reproduces; keep them separate.</summary>
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

        /// <summary>data.dead, and true also for a candidate whose Player or
        /// CharacterData could not be read. Which branches consult it differs by
        /// mode and is part of the fidelity - see Choose.</summary>
        public bool Dead;
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

        /// <summary>Bound on refusal diagnostics, so a contradiction that repeats
        /// every tick cannot flood the log.</summary>
        internal const int MaxRefusalDiagnostics = 8;

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

        /// <summary>Planar squared distance, for the SELECTION only. All three
        /// vanilla selectors are Vector2.Distance (PlayerManager.cs:71 and :115,
        /// FfaMode.cs:3815), so a planar measure is the faithful one here.</summary>
        private static float DistanceSquared(float ax, float ay, float bx, float by)
        {
            float dx = ax - bx;
            float dy = ay - by;
            return (dx * dx) + (dy * dy);
        }

        /// <summary>Squared distance in THREE dimensions, for the PREDICATE.
        /// PlayerInRangeTrigger.cs:67 is a Vector3.Distance, so the range test
        /// follows it into three dimensions. Planar distance is less than or equal
        /// to its 3D counterpart, so a planar range test admits every candidate
        /// vanilla admits AND some it rejects. For a repair whose whole purpose is
        /// to change which player takes the damage, widening the set is the failure
        /// direction that costs another player the match (#276/#430).</summary>
        private static float DistanceSquared3D(float ax, float ay, float az, float bx, float by, float bz)
        {
            float dx = ax - bx;
            float dy = ay - by;
            float dz = az - bz;
            return (dx * dx) + (dy * dy) + (dz * dz);
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
        /// candidate vanilla selected. That is why each branch below reproduces one
        /// named vanilla selector exactly, including a mis-indexed liveness test
        /// that a "tidier" loop would quietly repair. Change a branch so that it
        /// selects a different player and the relaxation argument no longer holds:
        /// a None would then mean nothing worse than "our candidate failed a test
        /// vanilla's candidate passed", and the caller's refusal - and the refusal
        /// diagnostic that names it a contradiction - would both be wrong (#351).
        ///
        /// SELECTION and PREDICATE measure different things, and each is matched to
        /// the vanilla call it reproduces: the selection is planar, against the
        /// position the corresponding vanilla selector reads; the predicate is 3D,
        /// against transform.position, because :67 is a Vector3.Distance. Do not
        /// unify them - the two mismatches point in opposite directions and one of
        /// them widens the card.</summary>
        internal static int Choose(
            IList<ProximityCandidate> candidates,
            int holderId,
            int holderTeam,
            ProximitySelection selection,
            float selectX, float selectY,
            float triggerX, float triggerY, float triggerZ,
            float effectiveRange,
            Func<int, bool> canSee)
        {
            if (candidates == null || candidates.Count == 0) return None;

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

                    // The mis-indexed gate, read positionally from the roster. A
                    // candidate we could not read is marked Dead, so an entry
                    // vanilla would have thrown on closes the gate here instead -
                    // the narrow direction, and the trigger cannot have fired off a
                    // throwing Update in any case.
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
            // from - and in three dimensions, against transform.position, because
            // that is what vanilla's Vector3.Distance does.
            if (effectiveRange <= 0f) return None;
            float rangeSquared = effectiveRange * effectiveRange;
            if (DistanceSquared3D(triggerX, triggerY, triggerZ, chosen.X, chosen.Y, chosen.Z) >= rangeSquared) return None;
            if (canSee != null && !canSee(chosen.Id)) return None;
            if (chosen.Dead) return None;

            return chosen.Id;
        }
    }
}
