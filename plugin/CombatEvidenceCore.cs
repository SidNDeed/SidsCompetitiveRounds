using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using W = CompetitiveRounds.CombatEvidenceWire;
using C = CompetitiveRounds.SeatEvidenceCore;

namespace CompetitiveRounds
{
    /// <summary>Combat evidence (design V2, B1 B2 B3 B5), the pure half: the
    /// record as the server's layout (CombatEvidenceWire, generated from the
    /// server's COMBAT_WIRE) describes it, its serializer and budgeter (ports
    /// of the server's dumps / budget_record / _trim_one, byte for byte), the
    /// signing canonical and envelope, the per-gun cycle accountant (equal to
    /// the server's rebuild on complete groups), the single-precision bullet
    /// path references, and the bounded collectors the hooks fill. Nothing
    /// here touches the game. Every value it writes is a MEASUREMENT: the cycle
    /// labels are the game's own rule arithmetic the server repeats; no value
    /// here decides a review item (that lives in a private store).</summary>
    internal static class CombatEvidenceCore
    {
        internal static readonly string[] KEYS = W.KEYS;
        internal static readonly int N = W.KEYS.Length;
        internal static readonly int[] LIST_IX = ListIndices();
        private static readonly Dictionary<string, int> _ix = Index();

        /// <summary>The bound of the two loops over the layout's keys (the layout has
        /// W.KEYS.Length of them; the harness's proof mode asserts they fit).</summary>
        internal const int KEY_CAP = 64;

        private static Dictionary<string, int> Index()
        {
            var d = new Dictionary<string, int>(W.KEYS.Length);
            for (int i = 0; i < W.KEYS.Length && i < KEY_CAP; i++) d[W.KEYS[i]] = i;
            return d;
        }

        private static int[] ListIndices()
        {
            var l = new List<int>();
            for (int i = 0; i < W.KEYS.Length && i < KEY_CAP; i++) if (W.KIND[i] == W.K_LIST || W.KIND[i] == W.K_GROUPS) l.Add(i);
            return l.ToArray();
        }

        internal static int Ix(string key) { return _ix[key]; }

        /// <summary>The position of a list key in `omit` (LISTS order).</summary>
        internal static int OmitPos(string key) { return Array.IndexOf(LIST_IX, Ix(key)); }

        internal static long Clamp(long v, long lo, long hi) { return v < lo ? lo : (v > hi ? hi : v); }

        /// <summary>v on the wrapping signed 32-bit stamp clock (the server's wrap).</summary>
        internal static long Wrap(long v) { return (long)unchecked((int)(uint)(ulong)v); }

        // -- the record ---------------------------------------------------------------------

        /// <summary>One cycle group: header, shots, regenerations.</summary>
        internal sealed class Group
        {
            internal long[] H;
            internal List<long[]> S = new List<long[]>();
            internal List<long[]> R = new List<long[]>();
            internal Group Copy(int shotCap, int regenCap)
            {
                var g = new Group { H = H };
                for (int i = 0; i < S.Count && i < shotCap; i++) g.S.Add(S[i]);
                for (int i = 0; i < R.Count && i < regenCap; i++) g.R.Add(R[i]);
                return g;
            }
        }

        /// <summary>A record: one value per layout key, in layout order. int: long;
        /// enum: string; row/hist: long[]; rows/list: List of long[]; groups: List of
        /// Group; omit: long[] in list order.</summary>
        internal sealed class Rec
        {
            internal readonly object[] V = new object[W.KEYS.Length];
            internal object this[string key] { get { return V[Ix(key)]; } set { V[Ix(key)] = value; } }
            internal long[] Omit { get { return (long[])V[N - 1]; } }
        }

        private static long[] Zeros(int n) { return new long[n]; }

        /// <summary>A record with every key at its empty value: zero scalars at
        /// their lowest legal value, zero rows, empty lists, zero omit counts.</summary>
        internal static Rec Empty()
        {
            var r = new Rec();
            for (int i = 0; i < N; i++)
            {
                switch (W.KIND[i])
                {
                    case W.K_INT: r.V[i] = Clamp(0, W.LO[i][0], W.HI[i][0]); break;
                    case W.K_ENUM: r.V[i] = W.ENUMS[i][0]; break;
                    case W.K_ROW: r.V[i] = ZeroRow(i); break;
                    case W.K_ROWS:
                        var rows = new List<long[]>();
                        for (int k = 0; k < W.CAP[i]; k++) rows.Add(ZeroRow(i));
                        r.V[i] = rows; break;
                    case W.K_HIST: r.V[i] = Zeros(W.CAP[i]); break;
                    case W.K_LIST: r.V[i] = new List<long[]>(); break;
                    case W.K_GROUPS: r.V[i] = new List<Group>(); break;
                    default: r.V[i] = Zeros(LIST_IX.Length); break;
                }
            }
            return r;
        }

        /// <summary>A row of key i with every field at zero clamped into its bounds.</summary>
        internal static long[] ZeroRow(int i)
        {
            var lo = W.LO[i]; var hi = W.HI[i];
            var a = new long[lo.Length];
            for (int k = 0; k < a.Length; k++) a[k] = Clamp(0, lo[k], hi[k]);
            return a;
        }

        // -- serialization (Python json.dumps(separators=(",", ":"), ensure_ascii=True)) ------

        internal static string Dumps(Rec r)
        {
            var sb = new StringBuilder(20000);
            WriteRec(sb, r);
            return sb.ToString();
        }

        private static void Num(StringBuilder sb, long v) { sb.Append(v.ToString(CultureInfo.InvariantCulture)); }

        private static void Arr(StringBuilder sb, long[] a)
        {
            sb.Append('[');
            for (int i = 0; i < a.Length; i++) { if (i > 0) sb.Append(','); Num(sb, a[i]); }
            sb.Append(']');
        }

        private static void Rows(StringBuilder sb, List<long[]> l)
        {
            sb.Append('[');
            for (int i = 0; i < l.Count; i++) { if (i > 0) sb.Append(','); Arr(sb, l[i]); }
            sb.Append(']');
        }

        internal static void WriteGroup(StringBuilder sb, Group g)
        {
            sb.Append('['); Arr(sb, g.H); sb.Append(','); Rows(sb, g.S); sb.Append(','); Rows(sb, g.R); sb.Append(']');
        }

        private static void WriteRec(StringBuilder sb, Rec r)
        {
            sb.Append('{');
            for (int i = 0; i < N; i++)
            {
                if (i > 0) sb.Append(',');
                C.WriteString(sb, W.KEYS[i]);
                sb.Append(':');
                object v = r.V[i];
                switch (W.KIND[i])
                {
                    case W.K_INT: Num(sb, (long)v); break;
                    case W.K_ENUM: C.WriteString(sb, (string)v); break;
                    case W.K_ROW: case W.K_HIST: Arr(sb, (long[])v); break;
                    case W.K_ROWS: case W.K_LIST: Rows(sb, (List<long[]>)v); break;
                    case W.K_GROUPS:
                        var gs = (List<Group>)v;
                        sb.Append('[');
                        for (int k = 0; k < gs.Count; k++) { if (k > 0) sb.Append(','); WriteGroup(sb, gs[k]); }
                        sb.Append(']');
                        break;
                    default:
                        var om = (long[])v;
                        sb.Append('{');
                        for (int k = 0; k < LIST_IX.Length; k++)
                        {
                            if (k > 0) sb.Append(',');
                            C.WriteString(sb, W.KEYS[LIST_IX[k]]);
                            sb.Append(':');
                            Num(sb, om[k]);
                        }
                        sb.Append('}');
                        break;
                }
            }
            sb.Append('}');
        }

        // -- the layout check (the server's check_record, so nothing is sent it refuses) ------

        private static bool RowOk(long[] v, long[] lo, long[] hi)
        {
            if (v == null || v.Length != lo.Length) return false;
            for (int k = 0; k < v.Length; k++) if (v[k] < lo[k] || v[k] > hi[k]) return false;
            return true;
        }

        private static bool GroupOk(Group g, int i)
        {
            if (g == null || !RowOk(g.H, W.HLO[i], W.HHI[i])) return false;
            if (g.S == null || g.S.Count < 1 || g.S.Count > W.SHOT_CAP[i]) return false;
            for (int k = 0; k < g.S.Count; k++) if (!RowOk(g.S[k], W.SLO[i], W.SHI[i])) return false;
            if (g.R == null || g.R.Count > W.REGEN_CAP[i]) return false;
            for (int k = 0; k < g.R.Count; k++) if (!RowOk(g.R[k], W.RLO[i], W.RHI[i])) return false;
            int hn = Array.IndexOf(W.HNAMES[i], "n"), hnrg = Array.IndexOf(W.HNAMES[i], "nrg"), rk = Array.IndexOf(W.RNAMES[i], "k");
            long n = g.H[hn], nrg = g.H[hnrg];
            if (g.S.Count > n || g.R.Count > nrg) return false;
            for (int k = 0; k < g.R.Count; k++)
            {
                if (g.R[k][rk] > n) return false;
                if (k > 0 && g.R[k][rk] < g.R[k - 1][rk]) return false;
            }
            return true;
        }

        /// <summary>The first layout key whose value is outside the layout, or null.</summary>
        internal static string Check(Rec r)
        {
            for (int i = 0; i < N; i++)
            {
                object v = r.V[i];
                bool ok;
                switch (W.KIND[i])
                {
                    case W.K_INT: ok = v is long && (long)v >= W.LO[i][0] && (long)v <= W.HI[i][0]; break;
                    case W.K_ENUM: ok = v is string && Array.IndexOf(W.ENUMS[i], (string)v) >= 0; break;
                    case W.K_ROW: ok = RowOk(v as long[], W.LO[i], W.HI[i]); break;
                    case W.K_ROWS:
                        var rows = v as List<long[]>;
                        ok = rows != null && rows.Count == W.CAP[i];
                        for (int k = 0; ok && k < rows.Count; k++) ok = RowOk(rows[k], W.LO[i], W.HI[i]);
                        break;
                    case W.K_HIST:
                        var h = v as long[];
                        ok = h != null && h.Length == W.CAP[i];
                        for (int k = 0; ok && k < h.Length; k++) ok = h[k] >= W.LO[i][0] && h[k] <= W.HI[i][0];
                        break;
                    case W.K_LIST:
                        var l = v as List<long[]>;
                        ok = l != null && l.Count <= W.CAP[i];
                        for (int k = 0; ok && k < l.Count; k++) ok = RowOk(l[k], W.LO[i], W.HI[i]);
                        break;
                    case W.K_GROUPS:
                        var gs = v as List<Group>;
                        ok = gs != null && gs.Count <= W.CAP[i];
                        for (int k = 0; ok && k < gs.Count; k++) ok = GroupOk(gs[k], i);
                        break;
                    default:
                        var om = v as long[];
                        ok = om != null && om.Length == LIST_IX.Length;
                        for (int k = 0; ok && k < om.Length; k++) ok = om[k] >= W.LO[i][0] && om[k] <= W.HI[i][0];
                        break;
                }
                if (!ok) return W.KEYS[i];
            }
            return null;
        }

        /// <summary>Every numeric field clamped into its layout bounds, in place. Each
        /// collector already clamps what it writes; this is the backstop before the
        /// check, so a bound written differently at a collector never costs the record.</summary>
        internal static void ClampToLayout(Rec r)
        {
            for (int i = 0; i < N; i++)
            {
                object v = r.V[i];
                switch (W.KIND[i])
                {
                    case W.K_INT: r.V[i] = Clamp((long)v, W.LO[i][0], W.HI[i][0]); break;
                    case W.K_ROW: ClampRow((long[])v, W.LO[i], W.HI[i]); break;
                    case W.K_ROWS:
                    case W.K_LIST:
                        foreach (var row in (List<long[]>)v) ClampRow(row, W.LO[i], W.HI[i]);
                        break;
                    case W.K_HIST:
                    case W.K_OMIT:
                        var h = (long[])v;
                        for (int k = 0; k < h.Length; k++) h[k] = Clamp(h[k], W.LO[i][0], W.HI[i][0]);
                        break;
                    case W.K_GROUPS:
                        foreach (var g in (List<Group>)v)
                        {
                            ClampRow(g.H, W.HLO[i], W.HHI[i]);
                            foreach (var s in g.S) ClampRow(s, W.SLO[i], W.SHI[i]);
                            foreach (var s in g.R) ClampRow(s, W.RLO[i], W.RHI[i]);
                        }
                        break;
                }
            }
        }

        private static void ClampRow(long[] a, long[] lo, long[] hi)
        {
            if (a == null || a.Length != lo.Length) return;
            for (int k = 0; k < a.Length; k++) a[k] = Clamp(a[k], lo[k], hi[k]);
        }

        // -- the budgeter (the server's budget_record, line for line) -------------------------

        private static int Popcount(long v) { int c = 0; for (int b = 0; b < 64; b++) if (((v >> b) & 1) != 0) c++; return c; }

        private static readonly int CX_S0 = Array.IndexOf(W.FIELDS[Ix("cx_s")], "s0");
        private static readonly int CX_UNITS = Array.IndexOf(W.FIELDS[Ix("cx_s")], "units");
        private static readonly int CX_MAG = Array.IndexOf(W.FIELDS[Ix("cx_s")], "mag");
        private static readonly int CX_REGEN = Array.IndexOf(W.FIELDS[Ix("cx_s")], "regen");
        private static readonly int CX_TAIL = Array.IndexOf(W.FIELDS[Ix("cx_s")], "tail");
        private static readonly int CX_WHY = Array.IndexOf(W.FIELDS[Ix("cx_s")], "why");
        private static readonly int HDR_S0 = Array.IndexOf(W.HNAMES[Ix("sh_s")], "s0");
        private static readonly int HDR_PT = Array.IndexOf(W.HNAMES[Ix("sh_s")], "pt");
        private static readonly int TB_PT = Array.IndexOf(W.FIELDS[Ix("tb")], "pt");

        private static long CxExcess(long[] e)
        {
            return Math.Max(0, e[CX_UNITS] - e[CX_MAG] - e[CX_REGEN] - e[CX_TAIL]);
        }

        private static int Count(Rec r, string k)
        {
            object v = r[k];
            var l = v as List<long[]>;
            return l != null ? l.Count : ((List<Group>)v).Count;
        }

        private static void RemoveLast(Rec r, string k)
        {
            object v = r[k];
            var l = v as List<long[]>;
            if (l != null) l.RemoveAt(l.Count - 1); else { var g = (List<Group>)v; g.RemoveAt(g.Count - 1); }
        }

        private static void RemoveAtIndex(Rec r, string k, int i)
        {
            object v = r[k];
            var l = v as List<long[]>;
            if (l != null) l.RemoveAt(i); else ((List<Group>)v).RemoveAt(i);
        }

        /// <summary>The protected groups per gun (indices) and the time base points they lie in.</summary>
        private static void Protected(Rec r, List<int>[] prot, HashSet<long> points)
        {
            points.Clear();
            for (int p = 0; p < W.PROTECT.Length; p++)
            {
                var keys = new HashSet<long>();
                foreach (var e in (List<long[]>)r[W.PROTECT[p][1]]) keys.Add(e[CX_S0]);
                var gs = (List<Group>)r[W.PROTECT[p][0]];
                var idx = new List<int>();
                for (int i = 0; i < gs.Count; i++) if (keys.Contains(gs[i].H[HDR_S0])) idx.Add(i);
                prot[p] = idx;
                foreach (int i in idx) points.Add(gs[i].H[HDR_PT]);
            }
        }

        private static bool TrimOne(Rec r, long[] omit)
        {
            for (int t = 0; t < 2; t++)
            {
                string best = null;
                foreach (var k in W.TIER_ORDER[t])
                    if (Count(r, k) > 0 && (best == null || Count(r, k) > Count(r, best))) best = k;
                if (best != null) { RemoveLast(r, best); omit[OmitPos(best)]++; return true; }
            }
            var prot = new List<int>[W.PROTECT.Length];
            var points = new HashSet<long>();
            Protected(r, prot, points);
            var removable = new Dictionary<string, List<int>>();
            var tbl = (List<long[]>)r["tb"];
            var tbr = new List<int>();
            for (int i = 0; i < tbl.Count; i++) if (!points.Contains(tbl[i][TB_PT])) tbr.Add(i);
            removable["tb"] = tbr;
            for (int p = 0; p < W.PROTECT.Length; p++)
            {
                var keep = new HashSet<int>(prot[p]);
                var rem = new List<int>();
                int n = Count(r, W.PROTECT[p][0]);
                for (int i = 0; i < n; i++) if (!keep.Contains(i)) rem.Add(i);
                removable[W.PROTECT[p][0]] = rem;
            }
            string b3 = null;
            foreach (var k in W.TIER_ORDER[2])
                if (removable[k].Count > 0 && (b3 == null || removable[k].Count > removable[b3].Count)) b3 = k;
            if (b3 != null)
            {
                RemoveAtIndex(r, b3, removable[b3][removable[b3].Count - 1]);
                omit[OmitPos(b3)]++;
                return true;
            }
            // one protected group: fewest reason bits, smallest excess, latest index, the other gun first on a full tie
            bool found = false;
            long bw = 0, be = 0, bi = 0, bp = 0; string bk = null; int bidx = -1;
            for (int p = 0; p < W.PROTECT.Length; p++)
            {
                var byS0 = new Dictionary<long, long[]>();
                foreach (var e in (List<long[]>)r[W.PROTECT[p][1]]) if (!byS0.ContainsKey(e[CX_S0])) byS0[e[CX_S0]] = e;
                var gs = (List<Group>)r[W.PROTECT[p][0]];
                foreach (int i in prot[p])
                {
                    var e = byS0[gs[i].H[HDR_S0]];
                    long kw = Popcount(e[CX_WHY]), ke = CxExcess(e), ki = -i, kp = -p;
                    bool less = !found || kw < bw || (kw == bw && (ke < be || (ke == be && (ki < bi || (ki == bi && kp < bp)))));
                    if (less) { found = true; bw = kw; be = ke; bi = ki; bp = kp; bk = W.PROTECT[p][0]; bidx = i; }
                }
            }
            if (!found) return false;
            RemoveAtIndex(r, bk, bidx);
            omit[OmitPos(bk)]++;
            return true;
        }

        /// <summary>A working copy whose lists the budgeter may cut (rows are shared: never mutated).</summary>
        private static Rec Working(Rec rec)
        {
            var o = new Rec();
            for (int i = 0; i < N; i++)
            {
                object v = rec.V[i];
                switch (W.KIND[i])
                {
                    case W.K_ROWS: case W.K_LIST: o.V[i] = new List<long[]>((List<long[]>)v); break;
                    case W.K_GROUPS: o.V[i] = new List<Group>((List<Group>)v); break;
                    case W.K_OMIT: o.V[i] = (long[])((long[])v).Clone(); break;
                    default: o.V[i] = v; break;
                }
            }
            return o;
        }

        /// <summary>The reference budgeter's output for `rec` (every layout key, full
        /// lists): step one cuts every list to its cap and every group to its caps
        /// (list cuts counted in omit), step two serializes, step three removes one
        /// entry by the tier rule and re-serializes while over `limit`. Throws when
        /// the never-trimmed part alone exceeds it.</summary>
        internal static string Budget(Rec rec, int limit = W.RECORD_MAX_BYTES)
        {
            var o = Working(rec);
            var omit = o.Omit;
            foreach (int i in LIST_IX)
            {
                int pos = Array.IndexOf(LIST_IX, i);
                if (W.KIND[i] == W.K_LIST)
                {
                    var l = (List<long[]>)o.V[i];
                    if (l.Count > W.CAP[i]) { omit[pos] += l.Count - W.CAP[i]; l.RemoveRange(W.CAP[i], l.Count - W.CAP[i]); }
                }
                else
                {
                    var gs = (List<Group>)o.V[i];
                    if (gs.Count > W.CAP[i]) { omit[pos] += gs.Count - W.CAP[i]; gs.RemoveRange(W.CAP[i], gs.Count - W.CAP[i]); }
                    for (int k = 0; k < gs.Count; k++) gs[k] = gs[k].Copy(W.SHOT_CAP[i], W.REGEN_CAP[i]);
                }
            }
            string body = Dumps(o);
            while (body.Length > limit)
            {
                if (!TrimOne(o, omit)) throw new InvalidOperationException("the never-trimmed part alone exceeds the record bound");
                body = Dumps(o);
            }
            return body;
        }

        // -- the byte proof (the server's byte_proof) -------------------------------------------

        private static long Widest(long lo, long hi)
        {
            return lo.ToString(CultureInfo.InvariantCulture).Length >= hi.ToString(CultureInfo.InvariantCulture).Length ? lo : hi;
        }

        private static long[] MaxRow(long[] lo, long[] hi)
        {
            var a = new long[lo.Length];
            for (int k = 0; k < a.Length; k++) a[k] = Widest(lo[k], hi[k]);
            return a;
        }

        internal static Rec MaxWidthRecord()
        {
            var r = new Rec();
            for (int i = 0; i < N; i++)
            {
                switch (W.KIND[i])
                {
                    case W.K_INT: r.V[i] = Widest(W.LO[i][0], W.HI[i][0]); break;
                    case W.K_ENUM:
                        string best = W.ENUMS[i][0];
                        foreach (var e in W.ENUMS[i]) if (e.Length > best.Length) best = e;
                        r.V[i] = best; break;
                    case W.K_ROW: r.V[i] = MaxRow(W.LO[i], W.HI[i]); break;
                    case W.K_ROWS:
                        var rows = new List<long[]>();
                        for (int k = 0; k < W.CAP[i]; k++) rows.Add(MaxRow(W.LO[i], W.HI[i]));
                        r.V[i] = rows; break;
                    case W.K_HIST:
                        var h = new long[W.CAP[i]];
                        for (int k = 0; k < h.Length; k++) h[k] = Widest(W.LO[i][0], W.HI[i][0]);
                        r.V[i] = h; break;
                    case W.K_LIST:
                        var l = new List<long[]>();
                        if (W.TIER[i] == 0) for (int k = 0; k < W.CAP[i]; k++) l.Add(MaxRow(W.LO[i], W.HI[i]));
                        r.V[i] = l; break;
                    case W.K_GROUPS: r.V[i] = new List<Group>(); break;
                    default:
                        var om = new long[LIST_IX.Length];
                        for (int k = 0; k < om.Length; k++) om[k] = Widest(W.LO[i][0], W.HI[i][0]);
                        r.V[i] = om; break;
                }
            }
            return r;
        }

        internal static Group MaxWidthGroup(string key)
        {
            int i = Ix(key);
            var g = new Group { H = MaxRow(W.HLO[i], W.HHI[i]) };
            for (int k = 0; k < W.SHOT_CAP[i]; k++) g.S.Add(MaxRow(W.SLO[i], W.SHI[i]));
            for (int k = 0; k < W.REGEN_CAP[i]; k++) g.R.Add(MaxRow(W.RLO[i], W.RHI[i]));
            return g;
        }

        /// <summary>[limit, never_trimmed_max, group_max, point_max, protected_floor].</summary>
        internal static long[] ByteProof()
        {
            long nt = Dumps(MaxWidthRecord()).Length;
            long group = 0;
            foreach (var p in W.PROTECT)
            {
                var sb = new StringBuilder();
                WriteGroup(sb, MaxWidthGroup(p[0]));
                group = Math.Max(group, sb.Length);
            }
            var pb = new StringBuilder();
            int tbi = Ix("tb");
            Arr(pb, MaxRow(W.LO[tbi], W.HI[tbi]));
            long point = pb.Length;
            long per = group + point + 2;
            return new long[] { W.RECORD_MAX_BYTES, nt, group, point, (W.RECORD_MAX_BYTES - nt) / per };
        }

        // -- signing and the envelope (server notes 4.1) ----------------------------------------

        internal static string Canonical(string seat, string other, string stable, string attach, string recordText)
        {
            return W.SIGN_PREFIX + seat + ":" + other + ":"
                   + C.Sha256Hex(Encoding.ASCII.GetBytes(stable)) + ":" + C.Sha256Hex(Encoding.ASCII.GetBytes(attach)) + ":"
                   + C.Sha256Hex(Encoding.ASCII.GetBytes(recordText));
        }

        /// <summary>The request body, or null when a field is outside the
        /// envelope's bounds (nothing is sent the route would refuse as malformed).</summary>
        internal static string Envelope(string seat, string other, string stable, string attach, string recordText, string sig)
        {
            if (!C.IsSteamId(seat) || !C.IsSteamId(other) || seat == other) return null;
            if (!C.IsAttachKey(stable, attach)) return null;
            if (recordText == null || recordText.Length == 0 || recordText.Length > W.RECORD_MAX_BYTES) return null;
            for (int i = 0; i < recordText.Length; i++) if (recordText[i] > '~' || recordText[i] < ' ') return null;
            if (sig == null || sig.Length != 64) return null;
            var o = new C.JObj().Add("contract", (long)W.CONTRACT).Add("seat_steam_id", seat).Add("other_steam_id", other)
                                .Add("stable_game_key", stable).Add("attach_key", attach).Add("record", recordText).Add("sig", sig);
            return C.Json(o);
        }

        // -- single-precision references (the server's integrate / residual / steering) ---------

        internal static float F(double x) { return (float)x; }
        private const double RAD_TO_DEG = 180.0 / Math.PI;
        private const double DEG_TO_RAD = Math.PI / 180.0;

        internal struct St { internal float X, Y, VX, VY; internal St(float x, float y, float vx, float vy) { X = x; Y = y; VX = vx; VY = vy; } }

        /// <summary>The integrator's parameters: the copy's MoveTransform fields.</summary>
        internal struct MovePrm
        {
            internal float Gravity, Drag, DragMin, Mult, Sim; internal bool AllowStop; internal int SimGravity;
        }

        /// <summary>One frame of the game's unsteered flight (MoveTransform.Update), in single precision.</summary>
        internal static St Step(St s, double raw, MovePrm p)
        {
            float x = s.X, y = s.Y, vx = s.VX, vy = s.VY;
            float clamp = F(W.MOVE_DT_CLAMP), floor = F(W.MOVE_SPEED_FLOOR);
            float dt = F(raw);
            float num = F(Math.Min(Math.Max(dt, 0f), clamp));
            num = F((double)num * p.Sim);
            float d = F((double)dt * p.Sim);
            if (p.SimGravity == 0) vy = F(vy + (double)F((double)F((double)F((double)p.Gravity * -1.0) * d) * p.Mult));
            float mag = F(Math.Sqrt(F((double)F((double)vx * vx) + F((double)vy * vy))));
            if ((mag > floor || p.AllowStop) && mag > p.DragMin)
            {
                float m01 = F(Math.Min(Math.Max(p.Mult, 0f), 1f));
                float k = F(Math.Min(Math.Max(F((double)F((double)p.Drag * num) * m01), 0f), 1f));
                vx = F(vx - (double)F((double)vx * k));
                vy = F(vy - (double)F((double)vy * k));
            }
            x = F(x + (double)F((double)F((double)vx * d) * p.Mult));
            y = F(y + (double)F((double)F((double)vy * d) * p.Mult));
            return new St(x, y, vx, vy);
        }

        internal static St Integrate(St s, IList<double> frames, MovePrm p)
        {
            for (int i = 0; i < frames.Count; i++) s = Step(s, frames[i], p);
            return s;
        }

        /// <summary>The unsteered flight over `span` game seconds in fixed steps
        /// (the last one partial), at most MAX_STEPS steps.</summary>
        internal static St IntegrateSpan(St s, double span, double step, MovePrm p)
        {
            for (int n = 0; n < MAX_STEPS && span > 1e-9; n++)
            {
                double d = Math.Min(step, span);
                s = Step(s, d, p);
                span -= d;
            }
            return s;
        }

        internal const int MAX_STEPS = 600;

        internal static St Turn(St s, double angle)
        {
            float c = F(Math.Cos(angle)), sn = F(Math.Sin(angle));
            return new St(s.X, s.Y, F(F((double)s.VX * c) - (double)F((double)s.VY * sn)), F(F((double)s.VX * sn) + (double)F((double)s.VY * c)));
        }

        internal static St Trace(St s, IList<double> frames, MovePrm p, double turnPerFrame)
        {
            for (int i = 0; i < frames.Count; i++)
            {
                if (turnPerFrame != 0) s = Turn(s, turnPerFrame);
                s = Step(s, frames[i], p);
            }
            return s;
        }

        internal static long RoundEven(double x) { return (long)Math.Round(x, MidpointRounding.ToEven); }

        internal static double Hypot(double a, double b) { return Math.Sqrt(a * a + b * b); }

        /// <summary>[d_perp, d_along, ang]: the observed state against the predicted
        /// unsteered one (centi-units, centi-units, mrad; half to even).</summary>
        internal static long[] Residual(St pred, St actual)
        {
            double dx = (double)actual.X - pred.X, dy = (double)actual.Y - pred.Y;
            double speed = Hypot(pred.VX, pred.VY);
            double along, perp;
            if (speed == 0) { along = Hypot(dx, dy); perp = 0.0; }
            else
            {
                double ux = pred.VX / speed, uy = pred.VY / speed;
                along = dx * ux + dy * uy;
                perp = Math.Abs(dx * uy - dy * ux);
            }
            double cross = (double)pred.VX * actual.VY - (double)pred.VY * actual.VX;
            double dot = (double)pred.VX * actual.VX + (double)pred.VY * actual.VY;
            double ang = Math.Abs(Math.Atan2(cross, dot));
            return new long[] { RoundEven(perp * W.CENTI), RoundEven(along * W.CENTI), RoundEven(ang * 1000) };
        }

        /// <summary>The engine's unsigned vector angle in degrees (zero for a zero vector).</summary>
        internal static double AngleDeg(double ax, double ay, double bx, double by)
        {
            if ((ax == 0 && ay == 0) || (bx == 0 && by == 0)) return 0.0;
            return Math.Abs(Math.Atan2(ax * by - ay * bx, ax * bx + ay * by)) * RAD_TO_DEG;
        }

        internal struct HomingPrm { internal MovePrm Move; internal float Amount, ScalingDrag, HDrag, Force; }

        /// <summary>One frame of a homing projectile (Homing.Update, then MoveTransform.Update).</summary>
        internal static St HomingStep(St s, float tgx, float tgy, double dtRaw, HomingPrm p, out bool on)
        {
            float x = s.X, y = s.Y, vx = s.VX, vy = s.VY;
            float d = F(dtRaw);
            float tx = F(tgx - (double)x), ty = F(tgy - (double)y);
            float ang = F(AngleDeg(vx, vy, tx, ty));
            on = ang < W.HOMING_CONE_DEG;
            if (on)
            {
                float sd = p.ScalingDrag, hd = p.HDrag;
                vx = F(vx - (double)F((double)F((double)F((double)vx * ang) * d) * sd));
                vy = F(vy - (double)F((double)F((double)F((double)vy * ang) * d) * sd));
                vx = F(vx - (double)F((double)F((double)vx * d) * hd));
                vy = F(vy - (double)F((double)F((double)vy * d) * hd));
                float n = F(Math.Sqrt(F((double)F((double)tx * tx) + F((double)ty * ty))));
                float cx = tx, cy = ty;
                if (n > 1) { cx = F((double)tx / n); cy = F((double)ty / n); }
                float force = p.Force, scale = F(W.HOMING_FORCE_SCALE), amount = p.Amount;
                vx = F(vx + (double)F((double)F((double)F((double)F((double)cx * d) * force) * scale) * amount));
                vy = F(vy + (double)F((double)F((double)F((double)F((double)cy * d) * force) * scale) * amount));
                vy = F(vy + (double)F((double)F((double)d * p.Move.Gravity) * p.Move.Mult));
            }
            var mp = p.Move;
            mp.SimGravity = p.Move.SimGravity + (on ? 1 : 0);
            return Step(new St(x, y, vx, vy), dtRaw, mp);
        }

        /// <summary>The owner's sync packages of a homing projectile (time, state).</summary>
        internal static List<KeyValuePair<float, St>> HomingTrace(St s, float tgx, float tgy, IList<double> frames, HomingPrm p, int syncEvery, double turnPerFrame)
        {
            float t = 0f;
            var o = new List<KeyValuePair<float, St>> { new KeyValuePair<float, St>(0f, s) };
            for (int i = 0; i < frames.Count; i++)
            {
                if (turnPerFrame != 0) s = Turn(s, turnPerFrame);
                bool on;
                s = HomingStep(s, tgx, tgy, frames[i], p, out on);
                t = F(t + (double)F(frames[i]));
                if ((i + 1) % syncEvery == 0) o.Add(new KeyValuePair<float, St>(t, s));
            }
            return o;
        }

        /// <summary>The turn rate between two packages as per mille of the homing
        /// bound at the earlier package's speed; -1 when it cannot be formed.</summary>
        internal static long HomingRatio(double dt, double avx, double avy, double bvx, double bvy, double force, double amount)
        {
            double bound = force * W.HOMING_FORCE_SCALE * amount;
            double speed = Hypot(avx, avy);
            if (dt <= 0 || speed == 0 || bound == 0) return -1;
            double rate = AngleDeg(avx, avy, bvx, bvy) * DEG_TO_RAD / dt;
            return RoundEven(rate / (bound / speed) * 1000);
        }

        /// <summary>The p3ht entry of one projectile from consecutive packages.</summary>
        internal static long[] HomingEntry(long pid, long sRel, List<KeyValuePair<float, St>> packs, double force, double amount)
        {
            long best = -1;
            int n = 0;
            for (int i = 0; i + 1 < packs.Count; i++)
            {
                var a = packs[i]; var b = packs[i + 1];
                long r = HomingRatio((double)b.Key - a.Key, a.Value.VX, a.Value.VY, b.Value.VX, b.Value.VY, force, amount);
                if (r < 0) continue;
                n++;
                if (r > best) best = r;
            }
            return new long[] { pid, sRel, n > 0 ? best : 0, packs.Count };
        }

        /// <summary>One target bounce as the game's code runs it (the server's
        /// target_bounce): [gap ms, has_retarget, ang_to_me mrad] and the new
        /// velocity; null when the frames end before the wait.</summary>
        internal static long[] TargetBounce(St s, float nxIn, float nyIn, bool hasTarget, float tgx, float tgy, float mex, float mey,
                                            IList<double> frames, float gravity, float speedM, double waitS, out float nvx, out float nvy)
        {
            nvx = nvy = 0f;
            float x = s.X, y = s.Y, vx = s.VX, vy = s.VY;
            float nx = nxIn, ny = nyIn;
            float k = F(-(double)F((double)F(F((double)nx * vx) + (double)F((double)ny * vy)) * 2));
            float rvx = F(F((double)k * nx) + (double)vx), rvy = F(F((double)k * ny) + (double)vy);
            vx = F((double)rvx * speedM); vy = F((double)rvy * speedM);
            float speed = F(Math.Sqrt(F((double)F((double)vx * vx) + F((double)vy * vy))));
            float nudge = F(W.BOUNCE_NUDGE);
            x = F(x + (double)F((double)F((double)vx / speed) * nudge));
            y = F(y + (double)F((double)F((double)vy / speed) * nudge));
            float waited = 0f, wait = F(waitS);
            bool done = false;
            for (int i = 0; i < frames.Count; i++)
            {
                waited = F(waited + (double)F(frames[i]));
                if (waited >= wait) { done = true; break; }
            }
            if (!done) return null;
            long has;
            if (!hasTarget) { nvx = vx; nvy = vy; has = 0; }
            else
            {
                float dist = Math.Abs(F(tgx - (double)x));
                float comp = F((double)F((double)F((double)F(Math.Pow(dist, F(W.BOUNCE_COMP_POW))) * gravity) / speed) * F(W.BOUNCE_COMP_SCALE));
                float ex = F(tgx - (double)x), ey = F((double)F(tgy + (double)comp) - y);
                float n = F(Math.Sqrt(F((double)F((double)ex * ex) + F((double)ey * ey))));
                nvx = F((double)F((double)ex / n) * speed); nvy = F((double)F((double)ey / n) * speed);
                has = 1;
            }
            double mx = (double)mex - x, my = (double)mey - y;
            double ang = Math.Abs(Math.Atan2((double)nvx * my - (double)nvy * mx, (double)nvx * mx + (double)nvy * my));
            return new long[] { RoundEven(waited * 1000.0), has, RoundEven(ang * 1000) };
        }

        // -- measurement constants (consts 1; they say how a number is measured, never what is flagged) --

        /// <summary>Aim error histogram edges (a1s, a1p, a1m, a1n), mrad of |error|:
        /// bin i holds edges[i] &lt;= v &lt; edges[i+1]; the last bin is open.</summary>
        internal static readonly long[] AIM_EDGES = { 0, 5, 10, 20, 35, 50, 75, 100, 150, 200, 300, 400, 600, 800, 1200, 2000 };
        /// <summary>Bullet residual d_perp histogram edges (p3dp0, p3dp1), centi-units.</summary>
        internal static readonly long[] PERP_EDGES = { 0, 5, 10, 20, 35, 50, 75, 100, 150, 200, 300, 500, 800, 1200 };
        /// <summary>Bullet residual angle histogram edges (p3an0, p3an1), mrad.</summary>
        internal static readonly long[] ANG_EDGES = { 0, 5, 10, 20, 35, 50, 75, 100, 150, 200, 300, 500, 800, 1200 };
        /// <summary>Homing turn ratio histogram edges (p3hm), per mille of the code's bound.</summary>
        internal static readonly long[] HOMING_EDGES = { 0, 100, 250, 500, 750, 900, 1000, 1100, 1500, 2500 };
        /// <summary>The window an a1n search spans beyond 2 L^, ms.</summary>
        internal const int A1N_W_MS = 100;
        /// <summary>The cap on a recorded sinceAttack, game ms.</summary>
        internal const long SINCE_CAP_MS = 600000;
        /// <summary>The fixed step a residual prediction integrates over, s.</summary>
        internal const double PRED_STEP_S = 1.0 / 60.0;

        internal static int Bin(long[] edges, long v)
        {
            int b = 0;
            for (int i = 1; i < edges.Length; i++) if (v >= edges[i]) b = i;
            return b;
        }

        /// <summary>Running sums of signed samples: n, sum, sum of squares, no-sight count.</summary>
        internal sealed class AimSet
        {
            internal readonly long[] Hist = new long[16];
            internal long Count, NoSight; internal double Sum, Sq;
            internal void Add(long signedMrad, bool noSight)
            {
                long a = signedMrad < 0 ? -signedMrad : signedMrad;
                Hist[Bin(AIM_EDGES, a)]++;
                Count++; Sum += signedMrad; Sq += (double)signedMrad * signedMrad;
                if (noSight) NoSight++;
            }
            internal long[] Summary()
            {
                if (Count == 0) return new long[] { 0, 0, 0, NoSight > 99999 ? 99999 : NoSight };
                double mean = Sum / Count;
                double var = Math.Max(0, Sq / Count - mean * mean);
                return new long[] { Clamp(Count, 0, 99999), Clamp(RoundEven(mean), -3142, 3142), Clamp(RoundEven(Math.Sqrt(var)), 0, 3142), Clamp(NoSight, 0, 99999) };
            }
            internal long[] HistClamped() { var h = new long[16]; for (int i = 0; i < 16; i++) h[i] = Clamp(Hist[i], 0, 99999); return h; }
        }

        // -- the per-gun cycle accountant (design 4.2; equal to the server's rebuild) -----------

        private static readonly string[] TOT_FIELDS = W.FIELDS[Ix("tot_s")];
        internal static int TotIx(string name) { return Array.IndexOf(TOT_FIELDS, name); }

        /// <summary>One gun's accounting on one seat: the recording seat's own gun
        /// (Own = true, shots carry rep/since/fl) or its copy of the other seat's
        /// gun (am). Fed the gun's events in order; keeps each cycle's group at
        /// the layout's caps while counting every shot, and whole-game totals
        /// over every cycle, kept or not. Storage is flat arrays sized at
        /// construction (game start): the hook path writes numbers into them
        /// and allocates nothing; Groups() builds the record's rows on the tick.</summary>
        internal sealed class GunAccount
        {
            internal readonly bool Own;
            internal long GroupsOmitted, CxOmitted;
            internal readonly long[] Tot = new long[TOT_FIELDS.Length];
            private readonly int _shotCap, _regenCap, _groupCap, _cxCap, _sw;
            private const int HW = 13, RW = 6, CW = 14, GAP_CAP = W.GAP_COUNT;
            private readonly long[] _hdr, _shots, _regs, _cx;
            private readonly int[] _nShots, _nRegs;
            private int _nGroups, _nCx;

            // the open cycle
            private bool _open, _listed;
            private int _gi;
            private long _s0, _pid0, _pt, _n, _lastPid, _lastStamp, _mag, _rexp;
            private long _count, _regen, _nrg, _vol, _volLast, _sx, _tail, _inRl, _postVolLast;
            private bool _hasVolLast, _exh, _inTail, _foundRl, _gateRl, _hasPostVol;
            private readonly long[] _gaps = new long[W.GAP_COUNT];
            private int _gapN;
            internal long Mag = 1, Rexp;   // the stat in force (set at each point start / stat change)
            internal long Point;

            internal GunAccount(bool own)
            {
                Own = own;
                int gi = Ix(own ? "sh_s" : "sh_o");
                _shotCap = W.SHOT_CAP[gi]; _regenCap = W.REGEN_CAP[gi]; _groupCap = W.CAP[gi];
                _sw = W.SNAMES[gi].Length;
                _cxCap = W.CAP[Ix(own ? "cx_s" : "cx_o")];
                _hdr = new long[_groupCap * HW];
                _shots = new long[_groupCap * _shotCap * _sw];
                _regs = new long[_groupCap * _regenCap * RW];
                _nShots = new int[_groupCap]; _nRegs = new int[_groupCap];
                _cx = new long[_cxCap * CW];
                Tot[TotIx("gap_minus_rexp_min")] = W.GAP_NONE;
            }

            internal bool Open { get { return _open; } }
            internal long OpenUnits { get { return _open ? _n : 0; } }
            internal int GroupCount { get { return _nGroups; } }
            internal int CxCount { get { return _nCx; } }

            /// <summary>An ammo projectile. The first projectile of an emission
            /// carries rep >= 0 (own gun) or am >= 0 (the copy).</summary>
            internal void AddShot(long pid, long stamp, long ammoBefore, bool reloading, long counterMs, long rep, long since, long fl, long am)
            {
                if (!_open) Start(pid, stamp);
                long j = _n;
                _n++;
                rep = Clamp(rep, -1, 999); am = Clamp(am, -1, 600000); fl = Clamp(fl, 0, 31);
                // the stamp the server rebuilds from the listed deltas (a delta beyond
                // the layout's bound is clamped, and every later delta follows it)
                long dt = Clamp(Wrap(stamp - _lastStamp), -600000, 600000);
                long dpid = Clamp(pid - _lastPid, -2147483647, 2147483647);
                if (_listed && _nShots[_gi] < _shotCap)
                {
                    int o = (_gi * _shotCap + _nShots[_gi]) * _sw;
                    _shots[o] = dpid; _shots[o + 1] = dt; _shots[o + 2] = Clamp(ammoBefore, -999, 999);
                    _shots[o + 3] = reloading ? 1 : 0; _shots[o + 4] = reloading ? Clamp(counterMs, -1, 600000) : -1;
                    if (Own) { _shots[o + 5] = rep; _shots[o + 6] = Clamp(since, -1, 600000); _shots[o + 7] = fl; }
                    else _shots[o + 5] = am;
                    _nShots[_gi]++;
                    _lastPid = _lastPid + dpid;
                    _lastStamp = Wrap(_lastStamp + dt);
                    stamp = _lastStamp;
                }
                else stamp = Wrap(stamp);
                bool marker = Own ? rep != -1 : am != -1;
                // the rule count (regenerations were added as they came)
                _count -= 1;
                if (!_hasVolLast || stamp != _volLast) { _vol++; _volLast = stamp; _hasVolLast = true; }
                if (!_exh)
                {
                    if (reloading) _foundRl = true;
                    if (_count <= 0) { _exh = true; _sx = stamp; _inTail = true; }
                }
                else
                {
                    if (_inTail && !marker) _tail++;
                    else
                    {
                        _inTail = false;
                        if (!_hasPostVol || stamp != _postVolLast)
                        {
                            if (_gapN < W.GAP_COUNT) _gaps[_gapN++] = Wrap(stamp - _sx);
                            _postVolLast = stamp; _hasPostVol = true;
                        }
                    }
                    if (reloading) _inRl++;
                }
                if (Own && rep == 0 && (fl & W.FL_RELOADING) != 0 && (fl & W.FL_FORCED) == 0) _gateRl = true;
                if (marker)
                {
                    if (Own) { Tot[TotIx("emit")]++; if (rep == 0) Tot[TotIx("gate")]++; }
                    else Tot[TotIx("atk_msg")]++;
                }
            }

            /// <summary>A regeneration of `amt` units seen on this copy (applied before the next shot).</summary>
            internal void AddRegen(long amt, long st, long gapG, long gapS, long gapR)
            {
                if (!_open || amt <= 0) return;
                amt = Clamp(amt, 1, 999);
                _count += amt; _regen += amt; _nrg++;
                if (_listed && _nRegs[_gi] < _regenCap)
                {
                    int o = (_gi * _regenCap + _nRegs[_gi]) * RW;
                    _regs[o] = Clamp(_n, 0, 99999); _regs[o + 1] = amt; _regs[o + 2] = Wrap(st);
                    _regs[o + 3] = Clamp(gapG, -1, 600000); _regs[o + 4] = Clamp(gapS, -1, 600000); _regs[o + 5] = Clamp(gapR, -1, 600000);
                    _nRegs[_gi]++;
                }
            }

            /// <summary>An accepted attack whose emission listed no ammo init (own:
            /// a gate call; copy: an attack message).</summary>
            internal void AddNoInit()
            {
                Tot[TotIx("atk_noinit")]++;
                if (Own) Tot[TotIx("gate")]++; else Tot[TotIx("atk_msg")]++;
            }

            internal void AddKind(bool noAmmo)
            {
                Tot[TotIx(noAmmo ? "noammo" : "separate")]++;
            }

            /// <summary>The refill or point end that closes the open cycle. A refill
            /// with no open cycle is counted (rf_idle).</summary>
            internal void CloseCycle(long end, long src, long amt, long stEnd, long rlG, long rlS, long rlR)
            {
                if (!_open)
                {
                    if (end != W.END_POINT) Tot[TotIx("rf_idle")]++;
                    return;
                }
                _open = false;
                bool timer = end == W.END_TIMER;
                if (_listed)
                {
                    int o = _gi * HW;
                    _hdr[o] = _s0; _hdr[o + 1] = Clamp(_pid0, 0, 2147483647); _hdr[o + 2] = Clamp(_n, 1, 99999); _hdr[o + 3] = Clamp(_pt, 0, 99);
                    _hdr[o + 4] = end; _hdr[o + 5] = Clamp(src, 0, 2); _hdr[o + 6] = Clamp(amt, -1, 999); _hdr[o + 7] = Wrap(stEnd);
                    _hdr[o + 8] = timer ? Clamp(rlG, -1, 600000) : -1; _hdr[o + 9] = timer ? Clamp(rlS, -1, 600000) : -1;
                    _hdr[o + 10] = timer ? Clamp(rlR, -1, 600000) : -1;
                    _hdr[o + 11] = Clamp(_regen, 0, 99999); _hdr[o + 12] = Clamp(_nrg, 0, 99999);
                    _nGroups++;
                }
                else GroupsOmitted++;
                long tail = _exh ? _tail : 0, inRl = _exh ? _inRl : 0;
                long excess = Math.Max(0, _n - _mag - _regen - tail);
                long why = 0;
                if (_n - tail > _mag + _regen) why |= W.WHY_OVER_MAG;
                if (inRl > tail) why |= W.WHY_IN_RELOAD;
                long g0 = _exh && _gapN > 0 ? _gaps[0] : -1;
                if (timer && g0 >= 0 && g0 < _rexp) why |= W.WHY_SHORT_GAP;
                if (_foundRl) why |= W.WHY_FOUND_RELOADING;
                if (Own && _gateRl) why |= W.WHY_GATE_RELOADING;
                Tot[TotIx("cycles")]++;
                Tot[TotIx("volleys")] += _vol;
                Tot[TotIx("units")] += _n;
                Tot[TotIx("sum_excess")] += excess;
                Tot[TotIx("inits_rl")] += inRl;
                if ((why & W.WHY_OVER_MAG) != 0) Tot[TotIx("why_over_mag")]++;
                if ((why & W.WHY_IN_RELOAD) != 0) Tot[TotIx("why_in_reload")]++;
                if ((why & W.WHY_SHORT_GAP) != 0) Tot[TotIx("why_short_gap")]++;
                if ((why & W.WHY_FOUND_RELOADING) != 0) Tot[TotIx("why_found_reloading")]++;
                if ((why & W.WHY_GATE_RELOADING) != 0) Tot[TotIx("why_gate_reloading")]++;
                if (g0 >= 0)
                {
                    int gi = TotIx("gap_minus_rexp_min");
                    long d = g0 - _rexp;
                    if (Tot[gi] == W.GAP_NONE || d < Tot[gi]) Tot[gi] = d;
                }
                if (why != 0)
                {
                    Tot[TotIx("cx_n")]++; Tot[TotIx("cx_volleys")] += _vol; Tot[TotIx("cx_units")] += _n;
                    if (_nCx < _cxCap)
                    {
                        int o = _nCx * CW;
                        _cx[o] = _s0; _cx[o + 1] = Clamp(_n, 0, 9999); _cx[o + 2] = Clamp(_vol, 0, 9999); _cx[o + 3] = Clamp(_mag, 1, 90);
                        _cx[o + 4] = Clamp(_regen, 0, 9999); _cx[o + 5] = _exh ? Clamp(Wrap(_sx - _s0), -1, 600000) : -1;
                        _cx[o + 6] = Clamp(inRl, 0, 9999); _cx[o + 7] = Clamp(tail, 0, 9999);
                        for (int i = 0; i < GAP_CAP; i++) _cx[o + 8 + i] = i < _gapN ? Clamp(_gaps[i], -1, 600000) : -1;
                        _cx[o + 11] = Clamp(_rexp, 0, 600000); _cx[o + 12] = end; _cx[o + 13] = why;
                        _nCx++;
                    }
                    else CxOmitted++;
                }
            }

            private void Start(long pid, long stamp)
            {
                _open = true;
                _listed = _nGroups < _groupCap;
                _gi = _nGroups;
                if (_listed) { _nShots[_gi] = 0; _nRegs[_gi] = 0; }
                _s0 = Wrap(stamp); _pid0 = pid; _pt = Point; _n = 0; _lastPid = pid; _lastStamp = _s0;
                _mag = Mag; _rexp = Rexp; _count = Mag; _regen = 0; _nrg = 0; _vol = 0; _hasVolLast = false;
                _exh = false; _inTail = false; _tail = 0; _inRl = 0; _gapN = 0; _hasPostVol = false; _foundRl = false; _gateRl = false;
            }

            /// <summary>The kept cycle groups as record rows (the tick's work).</summary>
            internal List<Group> Groups()
            {
                var o = new List<Group>(_nGroups);
                for (int g = 0; g < _nGroups; g++)
                {
                    var grp = new Group { H = Slice(_hdr, g * HW, HW) };
                    for (int k = 0; k < _nShots[g]; k++) grp.S.Add(Slice(_shots, (g * _shotCap + k) * _sw, _sw));
                    for (int k = 0; k < _nRegs[g]; k++) grp.R.Add(Slice(_regs, (g * _regenCap + k) * RW, RW));
                    o.Add(grp);
                }
                return o;
            }

            internal List<long[]> CxRows()
            {
                var o = new List<long[]>(_nCx);
                for (int i = 0; i < _nCx; i++) o.Add(Slice(_cx, i * CW, CW));
                return o;
            }

            internal long[] TotRow()
            {
                var lo = W.LO[Ix("tot_s")]; var hi = W.HI[Ix("tot_s")];
                var t = new long[Tot.Length];
                for (int i = 0; i < t.Length; i++) t[i] = Clamp(Tot[i], lo[i], hi[i]);
                return t;
            }
        }

        internal static long[] Slice(long[] a, int o, int n)
        {
            var r = new long[n];
            Array.Copy(a, o, r, 0, n);
            return r;
        }

        /// <summary>A capped list of fixed-width rows in one flat array sized at
        /// construction: the first `cap` rows kept, later rows counted
        /// (the budgeter's step one applied as they arrive). Total counts every
        /// row offered. Add writes numbers only; Rows() builds the record's
        /// rows on the tick.</summary>
        internal sealed class FixedRows
        {
            internal readonly int Cap, Width;
            private readonly long[] _a;
            internal int Count;
            internal long Omitted, Total;
            internal FixedRows(string key)
            {
                int i = Ix(key);
                Cap = W.CAP[i]; Width = W.LO[i].Length; _a = new long[Cap * Width];
            }
            /// <summary>The slot the next row is written to, or -1 when full (counted).</summary>
            internal int NextSlot()
            {
                Total++;
                if (Count >= Cap) { Omitted++; return -1; }
                return (Count++) * Width;
            }
            internal long[] Raw { get { return _a; } }
            internal void Add(params long[] row)
            {
                int o = NextSlot();
                if (o >= 0) Array.Copy(row, 0, _a, o, Math.Min(row.Length, Width));
            }
            internal List<long[]> Rows()
            {
                var o = new List<long[]>(Count);
                for (int i = 0; i < Count; i++) o.Add(Slice(_a, i * Width, Width));
                return o;
            }
        }

        // -- the time base (design 2.5) ---------------------------------------------------------

        /// <summary>A fixed frame-time histogram (250 us bins up to 100 ms, then one
        /// overflow bin): the median is read at 250 us resolution, with no
        /// per-frame allocation.</summary>
        internal sealed class FrameHist
        {
            internal const int BIN_US = 250, BIN_CAP = 401;
            internal readonly long[] H = new long[BIN_CAP];
            internal long N, Max;
            internal void Add(long us)
            {
                if (us < 0) us = 0;
                int b = (int)Math.Min(us / BIN_US, BIN_CAP - 1);
                H[b]++; N++; if (us > Max) Max = us;
            }
            internal long Median()
            {
                if (N == 0) return 0;
                long half = (N + 1) / 2, acc = 0;
                for (int i = 0; i < BIN_CAP; i++) { acc += H[i]; if (acc >= half) return (long)i * BIN_US + BIN_US / 2; }
                return Max;
            }
            internal void Clear() { Array.Clear(H, 0, BIN_CAP); N = 0; Max = 0; }
        }

        /// <summary>One point's sums on this seat's own clocks (SELF-STATED).</summary>
        internal sealed class PointClock
        {
            internal long Pt, PsRaw, SrvStart, SrvEnd, Frames, Base;
            internal double Real, Game, Slow, Ramp, Clamp;
            internal bool Ramping = true;
            internal readonly FrameHist Hist = new FrameHist();
            internal void Frame(double unscaled, double gameDelta, double engineDelta, double scale, double baseScale)
            {
                Frames++;
                Real += unscaled; Game += gameDelta;
                if (scale < baseScale) Slow += unscaled;
                if (Ramping) { if (scale >= baseScale) Ramping = false; else Ramp += unscaled; }
                double c = unscaled - engineDelta;
                if (c > 0) Clamp += c;
                Hist.Add((long)(unscaled * 1e6));
            }
            /// <summary>[pt, ps, real, game, srv, frames, slow, ramp, clamp, dt_med_us, dt_max_us, base].</summary>
            internal long[] PointRow(long t0)
            {
                return new long[] { CombatEvidenceCore.Clamp(Pt, 0, 99), Wrap(PsRaw - t0), Ms(Real, 3600000), Ms(Game, 3600000),
                                    CombatEvidenceCore.Clamp(Wrap(SrvEnd - SrvStart), -3600000, 3600000), CombatEvidenceCore.Clamp(Frames, 0, 1000000),
                                    Ms(Slow, 3600000), Ms(Ramp, 3600000), Ms(Clamp, 3600000),
                                    CombatEvidenceCore.Clamp(Hist.Median(), 0, 9999999), CombatEvidenceCore.Clamp(Hist.Max, 0, 99999999), CombatEvidenceCore.Clamp(Base, 0, 10000) };
            }
        }

        internal static long Ms(double seconds, long hi) { return Clamp(RoundEven(seconds * 1000.0), 0, hi); }

        /// <summary>tb_tot from the per-point rows (whole game, never trimmed).</summary>
        internal static long[] TbTot(List<long[]> rows, long baseChanges, long points)
        {
            long real = 0, game = 0, srv = 0, frames = 0, slow = 0, ramp = 0, clamp = 0;
            foreach (var r in rows) { real += r[2]; game += r[3]; srv += r[4]; frames += r[5]; slow += r[6]; ramp += r[7]; clamp += r[8]; }
            return new long[] { Clamp(real, 0, 99999999), Clamp(game, 0, 99999999), Clamp(srv, -99999999, 99999999), Clamp(frames, 0, 99999999),
                                Clamp(slow, 0, 99999999), Clamp(ramp, 0, 99999999), Clamp(clamp, 0, 99999999), Clamp(baseChanges, 0, 9999), Clamp(points, 0, 9999) };
        }

        /// <summary>The p3top list from the point's residual samples: the CAP
        /// largest d_perp (ties: the smaller pid, then the earlier sample).</summary>
        internal static List<long[]> TopByPerp(List<long[]> rows, int cap)
        {
            var idx = new List<int>(rows.Count);
            for (int i = 0; i < rows.Count; i++) idx.Add(i);
            idx.Sort((a, b) =>
            {
                int c = rows[b][2].CompareTo(rows[a][2]);
                if (c != 0) return c;
                c = rows[a][0].CompareTo(rows[b][0]);
                return c != 0 ? c : a.CompareTo(b);
            });
            var o = new List<long[]>(Math.Min(cap, rows.Count));
            for (int i = 0; i < idx.Count && o.Count < cap; i++) o.Add(rows[idx[i]]);
            return o;
        }
    }
}
