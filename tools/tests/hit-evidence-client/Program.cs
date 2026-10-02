using System;
using System.Collections.Generic;
using CompetitiveRounds;

namespace HitEvidenceTests
{
    /// <summary>Cases over plugin/HitEvidenceCore.cs. Usage: HitEvidenceTests
    /// [case ...] (no argument: every case). Exit 0 only when every selected
    /// case passes.</summary>
    internal static class Program
    {
        private static void Check(bool ok, string what) { if (!ok) throw new Exception(what); }

        private static void Eq<T>(T want, T got, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(want, got)) throw new Exception(what + ": want " + want + ", got " + got);
        }

        private static bool Throws(Action a)
        {
            try { a(); return false; } catch (ArgumentException) { return true; }
        }

        // The block buckets: [0, 0.3) inside the window, [0.3, 0.6) near, later,
        // and "never" whenever the local player did not block this point.
        private static void Bucket()
        {
            Eq(HitEvidenceCore.BlockBucket.Inside, HitEvidenceCore.Bucket(true, 0f), "0.0");
            Eq(HitEvidenceCore.BlockBucket.Inside, HitEvidenceCore.Bucket(true, 0.2999f), "0.2999");
            Eq(HitEvidenceCore.BlockBucket.Near, HitEvidenceCore.Bucket(true, 0.3f), "0.3 is outside Block.IsBlocking");
            Eq(HitEvidenceCore.BlockBucket.Near, HitEvidenceCore.Bucket(true, 0.5999f), "0.5999");
            Eq(HitEvidenceCore.BlockBucket.Later, HitEvidenceCore.Bucket(true, 0.6f), "0.6");
            Eq(HitEvidenceCore.BlockBucket.Later, HitEvidenceCore.Bucket(true, float.PositiveInfinity), "inf");
            Eq(HitEvidenceCore.BlockBucket.Never, HitEvidenceCore.Bucket(false, 0.1f), "not blocked this point, even with a fresh timer");
            Eq(HitEvidenceCore.BlockBucket.Never, HitEvidenceCore.Bucket(false, float.NaN), "never wins before the NaN check");
            Check(Throws(() => HitEvidenceCore.Bucket(true, float.NaN)), "NaN refused");
        }

        // Pairing: in order, within the window inclusive, each message used once.
        private static void Pair()
        {
            int p, d, f;
            HitEvidenceCore.Pair(new[] { 1.0f, 2.0f, 5.0f }, new[] { 1.01f, 2.3f, 9.0f }, 0.25f, out p, out d, out f);
            Eq(1, p, "paired"); Eq(2, d, "damage alone"); Eq(2, f, "force alone");
            HitEvidenceCore.Pair(new[] { 1.0f }, new[] { 1.25f }, 0.25f, out p, out d, out f);
            Eq(1, p, "the window is inclusive"); Eq(0, d + f, "nothing alone at the edge");
            HitEvidenceCore.Pair(new[] { 1.0f, 1.0f, 1.0f }, new[] { 1.0f }, 0.25f, out p, out d, out f);
            Eq(1, p, "one force pairs once"); Eq(2, d, "the other two damages are alone"); Eq(0, f, "no force alone");
            HitEvidenceCore.Pair(new float[0], new[] { 3f, 4f }, 0.25f, out p, out d, out f);
            Eq(0, p, "empty damage"); Eq(2, f, "every force alone");
            HitEvidenceCore.Pair(new[] { 3f, 4f }, new float[0], 0.25f, out p, out d, out f);
            Eq(2, d, "every damage alone"); Eq(0, f, "no force");
            Check(Throws(() => HitEvidenceCore.Pair(new[] { 2f, 1f }, new float[0], 0.25f, out p, out d, out f)), "unsorted refused");
        }

        // A projectile counts once however often it hits; blocked impacts are
        // separate and never make a projectile "hit".
        private static void Impacts()
        {
            var g = new HitEvidenceCore.GameTally();
            g.AddImpact(7, false, true);
            g.AddImpact(7, false, true);          // the same bullet bouncing back
            g.AddImpact(8, true, true);           // judged blocked by the shooter's seat
            g.AddImpact(9, false, false);         // a card's shot
            Eq(3, g.Impacts, "unblocked impacts"); Eq(1, g.ImpactsBlocked, "blocked impacts");
            Eq(1, g.DistinctAmmo, "distinct ammo projectiles"); Eq(1, g.DistinctOther, "distinct other projectiles");
            g.AddImpact(8, false, true);          // the blocked one later lands
            Eq(2, g.DistinctAmmo, "a blocked impact does not consume the projectile's hit");
        }

        // The tallies and the TIMES_CAP bound.
        private static void Tally()
        {
            var t = new HitEvidenceCore.PointTally();
            Check(!t.Any, "empty");
            t.AddDirect(1f, 30f, false); t.AddDirect(2f, 30f, true); t.AddForce(1.01f, 4.5f, false); t.AddForce(9f, 0.5f, true);
            t.AddDot(3f); t.AddDot(3f);
            Eq(2, t.Direct, "direct"); Eq(1, t.Converted, "converted"); Eq(2, t.Force, "force"); Eq(1, t.ForceInert, "inert");
            Eq(2, t.Dot, "dot"); Check(Math.Abs(t.DotSum - 6.0) < 1e-9, "dot sum");
            var big = new HitEvidenceCore.PointTally();
            for (int i = 0; i < HitEvidenceCore.TIMES_CAP + 5; i++) big.AddDirect(i, 1f, false);
            Eq(HitEvidenceCore.TIMES_CAP, big.DirectT.Count, "times are capped"); Eq(5, big.Unchecked, "the excess is reported");
            Eq(HitEvidenceCore.TIMES_CAP + 5, big.Direct, "the count still runs");
        }

        // The three lines, exactly.
        private static void Lines()
        {
            var t = new HitEvidenceCore.PointTally();
            t.AddDirect(1f, 30f, false); t.AddDirect(2f, 30f, true); t.AddForce(1.01f, 4.5f, false); t.AddForce(9f, 0.5f, true);
            t.AddDot(3f);
            Eq("[HIT-RECV] point=4 from=a2 direct=2 direct_sum=60.00 converted=1 force=2 force_sum=5.00 force_inert=1"
               + " paired=1 direct_no_force=1 force_no_direct=1 dot_ticks=1 dot_sum=3.00",
               HitEvidenceCore.HitRecvLine(4, 2, t), "HIT-RECV");
            var g = new HitEvidenceCore.GameTally();
            g.SpawnAmmo = 4; g.SpawnNoAmmo = 1; g.Direct = 3;
            g.AddImpact(1, false, true); g.AddImpact(2, false, true); g.AddImpact(3, true, true);
            g.Buckets[0] = 1; g.Buckets[1] = 0; g.Buckets[2] = 1; g.Buckets[3] = 1;
            Eq("[SHOT-OBS] game=1 from=a2 spawned_ammo=4 spawned_noammo=1 spawned_separate=0 hit_me_ammo=2 hit_me_other=0"
               + " impacts=2 impacts_blocked=1 direct_msgs=3 observed_hit_pct=50.00",
               HitEvidenceCore.ShotObsLine(1, 2, g), "SHOT-OBS");
            Eq("[BLOCK-MISS] game=1 from=a2 direct=3 inside_0.3=1 0.3_0.6=0 later=1 never_blocked_point=1",
               HitEvidenceCore.BlockMissLine(1, 2, g), "BLOCK-MISS");
            Check(HitEvidenceCore.ShotObsLine(1, 2, new HitEvidenceCore.GameTally()).EndsWith("observed_hit_pct=na"), "no spawn: na");
        }

        private static int Main(string[] args)
        {
            var cases = new Dictionary<string, Action>
            {
                { "bucket", Bucket }, { "pair", Pair }, { "impacts", Impacts }, { "tally", Tally }, { "lines", Lines },
            };
            var run = args.Length > 0 ? new List<string>(args) : new List<string>(cases.Keys);
            int failed = 0;
            foreach (var name in run)
            {
                Action a;
                if (!cases.TryGetValue(name, out a)) { Console.WriteLine("FAIL " + name + ": no such case"); failed++; continue; }
                try { a(); Console.WriteLine("PASS " + name); }
                catch (Exception e) { Console.WriteLine("FAIL " + name + ": " + e.Message); failed++; }
            }
            Console.WriteLine(failed == 0 ? "ALL PASS (" + run.Count + ")" : failed + " FAILED");
            return failed == 0 ? 0 : 1;
        }
    }
}
