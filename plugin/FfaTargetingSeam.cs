namespace CompetitiveRounds
{
    /// <summary>The running answer of one FFA enemy lookup: the index of the best
    /// candidate offered so far and its distance. A struct so the per-frame
    /// callers (every proximity ring calls GetOtherPlayer each frame) allocate
    /// nothing.</summary>
    internal struct FfaPick
    {
        public int Best;
        public float BestDist;
    }

    /// <summary>Bugs 437-439 - THE ONE FFA ENEMY RESOLVER, as pure rules.
    ///
    /// Vanilla answers "who is my enemy" in two shapes, both two-team:
    /// PlayerManager.GetOtherPlayer(asker) and
    /// GetClosestPlayerInTeam(position, GetOtherTeam(team)). GetOtherTeam returns
    /// 0 for every team except 0, so in free-for-all every holder outside slot 0
    /// would aim at slot 0 (learning #209). FfaMode prefixes both lookups and
    /// routes them here through FfaTargeting.NearestOpponent; every card effect
    /// that asks either question - the proximity ring, the effects it fires, the
    /// homing and line-of-sight family - therefore gets the same answer: the
    /// nearest living player that is not the asker.
    ///
    /// No Unity, Harmony or Photon type appears in this file, so
    /// tools/tests/ffa-targeting-seam compiles it as it ships and executes it.
    ///
    /// WHAT THIS FILE DOES NOT DO. It answers the question at the moment it is
    /// asked. An effect that asks once and keeps the answer (DealDamageToPlayer,
    /// StunPlayer and TeleportToOpponent cache their victim on the first call)
    /// is re-asked on every activation by the proximity-victim repair
    /// (ProximityVictimPatches.cs), which calls GetOtherPlayer and so arrives
    /// here. A fresh answer is only as good as the asking.</summary>
    internal static class FfaTargetingSeam
    {
        /// <summary>A candidate closer than this to a bare query position is the
        /// asker itself. Used ONLY when the caller could not name the asker:
        /// vanilla's GetClosestPlayerInTeam call sites pass their own transform
        /// position and nothing else.</summary>
        internal const float SelfRadius = 0.01f;

        internal static FfaPick Begin()
        {
            FfaPick pick;
            pick.Best = -1;
            pick.BestDist = float.PositiveInfinity;
            return pick;
        }

        /// <summary>True when a candidate is eligible AND strictly nearer than the
        /// best so far. Every exclusion the FFA resolver applies is here:
        ///   - a dead player is never an enemy to aim at;
        ///   - the asker's own team (in FFA, the asker) is excluded when known;
        ///   - the asker is excluded by identity when the caller named it;
        ///   - otherwise a candidate standing on the query position is taken to
        ///     be the asker (the positional rule the bare-position sites need).
        /// Strictly nearer keeps the earliest of equally near candidates, which
        /// is the roster order vanilla's own loops would also keep.</summary>
        internal static bool Improves(ref FfaPick pick, int team, bool dead, float dist,
                                      int excludeTeam, bool isExcludedPlayer, bool identityKnown)
        {
            if (dead) return false;
            if (excludeTeam >= 0 && team == excludeTeam) return false;
            if (isExcludedPlayer) return false;
            if (!identityKnown && dist < SelfRadius) return false;
            return dist < pick.BestDist;
        }

        /// <summary>Record a candidate the caller accepted (after its own vision
        /// check, which stays lazy: it runs only for a candidate that would
        /// improve the pick).</summary>
        internal static void Take(ref FfaPick pick, int index, float dist)
        {
            pick.Best = index;
            pick.BestDist = dist;
        }
    }
}
