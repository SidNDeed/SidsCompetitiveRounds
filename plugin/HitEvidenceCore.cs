using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Item D, EVIDENCE ONLY: the pure half of what the receiving seat
    /// records about the hits, knockback and blocks it was sent. No Unity, no
    /// Photon: tools/tests/hit-evidence-client compiles this file as it ships.
    ///
    /// Vanilla facts this rests on (decompile, logs-snapshot/decompiled/full):
    /// the SHOOTER's seat decides an impact (ProjectileHit.Hit, ~179: the block
    /// test reads the shooter's replica of the victim) and then sends the
    /// damage and the knockback as TWO messages (~271-299: CallTakeDamage, then
    /// CallTakeForce; HealthHandler ~208-212 RPCA_SendTakeDamage and ~119-123
    /// RPCA_SendTakeForce). The receiver applies the damage with ignoreBlock
    /// (HealthHandler ~237), so a block that is up on the victim's own screen
    /// does not stop a hit the shooter's seat judged unblocked. Nothing here
    /// changes any of that -- it counts.</summary>
    internal static class HitEvidenceCore
    {
        /// <summary>Damage and force from one impact are sent back to back in
        /// the same frame by the same seat, so they arrive together; a message
        /// with no partner from the same actor within this many seconds is
        /// counted alone.</summary>
        internal const float PAIR_WINDOW_S = 0.25f;
        /// <summary>Block.IsBlocking: sinceBlock &lt; 0.3f.</summary>
        internal const float BLOCK_WINDOW_S = 0.3f;
        internal const float BLOCK_NEAR_S = 0.6f;
        /// <summary>Arrival times kept per actor per point for the pairing; past
        /// this the counts still run and the line says how many were not
        /// paired-checked.</summary>
        internal const int TIMES_CAP = 2048;
        /// <summary>Projectiles remembered per game for D2's distinct count.</summary>
        internal const int PROJ_CAP = 8192;

        internal enum BlockBucket { Inside = 0, Near = 1, Later = 2, Never = 3 }

        /// <summary>Where a direct damage message landed relative to the local
        /// player's last block on THIS seat. sinceBlock is Block.sinceBlock,
        /// read when the message is applied.</summary>
        internal static BlockBucket Bucket(bool blockedThisPoint, float sinceBlock)
        {
            if (!blockedThisPoint) return BlockBucket.Never;
            if (float.IsNaN(sinceBlock)) throw new ArgumentException("sinceBlock is NaN");
            if (sinceBlock < BLOCK_WINDOW_S) return BlockBucket.Inside;
            if (sinceBlock < BLOCK_NEAR_S) return BlockBucket.Near;
            return BlockBucket.Later;
        }

        /// <summary>Greedy in-order pairing of two arrival-time lists (each
        /// ascending): a damage and a force within <paramref name="window"/>
        /// seconds of each other pair; everything else is alone.</summary>
        internal static void Pair(IList<float> damage, IList<float> force, float window,
                                  out int paired, out int damageAlone, out int forceAlone)
        {
            if (damage == null || force == null) throw new ArgumentNullException();
            if (!(window >= 0f)) throw new ArgumentException("window");
            Ascending(damage, "damage"); Ascending(force, "force");
            paired = 0; damageAlone = 0; forceAlone = 0;
            int i = 0, j = 0;
            while (i < damage.Count && j < force.Count)
            {
                float d = damage[i], f = force[j];
                if (Math.Abs(d - f) <= window) { paired++; i++; j++; }
                else if (d < f) { damageAlone++; i++; }
                else { forceAlone++; j++; }
            }
            damageAlone += damage.Count - i;
            forceAlone += force.Count - j;
        }

        private static void Ascending(IList<float> t, string name)
        {
            for (int k = 0; k < t.Count; k++)
            {
                if (float.IsNaN(t[k])) throw new ArgumentException(name + " has NaN");
                if (k > 0 && t[k] < t[k - 1]) throw new ArgumentException(name + " is not ascending");
            }
        }

        /// <summary>One remote actor's messages to the local player in one point.</summary>
        internal sealed class PointTally
        {
            internal int Direct;          // RPCA_SendTakeDamage on the local player
            internal double DirectSum;    // |damage| summed
            internal int Converted;       // ...of those, turned into damage over time by the local player's own stats
            internal int Force;           // RPCA_SendTakeForce on the local player
            internal double ForceSum;     // |force| summed
            internal int ForceInert;      // ...of those, arriving while the local player was not playing/simulated (TakeForce returns early)
            internal int Dot;             // damage-over-time ticks applied to the local player, credited to this actor
            internal double DotSum;
            internal readonly List<float> DirectT = new List<float>();
            internal readonly List<float> ForceT = new List<float>();
            internal int Unchecked;       // arrivals past TIMES_CAP, not pair-checked

            internal void AddDirect(float t, float mag, bool converted)
            {
                Direct++; DirectSum += mag; if (converted) Converted++;
                if (DirectT.Count < TIMES_CAP) DirectT.Add(t); else Unchecked++;
            }

            internal void AddForce(float t, float mag, bool inert)
            {
                Force++; ForceSum += mag; if (inert) ForceInert++;
                if (ForceT.Count < TIMES_CAP) ForceT.Add(t); else Unchecked++;
            }

            internal void AddDot(float mag) { Dot++; DotSum += mag; }

            internal bool Any { get { return Direct + Force + Dot > 0; } }
        }

        /// <summary>One remote actor in one game, as this seat saw it.</summary>
        internal sealed class GameTally
        {
            internal int SpawnAmmo;       // RPCA_Init: a held gun's ammo-using shot
            internal int SpawnNoAmmo;     // RPCA_Init_noAmmoUse: a held gun fired by a card/effect
            internal int SpawnSeparate;   // RPCA_Init_SeparateGun: a gun the player does not hold
            internal int Impacts;         // RPCA_DoHit on the local player, unblocked
            internal int ImpactsBlocked;  // RPCA_DoHit on the local player that the shooter's seat judged blocked
            internal int DistinctAmmo;    // distinct ammo-using projectiles with >= 1 unblocked impact
            internal int DistinctOther;   // distinct other projectiles with >= 1 unblocked impact
            internal int Direct;          // direct damage messages over the game
            internal readonly int[] Buckets = new int[4];
            internal readonly HashSet<int> Hit = new HashSet<int>();
            internal int HitOverflow;

            /// <summary>First unblocked impact of a projectile counts once
            /// (a bouncing bullet hitting twice is one projectile).</summary>
            internal void AddImpact(int projectile, bool blocked, bool ammo)
            {
                if (blocked) { ImpactsBlocked++; return; }
                Impacts++;
                if (Hit.Contains(projectile)) return;
                if (Hit.Count >= PROJ_CAP) { HitOverflow++; return; }
                Hit.Add(projectile);
                if (ammo) DistinctAmmo++; else DistinctOther++;
            }

            internal bool Any
            {
                get { return SpawnAmmo + SpawnNoAmmo + SpawnSeparate + Impacts + ImpactsBlocked + Direct > 0; }
            }
        }

        private static string F(double v) { return v.ToString("0.00", CultureInfo.InvariantCulture); }

        /// <summary>D1. Actor numbers are Photon actor numbers in the room,
        /// never an account identity.</summary>
        internal static string HitRecvLine(int point, int actor, PointTally t)
        {
            int paired, dAlone, fAlone;
            Pair(t.DirectT, t.ForceT, PAIR_WINDOW_S, out paired, out dAlone, out fAlone);
            var sb = new StringBuilder("[HIT-RECV] point=");
            sb.Append(point).Append(" from=a").Append(actor)
              .Append(" direct=").Append(t.Direct).Append(" direct_sum=").Append(F(t.DirectSum))
              .Append(" converted=").Append(t.Converted)
              .Append(" force=").Append(t.Force).Append(" force_sum=").Append(F(t.ForceSum))
              .Append(" force_inert=").Append(t.ForceInert)
              .Append(" paired=").Append(paired).Append(" direct_no_force=").Append(dAlone)
              .Append(" force_no_direct=").Append(fAlone)
              .Append(" dot_ticks=").Append(t.Dot).Append(" dot_sum=").Append(F(t.DotSum));
            if (t.Unchecked > 0) sb.Append(" unchecked=").Append(t.Unchecked);
            return sb.ToString();
        }

        /// <summary>D2.</summary>
        internal static string ShotObsLine(int game, int actor, GameTally g)
        {
            var sb = new StringBuilder("[SHOT-OBS] game=");
            sb.Append(game).Append(" from=a").Append(actor)
              .Append(" spawned_ammo=").Append(g.SpawnAmmo).Append(" spawned_noammo=").Append(g.SpawnNoAmmo)
              .Append(" spawned_separate=").Append(g.SpawnSeparate)
              .Append(" hit_me_ammo=").Append(g.DistinctAmmo).Append(" hit_me_other=").Append(g.DistinctOther)
              .Append(" impacts=").Append(g.Impacts).Append(" impacts_blocked=").Append(g.ImpactsBlocked)
              .Append(" direct_msgs=").Append(g.Direct)
              .Append(" observed_hit_pct=").Append(g.SpawnAmmo > 0 ? F(100.0 * g.DistinctAmmo / g.SpawnAmmo) : "na");
            if (g.HitOverflow > 0) sb.Append(" overflow=").Append(g.HitOverflow);
            return sb.ToString();
        }

        /// <summary>D3.</summary>
        internal static string BlockMissLine(int game, int actor, GameTally g)
        {
            var sb = new StringBuilder("[BLOCK-MISS] game=");
            sb.Append(game).Append(" from=a").Append(actor)
              .Append(" direct=").Append(g.Direct)
              .Append(" inside_0.3=").Append(g.Buckets[(int)BlockBucket.Inside])
              .Append(" 0.3_0.6=").Append(g.Buckets[(int)BlockBucket.Near])
              .Append(" later=").Append(g.Buckets[(int)BlockBucket.Later])
              .Append(" never_blocked_point=").Append(g.Buckets[(int)BlockBucket.Never]);
            return sb.ToString();
        }

        /// <summary>Merge pass 6, G1-L1: whether one RPCA_NextRound call
        /// decided a point on this seat, from what the point-end hook read
        /// before the call (its prefix) and after it (its postfix). One of
        /// three paths takes a point: vanilla's body ran and found
        /// isTransitioning false (its own duplicate guard returns at once when
        /// it is true); FfaMode.HandleNextRound passed its gate (its count of
        /// points taken moved); or a spectator seat's observer took a new
        /// round (its count of rounds taken moved: it counts only a round it
        /// latched, and a latched observer returns before counting). A call
        /// that none of them took is a duplicate or a refused broadcast and
        /// must not end the evidence point.</summary>
        internal static bool PointTaken(bool ranOriginal, bool vanillaWasTransitioning,
                                        int ffaTakenBefore, int ffaTakenAfter,
                                        int observedBefore, int observedAfter)
        {
            if (ffaTakenAfter != ffaTakenBefore) return true;
            if (observedAfter != observedBefore) return true;
            return ranOriginal && !vanillaWasTransitioning;
        }

        /// <summary>Merge pass 6, G1-L2: whether a point this seat took ended
        /// the game. Under the FFA engine the game is over when FfaMode's own
        /// game-over latch is set after the call (the engine keeps its round
        /// scores to itself, so vanilla's p1Rounds and p2Rounds say nothing
        /// there); otherwise when either side reached roundsToWinGame.</summary>
        internal static bool GameDecided(bool ffaEngine, bool ffaGameOver,
                                         int p1Rounds, int p2Rounds, int roundsToWinGame)
        {
            if (ffaEngine) return ffaGameOver;
            return p1Rounds >= roundsToWinGame || p2Rounds >= roundsToWinGame;
        }
    }
}
