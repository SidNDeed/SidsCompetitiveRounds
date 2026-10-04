using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using CompetitiveRounds;
using C = CompetitiveRounds.SeatEvidenceCore;

namespace SeatEvidenceTests
{
    /// <summary>Cases over plugin/SeatEvidenceCore.cs. Usage:
    ///   SeatEvidenceTests [case ...]        (no argument: every case)
    ///   SeatEvidenceTests fixtures DIR      (writes the server-comparison fixtures)
    /// Exit 0 only when every selected case passes.</summary>
    internal static class Program
    {
        private static void Check(bool ok, string what) { if (!ok) throw new Exception(what); }

        private static void Eq<T>(T want, T got, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(want, got)) throw new Exception(what + ": want " + want + ", got " + got);
        }

        private static string J(long[] a) { return C.Json(a); }

        // Python json.dumps(..., separators=(",", ":"), ensure_ascii=True) on the same values.
        private static void Json()
        {
            Eq("\"a\\\"b\\\\c\"", C.Json("a\"b\\c"), "quote and backslash");
            Eq("\"\\n\\r\\t\\b\\f\"", C.Json("\n\r\t\b\f"), "short control forms");
            Eq("\"\\u0001\\u001f\\u007f\"", C.Json("\u0001\u001f\u007f"), "other controls and DEL, lowercase hex");
            Eq("\"\\u00e9\\ud83d\\ude00\"", C.Json("é\U0001F600"), "non-ASCII as UTF-16 units");
            Eq("\" ~|:_-.\"", C.Json(" ~|:_-."), "printable ASCII as is");
            Eq("[-2147483648,0,9223372036854775807]", J(new long[] { int.MinValue, 0, long.MaxValue }), "integers");
            var o = new C.JObj().Add("b", 1L).Add("a", null).Add("c", new List<object> { "x", new long[] { 1, 2 } });
            Eq("{\"b\":1,\"a\":null,\"c\":[\"x\",[1,2]]}", C.Json(o), "insertion order, no whitespace");
        }

        internal static C.Record Sample(int n, bool wide)
        {
            var r = new C.Record();
            r.T0 = -2147480000; r.T0Src = "m"; r.Master = 1; r.Ranked = 1; r.RoundsSelf = 5; r.RoundsOther = 3;
            r.Build = new[] { "1.41.0", "standalone", "378a80342ec9" };
            r.DllSha = new string('a', 64); r.DllState = "ok"; r.GameDllState = "read_failed";
            r.Compat = "pass"; r.ForeignAsm = 2; r.ForeignOwners = 1; r.RttAvg = 41; r.RttMax = 96;
            r.OffsetUpdates = 33; r.OffsetStepMax = 12; r.ClkPpm = new long[] { -12, 340, -1000000 }; r.MonoSend = 123456789012;
            r.AgeView = new long[] { 70, 95, 400, 9000 }; r.AgeRpc = new long[] { 72, 99, 700000, 300 };
            r.AgeHit = new long[] { 80, 120, 40 }; r.AgeBlk = new long[] { -5, 90, 25 };
            r.DriftV = new long[] { -1234, 30, 2 }; r.Cad = new long[] { 30, 33, 33, 34, 3000 };
            for (int i = 0; i < 10; i++) r.Obs[i] = i * 7;
            r.OtherBuildV = "1.40.3|standalone|abc def"; r.OtherCapsV = new List<string> { "cr_build", "cr_dc2" };
            r.OtherPub = null;
            r.Shots = new long[] { 300, 4, 0 }; r.FireFloor = 2; r.Imp = new long[] { 41, 3, 30 }; r.Dec = new long[] { 38, 2 };
            r.Push = new long[] { 40, 39, 38, 2, 1, 0, 12 };
            int s = wide ? -2147000000 : 1000;
            for (int i = 0; i < n; i++)
            {
                r.BlkSent.Add(C.BlkSentEntry(s + i * 997, i % 4, i % 3, i % 2 == 0 ? 0 : -200));
                r.HitRecv.Add(C.HitRecvEntry(i % 2, s + i * 991, i % 2 == 1 ? 1000000 + i : 0, i % 5, s + i * 993, i % 3 == 0, i % 2 == 0, i % 7 == 0 ? -1 : 120 + i));
                r.BlkRecv.Add(C.BlkRecvEntry(s + i * 983, i % 4, i % 2, s + i * 989, i % 2 == 0));
                // amended B7: the three valid states only, in turn (never since_ms and last_* varied apart)
                var lr = i % 3 == 0 ? C.LastReset.Of(false, 0.4f, i % 2 == 0, s + i * 971, 0, i % 2)              // none
                       : i % 3 == 1 ? C.LastReset.Of(true, 0.25f + i * 0.001f, true, s + i * 971, i % 4, i % 2)    // keyed
                       : C.LastReset.Of(true, 0.25f + i * 0.001f, false, s + i * 971, i % 4, i % 2);               // unkeyed
                r.HitSent.Add(C.HitSentEntry(0, s + i * 977, 0, i % 3, lr, i % 2 == 0));
                r.AgeB.Add(new long[] { i - 1, i, i + 1, 300 + i, 40 + i, 70 + i });
            }
            r.BlkFaults = 1; r.UnpairBlocks = 3; r.UnpairHits = 4;
            return r;
        }

        // The budgeter: under the limit only the 160 cap acts; over it the
        // longest list (ties: the earliest) loses its LAST entry until it fits.
        private static void Budget()
        {
            var small = Sample(3, false).ToObj();
            string a = C.Budget(small);
            Check(a.Length <= C.RECORD_MAX_BYTES, "small fits");
            Check(a.EndsWith("\"omit\":{\"blk_sent\":0,\"hit_recv\":0,\"blk_recv\":0,\"hit_sent\":0,\"age_b\":0}}"), "no omissions when it fits: " + a.Substring(a.Length - 90));
            var big = Sample(200, true).ToObj();
            string b = C.Budget(big);
            Check(b.Length <= C.RECORD_MAX_BYTES, "worst case fits: " + b.Length);
            Check(b.Contains("\"omit\":{"), "omit present");
            var tail = b.Substring(b.IndexOf("\"omit\":", StringComparison.Ordinal));
            // every list lost at least the 40 past the cap; hit_recv (the widest
            // entries) is trimmed to the same count as its peers or below.
            Check(!tail.Contains("\"blk_sent\":0,"), "blk_sent omissions counted: " + tail);
            Check(!tail.Contains("\"age_b\":0}"), "age_b omissions counted: " + tail);
            // a tie on length removes the EARLIEST list's entry first
            var r = Sample(160, true); var o = r.ToObj();
            string c = C.Budget(o, C.Json(o).Length - 1);
            Check(c.Contains("\"omit\":{\"blk_sent\":1,\"hit_recv\":0,\"blk_recv\":0,\"hit_sent\":0,\"age_b\":0}"), "tie removes blk_sent's last: " + c.Substring(c.IndexOf("\"omit\"", StringComparison.Ordinal)));
            // determinism
            Eq(b, C.Budget(Sample(200, true).ToObj()), "same input, same bytes");
        }

        private static void Entries()
        {
            Eq("[5,9,255,600000]", J(C.BlkSentEntry(5, 12, 400, 700000)), "blk_sent clamps");
            Eq("[1,7,0,0,-9,0,1,-1]", J(C.HitRecvEntry(1, 7, -3, 0, -9, false, true, -5)), "hit_recv: own_since -1, pid floor 0");
            Eq("[0,7,0,2,-1,1,0,-1,0,0]", J(C.HitSentEntry(0, 7, 0, 2, C.LastReset.Of(false, 0.2999f, false, 99, 3, 4), true)), "hit_sent: none");
            Eq("[0,7,0,2,299,0,99,3,4,1]", J(C.HitSentEntry(0, 7, 0, 2, C.LastReset.Of(true, 0.2999f, true, 99, 3, 4), false)), "hit_sent: keyed");
            Eq("[1,7,9,2,299,0,0,-1,0,2]", J(C.HitSentEntry(1, 7, 9, 2, C.LastReset.Of(true, 0.2999f, false, 99, 3, 4), false)), "hit_sent: unkeyed");
            Eq("[0,7,0,2,-1,0,0,-1,0,0]", J(C.HitSentEntry(0, 7, 0, 2, C.LastReset.Of(false, 0.2999f, true, 99, 3, 4), false)), "hit_sent: a key without a seen reset is none");
            Eq(-1L, C.SinceMs(false, 0.1f), "never reset reads -1");
            Eq(299L, C.SinceMs(true, 0.2999f), "floor ms");
            Eq(300L, C.SinceMs(true, 0.3f), "0.3 s reads 300");
            Eq(600000L, C.SinceMs(true, 10000f), "clamped");
            Eq(0L, C.SinceMs(true, 0f), "a fresh reset reads 0");
        }

        // -- amended B7 (contract AMENDMENT 2026-10-04): the state space ---------------

        private static readonly float[] B7_SINCE = { float.NaN, -0.5f, 0f, 0.0004f, 0.05f, 0.2999f, 0.3f, 599.9999f, 600f, 10000f, float.PositiveInfinity };
        private static readonly int[] B7_TB = { int.MinValue, 0, 1, 2000000, int.MaxValue };
        private static readonly int[] B7_KIND = { -5, -1, 0, 1, 3, 9, 10 };
        private static readonly int[] B7_ORD = { -1, 0, 1, 255, 256 };

        /// <summary>Every input of LastReset.Of over the grid above, with the
        /// entry HitSentEntry writes for it (path 0 and path 1 alternating).</summary>
        private static List<KeyValuePair<string, long[]>> B7Space()
        {
            var l = new List<KeyValuePair<string, long[]>>();
            int n = 0;
            foreach (bool er in new[] { false, true })
                foreach (float s in B7_SINCE)
                    foreach (bool hl in new[] { false, true })
                        foreach (int tb in B7_TB)
                            foreach (int k in B7_KIND)
                                foreach (int o in B7_ORD)
                                {
                                    var e = C.HitSentEntry(n % 2, 1000 + n, n % 2 == 1 ? 7 : 0, n % 4, C.LastReset.Of(er, s, hl, tb, k, o), n % 3 == 0);
                                    l.Add(new KeyValuePair<string, long[]>(er + "|" + s.ToString("R", System.Globalization.CultureInfo.InvariantCulture)
                                                                           + "|" + hl + "|" + tb + "|" + k + "|" + o, e));
                                    n++;
                                }
            return l;
        }

        /// <summary>The state each input must map to, stated from the copy's
        /// state (not from the code): a reset seen with a readable sinceBlock
        /// is keyed when the last reset carried a key, unkeyed when it did not;
        /// anything else is none. Every entry of the space is exactly the
        /// state's triple, and every state occurs.</summary>
        private static void B7()
        {
            var seen = new int[3];
            foreach (var kv in B7Space())
            {
                var f = kv.Key.Split('|');
                bool er = f[0] == "True", hl = f[2] == "True";
                float s = float.Parse(f[1], System.Globalization.CultureInfo.InvariantCulture);
                int tb = int.Parse(f[3]), k = int.Parse(f[4]), o = int.Parse(f[5]);
                var e = kv.Value;
                Eq(10, e.Length, "ten elements: " + kv.Key);
                bool readable = er && !float.IsNaN(s);
                long want = !readable ? 0 : hl ? 1 : 2;
                Eq(want, e[9], "reset for " + kv.Key);
                seen[(int)e[9]]++;
                if (want == 0) Eq("[-1,0,-1,0]", J(new[] { e[4], e[6], e[7], e[8] }), "none: -1 and the sentinel, " + kv.Key);
                else
                {
                    long ms = s <= 0f ? 0 : Math.Min(600000L, (long)Math.Floor((double)s * 1000.0));
                    if (float.IsPositiveInfinity(s)) ms = 600000;
                    Eq(ms, e[4], "since_ms read for " + kv.Key);
                    if (want == 1)
                        Eq(J(new long[] { tb, Math.Max(0, Math.Min(9, k)), Math.Max(0, Math.Min(255, o)) }), J(new[] { e[6], e[7], e[8] }), "keyed: the key, " + kv.Key);
                    else Eq("[0,-1,0]", J(new[] { e[6], e[7], e[8] }), "unkeyed: the sentinel, " + kv.Key);
                }
            }
            Check(seen[0] > 0 && seen[1] > 0 && seen[2] > 0, "every state occurs: " + seen[0] + "/" + seen[1] + "/" + seen[2]);
            Eq("[0,7,0,0,-1,0,0,-1,0,0]", J(C.HitSentEntry(0, 7, 0, 0, default(C.LastReset), false)), "default(LastReset) reads as none");
        }

        // B9 drift: the sign is POSITIVE when the other seat's stamps run fast;
        // jumps are counted on the residuals after the line, not on the raw minima.
        private static void Drift()
        {
            var xs = new List<long>(); var ys = new List<long>();
            for (int i = 0; i < 30; i++) { xs.Add(i * 10000L); ys.Add((long)Math.Round(i * 10000L * 0.003)); }
            var d = C.Drift(xs, ys);
            Eq(300000L, d[0], "3000 ppm fast = +300000 centi-ppm");
            Eq(30L, d[1], "fit_n");
            Eq(0L, d[2], "a steady slope of 30 ms per bucket is not a jump");
            for (int i = 0; i < 30; i++) ys[i] = -ys[i];
            Eq(-300000L, C.Drift(xs, ys)[0], "slow = negative");
            for (int i = 0; i < 30; i++) ys[i] = i < 15 ? 0 : 48;
            var j = C.Drift(xs, ys);
            Check(j[2] >= 1, "a 48 ms step counts as a jump after detrending: " + j[2]);
            Eq(0L, C.Drift(new List<long> { 5 }, new List<long> { 9 })[0], "one point, no rate");
        }

        // L8: changing congestion with STABLE minima reads no drift; a fit on
        // means (or on any sample but the minimum) would read the congestion.
        private static void Congestion()
        {
            var log = new C.SampleLog();
            int t0 = 1000;
            var rng = new C.Rng(7);
            for (int ms = 0; ms < 300000; ms += 33)
            {
                int spread = ms < 150000 ? 5 : 80;      // queue delay widens in the second half
                int delay = ms % 330 == 0 ? 0 : (int)(rng.Next() % (uint)spread);
                int stamp = t0 + ms;                    // the other seat's clock runs true
                long sw = ms + delay;                   // arrival on this seat's Stopwatch
                int arr = t0 + ms + delay;
                log.Add(arr, 60 + delay, 0, true, stamp, sw);
            }
            var d = log.DriftTriple(t0);
            Check(Math.Abs(d[0]) < 2000, "stable minima read ~0 drift (centi-ppm): " + d[0]);
            Eq(0L, d[2], "no jumps");
            Check(d[1] >= 29, "one minimum per 10 s bucket: " + d[1]);
        }

        // age_b is cut against the FINAL t0, with epochs and the -1..720 range.
        private static void Buckets()
        {
            var log = new C.SampleLog();
            log.Add(100, 50, 0, false, 0, 0);      // rel -900 -> bucket -1
            log.Add(1000, 40, 1, true, 0, 0);       // rel 0 -> bucket 0
            log.Add(10999, 70, 2, false, 0, 0);     // rel 9999 -> bucket 0
            log.Add(11000, 90, 2, false, 0, 0);     // rel 10000 -> bucket 1
            log.Add(-20000000, 1, 0, false, 0, 0);  // far before: out of range
            var b = log.AgeBuckets(1000);
            Eq(3, b.Count, "three buckets");
            Eq("[-1,0,0,1,50,50]", J(b[0]), "bucket -1");
            Eq("[0,1,2,2,40,40]", J(b[1]), "bucket 0: ep0 1, ep1 2, n 2, min 40, p50 (lower) 40");
            Eq("[1,2,2,1,90,90]", J(b[2]), "bucket 1");
            var b2 = log.AgeBuckets(1001);
            Eq("[-1,0,1,2,40,40]", J(b2[0]), "a different t0 cuts different windows");
            Eq("[0,2,2,2,70,70]", J(b2[1]), "the rest fall in bucket 0");
            // wrap: t0 near int.MaxValue, arrival past the wrap
            var w = new C.SampleLog();
            w.Add(int.MinValue + 5, 10, 0, false, 0, 0);
            Eq("[0,0,0,1,10,10]", J(w.AgeBuckets(int.MaxValue - 4)[0]), "rel wraps on int32");
        }

        private static void Cadence()
        {
            var c = new C.Cadence();
            int[] stamps = { 0, 33, 33, 66, 50, 100, 200, 300 };
            long sw = 0;
            foreach (var s in stamps) { c.Add(s, sw); sw += 100; }
            // distinct, forward gaps only: 33, 33, 34, 100, 100
            var f = c.Five();
            Eq(33L, f[0], "p10"); Eq(34L, f[1], "p50");
            Eq(33L, f[2], "first half p50"); Eq(100L, f[3], "second half p50");
            Eq(8L * 100000 / 700, f[4], "batches per 100 s");
        }

        private static void Ordinals()
        {
            var o = new C.Ordinals();
            Eq(0, o.Next(5, 0, 0), "first"); Eq(1, o.Next(5, 0, 0), "second same prefix");
            Eq(0, o.Next(5, 1, 0), "another kind"); Eq(2, o.Next(5, 0, 0), "third");
            for (int i = 0; i < 300; i++) o.Next(9, 9, 9);
            Eq(255, o.Next(9, 9, 9), "capped at 255");
            // F4: a fixed ring of KEEP prefixes; the oldest is forgotten first
            var r = new C.Ordinals();
            r.Next(1, 0, 0); r.Next(1, 0, 0);
            for (int i = 0; i < C.Ordinals.KEEP - 1; i++) r.Next(1000 + i, 0, 0);
            Eq(2, r.Next(1, 0, 0), "held while the ring has room");
            r.Next(5000, 0, 0);
            Eq(0, r.Next(1, 0, 0), "the oldest prefix forgotten once the ring is full");
        }

        /// <summary>Fix pass 4, F4: a hook-written map refuses a NEW key at its
        /// cap and counts the refusal; an existing key is always updated; the
        /// cap is at least one; Clear and TakeRefused reset.</summary>
        private static void CappedMapCase()
        {
            var m = new C.CappedMap<int, int>(3);
            Check(m.Set(1, 10) && m.Set(2, 20) && m.Set(3, 30), "three keys below the cap are set");
            Check(!m.Set(4, 40), "a new key at the cap is refused");
            Eq(3, m.Count, "never above the cap");
            int v;
            Check(!m.TryGetValue(4, out v) && !m.ContainsKey(4), "the refused key is absent");
            Check(m.Set(2, 21), "an existing key at the cap is updated");
            Check(m.TryGetValue(2, out v) && v == 21, "the update is kept");
            Check(m.Admit(3), "a present key is admitted at the cap");
            Check(!m.Admit(5), "a new key is not admitted at the cap");
            Eq(2, m.Refused, "both refusals counted (one set, one admit)");
            Eq(2, m.TakeRefused(), "the refusals taken");
            Eq(0, m.Refused, "zero after taking");
            Check(m.Remove(1) && m.Set(6, 60), "a freed slot takes a new key");
            Eq(0, m.Refused, "no refusal below the cap");
            int n = 0;
            foreach (var kv in m) n++;
            Eq(3, n, "enumerates exactly what it holds");
            m.Clear();
            Eq(0, m.Count, "cleared");
            Check(m.Set(7, 70), "usable after a clear");
            var z = new C.CappedMap<int, int>(0);
            Eq(1, z.Cap, "the cap is at least one");
            Check(z.Set(1, 1) && !z.Set(2, 2), "a cap of one holds one key");
        }

        /// <summary>Fix pass 4, F4: a block admits in one forward pass; the
        /// admitted hits come back in arrival order and the rest stay pending,
        /// in arrival order.</summary>
        private static void WindowBlockOrder()
        {
            var w = new C.HitWindow();
            long[] st = { 2000, 9950, 3000, 10500, 4000, 10900, 5000 };
            foreach (var s in st) Check(!w.Offer(new long[] { 0, s, 0, 0, 0, 0, 0, -1 }, (int)s), "no block yet: " + s + " waits");
            var a = w.Block(10000, 1);
            Eq(3, a.Count, "the three hits inside the window admitted");
            Eq(9950L, a[0][1], "admitted 1st"); Eq(10500L, a[1][1], "admitted 2nd"); Eq(10900L, a[2][1], "admitted 3rd");
            Eq(4, w.Pending.Count, "the four outside stay pending");
            Eq(2000L, w.Pending[0][1], "pending 1st"); Eq(3000L, w.Pending[1][1], "pending 2nd");
            Eq(4000L, w.Pending[2][1], "pending 3rd"); Eq(5000L, w.Pending[3][1], "pending 4th");
            Eq(0, w.Block(10000, 1).Count, "nothing admitted twice");
            Eq(4, w.Pending.Count, "a block that admits nothing leaves pending whole");
        }

        /// <summary>Fix pass 2, F4: the window's lists are hard-capped.</summary>
        private static void WindowCaps()
        {
            var w = new C.HitWindow();
            for (int i = 0; i < 10; i++) w.Block(100000 * (i + 1), 1);
            Eq(C.HitWindow.RECENT_CAP, w.RecentBlocks.Count, "recent blocks capped");
            for (int i = 0; i < 70; i++) w.Offer(new long[] { 0, 5000000 + i, 0, 0, 0, 0, 0, -1 }, 5000000 + i);
            Eq(C.HitWindow.PENDING_CAP, w.Pending.Count, "pending hits capped");
            Eq(64, w.Block(5000000, 1).Count, "one block admits at most the cap");
        }

        private static void Window()
        {
            var w = new C.HitWindow();
            var early = new long[] { 0, 900, 0, 0, 0, 0, 0, -1 };
            Check(!w.Offer(early, 900), "no block yet: waits");
            var admitted = w.Block(1000, 1);
            Eq(1, admitted.Count, "a hit 100 ms before the block stamp is admitted when the block comes");
            Check(w.Offer(new long[] { 0, 1900, 0, 0, 0, 0, 0, -1 }, 1900), "+900 admitted");
            Check(!w.Offer(new long[] { 0, 1901, 0, 0, 0, 0, 0, -1 }, 1901), "+901 waits");
            Check(!w.Offer(new long[] { 0, 899, 0, 0, 0, 0, 0, -1 }, 899), "-101 waits");
        }

        private static void Decide()
        {
            long d; string why;
            var p = new C.Pending { FirstUnix = 1000, Attempts = 1 };
            Eq(C.Act.Drop, C.Decide(p, 200, "{\"status\":\"recorded\"}", 0, 1001, out d, out why), "200");
            Eq(C.Act.Drop, C.Decide(p, 200, "{\"status\":\"already_recorded\"}", 0, 1001, out d, out why), "200 already");
            Eq("already_recorded", why, "named");
            Eq(C.Act.Drop, C.Decide(p, 400, "{}", 0, 1001, out d, out why), "400");
            Eq(C.Act.Drop, C.Decide(p, 403, "{}", 0, 1001, out d, out why), "403");
            Eq(C.Act.Drop, C.Decide(p, 413, "{}", 0, 1001, out d, out why), "413");
            Eq(C.Act.Drop, C.Decide(p, 422, "{\"detail\":\"hit_recv\"}", 0, 1001, out d, out why), "422");
            Eq("field:hit_recv", why, "422 names the field");
            Eq(C.Act.Drop, C.Decide(p, 409, "{\"status\":\"conflict\"}", 0, 1001, out d, out why), "409 conflict");
            Eq(C.Act.Retry, C.Decide(p, 409, "{\"status\":\"not_ready\"}", 0, 1001, out d, out why), "409 not_ready");
            Eq(C.Act.RetryNextLaunch, C.Decide(p, 404, "", 0, 1001, out d, out why), "404 waits for the next launch");
            Eq(C.Act.Retry, C.Decide(p, 429, "", 900, 1001, out d, out why), "429"); Eq(900L, d, "Retry-After honoured");
            Eq(C.Act.Retry, C.Decide(p, 503, "{\"error\":\"seat_evidence_off\"}", 0, 1001, out d, out why), "503");
            Eq(C.Act.Retry, C.Decide(p, 0, "timeout", 0, 1001, out d, out why), "transport");
            var s = new C.Pending { FirstUnix = 1000, Attempts = 1 };
            for (int i = 0; i < 5; i++) Eq(C.Act.RefreshAndRetry, C.Decide(s, 401, "", 0, 1001, out d, out why), "401 #" + i);
            Eq(C.Act.Drop, C.Decide(s, 401, "", 0, 1001, out d, out why), "the sixth 401 drops");
            var spent = new C.Pending { FirstUnix = 1000, Attempts = 20 };
            Eq(C.Act.Drop, C.Decide(spent, 0, "", 0, 1001, out d, out why), "20 attempts in all");
            Eq(C.Act.Drop, C.Decide(spent, 503, "", 0, 1001, out d, out why), "20 attempts bound a 503 too");
            var old = new C.Pending { FirstUnix = 1000, Attempts = 1 };
            Eq(C.Act.Drop, C.Decide(old, 404, "", 0, 1000 + C.EXPIRY_S, out d, out why), "404 expires at 7 days");
            Eq(C.Act.Drop, C.Decide(old, 0, "", 0, 1000 + C.EXPIRY_S, out d, out why), "anything expires at 7 days");
            Eq(C.Act.Retry, C.Decide(old, 0, "", 0, 999 + C.EXPIRY_S, out d, out why), "not before");
            int st; string body; int ra;
            C.ParseAnswer(false, "HTTP 429: {\"error\":\"rate_limited\"}\nRetry-After: 600", out st, out body, out ra);
            Eq(429, st, "status parsed"); Eq(600, ra, "retry-after parsed"); Eq("{\"error\":\"rate_limited\"}", body, "body parsed");
            C.ParseAnswer(false, "Cannot resolve destination host", out st, out body, out ra);
            Eq(0, st, "transport has no status");
            C.ParseAnswer(true, "{\"status\":\"recorded\"}", out st, out body, out ra);
            Eq(200, st, "success");
        }

        private static void Line()
        {
            var p = new C.Pending { Route = "e", Body = "{\"a\":\"x\\ty\"}", FirstUnix = 1759400000, Attempts = 3, SessionRetries = 2 };
            var q = C.ParseLine(C.Line(p));
            Check(q != null, "parses");
            Eq(p.Body, q.Body, "body"); Eq(p.FirstUnix, q.FirstUnix, "first"); Eq(3, q.Attempts, "attempts persist");
            Eq(2, q.SessionRetries, "session retries persist"); Eq("e", q.Route, "route");
            Check(C.ParseLine("se1\t1\t2\t3\te\tx") == null, "another tag is not ours");
            Check(C.ParseLine("se2\t1\t2\t3\tz\tx") == null, "unknown route");
            // F6: the next-eligible time persists; a first-build line reads it as 0
            p.NotBeforeUnix = 1759400777;
            var r = C.ParseLine(C.Line(p));
            Eq(1759400777L, r.NotBeforeUnix, "next-eligible time persists");
            Check(C.Line(p).StartsWith("se3\t"), "written as se3");
            var v2 = C.ParseLine("se2\t1759400000\t4\t1\tk\t{\"b\":1}");
            Check(v2 != null, "an se2 line still reads");
            Eq(4, v2.Attempts, "se2 attempts"); Eq(0L, v2.NotBeforeUnix, "se2 has no next-eligible time"); Eq("k", v2.Route, "se2 route");
            Check(C.ParseLine("se3\t1\t2\t3\tx\te\tb") == null, "a non-number next-eligible time refused");
        }

        // F6: the limits hold before EVERY transmission, and a transmission is
        // counted (with its next-eligible time) before it leaves.
        private static void Refusal()
        {
            var p = new C.Pending { Route = "e", Body = "{}", FirstUnix = 1000, Attempts = 0 };
            Eq((string)null, C.SendRefusal(p, 1001), "fresh: may send");
            Eq("expired", C.SendRefusal(p, 1000 + C.EXPIRY_S), "seven days: settled unsent");
            Eq((string)null, C.SendRefusal(p, 999 + C.EXPIRY_S), "a second earlier: may send");
            p.Attempts = C.MAX_ATTEMPTS - 1;
            Eq((string)null, C.SendRefusal(p, 1001), "19 spent: one more");
            p.Attempts = C.MAX_ATTEMPTS;
            Eq("attempts_spent", C.SendRefusal(p, 1001), "20 spent: settled unsent, whatever answers came before");
            var q = new C.Pending { Route = "c", Body = "{}", FirstUnix = 1000, Attempts = 3, SessionRetries = 2, NotBeforeUnix = 5 };
            var t = C.AfterTransmission(q, 2000);
            Eq(4, t.Attempts, "the transmission is counted");
            Eq(2000 + C.Backoff(4), t.NotBeforeUnix, "and its next-eligible time set");
            Eq(3, q.Attempts, "the original is not changed until the write succeeds");
            Eq(2, t.SessionRetries, "session retries carried"); Eq("c", t.Route, "route carried"); Eq(1000L, t.FirstUnix, "first carried");
            var once = C.AfterTransmission(new C.Pending { Route = "e", Body = "{}", FirstUnix = 1000 }, 1500);
            Check(once.NotBeforeUnix > 1500, "a first transmission also persists a future next-eligible time");
        }

        // F8: the queue file's trailer, both copies weighed, the newest whole wins.
        private static void Queue()
        {
            var a = new C.Pending { Route = "e", Body = "{\"a\":1}", FirstUnix = 100, Attempts = 1, NotBeforeUnix = 7 };
            var b = new C.Pending { Route = "k", Body = "{\"b\":2}", FirstUnix = 200 };
            string one = C.QueueText(new List<C.Pending> { a }, 1);
            string two = C.QueueText(new List<C.Pending> { a, b }, 2);
            var p1 = C.ParseQueue(one, true);
            Check(p1.Whole && p1.Generation == 1 && p1.Items.Count == 1, "a written copy is whole");
            Eq(7L, p1.Items[0].NotBeforeUnix, "items read back");
            var empty = C.ParseQueue(C.QueueText(new List<C.Pending>(), 3), false);
            Check(empty.Whole && empty.Generation == 3 && empty.Items.Count == 0, "an empty queue is a whole copy with a generation");
            var t2 = C.ParseQueue(two, false);
            Eq(2, C.ChooseCopy(p1, t2), "the newer whole temporary is recovered");
            Eq(1, C.ChooseCopy(C.ParseQueue(two, true), C.ParseQueue(one, false)), "the newer whole primary is kept");
            Eq(1, C.ChooseCopy(p1, C.ParseQueue(C.QueueText(new List<C.Pending>(), 1), false)), "a tie keeps the primary");
            Eq(2, C.ChooseCopy(p1, empty), "a newer EMPTY temporary outranks an older copy that names requests");
            // a temporary torn mid-write: trailer intact, a line altered
            string torn = two.Replace("{\"b\":2}", "{\"b\":3}");
            Check(torn != two, "the planted damage is there");
            var tt = C.ParseQueue(torn, false);
            Check(!tt.Whole, "a hash mismatch is not whole");
            Eq(1, C.ChooseCopy(p1, tt), "a torn newer temporary loses to the whole primary");
            // a truncated temporary (no trailer) is never whole
            var cut = C.ParseQueue(two.Substring(0, two.IndexOf("#se-queue", StringComparison.Ordinal)), false);
            Check(!cut.Whole, "no trailer: a temporary is not whole");
            Eq(1, C.ChooseCopy(p1, cut), "the whole primary wins");
            // a primary written by a build before the trailer
            var legacy = C.ParseQueue(C.Line(a) + "\n" + "se2\t1\t2\t3\tc\t{}\n", true);
            Check(legacy.Whole && legacy.Generation == 0 && legacy.Items.Count == 2, "a legacy primary is whole at generation 0");
            Eq(2, C.ChooseCopy(legacy, t2), "any whole temporary outranks it");
            Eq(1, C.ChooseCopy(legacy, null), "alone it is recovered");
            Eq(0, C.ChooseCopy(new C.QueueCopy(), new C.QueueCopy()), "nothing present: nothing");
        }

        private static void Build()
        {
            Check(C.BuildTupleOk(new string('9', 16), new string('v', 16), new string('c', 12)), "46 characters in all is the limit");
            Check(!C.BuildTupleOk(new string('9', 17), "standalone", "abc"), "version over 16 refused");
            Check(!C.BuildTupleOk("1.0", new string('v', 17), "abc"), "variant over 16 refused");
            Check(!C.BuildTupleOk("1.0", "standalone", new string('c', 13)), "commit over 12 refused");
            Check(!C.BuildTupleOk("1.0", "stand alone", "abc"), "space refused");
            Check(C.SplitBuild("1.41.0|standalone|378a80342ec9") != null, "splits");
            Check(C.SplitBuild("1.41.0|standalone") == null, "two parts refused");
            Eq(46, C.OtherBuild(new string('x', 46)).Length, "46 relayed kept");
            Eq("", C.OtherBuild(new string('x', 47)), "47 relayed is not the field");
            Eq("", C.OtherBuild("a\"b"), "a quote is not the field");
            var caps = C.OtherCaps(new[] { "cr_zz", "cr_build", "x_other", "cr_bad-key", "cr_build", null });
            Eq("cr_build,cr_zz", string.Join(",", caps), "cr_ keys only, valid, sorted, unique");
            Eq(16, C.CompatPlugins(new[] { "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q" }).Count, "16 GUIDs");
        }

        private static void Reservoir()
        {
            var r = new C.Reservoir(512, 99);
            for (int i = 0; i < 10000; i++) r.Add(i % 1000);
            Eq(10000L, r.N, "n exact"); Eq(999, r.Max, "max exact"); Eq(0, r.Min, "min exact");
            Eq(512, r.Items.Count, "bounded");
            int p50 = r.Pct(50);
            Check(p50 > 400 && p50 < 600, "p50 near the middle: " + p50);
            var a = new C.AgeStats(1);
            Eq("[0,0,0,0]", J(a.Four()), "no samples");
            a.Add(700000); a.Add(-700000);
            Eq("[-600000,-600000,600000,2]", J(a.Four()), "ms clamped (p50 and p90 are the lower of two), n exact");
        }

        private static void Envelope()
        {
            string rec = C.Budget(Sample(2, false).ToObj());
            string seat = "76561198000000001", other = "76561198000000002";
            string stable = "ranked_abc_123456", attach = stable + "_r8";
            string canon = C.Canonical(seat, other, stable, attach, rec);
            Check(canon.StartsWith("seat-evidence:v2:" + seat + ":" + other + ":"), "canonical head");
            string sig = C.Hmac(Encoding.UTF8.GetBytes("k"), canon);
            Eq(64, sig.Length, "hex64");
            Check(C.Envelope(seat, other, stable, attach, rec, sig) != null, "envelope");
            Check(C.Envelope(seat, seat, stable, attach, rec, sig) == null, "same seat refused");
            Check(C.Envelope(seat, other, stable, stable + "_r123", rec, sig) == null, "3-digit suffix refused");
            Check(C.Envelope(seat, other, "a b", "a b_r1", rec, sig) == null, "space in the key refused");
            Check(C.Envelope(seat, other, stable, attach, rec + "é", sig) == null, "non-ASCII record refused");
            Check(C.IsAttachKey(new string('k', 60), new string('k', 60) + "_r9"), "63 bytes ok");
            Check(!C.IsAttachKey(new string('k', 60), new string('k', 60) + "_r99x"), "suffix shape");
        }

        // The end kind of a cut game (amendment A1): absent on a game this seat
        // saw over, right after "rounds" otherwise, only a known kind; the cut
        // score follows the report the game gets.
        private static void End()
        {
            var r = Sample(1, false);
            string over = C.Json(r.ToObj());
            Check(!over.Contains("\"end\""), "no end key on a game seen over");
            Check(over.Contains("\"rounds\":[5,3],\"build\":"), "rounds then build when no end");
            r.End = "other_left";
            Check(C.Json(r.ToObj()).Contains("\"rounds\":[5,3],\"end\":\"other_left\",\"build\":"), "end right after rounds");
            r.End = "quit";
            Check(!C.Json(r.ToObj()).Contains("\"end\""), "an unknown kind is never written");
            foreach (var k in new[] { "left", "other_left", "lost", "closing" }) Check(C.IsEndKind(k), "kind " + k);
            Check(!C.IsEndKind(null) && !C.IsEndKind("") && !C.IsEndKind("Left"), "not kinds");
            Eq("[4,5]", J(Array.ConvertAll(C.CutScore(4, 4, false), x => (long)x)), "the leaver of a tied 4-4 carries the awarded 5");
            Eq("[4,4]", J(Array.ConvertAll(C.CutScore(4, 4, true), x => (long)x)), "the other seat left first: as observed");
            Eq("[3,4]", J(Array.ConvertAll(C.CutScore(3, 4, false), x => (long)x)), "below match point: as observed");
            Eq("[4,2]", J(Array.ConvertAll(C.CutScore(4, 2, false), x => (long)x)), "not tied: as observed");
            Eq("[5,4]", J(Array.ConvertAll(C.CutScore(5, 4, false), x => (long)x)), "F2: a 5-4 is not the tied state: as observed");
            Eq("[4,5]", J(Array.ConvertAll(C.CutScore(4, 5, false), x => (long)x)), "F2: a 4-5 keeps the observed score");        }

        // The compat sender's step (V1 6.4): only a disabled seat with a queued
        // outcome acts; never without consent; gives up after the bound.
        private static void Sender()
        {
            long lim = C.COMPAT_SEND_LIMIT_MS;
            Eq(C.SendStep.Stop, C.CompatSenderStep(false, true, true, true, 0), "an enabled seat: the queue's own pump sends");
            Eq(C.SendStep.Stop, C.CompatSenderStep(true, true, false, true, 0), "nothing queued");
            Eq(C.SendStep.NoConsent, C.CompatSenderStep(true, false, true, true, 0), "no consent: nothing sent");
            Eq(C.SendStep.NoConsent, C.CompatSenderStep(true, false, true, false, lim + 1), "no consent wins over the bound");
            Eq(C.SendStep.Auth, C.CompatSenderStep(true, true, true, false, 0), "no session: the ticket exchange");
            Eq(C.SendStep.Auth, C.CompatSenderStep(true, true, true, false, lim), "the bound is inclusive");
            Eq(C.SendStep.GiveUp, C.CompatSenderStep(true, true, true, false, lim + 1), "past the bound: give up");
            Eq(C.SendStep.GiveUp, C.CompatSenderStep(true, true, true, true, lim + 1), "past the bound even with a session");
            Eq(C.SendStep.Post, C.CompatSenderStep(true, true, true, true, 10), "a session: post");
        }

        private static C.Pending Queued(C.Record r, long firstUnix)
        {
            string rec = C.Budget(r.ToObj());
            string seat = "76561198000000001", other = "76561198000000002", stable = "ranked_abc_123456", attach = stable + "_r8";
            string env = C.Envelope(seat, other, stable, attach, rec, C.Hmac(Encoding.UTF8.GetBytes("k"), C.Canonical(seat, other, stable, attach, rec)));
            return new C.Pending { Route = "e", Body = env, FirstUnix = firstUnix, Attempts = 1 };
        }

        // Integrator ruling on A1: a 422 on a cut game's record keeps it for
        // the next launch (same cap, expiry and attempt bound); any other
        // record's 422 still drops.
        private static void Cut422()
        {
            long now = 1000000000, d; string why;
            var cut = Sample(3, false); cut.End = "lost";
            var full = Sample(3, false);
            Check(C.IsCutRecord(Queued(cut, now)), "a record with end is a cut game's");
            Check(!C.IsCutRecord(Queued(full, now)), "a record without end is not");
            var elsewhere = Queued(full, now);
            elsewhere.Body = elsewhere.Body.Replace("\\\"blk_faults\\\":", "\\\"z\\\":0,\\\"end\\\":\\\"left\\\",\\\"blk_faults\\\":");
            Check(elsewhere.Body.Contains(",\\\"end\\\":\\\""), "the planted text is there");
            Check(!C.IsCutRecord(elsewhere), "end anywhere but right after rounds is not");
            var c = Queued(cut, now);
            c.Route = "c";
            Check(!C.IsCutRecord(c), "a compat outcome is not");
            string ans = "{\"detail\":\"end\"}";
            Eq(C.Act.RetryNextLaunch, C.Decide(Queued(cut, now), 422, ans, 0, now + 10, out d, out why), "cut game 422: kept");
            Eq("cut_game_field:end", why, "reason");
            Eq(C.Act.Drop, C.Decide(Queued(full, now), 422, ans, 0, now + 10, out d, out why), "full game 422: dropped");
            Eq(C.Act.Drop, C.Decide(Queued(cut, now), 422, ans, 0, now + C.EXPIRY_S, out d, out why), "cut game 422 past expiry: dropped");
            Eq("expired", why, "expired reason");
            var spent = Queued(cut, now); spent.Attempts = C.MAX_ATTEMPTS;
            Eq(C.Act.Drop, C.Decide(spent, 422, ans, 0, now + 10, out d, out why), "cut game 422 with attempts spent: dropped");
            Eq(C.Act.Drop, C.Decide(Queued(cut, now), 403, "", 0, now + 10, out d, out why), "a cut game's other refusals unchanged");
        }

        // -- the server-comparison fixtures --------------------------------------------

        private static void Fixtures(string dir)
        {
            Directory.CreateDirectory(dir);
            byte[] key = Encoding.UTF8.GetBytes("fixture-key-not-a-secret");
            var cases = new List<KeyValuePair<string, C.Record>>
            {
                new KeyValuePair<string, C.Record>("small", Sample(3, false)),
                new KeyValuePair<string, C.Record>("cap160", Sample(160, false)),
                new KeyValuePair<string, C.Record>("over160_wide", Sample(200, true)),
                new KeyValuePair<string, C.Record>("empty", Sample(0, false)),
            };
            var nulls = Sample(5, false); nulls.ClkPpm = null; nulls.OtherPub = null; nulls.Compat = "not_run"; nulls.DllState = "no_location"; nulls.DllSha = "";
            nulls.GameDllState = "ok"; nulls.GameDllSha = "";   // a hash that never arrived is not "ok"
            cases.Add(new KeyValuePair<string, C.Record>("nulls", nulls));
            var pub = Sample(40, true); pub.OtherPub = new long[] { 144, 60, 300, 41, 30, 18 }; pub.OtherBuildV = "1.41.0|standalone|0123456789ab";
            pub.T0Src = "o"; pub.Master = 0; pub.Omit[1] = 7;
            cases.Add(new KeyValuePair<string, C.Record>("pub_omit_seed", pub));
            // amendment A1: a cut game's end kind (compared with the amended
            // reference in run_tests.py; the current server refuses the key)
            var left = Sample(4, false); left.End = "left"; left.RoundsSelf = 4; left.RoundsOther = 5;
            cases.Add(new KeyValuePair<string, C.Record>("end_left", left));
            var closing = Sample(200, true); closing.End = "closing";
            cases.Add(new KeyValuePair<string, C.Record>("end_closing_over", closing));
            var lines = new StringBuilder();
            foreach (var kv in cases)
            {
                var obj = kv.Value.ToObj();
                string full = C.Json(obj);               // the unbudgeted input, as the reference reads it
                string rec = C.Budget(obj);
                string seat = "76561198000000001", other = "76561198000000002";
                string stable = "ranked_room_" + kv.Key + "_123456", attach = stable + "_r8";
                string sig = C.Hmac(key, C.Canonical(seat, other, stable, attach, rec));
                string env = C.Envelope(seat, other, stable, attach, rec, sig);
                File.WriteAllText(Path.Combine(dir, kv.Key + ".input.json"), full, new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(dir, kv.Key + ".record.txt"), rec, new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(dir, kv.Key + ".envelope.json"), env, new UTF8Encoding(false));
                lines.Append(kv.Key).Append('\n');
            }
            var plugins = C.CompatPlugins(new[] { "com.example.one", "bad guid!", "two_2" });
            string ccanon = C.CompatCanonical("76561198000000001", "not_run", plugins);
            string cbody = C.CompatBody("76561198000000001", "not_run", plugins, C.Hmac(key, ccanon));
            File.WriteAllText(Path.Combine(dir, "compat.json"), cbody, new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(dir, "cases.txt"), lines.ToString(), new UTF8Encoding(false));
            // amended B7: every entry the client writes over the state space (all must be admitted) ...
            var space = new List<object>();
            foreach (var kv in B7Space()) space.Add(kv.Value);
            File.WriteAllText(Path.Combine(dir, "b7_states.json"), C.Json(space), new UTF8Encoding(false));
            // ... and the refused combinations, each with the field the amended contract names (first failing rule)
            File.WriteAllText(Path.Combine(dir, "b7_negative.json"), C.Json(B7Negative()), new UTF8Encoding(false));
            Console.WriteLine("fixtures written: " + cases.Count + " records + compat + b7 " + space.Count + " states, " + B7Negative().Count + " refused");
        }

        /// <summary>The refused hit_sent combinations of the amended B7, written
        /// from the contract text as [field, entry]: every rule at least twice,
        /// the rule order where two rules fail, and the entry bound.</summary>
        private static List<object> B7Negative()
        {
            Func<long, long, long, long, long, long[]> E = (since, tb, kind, ord, reset) => new long[] { 0, 7, 0, 0, since, 0, tb, kind, ord, reset };
            var l = new List<object>();
            Action<string, long[]> N = (f, e) => l.Add(new List<object> { f, e });
            N("hit_sent.reset_none_since", E(0, 0, -1, 0, 0));
            N("hit_sent.reset_none_since", E(600000, 0, -1, 0, 0));
            N("hit_sent.reset_none_since", E(250, 5, 2, 1, 0));          // both rules fail: since first
            N("hit_sent.reset_none_last", E(-1, 5, 2, 1, 0));
            N("hit_sent.reset_none_last", E(-1, 0, 0, 0, 0));
            N("hit_sent.reset_none_last", E(-1, 0, -1, 3, 0));           // a sentinel with an ordinal is not the sentinel
            N("hit_sent.reset_none_last", E(-1, 7, -1, 0, 0));
            N("hit_sent.reset_keyed_since", E(-1, 5, 2, 1, 1));
            N("hit_sent.reset_keyed_since", E(-1, 0, -1, 0, 1));         // both rules fail: since first
            N("hit_sent.reset_keyed_last", E(250, 0, -1, 0, 1));
            N("hit_sent.reset_keyed_last", E(0, 7, -1, 2, 1));
            N("hit_sent.reset_unkeyed_since", E(-1, 0, -1, 0, 2));
            N("hit_sent.reset_unkeyed_since", E(-1, 5, 2, 1, 2));        // both rules fail: since first
            N("hit_sent.reset_unkeyed_last", E(250, 5, 2, 1, 2));
            N("hit_sent.reset_unkeyed_last", E(50, 0, 0, 0, 2));
            N("hit_sent.reset_unkeyed_last", E(50, 0, -1, 4, 2));
            N("hit_sent", new long[] { 0, 2000500, 0, 0, 50, 1, 0, -1, 0 });   // the round 5 entry, nine elements
            N("hit_sent", E(50, 0, -1, 0, 3));
            N("hit_sent", E(50, 0, -1, 0, -1));
            N("hit_sent", new long[] { 0, 7, 0, 0, 50, 0, 0, -1, 0, 2, 0 });
            return l;
        }

        private static readonly Dictionary<string, Action> Cases = new Dictionary<string, Action>
        {
            { "json", Json }, { "budget", Budget }, { "entries", Entries }, { "b7", B7 }, { "drift", Drift },
            { "congestion", Congestion }, { "buckets", Buckets }, { "cadence", Cadence }, { "ordinals", Ordinals }, { "window_caps", WindowCaps },
            { "window", Window }, { "decide", Decide }, { "line", Line }, { "build", Build },
            { "reservoir", Reservoir }, { "envelope", Envelope }, { "end", End }, { "sender", Sender }, { "cut422", Cut422 },
            { "refusal", Refusal }, { "queue", Queue }, { "capped_map", CappedMapCase }, { "window_block_order", WindowBlockOrder },
        };

        private static int Main(string[] args)
        {
            if (args.Length == 2 && args[0] == "fixtures") { Fixtures(args[1]); return 0; }
            var run = args.Length == 0 ? new List<string>(Cases.Keys) : new List<string>(args);
            int failed = 0;
            foreach (var name in run)
            {
                Action a;
                if (!Cases.TryGetValue(name, out a)) { Console.WriteLine("UNKNOWN " + name); failed++; continue; }
                try { a(); Console.WriteLine("PASS " + name); }
                catch (Exception ex) { Console.WriteLine("FAIL " + name + ": " + ex.Message); failed++; }
            }
            Console.WriteLine(failed == 0 ? "ALL PASS" : failed + " FAILED");
            return failed == 0 ? 0 : 1;
        }
    }
}
