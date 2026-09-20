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
    /// </summary>
    internal struct ProximityCandidate
    {
        /// <summary>Caller-assigned identity. ProximityVictimPatches uses the index
        /// into PlayerManager.instance.players, so mapping back is exact.</summary>
        public int Id;

        /// <summary>TeamID. In FFA every player is their own team, so an
        /// own-team exclusion collapses to a self exclusion; in 2v2 and 1v2 it
        /// excludes the whole friendly team, which is what vanilla's
        /// GetClosestPlayerInTeam(pos, GetOtherTeam(myTeam)) does.</summary>
        public int Team;

        /// <summary>transform.position. Used by the NearestEnemy SELECTION, which
        /// is what vanilla's GetClosestPlayerInTeam measures
        /// (PlayerManager.cs:115 - Vector2.Distance to playersInTeam[i].transform
        /// .position), and by the PREDICATE, which is what
        /// PlayerInRangeTrigger.cs:67 measures.</summary>
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

        public bool Dead;
    }

    internal enum ProximitySelection
    {
        /// <summary>PlayerInRangeTrigger.cs:61 - GetOtherPlayer(ownPlayer),
        /// measured from the HOLDER's position against each candidate's
        /// transform.position (PlayerManager.cs:60,115).</summary>
        NearestEnemy,

        /// <summary>PlayerInRangeTrigger.cs:65 - GetClosestPlayer(trigger position),
        /// measured from the TRIGGER's position against each candidate's
        /// data.playerVel.position (PlayerManager.cs:71), and vanilla excludes
        /// nobody here: GetClosestPlayer skips only the dead. The repair must not
        /// quietly narrow that.</summary>
        NearestAny
    }

    internal static class ProximityVictim
    {
        /// <summary>No victim. The repair refuses rather than guesses.</summary>
        internal const int None = -1;

        /// <summary>Positional self-exclusion, matching FfaTargeting.NearestOpponent.
        /// A candidate standing exactly where the lookup is measured from is the
        /// asker.</summary>
        internal const float SelfEpsilon = 0.01f;

        /// <summary>Bound on refusal diagnostics, so a contradiction that repeats
        /// every tick cannot flood the log.</summary>
        internal const int MaxRefusalDiagnostics = 8;

        /// <summary>The capability gate, as a pure predicate so the inert case is
        /// testable.
        ///
        /// roomCapable: EVERY fighter in the room advertises a build carrying this
        /// repair. This changes who takes damage in a shared simulation, so it is
        /// whole-room or nothing - never a room-name prefix (#286: the prefix set
        /// misses most rated play) and never mod_version (#301: a locally built DLL
        /// reports the last shipped version, so it lies on exactly the seat that
        /// tests it).
        ///
        /// targetsOther: the effect resolves a player OTHER than its holder. The
        /// own-player branch caches data.player (DealDamageToPlayer.cs:35), which is
        /// not a cross-player lookup and has no defect, so it stays vanilla.
        ///
        /// Both false-directions fall through to vanilla unchanged, which preserves
        /// today's behaviour rather than inventing a third one (#276/#430).</summary>
        internal static bool ShouldRepair(bool roomCapable, bool targetsOther)
        {
            return roomCapable && targetsOther;
        }

        /// <summary>Planar squared distance, for the SELECTION only. Both vanilla
        /// selectors are Vector2.Distance (PlayerManager.cs:71 and :115), so a
        /// planar measure is the faithful one here.</summary>
        private static float DistanceSquared(float ax, float ay, float bx, float by)
        {
            float dx = ax - bx;
            float dy = ay - by;
            return (dx * dx) + (dy * dy);
        }

        /// <summary>Squared distance in THREE dimensions, for the PREDICATE.
        /// PlayerInRangeTrigger.cs:67 is a Vector3.Distance, so the range test
        /// includes z. This is not interchangeable with the planar measure: every
        /// planar distance is less than or equal to its 3D counterpart, so a planar
        /// range test admits every candidate vanilla admits AND some it rejects.
        /// For a repair whose whole purpose is to change which player takes the
        /// damage, widening the set is the failure direction that costs another
        /// player the match (#276/#430).</summary>
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
        /// The predicate is vanilla's at :67 minus the `counter >= cooldown` term:
        /// vanilla zeroes counter at :69, one line before the invoke, so that term
        /// is unreadable from inside Go(). Dropping it only RELAXES the predicate,
        /// which is what makes a None answer on a trigger-driven call a
        /// CONTRADICTION rather than a routine outcome - and why the caller may log
        /// and refuse on it.
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

            bool enemy = selection == ProximitySelection.NearestEnemy;

            // Which position the vanilla selector for THIS path measures.
            // GetClosestPlayer (NearestAny) reads data.playerVel.position;
            // GetClosestPlayerInTeam (NearestEnemy) reads transform.position.
            bool selectByVelocity = !enemy;

            int bestIndex = -1;
            float bestDistanceSquared = float.PositiveInfinity;

            for (int i = 0; i < candidates.Count; i++)
            {
                ProximityCandidate c = candidates[i];
                if (c.Dead) continue;

                // The position vanilla's own selector measures for this path.
                float cx = selectByVelocity ? c.AnyX : c.X;
                float cy = selectByVelocity ? c.AnyY : c.Y;

                if (enemy)
                {
                    if (c.Id == holderId) continue;
                    if (c.Team == holderTeam) continue;
                    if (DistanceSquared(selectX, selectY, cx, cy) < SelfEpsilon * SelfEpsilon) continue;
                }

                float d2 = DistanceSquared(selectX, selectY, cx, cy);
                if (d2 >= bestDistanceSquared) continue;
                bestDistanceSquared = d2;
                bestIndex = i;
            }

            if (bestIndex < 0) return None;

            ProximityCandidate chosen = candidates[bestIndex];

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
