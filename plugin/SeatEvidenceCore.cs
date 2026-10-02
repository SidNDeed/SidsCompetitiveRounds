using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>SEAT EVIDENCE, the pure half (contract V2,
    /// ai-collab/integrity-1001/SEAT-EVIDENCE-CONTRACT-V2.md). What one seat
    /// records about one ranked game and sends once after it: its own build and
    /// clocks, the age, rate and cadence of the other seat's messages, the
    /// shots, hits and pushes it saw, and the block and hit lists both seats key
    /// the same way. No Unity, no Photon: tools/tests/seat-evidence-client
    /// compiles this file as it ships.
    ///
    /// This half records and serialises. It holds no threshold and decides
    /// nothing about a seat: every number it emits is a count, a stamp, a
    /// percentile or a fit of what arrived, and the server compares.
    ///
    /// The record text must be byte-identical to the server's reference
    /// budgeter (backend/api/seat_evidence.py::budget_record, which serialises
    /// with json.dumps(separators=(",", ":"), ensure_ascii=True)); the harness
    /// runs both over the same fixtures and compares the bytes.</summary>
    internal static class SeatEvidenceCore
    {
        internal const int CONTRACT = 2;
        internal const int SCHEMA = 2;
        internal const int RECORD_MAX_BYTES = 12288;
        internal const int LIST_CAP = 160;
        internal const long BIG = 10000000L;
        internal const int MS_BOUND = 600000;
        internal const int BUCKET_MS = 10000;
        internal const int BUCKET_MIN = -1, BUCKET_MAX = 720;
        /// <summary>The five lists the budgeter trims, in its tie order.</summary>
        internal static readonly string[] LIST_ORDER = { "blk_sent", "hit_recv", "blk_recv", "hit_sent", "age_b" };

        // -- clamps (every bound below is the contract's field bound) --------------

        internal static long Clamp(long v, long lo, long hi) { return v < lo ? lo : (v > hi ? hi : v); }
        internal static long Cnt(long v) { return Clamp(v, 0, BIG); }
        internal static long Ms(long v) { return Clamp(v, -MS_BOUND, MS_BOUND); }

        /// <summary>a - b on the wrapping int32 Photon clock (the server's
        /// wrap_diff).</summary>
        internal static int WrapDiff(int a, int b) { return unchecked(a - b); }

        /// <summary>floor(x / d) for a positive d.</summary>
        internal static int FloorDiv(int x, int d) { int q = x / d; if ((x % d != 0) && (x < 0)) q--; return q; }

        // -- JSON (Python json.dumps(separators=(",",":"), ensure_ascii=True)) ----

        /// <summary>An object whose keys keep their insertion order.</summary>
        internal sealed class JObj
        {
            internal readonly List<string> Keys = new List<string>();
            internal readonly List<object> Values = new List<object>();
            internal JObj Add(string k, object v) { Keys.Add(k); Values.Add(v); return this; }
            internal object Get(string k) { int i = Keys.IndexOf(k); return i >= 0 ? Values[i] : null; }
            internal void Set(string k, object v) { int i = Keys.IndexOf(k); if (i >= 0) Values[i] = v; else Add(k, v); }
        }

        internal static string Json(object v)
        {
            var sb = new StringBuilder(1024);
            Write(sb, v);
            return sb.ToString();
        }

        private static void Write(StringBuilder sb, object v)
        {
            if (v == null) { sb.Append("null"); return; }
            if (v is string) { WriteString(sb, (string)v); return; }
            if (v is long) { sb.Append(((long)v).ToString(CultureInfo.InvariantCulture)); return; }
            if (v is int) { sb.Append(((int)v).ToString(CultureInfo.InvariantCulture)); return; }
            if (v is JObj)
            {
                var o = (JObj)v;
                sb.Append('{');
                for (int i = 0; i < o.Keys.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    WriteString(sb, o.Keys[i]);
                    sb.Append(':');
                    Write(sb, o.Values[i]);
                }
                sb.Append('}');
                return;
            }
            if (v is long[])
            {
                var a = (long[])v;
                sb.Append('[');
                for (int i = 0; i < a.Length; i++) { if (i > 0) sb.Append(','); sb.Append(a[i].ToString(CultureInfo.InvariantCulture)); }
                sb.Append(']');
                return;
            }
            if (v is System.Collections.IList)
            {
                var l = (System.Collections.IList)v;
                sb.Append('[');
                for (int i = 0; i < l.Count; i++) { if (i > 0) sb.Append(','); Write(sb, l[i]); }
                sb.Append(']');
                return;
            }
            throw new ArgumentException("not a record value: " + v.GetType().Name);
        }

        /// <summary>Python's ensure_ascii escaping: '"' and '\\' escaped, the five
        /// short control forms, every other character outside ' '..'~' as a
        /// lowercase \uXXXX per UTF-16 unit (which is how Python writes a
        /// surrogate pair too).</summary>
        internal static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    default:
                        if (c >= ' ' && c <= '~') sb.Append(c);
                        else sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        break;
                }
            }
            sb.Append('"');
        }

        // -- string bounds (the server's regexes, applied before anything is sent) --

        internal static bool IsSteamId(string s)
        {
            if (s == null || s.Length < 15 || s.Length > 20) return false;
            for (int i = 0; i < s.Length; i++) if (s[i] < '0' || s[i] > '9') return false;
            return true;
        }

        /// <summary>stable_game_key: 1-60 printable ASCII '!'..'~' without '"' and '\'.</summary>
        internal static bool IsStableKey(string s)
        {
            if (s == null || s.Length < 1 || s.Length > 60) return false;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c < '!' || c > '~' || c == '"' || c == '\\') return false;
            }
            return true;
        }

        /// <summary>attach_key: exactly stable + "_r" + 1 or 2 digits, at most 64.</summary>
        internal static bool IsAttachKey(string stable, string attach)
        {
            if (!IsStableKey(stable) || attach == null || attach.Length > 64) return false;
            if (!attach.StartsWith(stable, StringComparison.Ordinal)) return false;
            string tail = attach.Substring(stable.Length);
            if (tail.Length < 3 || tail.Length > 4 || tail[0] != '_' || tail[1] != 'r') return false;
            for (int i = 2; i < tail.Length; i++) if (tail[i] < '0' || tail[i] > '9') return false;
            return true;
        }

        /// <summary>One build component: [A-Za-z0-9._+-]{0,max}.</summary>
        internal static bool IsBuildPart(string s, int max)
        {
            if (s == null || s.Length > max) return false;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
                          || c == '.' || c == '_' || c == '+' || c == '-';
                if (!ok) return false;
            }
            return true;
        }

        /// <summary>L7: the complete "version|variant|commit" tuple, each
        /// component inside its limit (16, 16, 12; 46 in all). A tuple that is
        /// not is refused before it is published, never cut.</summary>
        internal static bool BuildTupleOk(string version, string variant, string commit)
        {
            return IsBuildPart(version, 16) && IsBuildPart(variant, 16) && IsBuildPart(commit, 12);
        }

        /// <summary>Splits "version|variant|commit" into its three parts, or
        /// null when it is not exactly that shape inside the limits.</summary>
        internal static string[] SplitBuild(string tuple)
        {
            if (tuple == null) return null;
            string[] p = tuple.Split('|');
            if (p.Length != 3 || !BuildTupleOk(p[0], p[1], p[2])) return null;
            return p;
        }

        /// <summary>other_build: the other seat's cr_build exactly as relayed
        /// when it fits the field ([ -~] without '"' and '\', at most 46), else "".</summary>
        internal static string OtherBuild(string relayed)
        {
            if (relayed == null || relayed.Length > 46) return "";
            for (int i = 0; i < relayed.Length; i++)
            {
                char c = relayed[i];
                if (c < ' ' || c > '~' || c == '"' || c == '\\') return "";
            }
            return relayed;
        }

        /// <summary>other_caps: the other seat's cr_ key names that fit
        /// [A-Za-z0-9_]{1,32}, ordinal-sorted, at most 64.</summary>
        internal static List<string> OtherCaps(IEnumerable<string> keys)
        {
            var outp = new List<string>();
            if (keys == null) return outp;
            foreach (var k in keys)
            {
                if (k == null || !k.StartsWith("cr_", StringComparison.Ordinal) || k.Length > 32) continue;
                bool ok = true;
                for (int i = 0; i < k.Length && ok; i++)
                {
                    char c = k[i];
                    ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_';
                }
                if (ok && !outp.Contains(k)) outp.Add(k);
            }
            outp.Sort(StringComparer.Ordinal);
            if (outp.Count > 64) outp.RemoveRange(64, outp.Count - 64);
            return outp;
        }

        // -- sampling (private state: never the game's RNG) -------------------------

        /// <summary>xorshift32 owned by one collector.</summary>
        internal sealed class Rng
        {
            private uint _s;
            internal Rng(uint seed) { _s = seed == 0 ? 2463534242u : seed; }
            internal uint Next() { uint x = _s; x ^= x << 13; x ^= x >> 17; x ^= x << 5; _s = x; return x; }
        }

        /// <summary>Uniform reservoir (algorithm R) of at most Cap samples, with
        /// the exact count, minimum and maximum beside it.</summary>
        internal sealed class Reservoir
        {
            internal readonly int Cap;
            internal readonly List<int> Items = new List<int>();
            internal long N;
            internal int Min = int.MaxValue, Max = int.MinValue;
            private readonly Rng _rng;
            internal Reservoir(int cap, uint seed) { Cap = cap; _rng = new Rng(seed); }
            internal void Add(int v)
            {
                N++;
                if (v < Min) Min = v;
                if (v > Max) Max = v;
                if (Items.Count < Cap) { Items.Add(v); return; }
                long j = (long)(_rng.Next() % (ulong)N);
                if (j < Cap) Items[(int)j] = v;
            }
            internal int Pct(int p) { return Percentile(Items, p); }
        }

        /// <summary>The p-th percentile of the values: the element at index
        /// floor((n-1) * p / 100) of the sorted copy; 0 for none.</summary>
        internal static int Percentile(IList<int> values, int p)
        {
            if (values == null || values.Count == 0) return 0;
            var s = new List<int>(values);
            s.Sort();
            long idx = (long)(s.Count - 1) * p / 100;
            return s[(int)idx];
        }

        /// <summary>Message age for one class: own server-time estimate at
        /// dispatch minus the sender's envelope stamp (ms).</summary>
        internal sealed class AgeStats
        {
            internal readonly Reservoir R;
            internal AgeStats(uint seed) { R = new Reservoir(512, seed); }
            internal void Add(int ageMs) { R.Add(ageMs); }
            internal long[] Four()
            {
                if (R.N == 0) return new long[] { 0, 0, 0, 0 };
                return new long[] { Ms(R.Pct(50)), Ms(R.Pct(90)), Ms(R.Max), Cnt(R.N) };
            }
            internal long[] Three()
            {
                if (R.N == 0) return new long[] { 0, 0, 0 };
                return new long[] { Ms(R.Pct(50)), Ms(R.Max), Cnt(R.N) };
            }
        }

        // -- 10 s age buckets, offset epochs, drift (B9) ----------------------------

        /// <summary>The raw samples behind age_b and drift, kept so the 10 s
        /// buckets can be cut against the record's FINAL t0: a seat that is not
        /// master adopts the master's T0 when it adopts the shared token, which
        /// can be after the game started (B5), and both records must cut the
        /// same windows for the server to join their buckets. Bounded: past CAP
        /// samples the rest are counted in Dropped.</summary>
        internal sealed class SampleLog
        {
            internal const int CAP = 65536;
            internal readonly List<int> Arr = new List<int>();     // own server-time estimate at dispatch (raw int32)
            internal readonly List<int> Age = new List<int>();     // ms
            internal readonly List<int> Ep = new List<int>();      // own offset-update count at the sample
            internal readonly List<bool> View = new List<bool>();  // a view batch (drift input) or an RPC
            internal readonly List<int> Stamp = new List<int>();   // the sender's stamp
            internal readonly List<long> Sw = new List<long>();    // own Stopwatch ms at dispatch
            internal long Dropped;

            internal void Add(int arrivalEst, int ageMs, long epoch, bool view, int stamp, long swMs)
            {
                if (Arr.Count >= CAP) { Dropped++; return; }
                Arr.Add(arrivalEst); Age.Add(ageMs); Ep.Add((int)Clamp(epoch, 0, 1000000));
                View.Add(view); Stamp.Add(stamp); Sw.Add(swMs);
            }

            private int Index(int i, int t0) { return FloorDiv(WrapDiff(Arr[i], t0), BUCKET_MS); }

            /// <summary>age_b: [bucket, ep0, ep1, n, min, p50] for every bucket in
            /// -1..720 with a sample, ascending; ep0/ep1 are the own offset-update
            /// counts at the bucket's first and last sample in local order.</summary>
            internal List<long[]> AgeBuckets(int t0)
            {
                var by = new SortedDictionary<int, List<int>>();
                var ep0 = new Dictionary<int, int>();
                var ep1 = new Dictionary<int, int>();
                for (int i = 0; i < Arr.Count; i++)
                {
                    int b = Index(i, t0);
                    if (b < BUCKET_MIN || b > BUCKET_MAX) continue;
                    List<int> l;
                    if (!by.TryGetValue(b, out l)) { l = new List<int>(); by[b] = l; ep0[b] = Ep[i]; }
                    l.Add(Age[i]);
                    ep1[b] = Ep[i];
                }
                var outp = new List<long[]>();
                foreach (var kv in by)
                {
                    var l = kv.Value;
                    int min = int.MaxValue;
                    foreach (var a in l) if (a < min) min = a;
                    outp.Add(new long[] { kv.Key, ep0[kv.Key], ep1[kv.Key], Cnt(l.Count), Ms(min), Ms(Percentile(l, 50)) });
                }
                return outp;
            }

            /// <summary>drift over the view batches. Per bucket the least-delayed
            /// batch: the MAXIMUM of y = (stamp - own Stopwatch), unwrapped
            /// against the first view sample, which is the minimum transit
            /// (arrival - stamp) of the bucket, at x = its own Stopwatch; then
            /// Drift(xs, ys). Queueing only ever adds delay, so the bucket's
            /// fastest batch is the one a congestion change moves least (L8).</summary>
            internal long[] DriftTriple(int t0)
            {
                var bestY = new SortedDictionary<int, long>();
                var atX = new Dictionary<int, long>();
                bool has = false; int refStamp = 0; long refSw = 0;
                for (int i = 0; i < Arr.Count; i++)
                {
                    if (!View[i]) continue;
                    int b = Index(i, t0);
                    if (b < BUCKET_MIN || b > BUCKET_MAX) continue;
                    if (!has) { has = true; refStamp = Stamp[i]; refSw = Sw[i]; }
                    long x = Sw[i] - refSw;
                    long y = (long)WrapDiff(Stamp[i], refStamp) - x;
                    long cur;
                    if (!bestY.TryGetValue(b, out cur) || y > cur) { bestY[b] = y; atX[b] = x; }
                }
                var xs = new List<long>(); var ys = new List<long>();
                foreach (var kv in bestY) { xs.Add(atX[kv.Key]); ys.Add(kv.Value); }
                return Drift(xs, ys);
            }

            internal void Clear() { Arr.Clear(); Age.Clear(); Ep.Clear(); View.Clear(); Stamp.Clear(); Sw.Clear(); Dropped = 0; }
        }

        /// <summary>B9 drift. Least-squares line of y = (other's stamp - own
        /// Stopwatch) on x = own Stopwatch, both ms, over each 10 s bucket's
        /// least-delayed batch (SampleLog.DriftTriple). rate = slope in centi-ppm (1 = 0.01 ppm): POSITIVE means the
        /// other seat's stamp clock advances faster than this seat's
        /// Stopwatch. jumps = steps of 20 ms or more between consecutive
        /// residuals after the fitted line is removed. Fewer than two points:
        /// [0, n, 0].</summary>
        internal static long[] Drift(IList<long> xs, IList<long> ys)
        {
            int n = xs.Count;
            if (n < 2) return new long[] { 0, n, 0 };
            double mx = 0, my = 0;
            for (int i = 0; i < n; i++) { mx += xs[i]; my += ys[i]; }
            mx /= n; my /= n;
            double sxx = 0, sxy = 0;
            for (int i = 0; i < n; i++) { double dx = xs[i] - mx; sxx += dx * dx; sxy += dx * (ys[i] - my); }
            if (sxx <= 0) return new long[] { 0, n, 0 };
            double slope = sxy / sxx;
            double icept = my - slope * mx;
            long jumps = 0;
            double prev = 0;
            for (int i = 0; i < n; i++)
            {
                double r = ys[i] - (icept + slope * xs[i]);
                if (i > 0 && Math.Abs(r - prev) >= 20.0) jumps++;
                prev = r;
            }
            long rate = (long)Math.Round(slope * 1e8, MidpointRounding.AwayFromZero);
            return new long[] { Clamp(rate, -100000000, 100000000), Cnt(n), Cnt(jumps) };
        }

        // -- cadence ------------------------------------------------------------------

        /// <summary>Distinct-stamp gaps of the other seat's player view stream.</summary>
        internal sealed class Cadence
        {
            internal const int GAP_CAP = 32768;
            internal readonly List<int> Gaps = new List<int>();
            internal readonly List<long> GapSw = new List<long>();
            internal long Batches;
            internal long FirstSw = -1, LastSw = -1;
            private bool _has;
            private int _prev;

            internal void Add(int stamp, long swMs)
            {
                Batches++;
                if (FirstSw < 0) FirstSw = swMs;
                LastSw = swMs;
                if (!_has) { _has = true; _prev = stamp; return; }
                int gap = WrapDiff(stamp, _prev);
                if (gap <= 0) return;          // same stamp, or reordered: not a new batch interval
                _prev = stamp;
                if (Gaps.Count < GAP_CAP) { Gaps.Add(gap); GapSw.Add(swMs); }
            }

            /// <summary>cad: [p10, p50, p50 first half, p50 second half,
            /// batches per 100 s]; the halves split at the midpoint of this
            /// seat's own Stopwatch between the first and last batch.</summary>
            internal long[] Five()
            {
                long dur = LastSw - FirstSw;
                long mid = FirstSw + dur / 2;
                var a = new List<int>(); var b = new List<int>();
                for (int i = 0; i < Gaps.Count; i++) { if (GapSw[i] <= mid) a.Add(Gaps[i]); else b.Add(Gaps[i]); }
                long rate = dur > 0 ? Batches * 100000L / dur : 0;
                return new long[] { Clamp(Percentile(Gaps, 10), 0, MS_BOUND), Clamp(Percentile(Gaps, 50), 0, MS_BOUND),
                                    Clamp(Percentile(a, 50), 0, MS_BOUND), Clamp(Percentile(b, 50), 0, MS_BOUND),
                                    Clamp(rate, 0, MS_BOUND) };
            }
        }

        // -- event lists, ordinals ---------------------------------------------------------

        /// <summary>The first LIST_CAP entries in local order; later ones are
        /// counted (the budgeter's step 1, applied as they arrive, gives the
        /// same output as truncating at build).</summary>
        internal sealed class EventList
        {
            internal readonly List<long[]> Items = new List<long[]>();
            internal long Omitted;
            internal void Add(long[] e) { if (Items.Count < LIST_CAP) Items.Add(e); else Omitted++; }
        }

        /// <summary>ord: the 0-based count of earlier events with the same key
        /// prefix on this seat ((tb, kind) for blocks, (path, stamp, pid) for
        /// hits), capped at 255. Bounded memory: the oldest prefixes are
        /// forgotten past KEEP (their stamps are seconds old by then).</summary>
        internal sealed class Ordinals
        {
            internal const int KEEP = 1024;
            private readonly Dictionary<string, int> _seen = new Dictionary<string, int>();
            private readonly Queue<string> _order = new Queue<string>();
            internal int Next(long a, long b, long c)
            {
                string k = a.ToString(CultureInfo.InvariantCulture) + ":" + b.ToString(CultureInfo.InvariantCulture)
                           + ":" + c.ToString(CultureInfo.InvariantCulture);
                int n;
                if (_seen.TryGetValue(k, out n)) { _seen[k] = n + 1; return n > 255 ? 255 : n; }
                _seen[k] = 1;
                _order.Enqueue(k);
                while (_order.Count > KEEP) _seen.Remove(_order.Dequeue());
                return 0;
            }
            internal void Clear() { _seen.Clear(); _order.Clear(); }
        }

        /// <summary>A hit waiting for its admission: listed only when some block
        /// stamp tb of the same victim has wrap_diff(hit stamp, tb) in
        /// [-100, 900] (the window the server classifies in). Hits arrive before
        /// a later block's stamp is known, so recent ones wait here.</summary>
        internal sealed class HitWindow
        {
            internal const int LO = -100, HI = 900, PENDING_CAP = 64;
            internal readonly List<long[]> Pending = new List<long[]>();
            internal readonly List<int> RecentBlocks = new List<int>();

            /// <summary>Returns true when the hit is admitted now; otherwise it
            /// is kept (bounded) for a block stamp that may follow.</summary>
            internal bool Offer(long[] hit, int stamp)
            {
                for (int i = 0; i < RecentBlocks.Count; i++)
                {
                    int d = WrapDiff(stamp, RecentBlocks[i]);
                    if (d >= LO && d <= HI) return true;
                }
                Pending.Add(hit);
                if (Pending.Count > PENDING_CAP) Pending.RemoveAt(0);
                return false;
            }

            /// <summary>A block stamp: admits (and returns, in arrival order) the
            /// pending hits inside its window. `stampIndex` is the hit entry's
            /// stamp position.</summary>
            internal List<long[]> Block(int tb, int stampIndex)
            {
                RecentBlocks.Add(tb);
                if (RecentBlocks.Count > 8) RecentBlocks.RemoveAt(0);
                var admitted = new List<long[]>();
                for (int i = 0; i < Pending.Count; i++)
                {
                    int d = WrapDiff((int)Pending[i][stampIndex], tb);
                    if (d >= LO && d <= HI) { admitted.Add(Pending[i]); Pending.RemoveAt(i); i--; }
                }
                return admitted;
            }

            internal void Clear() { Pending.Clear(); RecentBlocks.Clear(); }
        }

        // -- the record ---------------------------------------------------------------------

        /// <summary>Every section-2 key, in the contract's order. Values are
        /// clamped to their bounds as they are set, so the server's check
        /// cannot refuse a record this seat built.</summary>
        internal sealed class Record
        {
            internal int T0;
            internal string T0Src = "o";
            internal int Master, Ranked;
            internal int RoundsSelf, RoundsOther;
            /// <summary>How the game ended as this seat observed it (END_KINDS),
            /// or null when this seat saw the game over: the "end" key is then
            /// absent (contract amendment A1, build notes).</summary>
            internal string End;
            internal string[] Build = { "", "", "" };
            internal string DllSha = "", DllState = "no_location";
            internal string GameDllSha = "", GameDllState = "no_location";
            internal string Compat = "not_run";
            internal long ForeignAsm, ForeignOwners;
            internal long RttAvg, RttMax;
            internal long OffsetUpdates, OffsetStepMax;
            internal long[] ClkPpm;            // null when unread
            internal long MonoSend;
            internal long[] AgeView = { 0, 0, 0, 0 }, AgeRpc = { 0, 0, 0, 0 };
            internal long[] AgeHit = { 0, 0, 0 }, AgeBlk = { 0, 0, 0 };
            internal List<long[]> AgeB = new List<long[]>();
            internal long[] DriftV = { 0, 0, 0 };
            internal long[] Cad = { 0, 0, 0, 0, 0 };
            internal long[] Obs = new long[10];
            internal string OtherBuildV = "";
            internal List<string> OtherCapsV = new List<string>();
            internal long[] OtherPub;          // null when unread
            internal long[] Shots = { 0, 0, 0 };
            internal long FireFloor;
            internal long[] Imp = { 0, 0, 0 };
            internal long[] Dec = { 0, 0 };
            internal long[] Push = new long[7];
            internal List<long[]> BlkSent = new List<long[]>(), HitRecv = new List<long[]>();
            internal List<long[]> BlkRecv = new List<long[]>(), HitSent = new List<long[]>();
            internal long BlkFaults;
            internal long UnpairBlocks, UnpairHits;
            internal long[] Omit = new long[5];  // LIST_ORDER

            internal List<long[]> List(int i)
            {
                switch (i) { case 0: return BlkSent; case 1: return HitRecv; case 2: return BlkRecv; case 3: return HitSent; default: return AgeB; }
            }

            private static long[] C(long[] a, long lo, long hi)
            {
                var r = new long[a.Length];
                for (int i = 0; i < a.Length; i++) r[i] = Clamp(a[i], lo, hi);
                return r;
            }

            /// <summary>An age tuple: every position but the last is ms, the last is n.</summary>
            private static long[] AgeC(long[] a)
            {
                var r = new long[a.Length];
                for (int i = 0; i < a.Length; i++) r[i] = i == a.Length - 1 ? Cnt(a[i]) : Ms(a[i]);
                return r;
            }

            private static object Dll(string sha, string state)
            {
                bool ok = state == "ok" && sha != null && sha.Length == 64;
                return new List<object> { ok ? sha : "", ok ? "ok" : (state == "read_failed" ? "read_failed" : "no_location") };
            }

            /// <summary>The record as an ordered object (contract section 2 order).</summary>
            internal JObj ToObj()
            {
                var o = new JObj();
                o.Add("schema", (long)SCHEMA);
                o.Add("t0", (long)T0);
                o.Add("t0_src", T0Src == "m" ? "m" : "o");
                o.Add("master", (long)(Master != 0 ? 1 : 0));
                o.Add("ranked", (long)(Ranked != 0 ? 1 : 0));
                o.Add("rounds", new long[] { Clamp(RoundsSelf, 0, 9), Clamp(RoundsOther, 0, 9) });
                if (IsEndKind(End)) o.Add("end", End);
                o.Add("build", new List<object> { Build[0], Build[1], Build[2] });
                o.Add("dll", Dll(DllSha, DllState));
                o.Add("game_dll", Dll(GameDllSha, GameDllState));
                o.Add("compat", Compat == "pass" ? "pass" : "not_run");
                o.Add("foreign", new long[] { Clamp(ForeignAsm, 0, 9999), Clamp(ForeignOwners, 0, 9999) });
                o.Add("rtt", new long[] { Clamp(RttAvg, 0, 60000), Clamp(RttMax, 0, 60000) });
                o.Add("offset", new long[] { Clamp(OffsetUpdates, 0, 1000000), Clamp(OffsetStepMax, 0, 1000000) });
                o.Add("clk_ppm", ClkPpm == null ? null : (object)C(ClkPpm, -1000000, 1000000));
                o.Add("mono_send", MonoSend < 0 ? 0L : MonoSend);
                o.Add("age", new JObj().Add("view", AgeC(AgeView)).Add("rpc", AgeC(AgeRpc))
                                        .Add("hit", AgeC(AgeHit)).Add("blk", AgeC(AgeBlk)));
                o.Add("age_b", new List<long[]>(AgeB));
                o.Add("drift", new long[] { Clamp(DriftV[0], -100000000, 100000000), Cnt(DriftV[1]), Cnt(DriftV[2]) });
                o.Add("cad", C(Cad, 0, MS_BOUND));
                o.Add("obs", C(Obs, 0, BIG));
                o.Add("other_build", OtherBuild(OtherBuildV));
                o.Add("other_caps", new List<object>(OtherCapsV.ConvertAll(s => (object)s)));
                o.Add("other_pub", OtherPub == null ? null : (object)C(OtherPub, 0, BIG));
                o.Add("shots", C(Shots, 0, BIG));
                o.Add("fire_floor", Cnt(FireFloor));
                o.Add("imp", C(Imp, 0, BIG));
                o.Add("dec", C(Dec, 0, BIG));
                o.Add("push", C(Push, 0, BIG));
                o.Add("blk_sent", new List<long[]>(BlkSent));
                o.Add("hit_recv", new List<long[]>(HitRecv));
                o.Add("blk_recv", new List<long[]>(BlkRecv));
                o.Add("hit_sent", new List<long[]>(HitSent));
                o.Add("blk_faults", Cnt(BlkFaults));
                o.Add("unpair", new long[] { Cnt(UnpairBlocks), Cnt(UnpairHits) });
                var om = new JObj();
                for (int i = 0; i < LIST_ORDER.Length; i++) om.Add(LIST_ORDER[i], Cnt(Omit[i]));
                o.Add("omit", om);
                return o;
            }
        }

        /// <summary>How a game that did not reach its game over ended, as one
        /// seat observed it: "left" (this seat left the room while the game was
        /// live), "other_left" (the other seat left or dropped while this seat
        /// stayed), "lost" (this seat's own connection dropped), "closing" (this
        /// seat's game was closing; the record is sent at its next launch).</summary>
        internal static readonly string[] END_KINDS = { "left", "other_left", "lost", "closing" };

        internal static bool IsEndKind(string k) { return k != null && Array.IndexOf(END_KINDS, k) >= 0; }

        /// <summary>The score a record of a cut game carries (and its attach
        /// key's round total), following the report that game gets: a seat
        /// that leaves a game tied at 4 or more each, with no departure of the
        /// other seat noted, carries the other seat's awarded 5 (the remaining
        /// seat's report awards it; the macro-evidence rule). Otherwise the
        /// score as observed.</summary>
        internal static int[] CutScore(int self, int other, bool otherLeft)
        {
            if (!otherLeft && self >= 4 && other >= 4) return new[] { self, 5 };
            return new[] { self, other };
        }

        /// <summary>The compat sender's next step (V1 6.4: a seat disabled by
        /// a finding makes ONE bounded attempt to send the queued outcome, then
        /// stays disabled). Stop: nothing to do (not disabled, or nothing
        /// queued); NoConsent: the seat has not granted data consent, so nothing
        /// is sent; GiveUp: the bound ran out (the outcome stays queued for the
        /// next launch); Auth: obtain a session through the existing Steam
        /// ticket exchange; Post: send it now.</summary>
        internal enum SendStep { Stop, NoConsent, GiveUp, Auth, Post }

        internal const long COMPAT_SEND_LIMIT_MS = 60000;

        internal static SendStep CompatSenderStep(bool disabled, bool consent, bool queued, bool hasToken, long elapsedMs)
        {
            if (!disabled || !queued) return SendStep.Stop;
            if (!consent) return SendStep.NoConsent;
            if (elapsedMs > COMPAT_SEND_LIMIT_MS) return SendStep.GiveUp;
            return hasToken ? SendStep.Post : SendStep.Auth;
        }

        /// <summary>The record keys in order (the server's RECORD_KEYS). The
        /// optional "end" key, when present, follows "rounds".</summary>
        internal static readonly string[] RECORD_KEYS =
        {
            "schema", "t0", "t0_src", "master", "ranked", "rounds", "build", "dll", "game_dll", "compat",
            "foreign", "rtt", "offset", "clk_ppm", "mono_send", "age", "age_b", "drift", "cad", "obs",
            "other_build", "other_caps", "other_pub", "shots", "fire_floor", "imp", "dec", "push",
            "blk_sent", "hit_recv", "blk_recv", "hit_sent", "blk_faults", "unpair", "omit",
        };

        // -- the byte budgeter (contract section 4; port of budget_record) ----------------

        /// <summary>The record text, at most `limit` bytes, with `omit`
        /// counting every entry dropped: every list cut to its first 160, then
        /// while too long the list with the most entries (ties: the earliest in
        /// LIST_ORDER) loses its LAST entry. Deterministic.</summary>
        internal static string Budget(JObj rec, int limit = RECORD_MAX_BYTES)
        {
            var omitObj = (JObj)rec.Get("omit");
            var omit = new long[LIST_ORDER.Length];
            var lists = new List<long[]>[LIST_ORDER.Length];
            for (int i = 0; i < LIST_ORDER.Length; i++)
            {
                omit[i] = omitObj != null && omitObj.Get(LIST_ORDER[i]) is long ? (long)omitObj.Get(LIST_ORDER[i]) : 0;
                var l = new List<long[]>((IEnumerable<long[]>)rec.Get(LIST_ORDER[i]));
                if (l.Count > LIST_CAP) { omit[i] += l.Count - LIST_CAP; l.RemoveRange(LIST_CAP, l.Count - LIST_CAP); }
                lists[i] = l;
            }
            var outp = new JObj();
            for (int k = 0; k < rec.Keys.Count; k++) outp.Add(rec.Keys[k], rec.Values[k]);
            Func<JObj> omitNow = () =>
            {
                var om = new JObj();
                for (int i = 0; i < LIST_ORDER.Length; i++) om.Add(LIST_ORDER[i], omit[i]);
                return om;
            };
            // The length is kept as (the record with the five lists EMPTY) plus
            // each list's contents, so a removal costs one re-serialisation of
            // the scalar part rather than of the whole record. The text is
            // ASCII (ensure_ascii), so characters are bytes. The removal order
            // is the reference's, one entry at a time; only the bookkeeping is
            // cheaper, and the bytes are written once at the end.
            var entryLen = new List<int>[LIST_ORDER.Length];
            var content = new long[LIST_ORDER.Length];
            for (int i = 0; i < LIST_ORDER.Length; i++)
            {
                entryLen[i] = new List<int>(lists[i].Count);
                foreach (var e in lists[i]) entryLen[i].Add(Json(e).Length);
                content[i] = ContentLen(entryLen[i]);
                outp.Set(LIST_ORDER[i], new List<long[]>());
            }
            outp.Set("omit", omitNow());
            long total = Json(outp).Length;
            for (int i = 0; i < LIST_ORDER.Length; i++) total += content[i];
            while (total > limit)
            {
                int longest = -1;
                for (int i = 0; i < LIST_ORDER.Length; i++)
                    if (longest < 0 || lists[i].Count > lists[longest].Count) longest = i;
                if (lists[longest].Count == 0) throw new InvalidOperationException("the scalar fields alone exceed the limit");
                lists[longest].RemoveAt(lists[longest].Count - 1);
                entryLen[longest].RemoveAt(entryLen[longest].Count - 1);
                content[longest] = ContentLen(entryLen[longest]);
                omit[longest]++;
                outp.Set("omit", omitNow());
                total = Json(outp).Length;
                for (int i = 0; i < LIST_ORDER.Length; i++) total += content[i];
            }
            for (int i = 0; i < LIST_ORDER.Length; i++) outp.Set(LIST_ORDER[i], lists[i]);
            string body = Json(outp);
            if (body.Length != total) throw new InvalidOperationException("budgeter length bookkeeping disagrees with the text");
            return body;
        }

        /// <summary>The characters a list's entries add between its brackets.</summary>
        private static long ContentLen(List<int> lens)
        {
            long s = 0;
            for (int i = 0; i < lens.Count; i++) s += lens[i];
            return s + (lens.Count > 0 ? lens.Count - 1 : 0);
        }

        // -- list entries (contract section 2.4), clamped to the server's bounds -----

        internal const int I32_MIN = int.MinValue, I32_MAX = int.MaxValue;

        /// <summary>blk_sent: [tb, kind, ord, own_open].</summary>
        internal static long[] BlkSentEntry(int tb, int kind, int ord, long ownOpenMs)
        {
            return new long[] { tb, Clamp(kind, 0, 9), Clamp(ord, 0, 255), Ms(ownOpenMs) };
        }

        /// <summary>hit_recv: [path, stamp, pid, ord, arr, blocked, dmg, own_since].</summary>
        internal static long[] HitRecvEntry(int path, int stamp, long pid, int ord, int arr, bool blocked, bool dmg, long ownSinceMs)
        {
            return new long[] { Clamp(path, 0, 1), stamp, Clamp(pid, 0, I32_MAX), Clamp(ord, 0, 255), arr,
                                blocked ? 1 : 0, dmg ? 1 : 0, ownSinceMs < 0 ? -1 : Clamp(ownSinceMs, 0, MS_BOUND) };
        }

        /// <summary>blk_recv: [tb, kind, ord, ta, started].</summary>
        internal static long[] BlkRecvEntry(int tb, int kind, int ord, int ta, bool started)
        {
            return new long[] { tb, Clamp(kind, 0, 9), Clamp(ord, 0, 255), ta, started ? 1 : 0 };
        }

        /// <summary>hit_sent: [path, stamp, pid, ord, since_ms, blocked, last_tb,
        /// last_kind, last_ord]; [0, -1, 0] for last_* when no block reset the copy.</summary>
        internal static long[] HitSentEntry(int path, int stamp, long pid, int ord, long sinceMs, bool blocked,
                                            bool hasLast, int lastTb, int lastKind, int lastOrd)
        {
            return new long[] { Clamp(path, 0, 1), stamp, Clamp(pid, 0, I32_MAX), Clamp(ord, 0, 255),
                                sinceMs < 0 ? -1 : Clamp(sinceMs, 0, MS_BOUND), blocked ? 1 : 0,
                                hasLast ? lastTb : 0, hasLast ? Clamp(lastKind, 0, 9) : -1, hasLast ? Clamp(lastOrd, 0, 255) : 0 };
        }

        /// <summary>A Block.sinceBlock reading (seconds, TimeHandler clock) as
        /// whole ms, the way the game reads it (B7); -1 when no block reset it.</summary>
        internal static long SinceMs(bool everReset, float sinceBlockS)
        {
            if (!everReset || float.IsNaN(sinceBlockS)) return -1;
            if (sinceBlockS <= 0f) return 0;
            double ms = Math.Floor((double)sinceBlockS * 1000.0);
            return ms >= MS_BOUND ? MS_BOUND : (long)ms;
        }

        // -- signing and the envelope (contract section 1) -----------------------------------

        internal static string Sha256Hex(byte[] data)
        {
            using (var sha = SHA256.Create()) return Hex(sha.ComputeHash(data));
        }

        internal static string Hex(byte[] h)
        {
            var sb = new StringBuilder(h.Length * 2);
            foreach (byte b in h) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        internal static string Canonical(string seat, string other, string stable, string attach, string recordText)
        {
            return "seat-evidence:v2:" + seat + ":" + other + ":"
                   + Sha256Hex(Encoding.ASCII.GetBytes(stable)) + ":" + Sha256Hex(Encoding.ASCII.GetBytes(attach)) + ":"
                   + Sha256Hex(Encoding.ASCII.GetBytes(recordText));
        }

        internal static string Hmac(byte[] key, string canonical)
        {
            using (var h = new HMACSHA256(key)) return Hex(h.ComputeHash(Encoding.UTF8.GetBytes(canonical)));
        }

        /// <summary>The request body. Null when an envelope field is outside
        /// its bound (nothing is sent that the server would refuse as malformed).</summary>
        internal static string Envelope(string seat, string other, string stable, string attach, string recordText, string sig)
        {
            if (!IsSteamId(seat) || !IsSteamId(other) || seat == other) return null;
            if (!IsAttachKey(stable, attach)) return null;
            if (recordText == null || recordText.Length == 0 || Encoding.UTF8.GetByteCount(recordText) > RECORD_MAX_BYTES) return null;
            for (int i = 0; i < recordText.Length; i++) if (recordText[i] > '~') return null;
            if (sig == null || sig.Length != 64) return null;
            var o = new JObj().Add("contract", (long)CONTRACT).Add("seat_steam_id", seat).Add("other_steam_id", other)
                              .Add("stable_game_key", stable).Add("attach_key", attach).Add("record", recordText).Add("sig", sig);
            return Json(o);
        }

        // -- the compat outcome (contract section 5.1) ----------------------------------------

        internal static string CompatCanonical(string seat, string outcome, IList<string> plugins)
        {
            string joined = plugins == null ? "" : string.Join(",", plugins);
            return "compat-outcome:v1:" + seat + ":" + outcome + ":" + Sha256Hex(Encoding.ASCII.GetBytes(joined));
        }

        /// <summary>At most 16 plug-in GUIDs that fit [A-Za-z0-9_.-]{1,64}, in the
        /// order given; others are left out.</summary>
        internal static List<string> CompatPlugins(IEnumerable<string> guids)
        {
            var l = new List<string>();
            if (guids == null) return l;
            foreach (var g in guids)
            {
                if (l.Count >= 16) break;
                if (g == null || g.Length < 1 || g.Length > 64) continue;
                bool ok = true;
                for (int i = 0; i < g.Length && ok; i++)
                {
                    char c = g[i];
                    ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '-';
                }
                if (ok) l.Add(g);
            }
            return l;
        }

        /// <summary>The compat body; null for an outcome other than finding /
        /// not_run (a pass is never sent).</summary>
        internal static string CompatBody(string seat, string outcome, IList<string> plugins, string sig)
        {
            if (!IsSteamId(seat) || (outcome != "finding" && outcome != "not_run") || sig == null || sig.Length != 64) return null;
            var arr = new List<object>();
            foreach (var p in plugins) arr.Add(p);
            return Json(new JObj().Add("seat_steam_id", seat).Add("outcome", outcome).Add("plugins", arr).Add("sig", sig));
        }

        // -- the answers (contract section 5) ------------------------------------------------

        internal enum Act { Drop, Retry, RetryNextLaunch, RefreshAndRetry }

        internal const int MAX_ATTEMPTS = 20;
        internal const int MAX_SESSION_RETRIES = 5;
        internal const long EXPIRY_S = 7L * 24 * 3600;

        /// <summary>One queued request: the frozen body, when it was first
        /// queued (unix s), how many sends it has spent, how many 401 refreshes.</summary>
        internal sealed class Pending
        {
            internal string Route;   // "e" seat evidence, "c" compat outcome, "k" card draw evidence
            internal string Body;
            internal long FirstUnix;
            internal int Attempts;
            internal int SessionRetries;
            internal long NotBeforeUnix;
            internal bool HoldUntilNextLaunch;   // in memory only
        }

        /// <summary>What to do with a request after an answer. `status` is the
        /// HTTP status (0 = transport, no answer); `body` the answer text;
        /// `retryAfterS` the Retry-After header (0 = none). The attempt has
        /// already been counted in p.Attempts. `reason` names the row.</summary>
        internal static Act Decide(Pending p, int status, string body, int retryAfterS, long nowUnix, out long delayS, out string reason)
        {
            delayS = 0;
            reason = "";
            body = body ?? "";
            bool expired = nowUnix - p.FirstUnix >= EXPIRY_S;
            if (status >= 200 && status < 300) { reason = body.Contains("already_recorded") ? "already_recorded" : "recorded"; return Act.Drop; }
            if (status == 400) { reason = "malformed"; return Act.Drop; }
            if (status == 403) { reason = "signature"; return Act.Drop; }
            if (status == 413) { reason = "budgeter_fault"; return Act.Drop; }
            if (status == 422 && IsCutRecord(p))
            {
                // A cut game's record is the one a review most needs, and a
                // server without amendment A1 refuses its "end" key: keep it
                // (same cap, same expiry, same attempt bound) for the next launch.
                if (expired) { reason = "expired"; return Act.Drop; }
                if (p.Attempts >= MAX_ATTEMPTS) { reason = "attempts_spent"; return Act.Drop; }
                reason = "cut_game_field:" + DetailField(body);
                return Act.RetryNextLaunch;
            }
            if (status == 422) { reason = "field:" + DetailField(body); return Act.Drop; }
            if (status == 409 && body.Contains("\"conflict\"")) { reason = "conflict"; return Act.Drop; }
            if (expired) { reason = "expired"; return Act.Drop; }
            if (status == 404) { reason = "no_route"; return Act.RetryNextLaunch; }
            if (status == 401)
            {
                if (p.SessionRetries >= MAX_SESSION_RETRIES) { reason = "session_retries_spent"; return Act.Drop; }
                p.SessionRetries++;
                reason = "session";
                delayS = 30;
                return Act.RefreshAndRetry;
            }
            if (p.Attempts >= MAX_ATTEMPTS) { reason = "attempts_spent"; return Act.Drop; }
            if (status == 429) { reason = "rate"; delayS = retryAfterS > 0 ? retryAfterS : 600; return Act.Retry; }
            reason = status == 409 ? "not_ready" : (status == 503 ? "unavailable" : (status == 0 ? "transport" : "status_" + status));
            delayS = Backoff(p.Attempts);
            return Act.Retry;
        }

        /// <summary>Whether a queued game record is a cut game's (its record
        /// carries "end"). The first "rounds" key in the envelope body is the
        /// record's own: the envelope fields before "record" cannot hold a
        /// quote, and a string value inside the record is escaped twice there.
        /// "end", when present, follows that key's two-number array directly.</summary>
        internal static bool IsCutRecord(Pending p)
        {
            if (p != null && p.Route == "k") return IsCutCardBody(p.Body);
            if (p == null || p.Route != "e" || p.Body == null) return false;
            const string R = "\\\"rounds\\\":[";
            const string E = ",\\\"end\\\":\\\"";
            int i = p.Body.IndexOf(R, StringComparison.Ordinal);
            if (i < 0) return false;
            int j = p.Body.IndexOf(']', i + R.Length);
            return j > 0 && j + 1 + E.Length <= p.Body.Length && string.CompareOrdinal(p.Body, j + 1, E, 0, E.Length) == 0;
        }

        /// <summary>Whether a queued card draw record (route "k") is a cut
        /// game's: its record opens {"schema":1,"g":&lt;digits&gt; and, for a cut
        /// game, "end" follows "g" directly (the envelope fields before
        /// "record" cannot hold a quote, so the first match is the record's).</summary>
        internal static bool IsCutCardBody(string body)
        {
            if (body == null) return false;
            const string H = "\\\"schema\\\":1,\\\"g\\\":";
            const string K = ",\\\"end\\\":\\\"";
            int i = body.IndexOf(H, StringComparison.Ordinal);
            if (i < 0) return false;
            int k = i + H.Length;
            while (k < body.Length && body[k] >= '0' && body[k] <= '9') k++;
            return k > i + H.Length && k + K.Length <= body.Length && string.CompareOrdinal(body, k, K, 0, K.Length) == 0;
        }

        /// <summary>Retry spacing: 2 min doubling, at most an hour.</summary>
        internal static long Backoff(int attempts)
        {
            long d = 120;
            for (int i = 1; i < attempts && d < 3600; i++) d *= 2;
            return d > 3600 ? 3600 : d;
        }

        /// <summary>The field name a 422 names ({"detail":"<field>"}), bounded
        /// and reduced to [A-Za-z0-9_] for the one log line.</summary>
        internal static string DetailField(string body)
        {
            int i = body.IndexOf("\"detail\"", StringComparison.Ordinal);
            if (i < 0) return "?";
            int q = body.IndexOf('"', body.IndexOf(':', i) + 1);
            if (q < 0) return "?";
            var sb = new StringBuilder();
            for (int j = q + 1; j < body.Length && sb.Length < 32; j++)
            {
                char c = body[j];
                if (c == '"') break;
                if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_') sb.Append(c);
            }
            return sb.Length > 0 ? sb.ToString() : "?";
        }

        /// <summary>"HTTP 409: {...}\nRetry-After: 600" (the client's error text) to
        /// its parts; a transport failure has status 0.</summary>
        internal static void ParseAnswer(bool ok, string text, out int status, out string body, out int retryAfterS)
        {
            status = 0; body = text ?? ""; retryAfterS = 0;
            if (ok) { status = 200; return; }
            if (body.StartsWith("HTTP ", StringComparison.Ordinal))
            {
                int colon = body.IndexOf(':');
                int s;
                if (colon > 5 && int.TryParse(body.Substring(5, colon - 5), NumberStyles.Integer, CultureInfo.InvariantCulture, out s)) status = s;
                body = colon >= 0 ? body.Substring(colon + 1).Trim() : body;
            }
            int ra = body.LastIndexOf("\nRetry-After:", StringComparison.Ordinal);
            if (ra >= 0)
            {
                int n;
                if (int.TryParse(body.Substring(ra + 13).Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out n) && n > 0) retryAfterS = n;
                body = body.Substring(0, ra);
            }
        }

        // -- the queue file line -----------------------------------------------------------------

        internal const string LINE_TAG = "se2";

        /// <summary>One persisted request: tag, first-queued unix s, attempts,
        /// session retries, route, body (JSON escapes every tab and newline, so
        /// the body never contains either).</summary>
        internal static string Line(Pending p)
        {
            return LINE_TAG + "\t" + p.FirstUnix.ToString(CultureInfo.InvariantCulture) + "\t"
                   + p.Attempts.ToString(CultureInfo.InvariantCulture) + "\t"
                   + p.SessionRetries.ToString(CultureInfo.InvariantCulture) + "\t" + p.Route + "\t" + p.Body;
        }

        internal static Pending ParseLine(string line)
        {
            if (line == null) return null;
            string[] f = line.Split(new[] { '\t' }, 6);
            if (f.Length != 6 || f[0] != LINE_TAG || (f[4] != "e" && f[4] != "c" && f[4] != "k") || f[5].Length == 0) return null;
            long first; int att, ses;
            if (!long.TryParse(f[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out first)
                || !int.TryParse(f[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out att)
                || !int.TryParse(f[3], NumberStyles.Integer, CultureInfo.InvariantCulture, out ses))
                return null;
            return new Pending { FirstUnix = first, Attempts = att, SessionRetries = ses, Route = f[4], Body = f[5] };
        }
    }
}
