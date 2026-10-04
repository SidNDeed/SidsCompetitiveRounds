using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>CARD DRAW EVIDENCE (B4), the pure half. What one seat records
    /// about the pick phases of one ranked 1v1 game: every hand dealt (its own
    /// and, from the game's own spawn and end-pick messages, the other seat's),
    /// the pick, the order, the cards applied, the held cards at the game's
    /// first phase, and the census of this seat's own card pool. No Unity, no
    /// Photon: tools/tests/card-draw-client compiles this file as it ships,
    /// together with SeatEvidenceCore.cs (JSON writer, hashing, signing).
    ///
    /// This half records and serialises. It holds no threshold, no rule of
    /// the deal and no deciding logic: every number it emits is an index, a
    /// count or a flag of what this seat saw, and the server compares.
    ///
    /// Record text is Python json.dumps(separators=(",", ":"),
    /// ensure_ascii=True) bytes, keys in the order of the wire layout in
    /// ai-collab/integrity-1001/CARD-DRAW-CLIENT-BUILD-NOTES.md.</summary>
    internal static class CardDrawEvidenceCore
    {
        internal const int SCHEMA = 1;
        internal const int CONTRACT = 2;
        internal const int RECORD_MAX_BYTES = 8192;
        internal const int SL_CAP = 16, HD_CAP = 40, PH_CAP = 40, AP_CAP = 64, CARDS_CAP = 128, HELD_CAP = 64, PO_CAP = 8;
        internal const int NAME_CAP = 64;
        internal const int SRC_SLOTS = 30;
        internal const long BIG = 10000000L;
        internal const string CANON_PREFIX = "card-evidence:v1:";
        /// <summary>The five lists the budgeter trims, in its tie order.</summary>
        internal static readonly string[] TRIM_ORDER = { "ap", "cards", "held0", "ph", "hd" };
        /// <summary>The record keys in order; "end", when present, follows "g".</summary>
        internal static readonly string[] RECORD_KEYS =
        {
            "schema", "g", "ns", "pool", "prof", "po", "sc", "inc", "cards", "held0", "ph", "hd", "ap", "apx", "tot", "cost", "omit",
        };
        internal const int COLLECTORS = 6;

        /// <summary>inc bits (CD-M3): the game's first phase was not captured
        /// whole (po and held0 are then not emitted); collector events were
        /// lost (the hook-side buffer was full); a collector faulted. Every bit
        /// says what this seat did NOT see; none decides anything.</summary>
        internal const int INC_FIRST = 1, INC_LOST = 2, INC_FAULT = 4;

        /// <summary>pool[2] (CD-M4).</summary>
        internal const string POOL_OK = "ok", POOL_COLLISION = "collision", POOL_CHANGED = "changed", POOL_NOT_RUN = "not_run";

        /// <summary>The pool state two census readings leave (CD-M4): the
        /// more severe one, in the order not_run, collision, changed, ok (an
        /// unknown state reads not_run). No reading turns a non-ok state
        /// back into ok.</summary>
        internal static string WorstPool(string a, string b)
        {
            return PoolRank(a) >= PoolRank(b) ? PoolStateOf(a) : PoolStateOf(b);
        }

        private static int PoolRank(string s)
        {
            return s == POOL_OK ? 0 : (s == POOL_CHANGED ? 1 : (s == POOL_COLLISION ? 2 : 3));
        }

        /// <summary>Application outcomes (CD-M1).</summary>
        internal const int APPLY_DONE = 0, APPLY_SKIPPED = 1, APPLY_FAULTED = 2;

        /// <summary>The revision of the record's slot and sampler semantics
        /// (what ix, sl, sp, src, gen, sq and the census mean). Raised with any
        /// change to them; the server half keys its registry on it (CD-M5).</summary>
        internal const string SEMANTICS = "cd-sem:2";
        internal const int RULES_CAP = 32;

        private static long Clamp(long v, long lo, long hi) { return v < lo ? lo : (v > hi ? hi : v); }
        private static long Cnt(long v) { return Clamp(v, 0, BIG); }

        // -- the census (finding M4: canonical JSON, arrays preserved, full digest) ---------------

        /// <summary>One element of CardChoice.cards as the deal's rules read it:
        /// the GameObject name, the raw rarity enum value, allowMultiple, the
        /// names of the categories and blacklisted categories in array order
        /// (a null element stays null; a null array stays null), and the card's
        /// own Gun.lockGunToDefault (no Gun = false).</summary>
        internal sealed class CensusCard
        {
            internal string Name;
            internal int Rarity;
            internal bool AllowMultiple;
            internal string[] Categories;
            internal string[] Blacklisted;
            internal bool Lock;
        }

        /// <summary>{"census":1,"cards":[[name,rarity,allowMultiple,categories,
        /// blacklisted,lock],...]} in pool order. Two pools that differ in any
        /// element, any order, any array split or any null give different text.</summary>
        internal static string CensusText(IList<CensusCard> cards)
        {
            var arr = new List<object>(cards != null ? cards.Count : 0);
            if (cards != null)
                foreach (var c in cards)
                    arr.Add(new List<object>
                    {
                        c != null && c.Name != null ? c.Name : "", (long)(c != null ? c.Rarity : 0),
                        c != null && c.AllowMultiple ? 1L : 0L, Names(c != null ? c.Categories : null),
                        Names(c != null ? c.Blacklisted : null), c != null && c.Lock ? 1L : 0L,
                    });
            return SeatEvidenceCore.Json(new SeatEvidenceCore.JObj().Add("census", 1L).Add("cards", arr));
        }

        private static object Names(string[] a)
        {
            if (a == null) return null;
            var l = new List<object>(a.Length);
            foreach (var s in a) l.Add(s);
            return l;
        }

        /// <summary>The full 64-hex SHA-256 of the census text (ASCII by construction).</summary>
        internal static string CensusDigest(string censusText)
        {
            return SeatEvidenceCore.Sha256Hex(Encoding.ASCII.GetBytes(censusText ?? ""));
        }

        /// <summary>True when two distinct category objects (by id) carry one
        /// name: the census, which compares by name, would then not be the
        /// pool the game compares by object, and the dump says so.</summary>
        internal static bool CategoryNameCollision(IList<KeyValuePair<int, string>> cats)
        {
            var seen = new Dictionary<string, int>(StringComparer.Ordinal);
            if (cats == null) return false;
            foreach (var kv in cats)
            {
                if (kv.Value == null) continue;
                int id;
                if (seen.TryGetValue(kv.Value, out id)) { if (id != kv.Key) return true; }
                else seen[kv.Value] = kv.Key;
            }
            return false;
        }

        // -- one game, as this seat saw it -----------------------------------------------------

        /// <summary>What the Unity side reads about the picker when a deal
        /// opens: the live gun lock bit (-1 unread), the held-card count on
        /// this seat (-1 unread), and the engine's draw index for an own deal
        /// (-1 when the engine did not run or the deal is the other seat's).</summary>
        internal struct DealFacts
        {
            internal int Gl;
            internal long Hn;
            internal int Sq;
            internal DealFacts(int gl, long hn, int sq) { Gl = gl; Hn = hn; Sq = sq; }
        }

        /// <summary>The identity the record carries (CD-M5), frozen with the
        /// game: the game assembly's hash, this mod's own assembly hash (the
        /// dealer implementation: the vanilla-mode and Same Cards dealers ship
        /// in it), the mod's build tuple, the record's slot and sampler
        /// semantics revision (SEMANTICS), and the room's active rules record.
        /// A state other than "ok" is a hash that was not read; the server half
        /// derives the profile key from all of it (build notes).</summary>
        internal sealed class Profile
        {
            internal string GameSha = "", GameState = "no_location", ModSha = "", ModState = "no_location";
            internal string[] Build = { "", "", "" };
            internal string Rules = "";

            internal List<object> ToList()
            {
                bool g = GameState == "ok" && GameSha != null && GameSha.Length == 64;
                bool m = ModState == "ok" && ModSha != null && ModSha.Length == 64;
                var b = Build ?? new string[0];
                return new List<object>
                {
                    g ? GameSha : "", HashState(g, GameState), m ? ModSha : "", HashState(m, ModState),
                    BuildPart(b, 0, 16), BuildPart(b, 1, 16), BuildPart(b, 2, 12), SEMANTICS, Printable(Rules, RULES_CAP),
                };
            }

            private static string HashState(bool ok, string state)
            {
                return ok ? "ok" : (state == "read_failed" ? "read_failed" : "no_location");
            }

            private static string BuildPart(string[] b, int i, int max)
            {
                string s = i < b.Length ? b[i] : null;
                return SeatEvidenceCore.IsBuildPart(s, max) ? s : "";
            }
        }

        /// <summary>s when it is printable ASCII without '"' and '\' and at
        /// most max long, else "".</summary>
        internal static string Printable(string s, int max)
        {
            if (s == null || s.Length > max) return "";
            for (int i = 0; i < s.Length; i++)
                if (s[i] < ' ' || s[i] > '~' || s[i] == '"' || s[i] == '\\') return "";
            return s;
        }

        private sealed class Hand
        {
            internal int O, K, W, Wp = -1, Pk = -2, Pi = -1, Vid = -1, Gl = -1, Sq = -1, SenderOk = -1;
            internal long An, Hn = -1, SlN;
            internal bool HasEndPick, Foreign, CreatorUnknown;
            internal List<long> Sl = new List<long>();
            internal readonly List<long> Spawns = new List<long>();
            internal readonly List<int> Shared = new List<int>();
        }

        internal sealed class CardGame
        {
            internal readonly int G, Ns, PoolN, OpeningDraws;
            /// <summary>The census digest of the pool this game's indexes name.</summary>
            internal string Digest;
            /// <summary>POOL_OK, POOL_COLLISION (two category objects share a
            /// name: the census does not identify the pool), POOL_CHANGED (the
            /// pool changed during the game) or POOL_NOT_RUN (no census).</summary>
            internal string PoolState;
            /// <summary>INC_* bits: what this seat did not capture whole.</summary>
            internal int Inc;
            /// <summary>Set at the dispatch: nothing changes the game after it (CD-M1).</summary>
            internal bool Sealed { get { return _sealed; } }
            private bool _sealed;
            private readonly string[] _canon;
            private readonly int[] _rar;
            internal readonly List<long> Po = new List<long>();
            internal readonly List<long>[] Held0 = new List<long>[2];
            internal readonly long[] Held0Omit = new long[2];
            internal readonly List<long[]> Ph = new List<long[]>();
            internal readonly List<object> Hd = new List<object>();
            internal readonly List<long[]> Ap = new List<long[]>();
            internal long PhOmit, HdOmit, ApOmit, SlOmit, SpOmit;
            /// <summary>Applications that did not complete: the original was
            /// skipped by a sibling patch, or it threw (CD-M1). Never in ap,
            /// tot or the applied counts.</summary>
            internal long ApSkipped, ApFaulted;
            /// <summary>Per role (0 this seat, 1 the other seat): phases, deals,
            /// spawns, picks, applications, unresolved slots, spawn-order
            /// differences, over the whole game (never capped).</summary>
            internal readonly long[][] Tot = { new long[7], new long[7] };
            internal readonly long[] AppsTo = new long[2];

            private int _phaseOrd = -1, _phaseW = -1, _phaseDeals;
            private long[] _phase;
            private bool _phaseOpen;
            private Hand _hand;

            /// <param name="held0">Each role's held cards (pool indexes) at the
            /// first phase; a null list = unread on this seat.</param>
            internal CardGame(int g, int ns, int openingDraws, int poolN, string digest, string[] canon, int[] rar,
                              IList<int> po, IList<int>[] held0)
            {
                G = g; Ns = ns; OpeningDraws = openingDraws; PoolN = poolN; Digest = digest ?? "";
                PoolState = Digest.Length == 64 ? POOL_OK : POOL_NOT_RUN;
                _canon = canon ?? new string[0]; _rar = rar ?? new int[0];
                if (po != null) for (int i = 0; i < po.Count && i < PO_CAP; i++) Po.Add(Clamp(po[i], -1, 1));
                for (int r = 0; r < 2; r++)
                {
                    var src = held0 != null && held0.Length > r ? held0[r] : null;
                    if (src == null) { Held0[r] = null; continue; }
                    var l = new List<long>();
                    for (int i = 0; i < src.Count; i++)
                    {
                        if (l.Count < HELD_CAP) l.Add(Ix(src[i]));
                        else Held0Omit[r]++;
                    }
                    Held0[r] = l;
                }
            }

            private long Ix(long ix) { return ix >= 0 && ix < PoolN ? ix : -1; }

            internal bool PhaseOpen { get { return _phaseOpen; } }

            /// <summary>The next spawn opens a deal (the Unity side reads the
            /// deal facts only then).</summary>
            internal bool WantsFacts { get { return _phaseOpen && _hand == null; } }

            /// <summary>The dispatch: an open deal is closed first (Close),
            /// then nothing a later collector reports changes the game.</summary>
            internal void Seal() { _sealed = true; }

            /// <summary>StartPick on this seat: a new phase; a deal still open
            /// in the previous phase closes with no pick (pk -2).</summary>
            internal void OpenPhase(int w, int picks, int rs, int ro, int sharedNow)
            {
                if (_sealed) return;
                CloseHand(sharedNow);
                _phaseOrd++;
                _phaseW = w == 0 || w == 1 ? w : -1;
                _phaseDeals = 0;
                _phaseOpen = true;
                var e = new long[] { Clamp(_phaseOrd, 0, 999), _phaseW, Clamp(picks, -9, 99), Clamp(rs, 0, 99), Clamp(ro, 0, 99), 0, 0 };
                if (Ph.Count < PH_CAP) { Ph.Add(e); _phase = e; }
                else { PhOmit++; _phase = null; }
                if (_phaseW >= 0) Tot[_phaseW][0]++;
            }

            private void OpenHand(DealFacts f)
            {
                var h = new Hand
                {
                    O = _phaseOrd, K = _phaseDeals, W = _phaseW, An = _phaseW >= 0 ? AppsTo[_phaseW] : -1,
                    Hn = f.Hn < 0 ? -1 : f.Hn, Gl = f.Gl == 0 || f.Gl == 1 ? f.Gl : -1, Sq = _phaseW == 0 && f.Sq >= 0 ? f.Sq : -1,
                };
                _hand = h;
                _phaseDeals++;
                if (_phase != null) _phase[5] = Clamp(_phaseDeals, 0, 999);
                if (_phaseW >= 0) Tot[_phaseW][1]++;
            }

            /// <summary>One network card spawn while a phase is open. creator: 1
            /// the picker's controller, 0 another actor, -1 unknown. ix -1 = no
            /// local source card (finding L2: still a spawn).</summary>
            internal void Spawn(int ix, int creator, DealFacts f, int sharedNow)
            {
                if (_sealed || !_phaseOpen) return;
                if (_hand == null) OpenHand(f);
                if (creator == 0) { _hand.Foreign = true; return; }
                if (creator < 0) _hand.CreatorUnknown = true;
                _hand.Spawns.Add(Ix(ix));
                _hand.Shared.Add(sharedNow);
                if (_hand.W >= 0) Tot[_hand.W][2]++;
            }

            /// <summary>RPCA_DoEndPick with every slot given (n = slots.Count).</summary>
            internal void EndPick(IList<long> slots, int pi, int vid, int pk, int wp, int senderOk, DealFacts f, int sharedNow)
            {
                EndPick(slots, slots != null ? slots.Count : 0, pi, vid, pk, wp, senderOk, f, sharedNow);
            }

            /// <summary>RPCA_DoEndPick: the hand in slot order (pool index per
            /// card id, -1 unresolved) as the hook kept it, the first SL_CAP of
            /// n slots (F4: the hook copies a hard-capped snapshot), the picked
            /// card's position (-1 absent), its view id, theInt, the role pickId
            /// names, and whether the sender was the picker's controller (1/0,
            /// -1 unknown).</summary>
            internal void EndPick(IList<long> slots, long n, int pi, int vid, int pk, int wp, int senderOk, DealFacts f, int sharedNow)
            {
                if (_sealed || !_phaseOpen) return;
                if (_hand == null) OpenHand(f);
                var h = _hand;
                h.HasEndPick = true;
                h.Sl = new List<long>();
                if (slots != null) for (int i = 0; i < slots.Count; i++) h.Sl.Add(Ix(slots[i]));
                h.SlN = n > h.Sl.Count ? n : h.Sl.Count;
                h.Pi = pi; h.Vid = vid; h.Pk = pk; h.Wp = wp == 0 || wp == 1 ? wp : -1;
                h.SenderOk = senderOk == 0 || senderOk == 1 ? senderOk : -1;
                if (h.W >= 0) Tot[h.W][3]++;
                CloseHand(sharedNow);
            }

            /// <summary>RPCA_DonePicking: the phase is done; a deal still open
            /// closes with no pick.</summary>
            internal void DonePicking(int sharedNow)
            {
                if (_sealed || !_phaseOpen) return;
                CloseHand(sharedNow);
                if (_phase != null) _phase[6] = 1;
                _phaseOpen = false;
            }

            /// <summary>One card application to one player. kind 0 RPCA_Pick, 1
            /// OFFLINE_Pick. outcome: APPLY_DONE the original ran and completed
            /// (the only kind recorded in ap, tot and the applied counts),
            /// APPLY_SKIPPED a sibling patch skipped it, APPLY_FAULTED it threw.</summary>
            internal void Apply(int w, int ix, int kind, int vid, int outcome)
            {
                if (_sealed) return;
                if (outcome != APPLY_DONE)
                {
                    if (outcome == APPLY_SKIPPED) ApSkipped++; else ApFaulted++;
                    return;
                }
                int r = w == 0 || w == 1 ? w : -1;
                if (r >= 0) { AppsTo[r]++; Tot[r][4]++; }
                if (Ap.Count < AP_CAP) Ap.Add(new long[] { r, Ix(ix), kind == 1 ? 1 : 0, Clamp(vid, -1, int.MaxValue) });
                else ApOmit++;
            }

            /// <summary>Game end on this seat: an open deal closes with no pick.</summary>
            internal void Close(int sharedNow)
            {
                if (_sealed) return;
                CloseHand(sharedNow);
                _phaseOpen = false;
            }

            private void CloseHand(int sharedNow)
            {
                var h = _hand;
                if (h == null) return;
                _hand = null;
                // the end-pick's slots as kept (at most n of them), else the spawns
                var sl = h.HasEndPick ? h.Sl : h.Spawns;
                long n = h.HasEndPick ? h.SlN : h.Spawns.Count;
                // a hand seen only by its end-pick (no spawn reached this seat) has no spawn order to differ
                bool same = h.Spawns.Count == 0 || (h.Spawns.Count == n && SamePrefix(h.Spawns, sl));
                long unres = n - sl.Count;      // slots the hook did not keep were not resolved
                for (int i = 0; i < sl.Count; i++) if (sl[i] < 0) unres++;
                long src = -1;
                int gen = -1;
                if (h.W == 0)
                {
                    src = SrcMask(h.Shared, sharedNow);
                    gen = Gen(src, h.Sq, OpeningDraws);
                }
                int ds;
                if (h.Foreign || (h.HasEndPick && h.SenderOk == 0)) ds = 0;
                else if (h.CreatorUnknown || !h.HasEndPick || h.SenderOk < 0) ds = -1;
                else ds = 1;
                if (h.W >= 0)
                {
                    Tot[h.W][5] += unres;
                    if (!same) Tot[h.W][6]++;
                }
                if (Hd.Count >= HD_CAP) { HdOmit++; return; }
                var slOut = new List<long>();
                for (int i = 0; i < sl.Count && i < SL_CAP; i++) slOut.Add(sl[i]);
                SlOmit += n - slOut.Count;
                var spOut = new List<long>();
                if (!same) for (int i = 0; i < h.Spawns.Count; i++) { if (i < SL_CAP) spOut.Add(h.Spawns[i]); else SpOmit++; }
                Hd.Add(new List<object>
                {
                    Clamp(h.O, 0, 999), Clamp(h.K, 0, 999), (long)h.W, (long)h.Wp, Clamp(h.An, -1, BIG), Clamp(n, 0, BIG), slOut,
                    Clamp(h.Spawns.Count, 0, BIG), spOut, Clamp(h.Pk, -2, 999), Clamp(h.Pi, -1, 999), (long)ds, src, (long)h.Sq,
                    Clamp(h.Vid, -1, int.MaxValue), (long)h.Gl, (long)gen, Clamp(h.Hn, -1, BIG),
                });
            }

            /// <summary>The record with only the game assembly's identity read
            /// (every other profile part unread).</summary>
            internal SeatEvidenceCore.JObj Record(string end, string profSha, string profState, int scRule, int scVerdict, long[][] cost)
            {
                return Record(end, new Profile { GameSha = profSha, GameState = profState }, scRule, scVerdict, cost);
            }

            /// <summary>The record (untrimmed): every list as recorded, `omit`
            /// holding the recording caps. Budget() trims it to the limit.
            /// scRule / scVerdict -1: not read (NOT-RUN; CD-M2). With INC_FIRST
            /// the first phase was not captured whole: po and held0, which only
            /// it reads, are emitted empty / null (CD-M3).</summary>
            internal SeatEvidenceCore.JObj Record(string end, Profile prof, int scRule, int scVerdict, long[][] cost)
            {
                var o = new SeatEvidenceCore.JObj();
                o.Add("schema", (long)SCHEMA).Add("g", Clamp(G, 0, 9999));
                if (SeatEvidenceCore.IsEndKind(end)) o.Add("end", end);
                bool first = (Inc & INC_FIRST) != 0;
                bool digestOk = Digest != null && Digest.Length == 64;
                o.Add("ns", Clamp(Ns, 0, 99))
                 .Add("pool", new List<object> { Clamp(PoolN, 0, 9999), digestOk ? Digest : "", digestOk ? PoolStateOf(PoolState) : POOL_NOT_RUN })
                 .Add("prof", (prof ?? new Profile()).ToList())
                 .Add("po", first ? new List<long>() : new List<long>(Po))
                 .Add("sc", new long[] { scRule == 0 || scRule == 1 ? scRule : -1, scVerdict >= 0 && scVerdict <= 2 ? scVerdict : -1 })
                 .Add("inc", (long)(Inc & (INC_FIRST | INC_LOST | INC_FAULT)));
                List<long> h0 = first ? null : Held0[0], h1 = first ? null : Held0[1];
                // cards (CD-A16): one entry for EVERY non-negative pool index the record keeps.
                // At most CARDS_CAP indices (the lowest) get metadata; every entry naming another
                // index is omitted and counted (a hand in omit.hd, a held card in omit.held0, an
                // application in omit.ap), so no kept reference lacks its card and every check
                // that needed an omitted entry reads it as omitted.
                var refs = new SortedSet<long>();
                foreach (var e in Hd) HandRefsOf((List<object>)e, refs);
                if (h0 != null) foreach (var s in h0) if (s >= 0) refs.Add(s);
                if (h1 != null) foreach (var s in h1) if (s >= 0) refs.Add(s);
                foreach (var a in Ap) if (a[1] >= 0) refs.Add(a[1]);
                var named = new HashSet<long>();
                long cardsOmit = 0;
                foreach (var ix in refs) { if (named.Count < CARDS_CAP) named.Add(ix); else cardsOmit++; }
                long hdDrop = 0, apDrop = 0;
                long[] heldDrop = { 0, 0 };
                var hd = new List<object>();
                foreach (var e in Hd)
                {
                    var hr = new SortedSet<long>();
                    HandRefsOf((List<object>)e, hr);
                    if (hr.IsSubsetOf(named)) hd.Add(e); else hdDrop++;
                }
                var heldOut = new List<long>[2];
                var hsrc = new[] { h0, h1 };
                for (int r = 0; r < 2; r++)
                {
                    if (hsrc[r] == null) continue;
                    heldOut[r] = new List<long>();
                    foreach (var s in hsrc[r]) { if (s < 0 || named.Contains(s)) heldOut[r].Add(s); else heldDrop[r]++; }
                }
                var ap = new List<object>();
                foreach (var e in Ap) { if (e[1] < 0 || named.Contains(e[1])) ap.Add(e); else apDrop++; }
                // the cards the kept entries name (a subset of `named`), ascending
                var kept = new SortedSet<long>();
                foreach (var e in hd) HandRefsOf((List<object>)e, kept);
                for (int r = 0; r < 2; r++) if (heldOut[r] != null) foreach (var s in heldOut[r]) if (s >= 0) kept.Add(s);
                foreach (long[] a in ap) if (a[1] >= 0) kept.Add(a[1]);
                var cards = new List<object>();
                foreach (var ix in kept)
                {
                    string nm = ix < _canon.Length && _canon[ix] != null ? _canon[ix] : "";
                    if (nm.Length > NAME_CAP) nm = nm.Substring(0, NAME_CAP);
                    cards.Add(new List<object> { ix, nm, (long)(ix < _rar.Length ? _rar[ix] : -1) });
                }
                var held = new List<object> { heldOut[0] != null ? (object)heldOut[0] : null, heldOut[1] != null ? (object)heldOut[1] : null };
                var ph = new List<object>(); foreach (var e in Ph) ph.Add((long[])e.Clone());
                var tot = new List<object>();
                for (int r = 0; r < 2; r++) { var t = new long[7]; for (int i = 0; i < 7; i++) t[i] = Cnt(Tot[r][i]); tot.Add(t); }
                var cst = new List<object>();
                for (int i = 0; i < COLLECTORS; i++)
                {
                    var c = cost != null && i < cost.Length && cost[i] != null ? cost[i] : new long[5];
                    var t = new long[5]; for (int j = 0; j < 5; j++) t[j] = Cnt(j < c.Length ? c[j] : 0); cst.Add(t);
                }
                o.Add("cards", cards).Add("held0", held).Add("ph", ph).Add("hd", hd).Add("ap", ap)
                 .Add("apx", new long[] { Cnt(ApSkipped), Cnt(ApFaulted) })
                 .Add("tot", tot).Add("cost", cst)
                 .Add("omit", Omit(cardsOmit, first ? 0 : Held0Omit[0] + heldDrop[0], first ? 0 : Held0Omit[1] + heldDrop[1], PhOmit,
                                   HdOmit + hdDrop, ApOmit + apDrop, SlOmit, SpOmit));
                return o;
            }

            /// <summary>The non-negative pool indexes one hd entry names (its sl
            /// and its sp).</summary>
            private static void HandRefsOf(List<object> entry, ISet<long> into)
            {
                foreach (var s in (List<long>)entry[6]) if (s >= 0) into.Add(s);
                foreach (var s in (List<long>)entry[8]) if (s >= 0) into.Add(s);
            }
        }

        private static string PoolStateOf(string s)
        {
            return s == POOL_OK || s == POOL_COLLISION || s == POOL_CHANGED ? s : POOL_NOT_RUN;
        }

        internal static SeatEvidenceCore.JObj Omit(long cards, long held0a, long held0b, long ph, long hd, long ap, long sl, long sp)
        {
            return new SeatEvidenceCore.JObj().Add("cards", Cnt(cards)).Add("held0", new long[] { Cnt(held0a), Cnt(held0b) })
                .Add("ph", Cnt(ph)).Add("hd", Cnt(hd)).Add("ap", Cnt(ap)).Add("sl", Cnt(sl)).Add("sp", Cnt(sp));
        }

        /// <summary>a's first b.Count entries equal b's.</summary>
        private static bool SamePrefix(List<long> a, List<long> b)
        {
            if (a.Count < b.Count) return false;
            for (int i = 0; i < b.Count; i++) if (a[i] != b[i]) return false;
            return true;
        }

        /// <summary>Which spawn positions the Same Cards engine served, from
        /// the engine's served-slot counter read before each spawn (a served
        /// slot raises it after its spawn returns) and once at the close. -1
        /// when any reading is missing or the counter does not move by 0 or 1.</summary>
        internal static long SrcMask(IList<int> readings, int closing)
        {
            if (readings == null || closing < 0 || readings.Count > SRC_SLOTS) return -1;
            long mask = 0;
            for (int i = 0; i < readings.Count; i++)
            {
                int cur = readings[i];
                int next = i + 1 < readings.Count ? readings[i + 1] : closing;
                if (cur < 0 || next < 0) return -1;
                int d = next - cur;
                if (d == 1) mask |= 1L << i;
                else if (d != 0) return -1;
            }
            return mask;
        }

        /// <summary>The generation source of an own hand (finding M2): 0 every
        /// slot vanilla, 1 engine slots of an opening draw (the engine's
        /// opening bypass), 2 engine slots of a later draw (its local legality
        /// substitution), -1 unknown.</summary>
        internal static int Gen(long src, int sq, int openingDraws)
        {
            if (src < 0) return -1;
            if (src == 0) return 0;
            if (sq < 1) return -1;
            return sq <= openingDraws ? 1 : 2;
        }

        // -- the budgeter (cap 8192; trim order ap, cards, held0, ph, hd) ---------------------

        /// <summary>The record text, at most `limit` bytes. While too long:
        /// among the lists that still have a removable entry, the one with the
        /// most entries (held0: both players' lists together; ties: earliest in
        /// TRIM_ORDER) loses its LAST removable entry: for `cards` the last
        /// entry no remaining entry names, for `held0` the last entry of the
        /// concatenation [this seat's, the other seat's]; `omit` counts each.
        /// Deterministic; a referenced `cards` entry is never removed.</summary>
        internal static string Budget(SeatEvidenceCore.JObj rec, int limit = RECORD_MAX_BYTES)
        {
            var om = (SeatEvidenceCore.JObj)rec.Get("omit");
            long oCards = (long)om.Get("cards"), oPh = (long)om.Get("ph"), oHd = (long)om.Get("hd"), oAp = (long)om.Get("ap");
            var oHeld = (long[])((long[])om.Get("held0")).Clone();
            long oSl = (long)om.Get("sl"), oSp = (long)om.Get("sp");

            var ap = new List<object>((IEnumerable<object>)rec.Get("ap"));
            var cards = new List<object>((IEnumerable<object>)rec.Get("cards"));
            var held = (List<object>)rec.Get("held0");
            var h0 = held[0] != null ? new List<long>((List<long>)held[0]) : null;
            var h1 = held[1] != null ? new List<long>((List<long>)held[1]) : null;
            var ph = new List<object>((IEnumerable<object>)rec.Get("ph"));
            var hd = new List<object>((IEnumerable<object>)rec.Get("hd"));

            var refs = new Dictionary<long, int>();
            Action<long, int> addRef = (ix, d) => { if (ix < 0) return; int c; refs.TryGetValue(ix, out c); refs[ix] = c + d; };
            foreach (var e in hd) HandRefs(e, addRef, 1);
            if (h0 != null) foreach (var s in h0) addRef(s, 1);
            if (h1 != null) foreach (var s in h1) addRef(s, 1);
            foreach (var e in ap) addRef(((long[])e)[1], 1);

            var lenAp = Lens(ap); var lenCards = Lens(cards); var lenPh = Lens(ph); var lenHd = Lens(hd);
            var lenH0 = h0 != null ? LongLens(h0) : new List<int>(); var lenH1 = h1 != null ? LongLens(h1) : new List<int>();

            var outp = new SeatEvidenceCore.JObj();
            for (int k = 0; k < rec.Keys.Count; k++) outp.Add(rec.Keys[k], rec.Values[k]);
            Func<long> skeleton = () =>
            {
                outp.Set("ap", new List<object>()); outp.Set("cards", new List<object>()); outp.Set("ph", new List<object>()); outp.Set("hd", new List<object>());
                outp.Set("held0", new List<object> { h0 != null ? (object)new List<long>() : null, h1 != null ? (object)new List<long>() : null });
                outp.Set("omit", Omit(oCards, oHeld[0], oHeld[1], oPh, oHd, oAp, oSl, oSp));
                return SeatEvidenceCore.Json(outp).Length;
            };
            Func<long> total = () => skeleton() + Content(lenAp) + Content(lenCards) + Content(lenH0) + Content(lenH1) + Content(lenPh) + Content(lenHd);
            long t = total();
            while (t > limit)
            {
                int lastFreeCard = -1;
                for (int i = cards.Count - 1; i >= 0; i--)
                {
                    int c; refs.TryGetValue((long)((List<object>)cards[i])[0], out c);
                    if (c <= 0) { lastFreeCard = i; break; }
                }
                int heldCount = (h0 != null ? h0.Count : 0) + (h1 != null ? h1.Count : 0);
                int[] counts = { ap.Count, lastFreeCard >= 0 ? cards.Count : -1, heldCount, ph.Count, hd.Count };
                int pick = -1;
                for (int i = 0; i < counts.Length; i++)
                    if (counts[i] > 0 && (pick < 0 || counts[i] > counts[pick])) pick = i;
                if (pick < 0) throw new InvalidOperationException("the fixed fields alone exceed the limit");
                switch (pick)
                {
                    case 0:
                        addRef(((long[])ap[ap.Count - 1])[1], -1);
                        ap.RemoveAt(ap.Count - 1); lenAp.RemoveAt(lenAp.Count - 1); oAp++;
                        break;
                    case 1:
                        cards.RemoveAt(lastFreeCard); lenCards.RemoveAt(lastFreeCard); oCards++;
                        break;
                    case 2:
                        if (h1 != null && h1.Count > 0) { addRef(h1[h1.Count - 1], -1); h1.RemoveAt(h1.Count - 1); lenH1.RemoveAt(lenH1.Count - 1); oHeld[1]++; }
                        else { addRef(h0[h0.Count - 1], -1); h0.RemoveAt(h0.Count - 1); lenH0.RemoveAt(lenH0.Count - 1); oHeld[0]++; }
                        break;
                    case 3:
                        ph.RemoveAt(ph.Count - 1); lenPh.RemoveAt(lenPh.Count - 1); oPh++;
                        break;
                    default:
                        HandRefs(hd[hd.Count - 1], addRef, -1);
                        hd.RemoveAt(hd.Count - 1); lenHd.RemoveAt(lenHd.Count - 1); oHd++;
                        break;
                }
                t = total();
            }
            outp.Set("ap", ap); outp.Set("cards", cards); outp.Set("ph", ph); outp.Set("hd", hd);
            outp.Set("held0", new List<object> { h0, h1 });
            outp.Set("omit", Omit(oCards, oHeld[0], oHeld[1], oPh, oHd, oAp, oSl, oSp));
            string body = SeatEvidenceCore.Json(outp);
            if (body.Length != t) throw new InvalidOperationException("budgeter length bookkeeping disagrees with the text");
            return body;
        }

        private static void HandRefs(object entry, Action<long, int> addRef, int d)
        {
            var l = (List<object>)entry;
            foreach (var s in (List<long>)l[6]) addRef(s, d);
            foreach (var s in (List<long>)l[8]) addRef(s, d);
        }

        private static List<int> Lens(List<object> l)
        {
            var r = new List<int>(l.Count);
            foreach (var e in l) r.Add(SeatEvidenceCore.Json(e).Length);
            return r;
        }

        private static List<int> LongLens(List<long> l)
        {
            var r = new List<int>(l.Count);
            foreach (var e in l) r.Add(SeatEvidenceCore.Json(e).Length);
            return r;
        }

        private static long Content(List<int> lens)
        {
            long s = 0;
            for (int i = 0; i < lens.Count; i++) s += lens[i];
            return s + (lens.Count > 0 ? lens.Count - 1 : 0);
        }

        // -- signing and the envelope ----------------------------------------------------------

        internal static string Canonical(string seat, string other, string stable, string attach, string recordText)
        {
            return CANON_PREFIX + seat + ":" + other + ":"
                   + SeatEvidenceCore.Sha256Hex(Encoding.ASCII.GetBytes(stable)) + ":"
                   + SeatEvidenceCore.Sha256Hex(Encoding.ASCII.GetBytes(attach)) + ":"
                   + SeatEvidenceCore.Sha256Hex(Encoding.ASCII.GetBytes(recordText));
        }

        /// <summary>The request body (the seat evidence envelope's keys, the
        /// card record's own limit). Null when a field is outside its bound.</summary>
        internal static string Envelope(string seat, string other, string stable, string attach, string recordText, string sig)
        {
            if (!SeatEvidenceCore.IsSteamId(seat) || !SeatEvidenceCore.IsSteamId(other) || seat == other) return null;
            if (!SeatEvidenceCore.IsAttachKey(stable, attach)) return null;
            if (recordText == null || recordText.Length == 0 || Encoding.UTF8.GetByteCount(recordText) > RECORD_MAX_BYTES) return null;
            for (int i = 0; i < recordText.Length; i++) if (recordText[i] > '~' || recordText[i] < ' ') return null;
            if (sig == null || sig.Length != 64) return null;
            var o = new SeatEvidenceCore.JObj().Add("contract", (long)CONTRACT).Add("seat_steam_id", seat).Add("other_steam_id", other)
                .Add("stable_game_key", stable).Add("attach_key", attach).Add("record", recordText).Add("sig", sig);
            return SeatEvidenceCore.Json(o);
        }
    }
}
