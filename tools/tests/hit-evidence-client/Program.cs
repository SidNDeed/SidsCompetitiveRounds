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

        // Merge pass 6, G1-L1: a duplicate or refused RPCA_NextRound ends no point.
        private static void PointGate()
        {
            // vanilla: the body ran with isTransitioning false -> a point; true -> its duplicate guard returned
            Check(HitEvidenceCore.PointTaken(true, false, 7, 7, 3, 3), "vanilla point");
            Check(!HitEvidenceCore.PointTaken(true, true, 7, 7, 3, 3), "vanilla duplicate");
            // a prefix skipped the body (FFA engine or spectator) and nothing else took it
            Check(!HitEvidenceCore.PointTaken(false, false, 7, 7, 3, 3), "skipped body, no path");
            // FFA: the engine's taken count moved -> a point; a refused master or a duplicate leaves it
            Check(HitEvidenceCore.PointTaken(false, false, 7, 8, 3, 3), "ffa point");
            Check(!HitEvidenceCore.PointTaken(false, false, 8, 8, 3, 3), "ffa refused or duplicate");
            Check(HitEvidenceCore.PointTaken(false, false, int.MaxValue, int.MinValue, 3, 3), "ffa count wraps");
            // spectator: the observer's count moved -> a point; a latched observer leaves it
            Check(HitEvidenceCore.PointTaken(false, false, 7, 7, 3, 4), "spectator point");
            Check(!HitEvidenceCore.PointTaken(false, false, 7, 7, 4, 4), "spectator duplicate");
        }

        // Merge pass 6, G1-L2: the FFA game ends on the engine's latch, not vanilla's rounds.
        private static void GameGate()
        {
            Check(HitEvidenceCore.GameDecided(true, true, 0, 0, 5), "ffa game over, vanilla rounds untouched");
            Check(!HitEvidenceCore.GameDecided(true, false, 5, 0, 5), "ffa not over whatever vanilla rounds say");
            Check(HitEvidenceCore.GameDecided(false, false, 5, 2, 5) && HitEvidenceCore.GameDecided(false, false, 1, 5, 5), "vanilla game over");
            Check(!HitEvidenceCore.GameDecided(false, true, 4, 4, 5), "vanilla not over");
        }

        // [PEER-BUILD] (merge pass 5): every key is listed, sorted; only the
        // version/variant/capability keys print a value; an account id in any
        // other key never reaches the line.
        private static void Peer()
        {
            var props = new Dictionary<string, string>
            {
                { "u_id", "ACCOUNT-ID-MARKER" }, { "playerID", "1" }, { "cr_build", "1.41.0|standalone|0c36c644e658" },
                { "cr_pois2", "1" }, { "cr_gstats", "9|9|9" }, { "cr_dc2", "2" },
            };
            Eq("[PEER-BUILD] actor=3 keys=6 ours=4 list=cr_build,cr_dc2,cr_gstats,cr_pois2,playerID,u_id"
               + " cr_build=1.41.0|standalone|0c36c644e658 cr_dc2=2 cr_dc3=- cr_ffacfg=- cr_game_token_v=- cr_grow2=-"
               + " cr_msv2=- cr_pois2=1 cr_pois3=- cr_prox1=- cr_saw1=- cr_wcd1=-",
               PeerBuildCore.Line(3, props), "PEER-BUILD");
            // Merge pass 6, R-L1: the shared token's version and poison v3 are capabilities, so their values print.
            var caps = new Dictionary<string, string>(props) { { "cr_game_token_v", "2" }, { "cr_pois3", "1" } };
            Check(PeerBuildCore.Line(3, caps).Contains(" cr_game_token_v=2 ") && PeerBuildCore.Line(3, caps).Contains(" cr_pois3=1 "),
                  "capability values");
            Check(PeerBuildCore.Values(props) != PeerBuildCore.Values(caps), "a capability change changes the values");
            Check(!PeerBuildCore.Line(3, props).Contains("ACCOUNT-ID-MARKER"), "no account id");
            Check(!PeerBuildCore.Line(3, props).Contains("9|9|9"), "no other value");
            // A seat with none of our keys still gets its line, saying so.
            var vanilla = new Dictionary<string, string> { { "playerID", "2" }, { "u_id", "x" } };
            Eq("[PEER-BUILD] actor=2 keys=2 ours=none list=playerID,u_id cr_build=- cr_dc2=- cr_dc3=- cr_ffacfg=-"
               + " cr_game_token_v=- cr_grow2=- cr_msv2=- cr_pois2=- cr_pois3=- cr_prox1=- cr_saw1=- cr_wcd1=-",
               PeerBuildCore.Line(2, vanilla), "PEER-BUILD vanilla");
            Check(PeerBuildCore.Line(5, new Dictionary<string, string>()).Contains(" keys=0 ours=none list=- "), "empty seat");
            // Tokens: unsafe characters masked, long ones cut.
            Eq("a?b", PeerBuildCore.Token("a b"), "mask");
            Eq(new string('x', PeerBuildCore.MAX_TOKEN) + "~", PeerBuildCore.Token(new string('x', 100)), "cut");
            Eq("null", PeerBuildCore.Token(null), "null");
            // The value part, which decides a reprint, ignores every non-value key.
            var moreKeys = new Dictionary<string, string>(props) { { "cr_cards", "A|B" } };
            Eq(PeerBuildCore.Values(props), PeerBuildCore.Values(moreKeys), "values ignore other keys");
            var newBuild = new Dictionary<string, string>(props);
            newBuild["cr_build"] = "1.41.1|standalone|aaaaaaaaaaaa";
            Check(PeerBuildCore.Values(props) != PeerBuildCore.Values(newBuild), "a new build changes the values");
            // Merge pass 6, R-L2: every key name is listed, on continuation lines past KEYS_PER_LINE.
            var many = new Dictionary<string, string>();
            int n = 2 * PeerBuildCore.KEYS_PER_LINE + 3;
            for (int i = 0; i < n; i++) many["k" + i.ToString("000")] = "v";
            string[] ml = PeerBuildCore.Line(1, many).Split('\n');
            Check(ml.Length == 3 && ml[0].Contains(" lines=3 ") && ml[1].StartsWith("[PEER-BUILD] actor=1 list(2/3)=")
                  && ml[2].StartsWith("[PEER-BUILD] actor=1 list(3/3)=k064,k065,k066"), "continuation lines");
            bool every = true;
            for (int i = 0; i < n; i++)
            {
                string k = "k" + i.ToString("000");
                int hits = 0;
                foreach (var l in ml)
                    foreach (var part in l.Split(' ', '=', ','))
                        if (part == k) hits++;
                if (hits != 1) every = false;
            }
            Check(every, "every key listed once");
            Check(PeerBuildCore.Line(1, new Dictionary<string, string> { { "k000", "v" } }).Split('\n').Length == 1, "one line");
            // A long key prints its head, length and hash: two names differing past KEY_HEAD print differently.
            string longA = new string('a', 90) + "1", longB = new string('a', 90) + "2";
            Check(PeerBuildCore.KeyToken(longA) != PeerBuildCore.KeyToken(longB), "long keys stay distinct");
            Check(PeerBuildCore.KeyToken(longA).StartsWith(new string('a', PeerBuildCore.KEY_HEAD) + "~91#"), "long key form");
            Eq("cr_build", PeerBuildCore.KeyToken("cr_build"), "a short safe key prints whole");
            Eq(new string('k', PeerBuildCore.MAX_KEY), PeerBuildCore.KeyToken(new string('k', PeerBuildCore.MAX_KEY)), "a key at MAX_KEY prints whole");
            Check(PeerBuildCore.KeyToken("a b") != PeerBuildCore.KeyToken("a\tb") && PeerBuildCore.KeyToken("a b").StartsWith("a?b#"),
                  "masked keys stay distinct");
        }

        private static int Main(string[] args)
        {
            var cases = new Dictionary<string, Action>
            {
                { "bucket", Bucket }, { "pair", Pair }, { "impacts", Impacts }, { "tally", Tally }, { "lines", Lines }, { "peer", Peer },
                { "pointgate", PointGate }, { "gamegate", GameGate },
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
