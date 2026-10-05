using CompetitiveRounds;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;

namespace CompetitiveRounds.Harness
{
    using R = FfaLateRules;

    /// <summary>The late-rules gate (evidence sec8.2).
    ///
    ///   BASELINE  FfaLateRules.SelfTest() over the real functions passes every
    ///             case, and ran more than zero of them.
    ///   MUTANTS   each wrong implementation named in K33, K42, K44 and K45
    ///             turns EXACTLY its declared fixtures red, its named fixture
    ///             among them. The declared sets were written from the rules
    ///             before any run; a mutant that reddens a fixture it should
    ///             not, or misses one, is a MISMATCH, never re-declared to fit.
    ///   TWINS     each behaviour-preserving implementation stays green with
    ///             printed lines identical to the baseline's.
    ///
    /// The mutants live here and not in the plugin: they reach the rules only
    /// through SelfTest's Impl seam, whose fields default to the real
    /// functions, plus the simulator knobs where the design's mutant is a
    /// wrong ORDER of a client's steps rather than a wrong rule.
    ///
    /// The harness's worlds give actors 1 to 3 kind s and 4 and 5 kind l in
    /// every simulated room (SelfTest's World, N7Receiver and N9Receiver), so
    /// the kind-s-only e1 mutant can read a sender's kind from its actor.</summary>
    internal static class Program
    {
        private sealed class Variant
        {
            internal string Name;
            internal string Row;
            internal string Named;
            internal string[] Red;
            internal Action<R.Impl> Apply;
        }

        /// <summary>WP7's client half: FfaLateRules.ChainOf and Fnv64 on the
        /// design's vectors (lobby8 1a2b3c4d; entries (2, 7) then (4, 9);
        /// the empty string; "a"). The structure test compares each line
        /// with the literal vector and with the server's _ffa_epoch_chain.</summary>
        private static int Wp7()
        {
            var entries = new List<R.EpochEntry> { new R.EpochEntry(2, 7), new R.EpochEntry(4, 9) };
            Console.WriteLine("wp7 chain n=1 " + R.ChainOf("1a2b3c4d", entries, 1));
            Console.WriteLine("wp7 chain n=2 " + R.ChainOf("1a2b3c4d", entries, 2));
            Console.WriteLine("wp7 fnv empty " + R.Hex16(R.Fnv64("")));
            Console.WriteLine("wp7 fnv a " + R.Hex16(R.Fnv64("a")));
            return 0;
        }

        private static int Main(string[] args)
        {
            bool quiet = Array.IndexOf(args, "--quiet") >= 0;
            if (Array.IndexOf(args, "--wp7") >= 0)
                return Wp7();
            Console.WriteLine("=== late-rules-harness ===");
            // Provenance for a captured log. Every line that can differ
            // between two runs of the same source starts with "invocation",
            // so a trace that must compare byte-equal drops exactly those.
            Console.WriteLine("invocation:     " + Environment.CommandLine);
            Console.WriteLine("invocation-cwd: " + Environment.CurrentDirectory);
            Console.WriteLine("invocation-utc: "
                              + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture));
            Console.WriteLine("invocation-rt:  " + Environment.Version);

            R.SelfTestResult baseline;
            try { baseline = R.SelfTest(); }
            catch (Exception ex)
            {
                Console.WriteLine("baseline THREW " + ex.GetType().Name + ": " + ex.Message);
                Console.WriteLine("RESULT verdict=THREW");
                return 2;
            }
            int run = baseline.Passed + baseline.Failed;
            Console.WriteLine("baseline cases=" + I(run) + " pass=" + I(baseline.Passed) + " fail="
                              + I(baseline.Failed));
            if (!quiet)
                Console.Write(baseline.Lines.ToString());
            foreach (var kv in baseline.Failures.OrderBy(k => k.Key, StringComparer.Ordinal))
                Console.WriteLine("baseline FAIL case=" + kv.Key + " what=" + kv.Value);
            bool ok = run > 0 && baseline.Failed == 0;
            if (run == 0)
                Console.WriteLine("GATE FAIL the baseline ran zero cases");
            string baseLines = baseline.Lines.ToString();
            var baseSet = new HashSet<string>(baseLines.Split('\n'), StringComparer.Ordinal);

            int mOk = 0, mAll = 0;
            foreach (var v in Mutants())
            {
                mAll++;
                var impl = new R.Impl();
                v.Apply(impl);
                var res = R.SelfTest(impl);
                var red = res.Failures.Keys.OrderBy(k => k, StringComparer.Ordinal).ToArray();
                var want = v.Red.OrderBy(k => k, StringComparer.Ordinal).ToArray();
                bool named = red.Contains(v.Named);
                bool exact = red.SequenceEqual(want);
                bool good = named && exact && baseline.Failed == 0;
                if (good) mOk++;
                Console.WriteLine("mutant " + v.Name + " row=" + v.Row + " named=" + v.Named + " red={"
                                  + string.Join(",", red) + "} declared={" + string.Join(",", want) + "} verdict="
                                  + (good ? "RED-NAMED" : "MISMATCH"));
                // the enumeration figures this mutant moved, for comparison with
                // the boundary model's (sec8.5); the verdict does not read them
                foreach (string line in res.Lines.ToString().Split('\n'))
                    if ((line.StartsWith("K45.xi.n7 n7", StringComparison.Ordinal)
                         || line.StartsWith("K45.xi.count count", StringComparison.Ordinal)
                         || line.StartsWith("K45.xii.e n9", StringComparison.Ordinal))
                        && !baseSet.Contains(line))
                        Console.WriteLine("  figure " + line);
                if (!good)
                    foreach (string c in red.Union(want).OrderBy(k => k, StringComparer.Ordinal))
                    {
                        string what;
                        res.Failures.TryGetValue(c, out what);
                        Console.WriteLine("  " + c + (red.Contains(c) ? " red" : " green") + " declared="
                                          + (want.Contains(c) ? "red" : "green") + (what != null ? " what=" + what : ""));
                    }
            }

            int tOk = 0, tAll = 0;
            foreach (var v in Twins())
            {
                tAll++;
                var impl = new R.Impl();
                v.Apply(impl);
                var res = R.SelfTest(impl);
                string lines = res.Lines.ToString();
                bool same = lines == baseLines;
                bool good = res.Failed == 0 && same && baseline.Failed == 0;
                if (good) tOk++;
                Console.WriteLine("twin " + v.Name + " row=" + v.Row + " fail=" + I(res.Failed) + " lines="
                                  + (same ? "identical" : "differ") + " verdict=" + (good ? "INERT" : "NOT-INERT"));
                if (!same)
                    Console.WriteLine("  first difference: " + FirstDifference(baseLines, lines));
                foreach (var kv in res.Failures.OrderBy(k => k.Key, StringComparer.Ordinal))
                    Console.WriteLine("  " + kv.Key + " what=" + kv.Value);
            }

            ok = ok && mOk == mAll && tOk == tAll && mAll > 0 && tAll > 0;
            Console.WriteLine("RESULT baseline=" + (baseline.Failed == 0 && run > 0 ? "GREEN" : "RED") + " cases="
                              + I(run) + " mutants=" + I(mOk) + "/" + I(mAll) + " twins=" + I(tOk) + "/" + I(tAll)
                              + " verdict=" + (ok ? "PASS" : "FAIL"));
            return ok ? 0 : 1;
        }

        private static string I(int v)
        {
            return v.ToString(CultureInfo.InvariantCulture);
        }

        private static string FirstDifference(string a, string b)
        {
            var la = a.Split('\n');
            var lb = b.Split('\n');
            for (int i = 0; i < Math.Max(la.Length, lb.Length); i++)
            {
                string x = i < la.Length ? la[i] : "<none>";
                string y = i < lb.Length ? lb[i] : "<none>";
                if (x != y)
                    return "line " + I(i + 1) + " baseline=[" + x + "] twin=[" + y + "]";
            }
            return "none";
        }

        private static Variant M(string name, string row, string named, string[] red, Action<R.Impl> apply)
        {
            return new Variant { Name = name, Row = row, Named = named, Red = red, Apply = apply };
        }

        private static Variant T(string name, string row, Action<R.Impl> apply)
        {
            return new Variant { Name = name, Row = row, Named = null, Red = new string[0], Apply = apply };
        }

        private static string[] S(params string[] xs)
        {
            return xs;
        }

        private static bool HarnessKindS(int actor)
        {
            return actor >= 1 && actor <= 3;
        }

        // ---------------------------------------------------------------- re-expressions the mutants share

        /// <summary>The digest gate with its skips and thresholds as knobs; the
        /// real rule is (false, false, 1, false).</summary>
        private static bool DigestWith(string snapDigest, int g, int k, int lateGame, IList<R.PeerBd> peers,
                                       out int peer, bool countMaster, bool countUnkept, int minAgree,
                                       bool differOk)
        {
            peer = -1;
            int agree = 0;
            bool differ = false;
            if (peers != null)
                foreach (var p in peers)
                {
                    if (p.IsMaster && !countMaster) continue;
                    if (!p.Kept && !countUnkept) continue;
                    int pg, pk;
                    string ph;
                    if (!R.ParseBd(p.Bd, out pg, out pk, out ph) || pg != g || pk != k)
                        continue;
                    if (ph != snapDigest) { differ = true; continue; }
                    agree++;
                    if (peer < 0 || p.Slot < peer) peer = p.Slot;
                }
            return agree >= minAgree && (differOk || !differ) && g >= lateGame;
        }

        private static R.FenceChoice NextAbove(int self, IList<int> present)
        {
            var sorted = new List<int>(present ?? new List<int>());
            sorted.Sort();
            foreach (int a in sorted)
                if (a > self)
                    return new R.FenceChoice { To = a, Why = "no_grant_next" };
            foreach (int a in sorted)
                if (a != self)
                    return new R.FenceChoice { To = a, Why = "no_grant_next" };
            return new R.FenceChoice { To = -1, Why = "none" };
        }

        private static long Pack(int game, int k)
        {
            return game * 1000000L + k;
        }

        // ---------------------------------------------------------------- the mutants

        private static IEnumerable<Variant> Mutants()
        {
            // K33: the spawn gate and the late spawn
            yield return M("seed_alone", "K33", "K33.i", S("K33.i", "K33.ii", "K33.iii"), i =>
                i.MaySpawn = (late, so, sa, snap, dig, seed, scale, ci) =>
                    late ? snap && seed && scale && !ci : R.MaySpawn(late, so, sa, snap, dig, seed, scale, ci));
            yield return M("master_or_unkept_bd", "K33", "K33.iii", S("K33.i", "K33.iii"), i =>
                i.DigestGate = (string d, int g, int k, int lg, IList<R.PeerBd> peers, out int peer) =>
                    DigestWith(d, g, k, lg, peers, out peer, true, true, 1, false));
            yield return M("snapshot_opens_arrival", "K33", "K33.i",
                           S("K33.i", "K33.ii", "K33.iii", "K33.iv", "K33.v", "K33.vi"), i =>
                i.MaySpawn = (late, so, sa, snap, dig, seed, scale, ci) =>
                    !late ? so || sa || snap : R.MaySpawn(late, so, sa, snap, dig, seed, scale, ci));
            yield return M("no_scale_compare", "K33", "K33.vi", S("K33.vi"), i =>
                i.MaySpawn = (late, so, sa, snap, dig, seed, scale, ci) =>
                    R.MaySpawn(late, so, sa, snap, dig, seed, true, ci));

            // K44: the digest check
            yield return M("no_peer_needed", "K44", "K33.i", S("K33.i", "K33.iii"), i =>
                i.DigestGate = (string d, int g, int k, int lg, IList<R.PeerBd> peers, out int peer) =>
                    DigestWith(d, g, k, lg, peers, out peer, false, false, 0, false));
            yield return M("master_bd_counts", "K44", "K33.i", S("K33.i", "K33.iii"), i =>
                i.DigestGate = (string d, int g, int k, int lg, IList<R.PeerBd> peers, out int peer) =>
                    DigestWith(d, g, k, lg, peers, out peer, true, false, 1, false));
            yield return M("unkept_bd_counts", "K44", "K33.iii", S("K33.iii"), i =>
                i.DigestGate = (string d, int g, int k, int lg, IList<R.PeerBd> peers, out int peer) =>
                    DigestWith(d, g, k, lg, peers, out peer, false, true, 1, false));
            yield return M("one_differs_ok", "K44", "K33.ii", S("K33.ii"), i =>
                i.DigestGate = (string d, int g, int k, int lg, IList<R.PeerBd> peers, out int peer) =>
                    DigestWith(d, g, k, lg, peers, out peer, false, false, 1, true));
            yield return M("kills_in_digest", "K44", "K44", S("K33.iv", "K33.vi", "K44"), i =>
                i.BoundaryDigest = (g, k, lvl, slots) =>
                {
                    var sb = new StringBuilder(R.BoundaryDigest(g, k, lvl, slots));
                    var ordered = new List<R.SlotState>(slots);
                    ordered.Sort((x, y) => x.Slot.CompareTo(y.Slot));
                    foreach (var s in ordered)
                        sb.Append('|').Append(s.Kills.ToString(CultureInfo.InvariantCulture));
                    return R.Hex16(R.Fnv64(sb.ToString()));
                });

            // K42: the positional pairing and fixtures a, d and e
            yield return M("pair_by_position", "K42", "K42.pair", S("K42.pair"), i =>
                i.PairIndices = kept =>
                {
                    var idx = new int[kept.Length];
                    for (int n = 0; n < kept.Length; n++)
                        idx[n] = kept[n] ? n : -1;
                    return idx;
                });
            yield return M("view_from_local_grant", "K42", "K42.a", S("K42.a", "K42.d", "K45.vii"), i =>
            {
                i.KeptActorTest = (gate, hg, a, grants, rec, pe) =>
                    !hg || R.KeptActorValue(gate, hg, a, grants, rec, pe);
                i.MasterKeptTest = (gate, hg, rg, m, grants, rec, pe) =>
                    !hg || R.MasterKeptValue(gate, hg, rg, m, grants, rec, pe);
            });
            yield return M("master_kept_no_list", "K42", "K42.a", S("K42.a", "K45.vii"), i =>
                i.MasterKeptTest = (gate, hg, rg, m, grants, rec, pe) =>
                    (gate != R.Gate.Ungated && !rg) || R.MasterKeptValue(gate, hg, rg, m, grants, rec, pe));
            yield return M("fence_ungranted", "K42", "K42.a", S("K42.a", "K45.vii"), i =>
                i.FenceTarget = (self, present, grants, hg, kept, lagged, ho) =>
                    hg ? R.FenceTarget(self, present, grants, hg, kept, lagged, ho)
                       : (ho ? new R.FenceChoice { To = -1, Why = "none" } : NextAbove(self, present)));
            yield return M("gate_unknown_ungated", "K42", "K42.d", S("K42.d", "K45.vii"), i =>
                i.GateValue = (hs, sa, sas, spe, tr, ea, sp) =>
                    !hs ? new R.GateResult { State = R.Gate.Ungated, Src = "default" }
                        : R.GateValue(hs, sa, sas, spe, tr, ea, sp));
            yield return M("gate_pre_entry_honoured", "K42", "K42.d", S("K42.d"), i =>
                i.GateValue = (hs, sa, sas, spe, tr, ea, sp) => R.GateValue(hs, sa, sas, true, tr, ea, sp));
            yield return M("gate_statement_undoes_trigger", "K42", "K42.d", S("K42.a", "K42.d"), i =>
                i.GateValue = (hs, sa, sas, spe, tr, ea, sp) =>
                    hs && sa && spe && !sas && ea && !sp
                        ? new R.GateResult { State = R.Gate.Pre, Src = "statement" }
                        : R.GateValue(hs, sa, sas, spe, tr, ea, sp));
            yield return M("scale_judge_at_load", "K42", "K42.e", S("K42.e"), i => i.ScaleJudgeAtLoad = true);
            yield return M("scale_keep_across_load", "K42", "K42.e", S("K42.e"), i =>
                i.ConsumeScale = (recs, g, k) => { });
            yield return M("scale_clear_at_switch", "K42", "K42.e", S("K42.e", "K45.xi.count"), i =>
                i.ScaleClearAtSwitch = true);
            yield return M("scale_no_hold", "K42", "K42.e", S("K42.e", "K45.xi.count"), i => i.ScaleNoHold = true);
            yield return M("scale_play_on", "K42", "K42.e", S("K42.e", "K45.xi.count"), i =>
                i.ScaleDecision = (recs, g, k, kk) =>
                {
                    var r = R.ScaleDecision(recs, g, k, kk);
                    r.LagOut = false;
                    return r;
                });
            yield return M("scale_game_alone", "K42", "K42.e", S("K42.e"), i =>
                i.ScaleDecision = (recs, g, k, kk) => R.ScaleDecision(recs, g, k, false));
            yield return M("scale_unconfirmed_used", "K42", "K42.e", S("K42.e"), i =>
                i.ScaleDecision = (recs, g, k, kk) =>
                {
                    var all = new List<R.ScaleRecord>();
                    foreach (var r in recs)
                        all.Add(new R.ScaleRecord { Game = r.Game, K = r.K, Count = r.Count, From = r.From,
                                                    Confirmed = true });
                    return R.ScaleDecision(all, g, k, kk);
                });

            // K45: the kept epoch, the pairing and the fence
            yield return M("false_ack", "K45", "K45.i", S("K45.i"), i =>
                i.ReadyEpoch = (rec, present, bodies, peerMax) =>
                    Math.Max(R.ReadyEpoch(rec, present, bodies, peerMax), peerMax));
            yield return M("latest_answer_wins", "K45", "K45.ii", S("K45.ii"), i =>
                i.RecordDecision = (held, l8, n, chain, entries) =>
                {
                    string d = R.RecordDecision(held, l8, n, chain, entries);
                    return d == "keep" ? "rx" : d;
                });
            yield return M("presence_refusal", "K45", "K45.iii", S("K45.iii"), i =>
                i.ValidateEpoch = (p, dm, mk, own, rec, ea, ac, g, k, kk, present) =>
                {
                    string why = R.ValidateEpoch(p, dm, mk, own, rec, ea, ac, g, k, kk, present);
                    if (why != null || rec == null || present == null)
                        return why;
                    for (int n = 0; n < p.N && n < rec.Entries.Count; n++)
                        if (!present.Contains(rec.Entries[n].Actor))
                            return "presence";
                    return null;
                });
            yield return M("immediate_pairing", "K45", "K45.iv", S("K45.iv"), i => i.MasterPairsAtRaise = true);
            yield return M("fence_lowest_present", "K45", "K45.iii", S("K45.iii"), i =>
                i.FenceTarget = (self, present, grants, hg, kept, lagged, ho) =>
                {
                    if (!hg)
                        return R.FenceTarget(self, present, grants, hg, kept, lagged, ho);
                    var sorted = new List<int>(present);
                    sorted.Sort();
                    foreach (int a in sorted)
                        if (a != self && !lagged(a))
                            return new R.FenceChoice { To = a, Why = "kept" };
                    return new R.FenceChoice { To = -1, Why = "none" };
                });
            yield return M("v7_e1", "K45", "K45.vi", S("K45.vi"), i =>
                i.ValidateEpoch = (p, dm, mk, own, rec, ea, ac, g, k, kk, present) =>
                    R.ValidateEpoch(p, dm, mk || R.ListedIn(dm, rec, p.N), own, rec, ea, ac, g, k, kk, present));
            yield return M("kind_s_only_e1", "K45", "K45.vi", S("K45.vi"), i =>
                i.ValidateEpoch = (p, dm, mk, own, rec, ea, ac, g, k, kk, present) =>
                    R.ValidateEpoch(p, dm, mk && HarnessKindS(dm), own, rec, ea, ac, g, k, kk, present));
            yield return M("kind_l_raise", "K45", "K45.vi", S("K45.vi"), i =>
                i.MayPropose = (nStar, pe, ks) => nStar > pe);
            yield return M("fence_no_kind_s_first", "K45", "K45.iii", S("K45.iii"), i =>
                i.FenceTarget = (self, present, grants, hg, kept, lagged, ho) =>
                {
                    if (!hg)
                        return R.FenceTarget(self, present, grants, hg, kept, lagged, ho);
                    var sorted = new List<int>(present);
                    sorted.Sort();
                    foreach (int a in sorted)
                        if (a != self && kept(a) && !lagged(a))
                            return new R.FenceChoice { To = a, Why = "kept" };
                    return new R.FenceChoice { To = -1, Why = "none" };
                });
            yield return M("fence_none_without_grant", "K45", "K45.vii", S("K42.a", "K45.vii"), i =>
                i.FenceTarget = (self, present, grants, hg, kept, lagged, ho) =>
                {
                    if (!hg && !present.Any(a => a != self && R.InGrants(a, grants)))
                        return new R.FenceChoice { To = -1, Why = "none" };
                    return R.FenceTarget(self, present, grants, hg, kept, lagged, ho);
                });
            yield return M("fence_every_switch", "K45", "K45.vii", S("K42.a", "K45.vii"), i =>
                i.FenceTarget = (self, present, grants, hg, kept, lagged, ho) =>
                    R.FenceTarget(self, present, grants, hg, kept, lagged, false));
            yield return M("kept_sender_candidate", "K45", "K45.vii", S("K42.e", "K45.vii"), i =>
                i.KeptSender = (a, grants, rec, pe) => R.KeptSender(a, grants, rec, rec == null ? pe : rec.N));
            yield return M("apply_at_proposal", "K45", "K45.xi.n7",
                           S("K45.iii", "K45.viii", "K45.ix", "K45.xi.n7", "K45.xii.e"), i => i.ApplyAtProposal = true);
            yield return M("no_hold", "K45", "K45.xi.n7",
                           S("K45.ix", "K45.xi.n7", "K45.xii.b", "K45.xii.d", "K45.xii.e"), i => i.NoHold = true);
            yield return M("s1_no_master_test", "K45", "K45.xi.n7",
                           S("K45.iii", "K45.ix", "K45.xi.n7", "K45.xii.a", "K45.xii.e"), i =>
                i.ValidateStamp = (s, ci, ks, kindS, own, rec, ea, ac, g, k, kk) =>
                    R.ValidateStamp(s, s == null ? ci : s.From, ks, kindS, own, rec, ea, ac, g, k, kk));
            yield return M("commit_without_acks", "K45", "K45.viii",
                           S("K45.viii", "K45.xi.n7", "K45.xii.b", "K45.xii.c", "K45.xii.e"), i =>
                i.StampDecision = (bool proposed, int nStar, bool ack, int pe, out string result, out int n,
                                   out bool apply) =>
                    R.MasterStampDecision(proposed, nStar, true, pe, out result, out n, out apply));
            yield return M("fence_unbounded", "K45", "K45.x", S("K45.x"), i =>
                i.FenceStep = (since, tries, landed, keptNow) =>
                    landed ? R.FenceAct.Done
                    : keptNow ? R.FenceAct.Kept
                    : tries < 1 ? R.FenceAct.Try : R.FenceAct.Wait);
            yield return M("v10_pairing", "K45", "K45.xii.a",
                           S("K45.iii", "K45.ix", "K45.xii.a", "K45.xii.e"), i => i.DispatchMasterStamp = true);
            yield return M("play_on", "K45", "K45.xii.e",
                           S("K45.ix", "K45.xi.n7", "K45.xii.b", "K45.xii.d", "K45.xii.e"), i =>
                i.PairDecision = (st, conflict, ci, lp, ack, pe, ea, rec) =>
                {
                    var r = R.PairDecision(st, conflict, ci, lp, ack, pe, ea, rec);
                    if (r.Kind == R.PairKind.LagOut)
                        r = new R.PairResult { Kind = R.PairKind.Carry, PointEpoch = pe, EpochApplied = ea };
                    return r;
                });
            yield return M("no_converge_down", "K45", "K45.xii.c", S("K45.ix", "K45.xii.c", "K45.xii.e"), i =>
                i.PairDecision = (st, conflict, ci, lp, ack, pe, ea, rec) =>
                {
                    if (st != null && !conflict && st.N < ea && rec != null && rec.N >= st.N)
                        return new R.PairResult { Kind = R.PairKind.Carry, PointEpoch = pe, EpochApplied = ea,
                                                  Why = "conflict" };
                    return R.PairDecision(st, conflict, ci, lp, ack, pe, ea, rec);
                });
            yield return M("no_stamp_late", "K45", "K45.xii.b", S("K45.xii.b", "K45.xii.e"), i =>
                i.PairDecision = (st, conflict, ci, lp, ack, pe, ea, rec) =>
                {
                    var r = R.PairDecision(st, conflict, ci, lp, ack, pe, ea, rec);
                    if (r.Kind == R.PairKind.StampLate)
                    {
                        r.Kind = R.PairKind.LagOut;
                        r.Why = "timeout";
                    }
                    return r;
                });
            yield return M("election_ignores_lag", "K45", "K45.xii.d", S("K45.xii.d", "K45.xii.e"), i =>
                i.ElectReporter = (cands, lagged, late) => R.ElectReporter(cands, a => false, late));
            yield return M("propose_against_applied", "K45", "K45.xii.c", S("K45.xii.c"), i =>
                i.ProposeAgainstApplied = true);
            yield return M("lag_ends_at_game_end", "K45", "K45.xii.d", S("K45.xii.d"), i =>
                i.LagOutEnds = (evt, atLoad) => evt == "game_end" || R.LagOutEnds(evt, atLoad));
        }

        // ---------------------------------------------------------------- the inert twins

        private static IEnumerable<Variant> Twins()
        {
            yield return T("peers_reverse", "K33", i =>
                i.DigestGate = (string d, int g, int k, int lg, IList<R.PeerBd> peers, out int peer) =>
                {
                    var rev = new List<R.PeerBd>(peers);
                    rev.Reverse();
                    return R.DigestGate(d, g, k, lg, rev, out peer);
                });
            yield return T("digest_local", "K44", i =>
                i.BoundaryDigest = (g, k, lvl, slots) =>
                {
                    var local = new List<R.SlotState>(slots);
                    return R.BoundaryDigest(g, k, lvl, local);
                });
            yield return T("pair_running_local", "K42", i =>
                i.PairIndices = kept =>
                {
                    var idx = new int[kept.Length];
                    int running = 0;
                    for (int n = 0; n < kept.Length; n++)
                    {
                        if (kept[n])
                        {
                            idx[n] = running;
                            running++;
                        }
                        else
                            idx[n] = -1;
                    }
                    return idx;
                });
            yield return T("gate_local", "K42", i =>
                i.GateValue = (hs, sa, sas, spe, tr, ea, sp) =>
                {
                    var gate = R.GateValue(hs, sa, sas, spe, tr, ea, sp);
                    return gate;
                });
            yield return T("scale_packed_key", "K42", i =>
            {
                i.ScaleDecision = (recs, game, k, kKnown) =>
                {
                    long want = Pack(game, k);
                    R.ScaleRecord hit = null;
                    bool conflict = false, stale = false, unconfirmedOnly = false;
                    if (recs != null)
                        foreach (var r in recs)
                        {
                            long key = Pack(r.Game, r.K);
                            bool keyed = kKnown ? key == want : r.Game == game;
                            if (!keyed)
                            {
                                if (key < want)
                                    stale = true;
                                continue;
                            }
                            if (!r.Confirmed)
                            {
                                unconfirmedOnly = hit == null;
                                continue;
                            }
                            if (hit != null && hit.Count != r.Count)
                                conflict = true;
                            hit = hit ?? r;
                        }
                    if (conflict)
                        return new R.ScaleResult { Count = -1, Why = "conflict", LagOut = true };
                    if (hit != null)
                        return new R.ScaleResult { Count = hit.Count, Why = null, LagOut = false };
                    if (unconfirmedOnly)
                        return new R.ScaleResult { Count = -1, Why = "unconfirmed", LagOut = true };
                    return new R.ScaleResult { Count = -1, Why = stale ? "stale" : "none", LagOut = true };
                };
                i.ConsumeScale = (recs, game, k) =>
                {
                    if (recs != null)
                        recs.RemoveAll(r => Pack(r.Game, r.K) <= Pack(game, k));
                };
            });
            yield return T("epoch_checks_reordered", "K45", i =>
                i.ValidateEpoch = (p, dm, mk, own, rec, ea, ac, g, k, kk, present) =>
                {
                    if (p.From != dm || !mk)
                        return "sender";
                    if (p.Lobby8 != own)
                        return "lobby";
                    if (p.G != g || (kk && p.K != k))
                        return "boundary";
                    if (p.N < ea)
                        return "stale";
                    if (rec == null || rec.N < p.N)
                        return "missing";
                    if (R.ChainOf(own, rec.Entries, p.N) != p.Chain)
                        return "mismatch";
                    if (R.ChainOf(own, rec.Entries, ea) != ac)
                        return "chain";
                    return null;
                });
            yield return T("stamp_checks_reordered", "K45", i =>
                i.ValidateStamp = (s, ci, ks, kindS, own, rec, ea, ac, g, k, kk) =>
                {
                    if (s == null)
                        return "sender";
                    bool raises = s.Result == "commit" || s.N > ea;
                    if (s.From != ci || !ks || (raises && !kindS))
                        return "sender";
                    if (s.G != g || (kk && s.K != k))
                        return "boundary";
                    if (s.Lobby8 != own)
                        return "lobby";
                    if (rec == null || rec.N < s.N || R.ChainOf(own, rec.Entries, s.N) != s.Chain
                        || R.ChainOf(own, rec.Entries, ea) != ac)
                        return "epoch";
                    return null;
                });
            yield return T("ack_complete_local", "K45", i =>
                i.AckComplete = (ICollection<int> barrier, ICollection<int> present, IList<R.Proposal> acks,
                                 R.Proposal p, int self, out List<int> missing) =>
                {
                    bool complete = R.AckComplete(barrier, present, acks, p, self, out missing);
                    return complete;
                });
            yield return T("pair_decision_local", "K45", i =>
                i.PairDecision = (st, conflict, ci, lp, ack, pe, ea, rec) =>
                {
                    int point = pe;
                    int lastPair = lp;
                    return R.PairDecision(st, conflict, ci, lastPair, ack, point, ea, rec);
                });
            yield return T("master_kept_local", "K45", i =>
                i.MasterKeptTest = (gate, hg, rg, m, grants, rec, pe) =>
                {
                    bool kept = R.MasterKeptValue(gate, hg, rg, m, grants, rec, pe);
                    return kept;
                });
            yield return T("kept_sender_local", "K45", i =>
                i.KeptSender = (a, grants, rec, pe) =>
                {
                    bool ks = R.KeptSender(a, grants, rec, pe);
                    return ks;
                });
        }
    }
}
