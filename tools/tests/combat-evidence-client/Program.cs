using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using E = CompetitiveRounds.CombatEvidenceCore;
using W = CompetitiveRounds.CombatEvidenceWire;
using C = CompetitiveRounds.SeatEvidenceCore;

namespace CombatEvidenceTests
{
    /// <summary>The client half of the combat evidence record against the
    /// server's canonical fixture set (the oracle). Modes:
    ///   fixtures DIR    every budget input: the parsed record re-serializes to
    ///                   the input's bytes, the client budgeter's output equals
    ///                   the server's .out.txt, and passes the layout check
    ///   proof DIR       the byte proof equals byte_proof.json
    ///   sign DIR        canonical and HMAC of sign.json's envelopes; the envelope body
    ///   integrator DIR  integrator.json: the single-precision flight bit for bit,
    ///                   the control and turn-mutant residuals
    ///   steering DIR    steering.json: homing packages bit for bit and their
    ///                   p3ht entries, target bounce entries and velocities
    ///   accountant DIR  every fixture group replayed through the cycle accountant:
    ///                   groups at the caps, cycle summaries, omit counts, totals
    ///   replay OUT      synthetic games through the accountant into whole records,
    ///                   written (name, full, budgeted) for run_replay.py
    ///   all DIR         every fixture mode
    /// Exit 0 only when every case passes.</summary>
    internal static class Program
    {
        private static int _fail, _pass;

        private static void Ok(bool cond, string what)
        {
            if (cond) { _pass++; Console.WriteLine("PASS " + what); }
            else { _fail++; Console.WriteLine("FAIL " + what); }
        }

        // -- a small JSON reader (objects keep their key order) ------------------------------

        private sealed class JObject : List<KeyValuePair<string, object>>
        {
            internal object this[string k]
            {
                get { foreach (var kv in this) if (kv.Key == k) return kv.Value; throw new KeyNotFoundException(k); }
            }
            internal bool Has(string k) { foreach (var kv in this) if (kv.Key == k) return true; return false; }
        }

        private sealed class Reader
        {
            private readonly string _s; private int _i;
            internal Reader(string s) { _s = s; }
            private void Ws() { while (_i < _s.Length && char.IsWhiteSpace(_s[_i])) _i++; }
            internal object Value()
            {
                Ws();
                char c = _s[_i];
                if (c == '{')
                {
                    _i++; var o = new JObject(); Ws();
                    if (_s[_i] == '}') { _i++; return o; }
                    while (true)
                    {
                        Ws(); string k = Str(); Ws(); Expect(':'); object v = Value(); o.Add(new KeyValuePair<string, object>(k, v)); Ws();
                        if (_s[_i] == ',') { _i++; continue; }
                        Expect('}'); return o;
                    }
                }
                if (c == '[')
                {
                    _i++; var l = new List<object>(); Ws();
                    if (_s[_i] == ']') { _i++; return l; }
                    while (true)
                    {
                        l.Add(Value()); Ws();
                        if (_s[_i] == ',') { _i++; continue; }
                        Expect(']'); return l;
                    }
                }
                if (c == '"') return Str();
                if (_s.Substring(_i).StartsWith("true")) { _i += 4; return true; }
                if (_s.Substring(_i).StartsWith("false")) { _i += 5; return false; }
                if (_s.Substring(_i).StartsWith("null")) { _i += 4; return null; }
                int st = _i;
                while (_i < _s.Length && "+-0123456789.eE".IndexOf(_s[_i]) >= 0) _i++;
                string num = _s.Substring(st, _i - st);
                if (num.IndexOfAny(new[] { '.', 'e', 'E' }) >= 0) return double.Parse(num, CultureInfo.InvariantCulture);
                return long.Parse(num, CultureInfo.InvariantCulture);
            }
            private void Expect(char c) { if (_s[_i] != c) throw new FormatException("expected " + c + " at " + _i); _i++; }
            private string Str()
            {
                Expect('"');
                var sb = new StringBuilder();
                while (_s[_i] != '"')
                {
                    char c = _s[_i++];
                    if (c != '\\') { sb.Append(c); continue; }
                    char e = _s[_i++];
                    switch (e)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 't': sb.Append('\t'); break;
                        case 'r': sb.Append('\r'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'u': sb.Append((char)Convert.ToInt32(_s.Substring(_i, 4), 16)); _i += 4; break;
                        default: sb.Append(e); break;
                    }
                }
                _i++;
                return sb.ToString();
            }
        }

        private static object Parse(string s) { return new Reader(s).Value(); }
        private static string ReadAscii(string path) { return Encoding.ASCII.GetString(File.ReadAllBytes(path)); }
        private static double D(object o) { return o is long ? (long)o : (double)o; }
        private static long L(object o) { return (long)o; }
        private static List<object> A(object o) { return (List<object>)o; }
        private static long[] Row(object o) { return A(o).Select(L).ToArray(); }
        private static List<long[]> Rows(object o) { return A(o).Select(Row).ToList(); }

        /// <summary>A float.hex string ("0x1.8p+1", "-0x0.0p+0") as a double, exactly.</summary>
        private static double Hex(string h)
        {
            bool neg = h.StartsWith("-");
            if (neg) h = h.Substring(1);
            if (!h.StartsWith("0x")) throw new FormatException(h);
            h = h.Substring(2);
            int p = h.IndexOf('p');
            int exp = int.Parse(h.Substring(p + 1), CultureInfo.InvariantCulture);
            string m = h.Substring(0, p);
            int dot = m.IndexOf('.');
            string ip = dot < 0 ? m : m.Substring(0, dot), fp = dot < 0 ? "" : m.Substring(dot + 1);
            double v = Convert.ToInt64(ip, 16);
            if (fp.Length > 0) v += Math.ScaleB(Convert.ToInt64(fp, 16), -4 * fp.Length);
            v = Math.ScaleB(v, exp);
            return neg ? -v : v;
        }

        private static bool Bits(float got, string hex) { return (double)got == Hex(hex) && (got != 0 || (hex.StartsWith("-") == float.IsNegative(got))); }

        // -- a record from its JSON (the layout's key order is checked by the round trip) -------

        private static E.Rec ToRec(JObject j)
        {
            var r = new E.Rec();
            for (int i = 0; i < E.N; i++)
            {
                object v = j[W.KEYS[i]];
                switch (W.KIND[i])
                {
                    case W.K_INT: r.V[i] = L(v); break;
                    case W.K_ENUM: r.V[i] = (string)v; break;
                    case W.K_ROW: case W.K_HIST: r.V[i] = Row(v); break;
                    case W.K_ROWS: case W.K_LIST: r.V[i] = Rows(v); break;
                    case W.K_GROUPS:
                        r.V[i] = A(v).Select(g => new E.Group { H = Row(A(g)[0]), S = Rows(A(g)[1]), R = Rows(A(g)[2]) }).ToList();
                        break;
                    default:
                        var om = (JObject)v;
                        r.V[i] = E.LIST_IX.Select(li => L(om[W.KEYS[li]])).ToArray();
                        break;
                }
            }
            return r;
        }

        private static readonly string[] BUDGET_INPUTS = { "a24_owner", "a24_meas", "a24_regen_owner", "empty", "r_sections_victim",
                                                           "r_sections_shooter", "m6_25_cycles", "over_cap_owner", "over_cap_meas", "max_width_protected" };

        private static void Fixtures(string dir)
        {
            int same = 0;
            foreach (var name in BUDGET_INPUTS)
            {
                string inText = ReadAscii(Path.Combine(dir, name + ".in.json"));
                string outText = ReadAscii(Path.Combine(dir, name + ".out.txt"));
                var rec = ToRec((JObject)Parse(inText));
                bool round = E.Dumps(rec) == inText;
                string got = E.Budget(rec);
                bool eq = got == outText;
                string check = E.Check(ToRec((JObject)Parse(got)));
                bool bounded = got.Length <= W.RECORD_MAX_BYTES;
                Ok(round && eq && check == null && bounded, "fixture " + name + ": round trip " + round + ", budget equals the server's output " + eq
                   + " (" + got.Length + " of " + outText.Length + " bytes), layout check " + (check ?? "clean"));
                if (round && eq && check == null && bounded) same++;
            }
            Console.WriteLine("server fixtures reproduced: " + same + " of " + BUDGET_INPUTS.Length);
        }

        private static void Proof(string dir)
        {
            var j = (JObject)Parse(ReadAscii(Path.Combine(dir, "byte_proof.json")));
            long[] want = { L(j["limit"]), L(j["never_trimmed_max"]), L(j["group_max"]), L(j["point_max"]), L(j["protected_floor"]) };
            long[] got = E.ByteProof();
            Ok(got.SequenceEqual(want), "byte proof [" + string.Join(",", got) + "] equals the server's [" + string.Join(",", want) + "]");
            // the layout backstop: out-of-bound values are clamped and the record passes the check;
            // a record already at its widest is left byte-identical
            var wide = E.MaxWidthRecord();
            string before = E.Dumps(wide);
            E.ClampToLayout(wide);
            var bad = E.Empty();
            ((List<long[]>)bad["cost"])[0][1] = long.MaxValue;
            ((long[])bad["a1s"])[0] = -5;
            bad["l_hat"] = long.MinValue;
            ((List<long[]>)bad["tb"]).Add(Enumerable.Repeat(long.MaxValue, W.LO[E.Ix("tb")].Length).ToArray());
            bool refusedFirst = E.Check(bad) != null;
            E.ClampToLayout(bad);
            Ok(E.Dumps(wide) == before && refusedFirst && E.Check(bad) == null,
               "layout backstop: a widest record unchanged; an out-of-bound record refused, then clamped and accepted");
        }

        private static void Sign(string dir)
        {
            var outs = new Dictionary<string, string>();
            foreach (var p in Directory.GetFiles(dir, "*.out.txt")) outs[C.Sha256Hex(File.ReadAllBytes(p))] = ReadAscii(p);
            foreach (JObject e in A(Parse(ReadAscii(Path.Combine(dir, "sign.json")))))
            {
                string sha = (string)e["record_sha256"];
                if (!outs.ContainsKey(sha)) { Ok(false, "sign: no fixture output with sha " + sha); continue; }
                string text = outs[sha];
                string canon = E.Canonical((string)e["seat"], (string)e["other"], (string)e["stable"], (string)e["attach"], text);
                string sig = C.Hmac(Encoding.UTF8.GetBytes((string)e["key"]), canon);
                Ok(canon == (string)e["canonical"] && sig == (string)e["sig"], "sign " + e["attach"] + ": canonical " + (canon == (string)e["canonical"])
                   + ", signature " + (sig == (string)e["sig"]));
            }
            // the envelope body: the route's field order, the record as one JSON string
            string rec = ReadAscii(Path.Combine(dir, "a24_owner.out.txt"));
            string s = new string('a', 64);
            string env = E.Envelope("76561198000000001", "76561198000000002", "ranked_cev_000001", "ranked_cev_000001_r8", rec, s);
            var pj = env == null ? null : (JObject)Parse(env);
            bool shape = pj != null && string.Join(",", pj.Select(kv => kv.Key)) == "contract,seat_steam_id,other_steam_id,stable_game_key,attach_key,record,sig"
                         && L(pj["contract"]) == W.CONTRACT && (string)pj["record"] == rec && (string)pj["sig"] == s;
            Ok(shape, "envelope: the route's seven fields in order, the record carried byte for byte");
            Ok(E.Envelope("76561198000000001", "76561198000000001", "ranked_cev_000001", "ranked_cev_000001_r8", rec, s) == null
               && E.Envelope("76561198000000001", "76561198000000002", "ranked_cev_000001", "ranked_cev_000001_r8", rec + "é", s) == null
               && E.Envelope("76561198000000001", "76561198000000002", "ranked_cev_000001", "ranked_cev_000001_r8", rec, "ab") == null,
               "envelope refuses a self pair, a non-ASCII record and a short signature");
        }

        private static E.MovePrm Move(JObject p)
        {
            return new E.MovePrm
            {
                Gravity = (float)D(p["gravity"]), Drag = (float)D(p["drag"]), DragMin = (float)D(p["drag_min"]), Mult = (float)D(p["mult"]),
                Sim = (float)D(p["sim"]), AllowStop = (bool)p["allow_stop"], SimGravity = (int)L(p["sim_gravity"]),
            };
        }

        private static E.St State(JObject s) { return new E.St((float)D(s["x"]), (float)D(s["y"]), (float)D(s["vx"]), (float)D(s["vy"])); }
        private static List<double> Frames(object o) { return A(o).Select(D).ToList(); }
        private static bool Res(long[] got, JObject want)
        {
            return got[0] == L(want["d_perp"]) && got[1] == L(want["d_along"]) && got[2] == L(want["ang"]);
        }

        private static void Integrator(string dir)
        {
            foreach (JObject c in A(Parse(ReadAscii(Path.Combine(dir, "integrator.json")))))
            {
                var s = State((JObject)c["state"]); var fr = Frames(c["frames"]); var p = Move((JObject)c["prm"]);
                var pred = E.Integrate(s, fr, p);
                var ph = (JObject)c["pred"];
                bool bits = Bits(pred.X, (string)ph["x"]) && Bits(pred.Y, (string)ph["y"]) && Bits(pred.VX, (string)ph["vx"]) && Bits(pred.VY, (string)ph["vy"]);
                var ctl = E.Residual(pred, E.Trace(s, fr, p, 0));
                var mut = E.Residual(pred, E.Trace(s, fr, p, D(c["turn_per_frame"])));
                bool ctlOk = Res(ctl, (JObject)c["control_residual"]), mutOk = Res(mut, (JObject)c["mutant_residual"]);
                Ok(bits && ctlOk && mutOk && !ctl.SequenceEqual(mut), "integrator " + c["name"] + ": prediction bit for bit " + bits
                   + ", control residual " + ctlOk + ", turn mutant residual [" + string.Join(",", mut) + "] " + mutOk);
            }
        }

        private static E.HomingPrm Homing(JObject p)
        {
            return new E.HomingPrm { Move = Move(p), Amount = (float)D(p["amount"]), ScalingDrag = (float)D(p["scaling_drag"]), HDrag = (float)D(p["h_drag"]), Force = (float)D(p["force"]) };
        }

        private static void Steering(string dir)
        {
            var j = (JObject)Parse(ReadAscii(Path.Combine(dir, "steering.json")));
            foreach (JObject c in A(j["homing"]))
            {
                var s = State((JObject)c["state"]); var tg = A(c["target"]); var fr = Frames(c["frames"]); var pj = (JObject)c["prm"];
                var hp = Homing(pj);
                int every = (int)L(c["sync_every"]);
                var packs = E.HomingTrace(s, (float)D(tg[0]), (float)D(tg[1]), fr, hp, every, 0);
                var want = A(c["packages"]);
                bool bits = packs.Count == want.Count;
                for (int i = 0; bits && i < packs.Count; i++)
                {
                    var w = A(want[i]); var st = (JObject)w[1];
                    bits = Bits(packs[i].Key, (string)w[0]) && Bits(packs[i].Value.X, (string)st["x"]) && Bits(packs[i].Value.Y, (string)st["y"])
                           && Bits(packs[i].Value.VX, (string)st["vx"]) && Bits(packs[i].Value.VY, (string)st["vy"]);
                }
                var entry = E.HomingEntry(1, 0, packs, D(pj["force"]), D(pj["amount"]));
                var turned = E.HomingTrace(s, (float)D(tg[0]), (float)D(tg[1]), fr, hp, every, D(c["turn_per_frame"]));
                var mentry = E.HomingEntry(1, 0, turned, D(pj["force"]), D(pj["amount"]));
                bool eOk = entry.SequenceEqual(Row(c["entry"])), mOk = mentry.SequenceEqual(Row(c["mutant_entry"]));
                Ok(bits && eOk && mOk && !entry.SequenceEqual(mentry), "homing " + c["name"] + ": packages bit for bit " + bits + ", entry ["
                   + string.Join(",", entry) + "] " + eOk + ", mutant entry [" + string.Join(",", mentry) + "] " + mOk);
            }
            foreach (JObject c in A(j["bounce"]))
            {
                var s = State((JObject)c["state"]); var n = A(c["normal"]); var me = A(c["me"]); var fr = Frames(c["frames"]); var pj = (JObject)c["prm"];
                bool hasT = c["target"] != null;
                var tg = hasT ? A(c["target"]) : null;
                float tx = hasT ? (float)D(tg[0]) : 0f, ty = hasT ? (float)D(tg[1]) : 0f;
                float vx, vy, mvx, mvy;
                var got = E.TargetBounce(s, (float)D(n[0]), (float)D(n[1]), hasT, tx, ty, (float)D(me[0]), (float)D(me[1]), fr,
                                         (float)D(pj["gravity"]), (float)D(pj["speed_m"]), W.BOUNCE_WAIT_S, out vx, out vy);
                var early = E.TargetBounce(s, (float)D(n[0]), (float)D(n[1]), hasT, tx, ty, (float)D(me[0]), (float)D(me[1]), fr,
                                           (float)D(pj["gravity"]), (float)D(pj["speed_m"]), 0.0, out mvx, out mvy);
                var we = (JObject)c["entry"]; var wm = (JObject)c["mutant_entry"]; var wv = (JObject)c["velocity"];
                bool eOk = got != null && got[0] == L(we["gap"]) && got[1] == L(we["has_retarget"]) && got[2] == L(we["ang_to_me"]);
                bool mOk = early != null && early[0] == L(wm["gap"]) && early[1] == L(wm["has_retarget"]) && early[2] == L(wm["ang_to_me"]);
                bool vOk = Bits(vx, (string)wv["vx"]) && Bits(vy, (string)wv["vy"]);
                Ok(eOk && mOk && vOk && !got.SequenceEqual(early), "target bounce " + c["name"] + ": entry " + eOk + ", velocity bit for bit " + vOk
                   + ", early-send mutant entry " + mOk);
            }
        }

        // -- the cycle accountant against every fixture group ------------------------------------

        private static readonly string[] ACCOUNT_INPUTS = { "a24_owner", "a24_meas", "a24_regen_owner", "m6_25_cycles", "over_cap_owner", "over_cap_meas" };

        /// <summary>One gun's listed groups replayed through a fresh accountant, in order.</summary>
        internal static E.GunAccount Replay(List<E.Group> groups, List<long[]> gunList, bool own)
        {
            var acct = new E.GunAccount(own);
            int gi = E.Ix(own ? "sh_s" : "sh_o");
            string[] sn = W.SNAMES[gi], hn = W.HNAMES[gi], rn = W.RNAMES[gi];
            Func<string[], string, int> ix = (a, k) => Array.IndexOf(a, k);
            foreach (var g in groups)
            {
                long pt = g.H[ix(hn, "pt")];
                long[] blk = null;
                foreach (var e in gunList) if (e[0] <= pt) blk = e;
                acct.Point = pt; acct.Mag = blk[1]; acct.Rexp = blk[5];
                long pid = g.H[ix(hn, "pid0")], st = g.H[ix(hn, "s0")];
                int ri = 0;
                for (int j = 0; j < g.S.Count; j++)
                {
                    while (ri < g.R.Count && g.R[ri][ix(rn, "k")] <= j)
                    {
                        var r = g.R[ri++];
                        acct.AddRegen(r[ix(rn, "amt")], r[ix(rn, "st")], r[ix(rn, "gap_g")], r[ix(rn, "gap_s")], r[ix(rn, "gap_r")]);
                    }
                    var s = g.S[j];
                    pid += s[ix(sn, "dpid")]; st = E.Wrap(st + s[ix(sn, "dt")]);
                    bool rl = s[ix(sn, "reloading")] != 0;
                    if (own) acct.AddShot(pid, st, s[ix(sn, "ammo_before")], rl, s[ix(sn, "counter")], s[ix(sn, "rep")], s[ix(sn, "since")], s[ix(sn, "fl")], -1);
                    else acct.AddShot(pid, st, s[ix(sn, "ammo_before")], rl, s[ix(sn, "counter")], -1, -1, 0, s[ix(sn, "am")]);
                }
                while (ri < g.R.Count)
                {
                    var r = g.R[ri++];
                    acct.AddRegen(r[ix(rn, "amt")], r[ix(rn, "st")], r[ix(rn, "gap_g")], r[ix(rn, "gap_s")], r[ix(rn, "gap_r")]);
                }
                acct.CloseCycle(g.H[ix(hn, "end")], g.H[ix(hn, "src")], g.H[ix(hn, "amt")], g.H[ix(hn, "st_end")],
                                g.H[ix(hn, "rl_g")], g.H[ix(hn, "rl_s")], g.H[ix(hn, "rl_r")]);
            }
            return acct;
        }

        private static bool SameRows(List<long[]> a, List<long[]> b)
        {
            if (a.Count != b.Count) return false;
            for (int i = 0; i < a.Count; i++) if (!a[i].SequenceEqual(b[i])) return false;
            return true;
        }

        /// <summary>The fixture's group as the client lists it: the caps of step
        /// one, and the counter of a shot taken while not reloading written -1
        /// (design 2.2: rc is -1 when not reloading; the server's synthetic
        /// fixtures carry a counter there, which the rebuild never reads).</summary>
        private static E.Group AsListed(E.Group g, int i, bool own)
        {
            int rlx = Array.IndexOf(W.SNAMES[i], "reloading"), cx = Array.IndexOf(W.SNAMES[i], "counter");
            var o = g.Copy(W.SHOT_CAP[i], W.REGEN_CAP[i]);
            o.S = o.S.Select(s => { var c = (long[])s.Clone(); if (c[rlx] == 0) c[cx] = -1; return c; }).ToList();
            return o;
        }

        private static void Accountant(string dir)
        {
            foreach (var name in ACCOUNT_INPUTS)
            {
                var rec = ToRec((JObject)Parse(ReadAscii(Path.Combine(dir, name + ".in.json"))));
                foreach (bool own in new[] { true, false })
                {
                    string side = own ? "s" : "o";
                    var groups = (List<E.Group>)rec["sh_" + side];
                    if (groups.Count == 0) continue;
                    int gi = E.Ix("sh_" + side);
                    var acct = Replay(groups, (List<long[]>)rec["gun_" + side], own);
                    var want = groups.Take(W.CAP[gi]).Select(g => AsListed(g, gi, own)).ToList();
                    var got = acct.Groups();
                    bool gOk = got.Count == want.Count;
                    for (int k = 0; gOk && k < got.Count; k++)
                        gOk = got[k].H.SequenceEqual(want[k].H) && SameRows(got[k].S, want[k].S) && SameRows(got[k].R, want[k].R);
                    bool omitOk = acct.GroupsOmitted == Math.Max(0, groups.Count - W.CAP[gi])
                                  && acct.CxOmitted == rec.Omit[E.OmitPos("cx_" + side)];
                    bool cxOk = SameRows(acct.CxRows(), (List<long[]>)rec["cx_" + side]);
                    bool totOk = acct.TotRow().SequenceEqual((long[])rec["tot_" + side]);
                    Ok(gOk && omitOk && cxOk && totOk, "accountant " + name + " gun " + side + " (" + groups.Count + " groups): listed groups " + gOk
                       + ", omit counts " + omitOk + ", cycle summaries " + cxOk + ", totals " + totOk
                       + (totOk ? "" : " got [" + string.Join(",", acct.TotRow()) + "] want [" + string.Join(",", (long[])rec["tot_" + side]) + "]"));
                }
            }
        }

        // -- synthetic games for the server-side replay -------------------------------------------

        private sealed class Gun
        {
            internal readonly E.GunAccount Acct; internal readonly bool Own;
            internal readonly List<long[]> Stats = new List<long[]>();
            internal long Mag, Rexp;
            internal Gun(bool own) { Own = own; Acct = new E.GunAccount(own); }
        }

        private static void PointStart(Gun g, Random rnd, int pt, bool keep)
        {
            if (!keep || g.Stats.Count == 0) { g.Mag = 1 + rnd.Next(6); g.Rexp = 300 + rnd.Next(2000); }
            g.Acct.Mag = g.Mag; g.Acct.Rexp = g.Rexp; g.Acct.Point = pt;
            int i = E.Ix(g.Own ? "gun_s" : "gun_o");
            var row = E.ZeroRow(i);
            row[0] = pt; row[1] = g.Mag; row[5] = g.Rexp;
            if (g.Stats.Count == 0 || g.Stats[g.Stats.Count - 1][1] != g.Mag || g.Stats[g.Stats.Count - 1][5] != g.Rexp) g.Stats.Add(row);
        }

        private static void Fire(Gun g, Random rnd, ref long stamp, ref long pid, bool big)
        {
            int volleys = big ? 1 + rnd.Next(6) : (rnd.Next(8) == 0 ? 15 + rnd.Next(10) : 1 + rnd.Next(8));   // some cycles over the 32-shot cap
            long ammo = g.Mag; bool rl = false;
            for (int v = 0; v < volleys; v++)
            {
                stamp = E.Wrap(stamp + 40 + rnd.Next(400));
                if (rnd.Next(6) == 0) g.Acct.AddRegen(1 + rnd.Next(2), stamp - 5, rnd.Next(300), rnd.Next(300), rnd.Next(320));
                int nproj = 1 + rnd.Next(3);
                bool leadNonFirst = rnd.Next(5) == 0;
                for (int p = 0; p < nproj; p++)
                {
                    bool first = p == 0 && !leadNonFirst;
                    long rep = -1, since = -1, fl = 0, am = -1;
                    if (g.Own && first)
                    {
                        rep = rnd.Next(3) == 0 ? 1 + rnd.Next(3) : 0;
                        if (rep == 0)
                        {
                            since = rnd.Next(1200);
                            fl = W.FL_USE_AMMO | (rl ? W.FL_RELOADING : 0) | (rnd.Next(4) == 0 ? W.FL_FORCED : 0);
                        }
                    }
                    else if (!g.Own && first) am = rnd.Next(120);
                    g.Acct.AddShot(pid, stamp, ammo, rl, rl ? rnd.Next(1500) : -1, rep, since, fl, am);
                    pid += 1 + (rnd.Next(8) == 0 ? rnd.Next(50) : 0);
                    ammo--;
                    if (ammo <= 0) rl = true;
                }
                if (rnd.Next(9) == 0) g.Acct.AddNoInit();
                if (rnd.Next(12) == 0) g.Acct.AddKind(rnd.Next(2) == 0);
            }
            int end = rnd.Next(5);
            stamp = E.Wrap(stamp + 100 + rnd.Next(1500));
            if (end == 0) g.Acct.CloseCycle(W.END_TIMER, W.SRC_NONE, g.Mag, stamp, g.Rexp + rnd.Next(40), g.Rexp + rnd.Next(60), g.Rexp + rnd.Next(80));
            else if (end == 1) g.Acct.CloseCycle(W.END_AUTOMATIC, W.SRC_NONE, 1 + rnd.Next((int)g.Mag), stamp, -1, -1, -1);
            else if (end == 2) g.Acct.CloseCycle(W.END_EXTERNAL, 1 + rnd.Next(2), g.Mag, stamp, -1, -1, -1);
            else if (end == 3) g.Acct.CloseCycle(W.END_REDRAW, W.SRC_NONE, g.Mag, stamp, -1, -1, -1);
            if (rnd.Next(10) == 0) g.Acct.CloseCycle(W.END_TIMER, W.SRC_NONE, g.Mag, stamp, 1, 1, 1);   // a refill with nothing open: rf_idle
        }

        internal static E.Rec Synthetic(int seed, bool big)
        {
            var rnd = new Random(seed);
            var own = new Gun(true); var opp = new Gun(false);
            var tb = new List<long[]>();
            long stamp = rnd.Next(-2000000000, 2000000000), pid = 1000 + rnd.Next(5000);
            if (seed % 7 == 3) stamp = int.MaxValue - 3000;   // the stamp clock wraps inside a cycle
            int points = big ? 2 : 1 + rnd.Next(4);
            for (int pt = 0; pt < points; pt++)
            {
                PointStart(own, rnd, pt, rnd.Next(2) == 0); PointStart(opp, rnd, pt, rnd.Next(2) == 0);
                var row = E.ZeroRow(E.Ix("tb")); row[0] = pt; tb.Add(row);
                int cycles = big ? 85 + rnd.Next(10) : 1 + rnd.Next(4);   // big: over the 160-group cap per gun
                for (int c = 0; c < cycles; c++)
                {
                    Fire(own, rnd, ref stamp, ref pid, big);
                    Fire(opp, rnd, ref stamp, ref pid, big);
                }
                own.Acct.CloseCycle(W.END_POINT, W.SRC_NONE, -1, stamp, -1, -1, -1);
                opp.Acct.CloseCycle(W.END_POINT, W.SRC_NONE, -1, stamp, -1, -1, -1);
            }
            var r = E.Empty();
            r["tb"] = tb;
            r["tb_tot"] = E.TbTot(tb, 0, points);
            foreach (var g in new[] { own, opp })
            {
                string side = g.Own ? "s" : "o";
                r["gun_" + side] = g.Stats.Take(W.CAP[E.Ix("gun_" + side)]).ToList();
                r["sh_" + side] = g.Acct.Groups();
                r["cx_" + side] = g.Acct.CxRows();
                r["tot_" + side] = g.Acct.TotRow();
                r.Omit[E.OmitPos("sh_" + side)] = g.Acct.GroupsOmitted;
                r.Omit[E.OmitPos("cx_" + side)] = g.Acct.CxOmitted;
            }
            return r;
        }

        private static void ReplayOut(string outPath, int n)
        {
            var sb = new StringBuilder();
            int clean = 0;
            for (int seed = 0; seed < n; seed++)
            {
                bool big = seed % 5 == 4;
                var rec = Synthetic(seed, big);
                string full = E.Dumps(rec);
                string budgeted = E.Budget(rec);
                string check = E.Check(ToRec((JObject)Parse(budgeted)));
                if (check == null) clean++;
                else Console.WriteLine("FAIL synthetic " + seed + ": layout check " + check);
                sb.Append("seed" + seed + (big ? "_big" : "")).Append('\t').Append(full).Append('\t').Append(budgeted).Append('\n');
            }
            File.WriteAllBytes(outPath, Encoding.ASCII.GetBytes(sb.ToString()));
            Ok(clean == n, "synthetic games: " + n + " written, " + clean + " pass the layout check after the budget");
        }

        private static int Main(string[] args)
        {
            if (args.Length < 2) { Console.WriteLine("usage: CombatEvidenceTests MODE DIR|OUT [N]"); return 2; }
            string mode = args[0], dir = args[1];
            try
            {
                switch (mode)
                {
                    case "fixtures": Fixtures(dir); break;
                    case "proof": Proof(dir); break;
                    case "sign": Sign(dir); break;
                    case "integrator": Integrator(dir); break;
                    case "steering": Steering(dir); break;
                    case "accountant": Accountant(dir); break;
                    case "replay": ReplayOut(dir, args.Length > 2 ? int.Parse(args[2], CultureInfo.InvariantCulture) : 60); break;
                    case "all": Fixtures(dir); Proof(dir); Sign(dir); Integrator(dir); Steering(dir); Accountant(dir); break;
                    default: Console.WriteLine("unknown mode " + mode); return 2;
                }
            }
            catch (Exception ex) { Console.WriteLine("FAIL " + mode + ": " + ex.GetType().Name + " " + ex.Message); _fail++; }
            Console.WriteLine(mode + ": " + _pass + " passed, " + _fail + " failed");
            return _fail == 0 ? 0 : 1;
        }
    }
}
