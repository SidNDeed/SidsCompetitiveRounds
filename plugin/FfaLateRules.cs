using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>The late entry's and the kept epoch's decisions as pure
    /// functions, with no Unity, Photon or BepInEx type anywhere in the file
    /// (V11 sec3.5 items 5 and 13; evidence sec8.2, the late-rules harness).
    ///
    /// Callers pass plain values: actor numbers, the master's actor read at
    /// dispatch, the grant set, the client's own epoch record and applied
    /// epoch, readiness signals, kept flags in list order, present actors, the
    /// published boundary digests, the gate's latest statement, a proposal's
    /// and a stamp's fields, the acknowledgements received, the call-in's
    /// (g, k) and its master, a load's key and records, and the fence's
    /// elapsed realtime and tries. FfaLateEntry and FfaAssembly hold the live
    /// state and hand it in here, so the rules are EXECUTED by
    /// tools/late-rules-harness under a plain compiler (#391), not only
    /// asserted about by a source-shape test.
    ///
    /// Naming note: no member here reads a player list or a Photon sender, so
    /// the kept-view census (tools/kept_view_census) finds no consumer in this
    /// file; the field that carries an event's sending actor is `From`.
    /// </summary>
    internal static class FfaLateRules
    {
        // The windows the lock payload carries (sec3.2 constants). The payload
        // value wins at run time; these are the harness's and the fallback's.
        internal const int SpawnOpenS = 6;
        internal const int FenceS = 3;
        internal const int FenceTries = 3;
        internal const int StampWaitS = 2;
        internal const int EpochAckS = 2;

        internal enum Gate { Ungated, Pre, Started }

        internal struct GrantEntry
        {
            public int Slot;
            public int Actor;
            public char Kind;   // 's' start roster, 'l' admitted late
            public GrantEntry(int slot, int actor, char kind) { Slot = slot; Actor = actor; Kind = kind; }
        }

        internal struct EpochEntry
        {
            public int Slot;
            public int Actor;
            public EpochEntry(int slot, int actor) { Slot = slot; Actor = actor; }
        }

        /// <summary>A client's copy of the server's kept-epoch record: the
        /// highest-n record it verified (item 13). Entry i is epoch i + 1.</summary>
        internal sealed class EpochRecord
        {
            public int N;
            public string Chain = "0";
            public List<EpochEntry> Entries = new List<EpochEntry>();

            public EpochRecord Copy()
            {
                return new EpochRecord { N = N, Chain = Chain, Entries = new List<EpochEntry>(Entries) };
            }
        }

        /// <summary>EVT_EPOCH's payload {lobby8, n, chain, g, k} (a proposal
        /// since V10), and EVT_EPOCH_ACK's, copied from the proposal.</summary>
        internal struct Proposal
        {
            public string Lobby8;
            public int N;
            public string Chain;
            public int G;
            public int K;
            public int From;
        }

        /// <summary>EVT_CALLIN's payload {lobby8, g, k, n, chain, result}.</summary>
        internal sealed class Stamp
        {
            public string Lobby8;
            public int G;
            public int K;
            public int N;
            public string Chain;
            public string Result;   // commit | unacked | carry
            public int From;

            public bool SameAs(Stamp o)
            {
                return o != null && o.N == N && o.Chain == Chain && o.Result == Result && o.G == G && o.K == K;
            }
        }

        // ---------------------------------------------------------------- chain

        /// <summary>FNV-1a 64 over the ASCII bytes of a string.</summary>
        internal static ulong Fnv64(string s)
        {
            ulong h = 0xcbf29ce484222325UL;
            for (int i = 0; i < s.Length; i++)
            {
                h ^= (byte)(s[i] & 0x7f);
                h *= 0x100000001b3UL;
            }
            return h;
        }

        internal static string Hex16(ulong h)
        {
            return h.ToString("x16", CultureInfo.InvariantCulture);
        }

        /// <summary>The chain at epoch n over a record's entries, the client's
        /// twin of the server's _ffa_epoch_chain: FNV-1a 64 over
        /// "{prev}:{lobby8}:{i}:{slot}:{actor}", prev "0" for epoch 1. Epoch 0
        /// (nothing applied) is "0". Null when the entries do not reach n.</summary>
        internal static string ChainOf(string lobby8, IList<EpochEntry> entries, int n)
        {
            if (n <= 0)
                return "0";
            if (entries == null || entries.Count < n)
                return null;
            string prev = "0";
            for (int i = 0; i < n; i++)
            {
                var e = entries[i];
                prev = Hex16(Fnv64(prev + ":" + lobby8 + ":" + (i + 1).ToString(CultureInfo.InvariantCulture)
                                   + ":" + e.Slot.ToString(CultureInfo.InvariantCulture)
                                   + ":" + e.Actor.ToString(CultureInfo.InvariantCulture)));
            }
            return prev;
        }

        /// <summary>What an answer's `epoch` does to the record held (item 13):
        /// "bad" when its chain does not verify (the answer's epoch is ignored,
        /// `epoch_bad`), "rx" when it verifies with a higher n (it replaces the
        /// held record, `epoch_rx`), and "keep" otherwise: a lower, equal or
        /// absent n changes nothing, so a delayed older answer never erases a
        /// record (K45 fixture ii).</summary>
        internal static string RecordDecision(EpochRecord held, string lobby8, int n, string chain,
                                              IList<EpochEntry> entries)
        {
            if (n <= 0 || entries == null)
                return "keep";
            if (entries.Count != n || ChainOf(lobby8, entries, n) != chain)
                return "bad";
            int heldN = held == null ? 0 : held.N;
            return n > heldN ? "rx" : "keep";
        }

        // ---------------------------------------------------------------- the kept set

        internal static bool IsKindS(int actor, IList<GrantEntry> grants)
        {
            if (grants == null) return false;
            for (int i = 0; i < grants.Count; i++)
                if (grants[i].Actor == actor && grants[i].Kind == 's')
                    return true;
            return false;
        }

        internal static bool InGrants(int actor, IList<GrantEntry> grants)
        {
            if (grants == null) return false;
            for (int i = 0; i < grants.Count; i++)
                if (grants[i].Actor == actor)
                    return true;
            return false;
        }

        internal static bool ListedIn(int actor, EpochRecord rec, int upto)
        {
            if (rec == null || upto <= 0) return false;
            int m = Math.Min(upto, rec.Entries.Count);
            for (int i = 0; i < m; i++)
                if (rec.Entries[i].Actor == actor)
                    return true;
            return false;
        }

        /// <summary>The sender test at an event's dispatch (N3; V11 N9): the
        /// actor is kind s in this client's grant set, or listed in the first
        /// PointEpoch entries of its record (the set it paired at its last
        /// call-in). Never an entry of a candidate epoch it has not paired.</summary>
        internal static bool KeptSender(int actor, IList<GrantEntry> grants, EpochRecord rec, int pointEpoch)
        {
            return IsKindS(actor, grants) || ListedIn(actor, rec, pointEpoch);
        }

        /// <summary>The one kept-actor view's value (item 13):
        /// !GatedRunning || (HoldsGrant && kept(a)), with kept(a) the
        /// KeptSender test.</summary>
        internal static bool KeptActorValue(Gate gate, bool holdsGrant, int actor, IList<GrantEntry> grants,
                                            EpochRecord rec, int pointEpoch)
        {
            if (gate != Gate.Started)
                return true;
            return holdsGrant && KeptSender(actor, grants, rec, pointEpoch);
        }

        /// <summary>The authority fence's value for the current master (item
        /// 13): always in an ungated room; while the gate reads started, the
        /// kept view; while it reads pre, kind s in the grant set, or always
        /// on a client that has read no granted list yet.</summary>
        internal static bool MasterKeptValue(Gate gate, bool holdsGrant, bool readGranted, int master,
                                             IList<GrantEntry> grants, EpochRecord rec, int pointEpoch)
        {
            if (gate == Gate.Ungated)
                return true;
            if (gate == Gate.Pre)
                return !readGranted || IsKindS(master, grants);
            return KeptActorValue(gate, holdsGrant, master, grants, rec, pointEpoch);
        }

        // ---------------------------------------------------------------- the gate

        internal struct GateResult
        {
            public Gate State;
            public string Src;   // statement | default | trigger
        }

        /// <summary>The gate's value from plain inputs (V9, N2): ungated when
        /// the engine is inactive, this client is a spectator, or the latest
        /// statement says assembly 0; pre only on a statement received after
        /// this client's entry with assembly 1 and asm_started 0 and no start
        /// trigger seen; started otherwise, with no statement included
        /// (fail-closed).</summary>
        internal static GateResult GateValue(bool haveStatement, bool stmtAssembly, bool stmtAsmStarted,
                                             bool stmtPostEntry, bool triggerSeen, bool engineActive,
                                             bool isSpectator)
        {
            if (!engineActive || isSpectator)
                return new GateResult { State = Gate.Ungated, Src = "default" };
            if (haveStatement && !stmtAssembly)
                return new GateResult { State = Gate.Ungated, Src = "statement" };
            if (triggerSeen)
                return new GateResult { State = Gate.Started, Src = "trigger" };
            if (haveStatement && stmtPostEntry && stmtAssembly && !stmtAsmStarted)
                return new GateResult { State = Gate.Pre, Src = "statement" };
            return new GateResult { State = Gate.Started, Src = "default" };
        }

        // ---------------------------------------------------------------- readiness and the barrier

        /// <summary>The epoch this client signals with EVT_READY (item 13): the
        /// highest n its own verified record holds, once every present actor
        /// that epoch lists has a registered body here; -1 while one does not,
        /// or when it holds no epoch. peerMax, the highest epoch any peer has
        /// signalled, is NOT an input to the answer: a signal states only what
        /// its sender holds and sees (K45 fixture i).</summary>
        internal static int ReadyEpoch(EpochRecord rec, ICollection<int> present, ICollection<int> bodies,
                                       int peerMax)
        {
            if (rec == null || rec.N <= 0)
                return -1;
            for (int i = 0; i < rec.N && i < rec.Entries.Count; i++)
            {
                int a = rec.Entries[i].Actor;
                if (present != null && present.Contains(a) && (bodies == null || !bodies.Contains(a)))
                    return -1;
            }
            return rec.N;
        }

        /// <summary>The master's readiness barrier (item 13): the highest n at
        /// or below its own record such that every present actor of the barrier
        /// set (the kind-s actors of its grant set and every actor epoch n
        /// lists, itself included) has signalled at least n; 0 when none.</summary>
        internal static int BarrierEpoch(EpochRecord rec, IList<GrantEntry> grants, ICollection<int> present,
                                         IDictionary<int, int> ready, int self, int selfReady)
        {
            if (rec == null)
                return 0;
            for (int n = rec.N; n >= 1; n--)
            {
                bool ok = true;
                foreach (int a in BarrierSet(rec, grants, n))
                {
                    if (present != null && !present.Contains(a))
                        continue;
                    int r;
                    if (a == self)
                        r = selfReady;
                    else if (ready == null || !ready.TryGetValue(a, out r))
                        r = -1;
                    if (r < n) { ok = false; break; }
                }
                if (ok)
                    return n;
            }
            return 0;
        }

        /// <summary>The barrier set of epoch n: the kind-s actors of the grant
        /// set and every actor the first n entries list, in actor order.</summary>
        internal static List<int> BarrierSet(EpochRecord rec, IList<GrantEntry> grants, int n)
        {
            var set = new SortedSet<int>();
            if (grants != null)
                for (int i = 0; i < grants.Count; i++)
                    if (grants[i].Kind == 's')
                        set.Add(grants[i].Actor);
            if (rec != null)
                for (int i = 0; i < n && i < rec.Entries.Count; i++)
                    set.Add(rec.Entries[i].Actor);
            return new List<int>(set);
        }

        // ---------------------------------------------------------------- the proposal and its acknowledgements

        /// <summary>The checks e1-e6 at a proposal's dispatch (item 13). Null
        /// when all six hold (the client acknowledges and applies nothing);
        /// otherwise the refusal's why. `dispatchMaster` is
        /// PhotonNetwork.MasterClient read at the dispatch; `masterKept` is
        /// MasterKept() for it on this client. `kKnown` is false for a late
        /// seat with no accepted snapshot, which matches on g alone. `present`
        /// is NOT an input to any check: a listed actor that has left stays in
        /// the record and matches no body (K45 fixture iii).</summary>
        internal static string ValidateEpoch(Proposal p, int dispatchMaster, bool masterKept, string ownLobby8,
                                             EpochRecord rec, int epochApplied, string appliedChain,
                                             int ownG, int ownK, bool kKnown, ICollection<int> present)
        {
            if (p.From != dispatchMaster || !masterKept)
                return "sender";                                         // e1
            if (p.Lobby8 != ownLobby8)
                return "lobby";                                          // e2
            if (p.N < epochApplied)
                return "stale";                                          // e3
            if (rec == null || rec.N < p.N)
                return "missing";                                        // e4 (held)
            if (ChainOf(ownLobby8, rec.Entries, p.N) != p.Chain)
                return "mismatch";                                       // e4 (chain at n)
            if (ChainOf(ownLobby8, rec.Entries, epochApplied) != appliedChain)
                return "chain";                                          // e5
            if (p.G != ownG || (kKnown && p.K != ownK))
                return "boundary";                                       // e6
            return null;
        }

        /// <summary>Whether every present member of the barrier set other than
        /// the master has acknowledged this proposal (V10, N7): one
        /// acknowledgement per sender, matched on (n, chain, g, k); an
        /// acknowledgement for another proposal, or from a client outside the
        /// barrier set, is not counted (K45 fixture viii).</summary>
        internal static bool AckComplete(ICollection<int> barrier, ICollection<int> present, IList<Proposal> acks,
                                         Proposal p, int self, out List<int> missing)
        {
            missing = new List<int>();
            var got = new HashSet<int>();
            if (acks != null)
                for (int i = 0; i < acks.Count; i++)
                {
                    var a = acks[i];
                    if (a.N == p.N && a.Chain == p.Chain && a.G == p.G && a.K == p.K && a.Lobby8 == p.Lobby8
                        && barrier != null && barrier.Contains(a.From))
                        got.Add(a.From);
                }
            if (barrier != null)
                foreach (int m in barrier)
                {
                    if (m == self) continue;
                    if (present != null && !present.Contains(m)) continue;
                    if (!got.Contains(m)) missing.Add(m);
                }
            missing.Sort();
            return missing.Count == 0;
        }

        /// <summary>The master's stamp at a boundary (item 13): commit n* when
        /// it proposed and every acknowledgement arrived, unacked when it
        /// proposed and one did not, carry when it proposed nothing. Commit
        /// names n*; unacked and carry name its own PointEpoch (V11, N9).
        /// `proposed` is false for a kind-l master and for n* at or below its
        /// PointEpoch. `apply` is what the master applies at the stamp's send:
        /// the committed epoch, never earlier (V10, N7).</summary>
        internal static void MasterStampDecision(bool proposed, int nStar, bool ackComplete, int pointEpoch,
                                                 out string result, out int n, out bool apply)
        {
            if (!proposed) { result = "carry"; n = pointEpoch; apply = false; return; }
            if (ackComplete) { result = "commit"; n = nStar; apply = true; return; }
            result = "unacked"; n = pointEpoch; apply = false;
        }

        /// <summary>Whether a master proposes at a boundary (item 13): only an
        /// epoch above its PointEpoch (V11, N9) and only while its own actor is
        /// kind s in its grant set (V8, V7-F3). A kind-l master proposes
        /// nothing and stamps carry.</summary>
        internal static bool MayPropose(int nStar, int pointEpoch, bool selfKindS)
        {
            return selfKindS && nStar > pointEpoch;
        }

        // ---------------------------------------------------------------- the stamp and the pairing

        /// <summary>The checks s1-s4 at a stamp's pairing (item 13; V11, N9).
        /// Null when they hold. s1: the sender is CallInMaster(g, k), the
        /// KeptSender test holds for it, and it is kind s in the grant set when
        /// the stamp commits or names an n above EpochApplied; s2 the lobby;
        /// s3 the boundary; s4 the record holds n with that chain and the
        /// applied prefix still re-hashes to the applied chain.</summary>
        internal static string ValidateStamp(Stamp s, int callInMaster, bool keptSender, bool senderKindS,
                                             string ownLobby8, EpochRecord rec, int epochApplied,
                                             string appliedChain, int ownG, int ownK, bool kKnown)
        {
            if (s == null)
                return "sender";
            bool raises = s.Result == "commit" || s.N > epochApplied;
            if (s.From != callInMaster || !keptSender || (raises && !senderKindS))
                return "sender";                                         // s1
            if (s.Lobby8 != ownLobby8)
                return "lobby";                                          // s2
            if (s.G != ownG || (kKnown && s.K != ownK))
                return "boundary";                                       // s3
            if (rec == null || rec.N < s.N || ChainOf(ownLobby8, rec.Entries, s.N) != s.Chain
                || ChainOf(ownLobby8, rec.Entries, epochApplied) != appliedChain)
                return "epoch";                                          // s4
            return null;
        }

        internal enum PairKind { Apply, Carry, CarryDown, StampLate, LagOut, Nothing }

        internal struct PairResult
        {
            public PairKind Kind;
            public int PointEpoch;      // the point's epoch after the decision
            public int EpochApplied;    // EpochApplied after the decision
            public string Why;          // LAG_OUT's why
            public bool Late;           // a stamp after the hold (stamp_rx late=1)
        }

        /// <summary>What a call-in pairs (item 13; V11, N9). `stamp` is the
        /// valid stamp of CallInMaster(g, k) held for (g, k), or null when the
        /// hold ended without one; `conflict` is two valid stamps of that
        /// master for (g, k) that differ. A valid stamp sets PointEpoch = n and
        /// raises EpochApplied to max(EpochApplied, n): above it applies
        /// (kept src=epoch), equal carries, below converges down (kept
        /// src=carry down=1). With no stamp the hold ends in stamp_late only
        /// when this client sent no acknowledgement at (g, k) and its last
        /// pairing was with the call-in's master; otherwise LAG_OUT
        /// why=timeout.</summary>
        internal static PairResult PairDecision(Stamp stamp, bool conflict, int callInMaster, int lastPairMaster,
                                                bool ackSent, int pointEpoch, int epochApplied, EpochRecord rec)
        {
            var r = new PairResult { PointEpoch = pointEpoch, EpochApplied = epochApplied };
            if (conflict)
            {
                r.Kind = PairKind.LagOut; r.Why = "conflict";
                return r;
            }
            if (stamp != null)
            {
                if (rec == null || rec.N < stamp.N)
                {
                    r.Kind = PairKind.LagOut; r.Why = "stamp_above";
                    return r;
                }
                r.PointEpoch = stamp.N;
                r.EpochApplied = Math.Max(epochApplied, stamp.N);
                r.Kind = stamp.N > epochApplied ? PairKind.Apply
                    : (stamp.N == epochApplied ? PairKind.Carry : PairKind.CarryDown);
                return r;
            }
            if (!ackSent && lastPairMaster >= 0 && lastPairMaster == callInMaster)
            {
                r.Kind = PairKind.StampLate;
                return r;
            }
            r.Kind = PairKind.LagOut; r.Why = "timeout";
            return r;
        }

        /// <summary>A valid stamp of the call-in's master that arrives after
        /// the point was decided changes nothing for that point (stamp_rx
        /// late=1): a pairing, a stamp_late carry and LAG_OUT all stand. Two
        /// exceptions start LAG_OUT, neither of which a compliant master can
        /// cause: a stamp that differs from the one the point paired
        /// (why=conflict), and one that contradicts a stamp_late carry
        /// (why=stamp_above). `paired` is the stamp the point paired, or null.</summary>
        internal static PairResult LateStampDecision(PairResult decided, Stamp paired, Stamp s)
        {
            var r = decided;
            r.Late = true;
            if (decided.Kind == PairKind.LagOut)
                return r;
            if (paired != null && s != null && !paired.SameAs(s))
            {
                r.Kind = PairKind.LagOut; r.Why = "conflict";
                return r;
            }
            if (decided.Kind == PairKind.StampLate && s != null && s.N != decided.PointEpoch)
            {
                r.Kind = PairKind.LagOut; r.Why = "stamp_above";
                return r;
            }
            r.Kind = PairKind.Nothing;
            return r;
        }

        /// <summary>LastPairMaster at a game's start (V11, N9): a start-roster
        /// seat that has paired no call-in yet takes the master whose start
        /// began its sitting's first game, so an undisputed first point can
        /// end in stamp_late; any later game's start changes nothing (neither
        /// LastPairMaster nor PointEpoch).</summary>
        internal static int LastPairAtGameStart(int lastPairMaster, bool pairedAny, bool firstGameOfSitting,
                                                int startMaster)
        {
            if (!pairedAny && firstGameOfSitting && lastPairMaster < 0)
                return startMaster;
            return lastPairMaster;
        }

        /// <summary>The reporter election's lag rule (K39; V11, N9): the first
        /// candidate, in the election's order, that is neither a late seat
        /// (cr_late) nor lagged in the game (cr_lag); -1 when none.</summary>
        internal static int ElectReporter(IList<int> candidates, Func<int, bool> lagged, Func<int, bool> late)
        {
            if (candidates == null)
                return -1;
            for (int i = 0; i < candidates.Count; i++)
            {
                int a = candidates[i];
                if (late != null && late(a)) continue;
                if (lagged != null && lagged(a)) continue;
                return a;
            }
            return -1;
        }

        /// <summary>Whether an event ends LAG_OUT (V11, N9): the room exit
        /// ("room_exit") always; a call-in paired with a valid stamp
        /// ("callin") unless it is the call-in of the point whose load started
        /// the state; a game's end or start never.</summary>
        internal static bool LagOutEnds(string evt, bool startedAtThisPointsLoad)
        {
            if (evt == "room_exit")
                return true;
            if (evt == "callin")
                return !startedAtThisPointsLoad;
            return false;
        }

        /// <summary>The cr_lag value (V11, N9): "{lobby8}:{g}:{k}".</summary>
        internal static string LagValue(string lobby8, int g, int k)
        {
            return lobby8 + ":" + g.ToString(CultureInfo.InvariantCulture) + ":"
                   + k.ToString(CultureInfo.InvariantCulture);
        }

        /// <summary>Whether a published cr_lag names this lobby and game, at
        /// point k when k is at least 1, or at any point when k is 0.</summary>
        internal static bool LagNames(string crLag, string lobby8, int g, int k)
        {
            if (string.IsNullOrEmpty(crLag))
                return false;
            var parts = crLag.Split(':');
            int pg, pk;
            if (parts.Length != 3 || parts[0] != lobby8
                || !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out pg)
                || !int.TryParse(parts[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out pk))
                return false;
            return pg == g && (k <= 0 || pk == k);
        }

        /// <summary>The authority fence's test (item 13): a master is fenced
        /// when the kept view rejects it, or since V11 (N9) when it is in
        /// LAG_OUT.</summary>
        internal static bool MasterFencedValue(bool masterKept, bool lagOut)
        {
            return !masterKept || lagOut;
        }

        /// <summary>The call-in pairing over kept flags in list order (item 13,
        /// surface 4): each kept entry takes the next index, a quarantined
        /// entry takes -1. [kept, quarantined, kept] maps to [0, -1, 1].</summary>
        internal static int[] PairIndices(bool[] kept)
        {
            if (kept == null)
                return new int[0];
            var idx = new int[kept.Length];
            int next = 0;
            for (int i = 0; i < kept.Length; i++)
                idx[i] = kept[i] ? next++ : -1;
            return idx;
        }

        // ---------------------------------------------------------------- the fence

        internal struct FenceChoice
        {
            public int To;       // -1: none
            public string Why;   // no_grant | no_grant_next | kept | kind_s
        }

        /// <summary>The actor the fence hands the master role to (item 13, the
        /// transfer). On a client that holds a grant: the lowest present kind-s
        /// actor of its grant set that the fence accepts, else the lowest
        /// present kept actor, skipping every actor lagged for this point and
        /// itself; none when none is acceptable. On a client that holds no
        /// grant: the lowest present actor its grant set names, kind s first
        /// (why=no_grant), else, once per entry, the next present actor above
        /// its own, wrapping (why=no_grant_next).</summary>
        internal static FenceChoice FenceTarget(int self, IList<int> present, IList<GrantEntry> grants,
                                                bool holdsGrant, Func<int, bool> kept, Func<int, bool> lagged,
                                                bool handedOffThisEntry)
        {
            var sorted = new List<int>(present ?? new List<int>());
            sorted.Sort();
            if (holdsGrant)
            {
                foreach (int a in sorted)
                    if (a != self && IsKindS(a, grants) && kept(a) && !lagged(a))
                        return new FenceChoice { To = a, Why = "kind_s" };
                foreach (int a in sorted)
                    if (a != self && kept(a) && !lagged(a))
                        return new FenceChoice { To = a, Why = "kept" };
                return new FenceChoice { To = -1, Why = "none" };
            }
            foreach (int a in sorted)
                if (a != self && IsKindS(a, grants) && !lagged(a))
                    return new FenceChoice { To = a, Why = "no_grant" };
            foreach (int a in sorted)
                if (a != self && InGrants(a, grants) && !lagged(a))
                    return new FenceChoice { To = a, Why = "no_grant" };
            if (handedOffThisEntry)
                return new FenceChoice { To = -1, Why = "none" };
            foreach (int a in sorted)
                if (a > self)
                    return new FenceChoice { To = a, Why = "no_grant_next" };
            foreach (int a in sorted)
                if (a != self)
                    return new FenceChoice { To = a, Why = "no_grant_next" };
            return new FenceChoice { To = -1, Why = "none" };
        }

        internal enum FenceAct { Wait, Try, Done, Kept, Expired }

        /// <summary>The fence's next step (V10, N7): a hand-off every FenceS
        /// seconds of realtime, at most FenceTries tries, the episode ending
        /// done when the switch lands, kept when this client becomes kept (and
        /// is not in LAG_OUT), and expired FenceS * FenceTries seconds after
        /// the first try (FENCE_EXPIRED).</summary>
        internal static FenceAct FenceStep(double sinceFirstTry, int triesMade, bool switchLanded, bool keptNow)
        {
            if (switchLanded)
                return FenceAct.Done;
            if (keptNow)
                return FenceAct.Kept;
            if (sinceFirstTry >= FenceS * FenceTries)
                return FenceAct.Expired;
            if (triesMade < FenceTries && sinceFirstTry >= triesMade * FenceS)
                return FenceAct.Try;
            return FenceAct.Wait;
        }

        // ---------------------------------------------------------------- the count

        internal sealed class ScaleRecord
        {
            public int Game;
            public int K;
            public int Count;
            public int From;
            public bool Confirmed;
        }

        internal struct ScaleResult
        {
            public int Count;      // -1: unscaled
            public string Why;     // null, none, stale, unconfirmed, conflict
            public bool LagOut;    // V11 (N9): an unscaled gated load sits the point out
        }

        /// <summary>Whether an EVT_SCALE is recorded at its dispatch (V9, N3;
        /// V10, N7): the lobby is this client's, the sender is the current
        /// master at the dispatch or LatchMaster(game, k), and the KeptSender
        /// test holds for it then. Null when recorded, else the refusal's why.</summary>
        internal static string ScaleRecordDecision(string lobby8, string ownLobby8, int from, int dispatchMaster,
                                                   int latchMaster, bool keptSender)
        {
            if (lobby8 != ownLobby8) return "lobby";
            if (from != dispatchMaster && from != latchMaster) return "sender";
            if (!keptSender) return "unkept";
            return null;
        }

        /// <summary>A load's count from its keyed records (V10, N7; V11, N9):
        /// the record for the load's (game, k) serves only when confirmed, and
        /// the caller clears every key at or below it. Two confirmed records
        /// that differ for the key load unscaled; no record, a stale one or an
        /// unconfirmed one load unscaled; every unscaled gated load enters
        /// LAG_OUT (why=scale). A late seat that holds no snapshot matches on
        /// game alone (kKnown false).</summary>
        internal static ScaleResult ScaleDecision(IList<ScaleRecord> records, int game, int k, bool kKnown)
        {
            ScaleRecord hit = null;
            bool conflict = false, stale = false, unconfirmedOnly = false;
            if (records != null)
                for (int i = 0; i < records.Count; i++)
                {
                    var r = records[i];
                    bool keyed = r.Game == game && (!kKnown || r.K == k);
                    if (!keyed)
                    {
                        if (r.Game < game || (r.Game == game && r.K < k))
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
                return new ScaleResult { Count = -1, Why = "conflict", LagOut = true };
            if (hit != null)
                return new ScaleResult { Count = hit.Count, Why = null, LagOut = false };
            if (unconfirmedOnly)
                return new ScaleResult { Count = -1, Why = "unconfirmed", LagOut = true };
            return new ScaleResult { Count = -1, Why = stale ? "stale" : "none", LagOut = true };
        }

        /// <summary>A record that arrives after a load already used a count for
        /// its key and differs from it starts LAG_OUT (why=scale_late).</summary>
        internal static bool ScaleLate(int appliedGame, int appliedK, int appliedCount, ScaleRecord arrived)
        {
            return arrived != null && arrived.Confirmed && arrived.Game == appliedGame && arrived.K == appliedK
                   && arrived.Count != appliedCount;
        }

        /// <summary>A load consumes its key (V10, N7): every record at or below
        /// (game, k) is removed, whether the load used one or loaded unscaled.</summary>
        internal static void ConsumeScale(List<ScaleRecord> records, int game, int k)
        {
            if (records == null)
                return;
            records.RemoveAll(r => r.Game < game || (r.Game == game && r.K <= k));
        }

        /// <summary>The snapshot's `scale` field: the (g, k, count, sender) the
        /// master applied to its own load, "{g}:{k}:{count}:{sender}".</summary>
        internal static string ScaleTag(int g, int k, int count, int sender)
        {
            return g.ToString(CultureInfo.InvariantCulture) + ":" + k.ToString(CultureInfo.InvariantCulture) + ":"
                   + count.ToString(CultureInfo.InvariantCulture) + ":" + sender.ToString(CultureInfo.InvariantCulture);
        }

        // ---------------------------------------------------------------- the digest and the spawn

        internal sealed class SlotState
        {
            public int Slot;
            public int Rounds;
            public int Points;
            public int PointsTotal;
            public int Kills;                                   // never digested (sec16.4, deviation 9)
            public List<string> Cards = new List<string>();     // absent slots' recorded automatic picks included
        }

        /// <summary>The boundary digest's hash (item 13): FNV-1a over g, k, the
        /// boundary's levelId and, per slot in slot order, its rounds, points,
        /// point total and card list. Kills are left out.</summary>
        internal static string BoundaryDigest(int g, int k, string levelId, IList<SlotState> slots)
        {
            var sb = new StringBuilder();
            sb.Append(g.ToString(CultureInfo.InvariantCulture)).Append('|')
              .Append(k.ToString(CultureInfo.InvariantCulture)).Append('|')
              .Append(levelId ?? "");
            var ordered = new List<SlotState>(slots ?? new List<SlotState>());
            ordered.Sort((a, b) => a.Slot.CompareTo(b.Slot));
            foreach (var s in ordered)
            {
                sb.Append('|').Append(s.Slot.ToString(CultureInfo.InvariantCulture))
                  .Append(':').Append(s.Rounds.ToString(CultureInfo.InvariantCulture))
                  .Append(':').Append(s.Points.ToString(CultureInfo.InvariantCulture))
                  .Append(':').Append(s.PointsTotal.ToString(CultureInfo.InvariantCulture))
                  .Append(':').Append(string.Join(",", s.Cards ?? new List<string>()));
            }
            return Hex16(Fnv64(sb.ToString()));
        }

        /// <summary>A published cr_bd "{g}:{k}:{hash}", split; false when it is
        /// not that shape.</summary>
        internal static bool ParseBd(string bd, out int g, out int k, out string hash)
        {
            g = k = -1; hash = null;
            if (string.IsNullOrEmpty(bd)) return false;
            var parts = bd.Split(':');
            if (parts.Length != 3) return false;
            if (!int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out g)) return false;
            if (!int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out k)) return false;
            hash = parts[2];
            return hash.Length > 0;
        }

        internal struct PeerBd
        {
            public int Actor;
            public int Slot;
            public bool IsMaster;
            public bool Kept;    // on the late seat's own view
            public string Bd;    // the peer's cr_bd, or null when it published none
        }

        /// <summary>The late seat's digest check (item 5, step 5; V6): it passes
        /// only when at least one present non-master kept peer has published a
        /// cr_bd for the snapshot's (g, k), every such published one equals the
        /// snapshot's digest, and g >= late_game. `peer` is the lowest slot of a
        /// matching peer (order-independent), -1 when none published.</summary>
        internal static bool DigestGate(string snapDigest, int g, int k, int lateGame, IList<PeerBd> peers,
                                        out int peer)
        {
            peer = -1;
            int agree = 0;
            bool differ = false;
            if (peers != null)
                for (int i = 0; i < peers.Count; i++)
                {
                    var p = peers[i];
                    if (p.IsMaster || !p.Kept)
                        continue;
                    int pg, pk; string ph;
                    if (!ParseBd(p.Bd, out pg, out pk, out ph) || pg != g || pk != k)
                        continue;
                    if (ph != snapDigest) { differ = true; continue; }
                    agree++;
                    if (peer < 0 || p.Slot < peer) peer = p.Slot;
                }
            return agree >= 1 && !differ && g >= lateGame;
        }

        /// <summary>The spawn permission (item 1 and item 5, step 5). Arrival:
        /// a start_ok, or a state-A answer carrying spawn_ok = 1 whose window
        /// test held (the gate's span tests server_age_ms - spawn_ok_age_ms
        /// against spawn_open_s and passes the result in). A snapshot never
        /// opens the arrival gate. Late: the digest gate, the seed match and
        /// the scale match, before this boundary's call-in.</summary>
        internal static bool MaySpawn(bool late, bool startOk, bool stateAInWindow, bool snapshot,
                                      bool digestOk, bool seedMatch, bool scaleMatch, bool callInCame)
        {
            if (!late)
                return startOk || stateAInWindow;
            return snapshot && digestOk && seedMatch && scaleMatch && !callInCame;
        }

        // ================================================================
        // The self-test, EXECUTED by tools/late-rules-harness (sec8.2).
        // SelfTest() runs every fixture of K33 (i to vi), K44, K42 (the
        // positional pairing and fixtures a, d and e) and K45 (i to xii)
        // against the real functions above. The harness then runs it against
        // each named mutant, which must turn exactly its fixtures red, and
        // each inert twin, which must stay green with identical printed
        // lines. Production never calls anything below this line.
        // ================================================================

        internal delegate string ValidateEpochFn(Proposal p, int dispatchMaster, bool masterKept, string ownLobby8,
            EpochRecord rec, int epochApplied, string appliedChain, int ownG, int ownK, bool kKnown,
            ICollection<int> present);
        internal delegate string ValidateStampFn(Stamp s, int callInMaster, bool keptSender, bool senderKindS,
            string ownLobby8, EpochRecord rec, int epochApplied, string appliedChain, int ownG, int ownK,
            bool kKnown);
        internal delegate PairResult PairDecisionFn(Stamp stamp, bool conflict, int callInMaster, int lastPairMaster,
            bool ackSent, int pointEpoch, int epochApplied, EpochRecord rec);
        internal delegate bool AckCompleteFn(ICollection<int> barrier, ICollection<int> present,
            IList<Proposal> acks, Proposal p, int self, out List<int> missing);
        internal delegate void StampDecisionFn(bool proposed, int nStar, bool ackComplete, int pointEpoch,
            out string result, out int n, out bool apply);
        internal delegate bool MayProposeFn(int nStar, int pointEpoch, bool selfKindS);
        internal delegate int BarrierEpochFn(EpochRecord rec, IList<GrantEntry> grants, ICollection<int> present,
            IDictionary<int, int> ready, int self, int selfReady);
        internal delegate int ReadyEpochFn(EpochRecord rec, ICollection<int> present, ICollection<int> bodies,
            int peerMax);
        internal delegate string RecordDecisionFn(EpochRecord held, string lobby8, int n, string chain,
            IList<EpochEntry> entries);
        internal delegate FenceChoice FenceTargetFn(int self, IList<int> present, IList<GrantEntry> grants,
            bool holdsGrant, Func<int, bool> kept, Func<int, bool> lagged, bool handedOffThisEntry);
        internal delegate FenceAct FenceStepFn(double sinceFirstTry, int triesMade, bool switchLanded,
            bool keptNow);
        internal delegate ScaleResult ScaleDecisionFn(IList<ScaleRecord> records, int game, int k, bool kKnown);
        internal delegate string ScaleRecordFn(string lobby8, string ownLobby8, int from, int dispatchMaster,
            int latchMaster, bool keptSender);
        internal delegate bool DigestGateFn(string snapDigest, int g, int k, int lateGame, IList<PeerBd> peers,
            out int peer);
        internal delegate string BoundaryDigestFn(int g, int k, string levelId, IList<SlotState> slots);
        internal delegate bool MaySpawnFn(bool late, bool startOk, bool stateAInWindow, bool snapshot,
            bool digestOk, bool seedMatch, bool scaleMatch, bool callInCame);
        internal delegate GateResult GateValueFn(bool haveStatement, bool stmtAssembly, bool stmtAsmStarted,
            bool stmtPostEntry, bool triggerSeen, bool engineActive, bool isSpectator);
        internal delegate bool KeptActorFn(Gate gate, bool holdsGrant, int actor, IList<GrantEntry> grants,
            EpochRecord rec, int pointEpoch);
        internal delegate bool MasterKeptFn(Gate gate, bool holdsGrant, bool readGranted, int master,
            IList<GrantEntry> grants, EpochRecord rec, int pointEpoch);
        internal delegate bool KeptSenderFn(int actor, IList<GrantEntry> grants, EpochRecord rec, int pointEpoch);
        internal delegate int[] PairIndicesFn(bool[] kept);
        internal delegate int ElectReporterFn(IList<int> candidates, Func<int, bool> lagged, Func<int, bool> late);
        internal delegate bool LagOutEndsFn(string evt, bool startedAtThisPointsLoad);
        internal delegate void ConsumeScaleFn(List<ScaleRecord> records, int game, int k);

        /// <summary>The rules under test. Production calls the functions
        /// above directly; the harness passes wrong implementations and inert
        /// twins through here, so the fixtures measure BEHAVIOUR rather than
        /// this file's text (#342). The knobs at the end change only the
        /// self-test's simulated clients, where the mutant the design names is
        /// a wrong ORDER of steps rather than a wrong rule.</summary>
        internal sealed class Impl
        {
            internal ValidateEpochFn ValidateEpoch = FfaLateRules.ValidateEpoch;
            internal ValidateStampFn ValidateStamp = FfaLateRules.ValidateStamp;
            internal PairDecisionFn PairDecision = FfaLateRules.PairDecision;
            internal AckCompleteFn AckComplete = FfaLateRules.AckComplete;
            internal StampDecisionFn StampDecision = FfaLateRules.MasterStampDecision;
            internal MayProposeFn MayPropose = FfaLateRules.MayPropose;
            internal BarrierEpochFn BarrierEpoch = FfaLateRules.BarrierEpoch;
            internal ReadyEpochFn ReadyEpoch = FfaLateRules.ReadyEpoch;
            internal RecordDecisionFn RecordDecision = FfaLateRules.RecordDecision;
            internal FenceTargetFn FenceTarget = FfaLateRules.FenceTarget;
            internal FenceStepFn FenceStep = FfaLateRules.FenceStep;
            internal ScaleDecisionFn ScaleDecision = FfaLateRules.ScaleDecision;
            internal ScaleRecordFn ScaleRecord = FfaLateRules.ScaleRecordDecision;
            internal DigestGateFn DigestGate = FfaLateRules.DigestGate;
            internal BoundaryDigestFn BoundaryDigest = FfaLateRules.BoundaryDigest;
            internal MaySpawnFn MaySpawn = FfaLateRules.MaySpawn;
            internal GateValueFn GateValue = FfaLateRules.GateValue;
            internal KeptActorFn KeptActorTest = FfaLateRules.KeptActorValue;
            internal MasterKeptFn MasterKeptTest = FfaLateRules.MasterKeptValue;
            internal KeptSenderFn KeptSender = FfaLateRules.KeptSender;
            internal PairIndicesFn PairIndices = FfaLateRules.PairIndices;
            internal ElectReporterFn ElectReporter = FfaLateRules.ElectReporter;
            internal LagOutEndsFn LagOutEnds = FfaLateRules.LagOutEnds;
            internal ConsumeScaleFn ConsumeScale = FfaLateRules.ConsumeScale;

            /// <summary>V9: a client applies at EVT_EPOCH's dispatch.</summary>
            internal bool ApplyAtProposal;
            /// <summary>V6: the master pairs at the raise, before its own copy of the call-in.</summary>
            internal bool MasterPairsAtRaise;
            /// <summary>V9: the call-in pairs at once, without waiting for its stamp.</summary>
            internal bool NoHold;
            /// <summary>V10: s1 also accepts the master read at the stamp's dispatch.</summary>
            internal bool DispatchMasterStamp;
            /// <summary>V10: the master tests its proposal against EpochApplied, not PointEpoch.</summary>
            internal bool ProposeAgainstApplied;
            /// <summary>V8: the count's sender judged at the load, not at the dispatch.</summary>
            internal bool ScaleJudgeAtLoad;
            /// <summary>V9: every master switch clears the count's records.</summary>
            internal bool ScaleClearAtSwitch;
            /// <summary>V9: the load does not hold for a count on its way, and loads unscaled at once.</summary>
            internal bool ScaleNoHold;
        }

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly List<string> Cases = new List<string>();
            internal readonly Dictionary<string, string> Failures = new Dictionary<string, string>();
            internal readonly StringBuilder Lines = new StringBuilder();
        }

        private sealed class CaseFail : Exception
        {
            internal CaseFail(string m) : base(m) { }
        }

        private sealed class Ctx
        {
            private readonly string _case;
            private readonly SelfTestResult _r;

            internal Ctx(string c, SelfTestResult r) { _case = c; _r = r; }

            internal static Ctx Quiet() { return new Ctx(null, null); }

            internal void P(string line)
            {
                if (_r == null)
                    return;
                _r.Lines.Append(_case).Append(' ').Append(line).Append('\n');
            }

            internal void Ok(bool cond, string what)
            {
                if (!cond)
                    throw new CaseFail(what);
            }
        }

        internal static SelfTestResult SelfTest()
        {
            return SelfTest(new Impl());
        }

        internal static SelfTestResult SelfTest(Impl impl)
        {
            var I = impl ?? new Impl();
            var r = new SelfTestResult();
            for (int i = 1; i <= 6; i++)
            {
                int which = i;
                Run(r, "K33." + Romans[which], x => K33Case(I, x, which));
            }
            Run(r, "K44", x => K44Case(I, x));
            Run(r, "K42.pair", x => K42Pair(I, x));
            Run(r, "K42.a", x => K42a(I, x));
            Run(r, "K42.d", x => K42d(I, x));
            Run(r, "K42.e", x => K42e(I, x));
            Run(r, "K45.i", x => K45i(I, x));
            Run(r, "K45.ii", x => K45ii(I, x));
            Run(r, "K45.iii", x => K45iii(I, x));
            Run(r, "K45.iv", x => K45iv(I, x));
            Run(r, "K45.v", x => K45v(I, x));
            Run(r, "K45.vi", x => K45vi(I, x));
            Run(r, "K45.vii", x => K45vii(I, x));
            Run(r, "K45.viii", x => K45viii(I, x));
            Run(r, "K45.ix", x => K45ix(I, x));
            Run(r, "K45.x", x => K45x(I, x));
            Run(r, "K45.xi.n7", x => K45xiN7(I, x));
            Run(r, "K45.xi.count", x => K45xiCount(I, x));
            Run(r, "K45.xii.a", x => K45xiia(I, x));
            Run(r, "K45.xii.b", x => K45xiib(I, x));
            Run(r, "K45.xii.c", x => K45xiic(I, x));
            Run(r, "K45.xii.d", x => K45xiid(I, x));
            Run(r, "K45.xii.e", x => K45xiie(I, x));
            return r;
        }

        private static void Run(SelfTestResult r, string name, Action<Ctx> body)
        {
            var x = new Ctx(name, r);
            r.Cases.Add(name);
            try
            {
                body(x);
                r.Passed++;
                x.P("PASS");
            }
            catch (CaseFail f)
            {
                r.Failed++;
                r.Failures[name] = f.Message;
                x.P("FAIL " + f.Message);
            }
            catch (Exception e)
            {
                r.Failed++;
                r.Failures[name] = "threw " + e.GetType().Name + ": " + e.Message;
                x.P("FAIL threw " + e.GetType().Name);
            }
        }

        private static readonly string[] Romans = { "", "i", "ii", "iii", "iv", "v", "vi" };

        private const string Lobby8 = "5eed0a11";

        private static string I2S(long v)
        {
            return v.ToString(CultureInfo.InvariantCulture);
        }

        private static string B01(bool b)
        {
            return b ? "1" : "0";
        }

        private static string Ints(IEnumerable<int> xs)
        {
            var sb = new StringBuilder();
            if (xs != null)
                foreach (int v in xs)
                {
                    if (sb.Length > 0) sb.Append(',');
                    sb.Append(v.ToString(CultureInfo.InvariantCulture));
                }
            return sb.ToString();
        }

        private static bool SameInts(int[] a, int[] b)
        {
            if (a == null || b == null || a.Length != b.Length)
                return false;
            for (int i = 0; i < a.Length; i++)
                if (a[i] != b[i])
                    return false;
            return true;
        }

        private static string GateName(Gate g)
        {
            return g == Gate.Ungated ? "ungated" : (g == Gate.Pre ? "pre" : "started");
        }

        private static IEnumerable<string> Perms(string s)
        {
            if (s.Length <= 1)
            {
                yield return s;
                yield break;
            }
            for (int i = 0; i < s.Length; i++)
                foreach (string rest in Perms(s.Remove(i, 1)))
                    yield return s[i] + rest;
        }

        // ---------------------------------------------------------------- K33 and K44: the late spawn and the digest

        private sealed class Snap
        {
            internal int G;
            internal int K;
            internal string Level;
            internal List<SlotState> Slots;
            internal string Seed;
            internal int Scale;
        }

        /// <summary>Four slots in a room's state: three fighters and an absent
        /// slot whose recorded automatic pick is part of the state.</summary>
        private static List<SlotState> RoomSlots(int roundsBump, int killsBump)
        {
            var list = new List<SlotState>();
            for (int s = 0; s < 3; s++)
            {
                var st = new SlotState
                {
                    Slot = s,
                    Rounds = (s == 0 ? 2 + roundsBump : 1),
                    Points = s == 2 ? 1 : 0,
                    PointsTotal = 6 + s,
                    Kills = 3 + s + killsBump,
                };
                st.Cards.Add("Brawler");
                st.Cards.Add(s == 1 ? "Leech" : "Grow");
                list.Add(st);
            }
            var absent = new SlotState { Slot = 3, Rounds = 0, Points = 0, PointsTotal = 0, Kills = 0 };
            absent.Cards.Add("Shield");
            list.Add(absent);
            return list;
        }

        private static string PeerBdOf(Impl I, int g, int k, string level, List<SlotState> slots)
        {
            return I2S(g) + ":" + I2S(k) + ":" + I.BoundaryDigest(g, k, level, slots);
        }

        /// <summary>The late seat's snapshot handler, reduced to its decisions:
        /// the digest from the snapshot's own fields, the digest gate over the
        /// published peers, the seed and the scale compared, and both spawn
        /// paths asked; a snapshot must never open the arrival path.</summary>
        private static bool LateSpawnCheck(Impl I, Ctx x, Snap snap, List<PeerBd> peers, string derivedSeed,
                                           int appliedScale, bool callInCame)
        {
            string digest = I.BoundaryDigest(snap.G, snap.K, snap.Level, snap.Slots);
            int peer;
            bool dig = I.DigestGate(digest, snap.G, snap.K, 1, peers, out peer);
            x.P("late_digest match=" + B01(dig) + " peer=" + I2S(peer));
            bool seed = snap.Seed == derivedSeed;
            if (!seed)
                x.P("seq_mismatch");
            bool scale = snap.Scale == appliedScale;
            x.P("late_scale match=" + B01(scale));
            bool late = I.MaySpawn(true, false, false, true, dig, seed, scale, callInCame);
            bool arrival = I.MaySpawn(false, false, false, true, dig, seed, scale, callInCame);
            x.P("spawn late=" + B01(late) + " arrival=" + B01(arrival));
            return late || arrival;
        }

        private static void K33Case(Impl I, Ctx x, int which)
        {
            const int g = 2, k = 3;
            const string level = "L07";
            const string seed = "seq-2-3";
            var room = RoomSlots(0, 0);
            var peerView = RoomSlots(0, 1);     // a peer's own copy: its kill tally differs, nothing else
            var forged = RoomSlots(1, 0);       // self-consistent, but not the room's state
            string roomBd = PeerBdOf(I, g, k, level, peerView);
            string forgedBd = PeerBdOf(I, g, k, level, forged);
            var forgedSnap = new Snap { G = g, K = k, Level = level, Slots = forged, Seed = seed, Scale = 5 };
            var goodSnap = new Snap { G = g, K = k, Level = level, Slots = room, Seed = seed, Scale = 5 };
            switch (which)
            {
                case 1:
                {
                    var peers = new List<PeerBd>
                    {
                        new PeerBd { Actor = 1, Slot = 0, IsMaster = true, Kept = true, Bd = forgedBd },
                        new PeerBd { Actor = 2, Slot = 1, Kept = true, Bd = null },
                        new PeerBd { Actor = 3, Slot = 2, Kept = true, Bd = null },
                    };
                    x.Ok(!LateSpawnCheck(I, x, forgedSnap, peers, seed, 5, false),
                         "i: no spawn while no non-master kept peer has published a cr_bd for (g, k)");
                    break;
                }
                case 2:
                {
                    var one = new List<PeerBd>
                    {
                        new PeerBd { Actor = 1, Slot = 0, IsMaster = true, Kept = true, Bd = forgedBd },
                        new PeerBd { Actor = 2, Slot = 1, Kept = true, Bd = roomBd },
                    };
                    x.Ok(!LateSpawnCheck(I, x, forgedSnap, one, seed, 5, false),
                         "ii: no spawn on one non-master kept peer's differing cr_bd");
                    var two = new List<PeerBd>
                    {
                        new PeerBd { Actor = 1, Slot = 0, IsMaster = true, Kept = true, Bd = forgedBd },
                        new PeerBd { Actor = 2, Slot = 1, Kept = true, Bd = forgedBd },
                        new PeerBd { Actor = 3, Slot = 2, Kept = true, Bd = roomBd },
                    };
                    x.Ok(!LateSpawnCheck(I, x, forgedSnap, two, seed, 5, false),
                         "ii: no spawn while any published kept peer differs");
                    break;
                }
                case 3:
                {
                    var peers = new List<PeerBd>
                    {
                        new PeerBd { Actor = 1, Slot = 0, IsMaster = true, Kept = true, Bd = forgedBd },
                        new PeerBd { Actor = 4, Slot = 3, Kept = false, Bd = forgedBd },
                        new PeerBd { Actor = 2, Slot = 1, Kept = true, Bd = null },
                    };
                    x.Ok(!LateSpawnCheck(I, x, forgedSnap, peers, seed, 5, false),
                         "iii: neither the master's own cr_bd nor an unkept peer's counts");
                    break;
                }
                case 4:
                {
                    var peers = new List<PeerBd>
                    {
                        new PeerBd { Actor = 1, Slot = 0, IsMaster = true, Kept = true, Bd = roomBd },
                        new PeerBd { Actor = 3, Slot = 2, Kept = true, Bd = roomBd },
                        new PeerBd { Actor = 2, Slot = 1, Kept = true, Bd = roomBd },
                        new PeerBd { Actor = 5, Slot = 4, Kept = true, Bd = null },
                    };
                    x.Ok(LateSpawnCheck(I, x, goodSnap, peers, seed, 5, false), "iv: the valid case spawns");
                    x.Ok(!LateSpawnCheck(I, x, goodSnap, peers, seed, 5, true),
                         "iv: no late spawn once this boundary's call-in has come");
                    x.Ok(!LateSpawnCheck(I, x, goodSnap, peers, "seq-other", 5, false),
                         "iv: no late spawn on a seed mismatch");
                    break;
                }
                case 5:
                {
                    bool a = I.MaySpawn(false, true, false, false, false, false, false, false);
                    bool b = I.MaySpawn(false, false, true, false, false, false, false, false);
                    bool c = I.MaySpawn(false, false, false, true, true, true, true, false);
                    x.P("arrival start_ok=" + B01(a) + " state_a=" + B01(b) + " snapshot=" + B01(c));
                    x.Ok(a && b, "v: a start_ok or an in-window state-A answer permits the arrival spawn");
                    x.Ok(!c, "v: a snapshot alone never opens the arrival gate");
                    break;
                }
                default:
                {
                    var peers = new List<PeerBd> { new PeerBd { Actor = 2, Slot = 1, Kept = true, Bd = roomBd } };
                    x.Ok(!LateSpawnCheck(I, x, goodSnap, peers, seed, 7, false),
                         "vi: no spawn when the snapshot's scale differs from the count this seat applied");
                    x.Ok(LateSpawnCheck(I, x, goodSnap, peers, seed, 5, false), "vi: the equal scale spawns");
                    break;
                }
            }
        }

        private static void K44Case(Impl I, Ctx x)
        {
            var baseSlots = RoomSlots(0, 0);
            string d0 = I.BoundaryDigest(2, 3, "L07", baseSlots);
            x.P("digest " + d0);
            x.Ok(d0 == I.BoundaryDigest(2, 3, "L07", RoomSlots(0, 5)), "kills never move the digest");
            x.Ok(d0 != I.BoundaryDigest(3, 3, "L07", baseSlots), "g moves the digest");
            x.Ok(d0 != I.BoundaryDigest(2, 4, "L07", baseSlots), "k moves the digest");
            x.Ok(d0 != I.BoundaryDigest(2, 3, "L08", baseSlots), "the levelId moves the digest");
            x.Ok(d0 != I.BoundaryDigest(2, 3, "L07", RoomSlots(1, 0)), "a slot's rounds move the digest");
            var pts = RoomSlots(0, 0);
            pts[1].Points = 1;
            x.Ok(d0 != I.BoundaryDigest(2, 3, "L07", pts), "a slot's points move the digest");
            var tot = RoomSlots(0, 0);
            tot[2].PointsTotal = 9;
            x.Ok(d0 != I.BoundaryDigest(2, 3, "L07", tot), "a slot's point total moves the digest");
            var cards = RoomSlots(0, 0);
            cards[3].Cards.Add("Grow");
            x.Ok(d0 != I.BoundaryDigest(2, 3, "L07", cards),
                 "an absent slot's recorded automatic pick moves the digest");
            var rev = RoomSlots(0, 0);
            rev.Reverse();
            x.Ok(d0 == I.BoundaryDigest(2, 3, "L07", rev), "the digest is taken in slot order");
        }

        // ---------------------------------------------------------------- K42: the positional pairing, fixtures a, d and e

        private static void K42Pair(Impl I, Ctx x)
        {
            var idx = I.PairIndices(new[] { true, false, true });
            x.P("pair_indices " + Ints(idx));
            x.Ok(idx != null && idx.Length == 3 && idx[0] == 0 && idx[1] == -1 && idx[2] == 1,
                 "pair: [kept, quarantined, kept] maps to [0, -1, 1]");
        }

        private static void K42a(Impl I, Ctx x)
        {
            // own actor 6 holds no grant; the grant set names 3 (kind s) and 2 (kind l)
            var grants = new List<GrantEntry> { new GrantEntry(0, 3, 's'), new GrantEntry(1, 2, 'l') };
            var present = new List<int> { 1, 2, 3, 6 };
            var rec = new EpochRecord();
            foreach (bool listTrigger in new[] { true, false })
            {
                // the trigger: a non-empty granted list that does not name it, or game_in_progress: true
                var gv = I.GateValue(true, true, false, true, true, true, false);
                x.P("gate state=" + GateName(gv.State) + " src=" + gv.Src + " list=" + B01(listTrigger));
                var gr = listTrigger ? grants : new List<GrantEntry>();
                bool anyKept = false, anyMaster = false;
                foreach (int a in present)
                {
                    anyKept |= I.KeptActorTest(gv.State, false, a, gr, rec, 0);
                    anyMaster |= I.MasterKeptTest(gv.State, false, listTrigger, a, gr, rec, 0);
                }
                x.Ok(!anyKept, "a: IsKeptActor is false for every actor, so KeptPlayers() is empty");
                x.Ok(!I.KeptActorTest(gv.State, false, 6, gr, rec, 0), "a: LocalSitsOut() holds");
                x.Ok(!anyMaster, "a: MasterKept() is false for every master");
            }
            var f1 = I.FenceTarget(6, present, grants, false, a => false, a => false, false);
            x.P("master_fence to=" + I2S(f1.To) + " why=" + f1.Why);
            x.Ok(f1.To == 3 && f1.Why == "no_grant",
                 "a: FenceTarget returns the lowest present actor the grant set names, kind s first");
            var others = new List<int> { 1, 4, 6 };
            var f2 = I.FenceTarget(6, others, grants, false, a => false, a => false, false);
            x.P("master_fence to=" + I2S(f2.To) + " why=" + f2.Why);
            x.Ok(f2.To == 1 && f2.Why == "no_grant_next",
                 "a: with none named present, the next present actor above its own, wrapping");
            var f3 = I.FenceTarget(6, others, grants, false, a => false, a => false, true);
            x.Ok(f3.To == -1, "a: the no_grant_next hand-off happens once per entry");
            var pre = I.GateValue(true, true, false, true, false, true, false);
            x.P("gate state=" + GateName(pre.State) + " src=" + pre.Src);
            x.Ok(pre.State == Gate.Pre, "a: a post-entry asm_started 0 with no trigger reads pre");
            x.Ok(I.MasterKeptTest(pre.State, false, true, 3, grants, rec, 0),
                 "a: in pre, MasterKept() holds for a kind-s master of its grant set");
            x.Ok(I.MasterKeptTest(pre.State, false, false, 1, new List<GrantEntry>(), rec, 0),
                 "a: in pre, MasterKept() holds with no granted list read");
        }

        private static void K42d(Impl I, Ctx x)
        {
            var grants = new List<GrantEntry>
            {
                new GrantEntry(0, 1, 's'), new GrantEntry(1, 2, 's'), new GrantEntry(4, 5, 'l'),
            };
            var rec = new EpochRecord();
            var g0 = I.GateValue(false, false, false, false, false, true, false);
            x.P("gate state=" + GateName(g0.State) + " src=" + g0.Src);
            x.Ok(g0.State == Gate.Started && g0.Src == "default", "d: no statement reads started (src=default)");
            bool any = false;
            foreach (int a in new[] { 1, 2, 5, 7 })
                any |= I.KeptActorTest(g0.State, false, a, grants, rec, 0);
            x.Ok(!any, "d: IsKeptActor is false for every actor while it holds no grant");
            x.Ok(!I.KeptActorTest(g0.State, false, 7, grants, rec, 0), "d: LocalSitsOut() holds");
            x.Ok(!I.MasterKeptTest(g0.State, false, true, 5, grants, rec, 0),
                 "d: MasterKept() is false for an unkept master");
            var g1 = I.GateValue(true, true, false, false, false, true, false);
            x.P("gate state=" + GateName(g1.State) + " src=" + g1.Src);
            x.Ok(g1.State == Gate.Started, "d: a statement received before the entry leaves it started");
            var g2 = I.GateValue(true, true, false, true, false, true, false);
            x.P("gate state=" + GateName(g2.State) + " src=" + g2.Src);
            x.Ok(g2.State == Gate.Pre && g2.Src == "statement",
                 "d: a post-entry asm_started 0 with no trigger reads pre (src=statement)");
            var g3 = I.GateValue(true, true, false, true, true, true, false);
            x.P("gate state=" + GateName(g3.State) + " src=" + g3.Src);
            x.Ok(g3.State == Gate.Started && g3.Src == "trigger",
                 "d: a trigger reads started for good (src=trigger), a later asm_started 0 included");
            x.Ok(I.GateValue(true, false, false, true, false, true, false).State == Gate.Ungated,
                 "d: assembly 0 reads ungated");
            x.Ok(I.GateValue(true, true, false, true, false, true, true).State == Gate.Ungated,
                 "d: a spectator reads ungated");
            x.Ok(I.GateValue(true, true, false, true, false, false, false).State == Gate.Ungated,
                 "d: an inactive engine reads ungated");
        }

        private sealed class Loader
        {
            internal readonly List<ScaleRecord> Records = new List<ScaleRecord>();
            internal int Master;
            internal int Latch = -1;
            internal bool Holding;
            internal int HoldG;
            internal int HoldK;
            internal int Loaded = -2;
            internal string LastWhy;
            internal bool Lag;
            internal string LagWhy;
            internal int UsedG = -1;
            internal int UsedK = -1;
            internal int UsedCount = -1;
        }

        private static void LoaderLag(Ctx x, Loader c, string why)
        {
            c.Lag = true;
            c.LagWhy = why;
            x.P("lag_out why=" + why);
        }

        /// <summary>EVT_SCALE at its dispatch: recorded only from the current
        /// master or the point's LatchMaster that the kept view accepts then.</summary>
        private static void ScaleRx(Impl I, Ctx x, Loader c, int from, int g, int k, int count,
                                    bool keptAtDispatch, bool confirmed)
        {
            string why = I.ScaleRecord(Lobby8, Lobby8, from, c.Master, c.Latch,
                                       I.ScaleJudgeAtLoad || keptAtDispatch);
            if (why != null)
            {
                x.P("scale_refused why=" + why + " from=" + I2S(from));
                return;
            }
            var rec = new ScaleRecord { Game = g, K = k, Count = count, From = from, Confirmed = confirmed };
            if (ScaleLate(c.UsedG, c.UsedK, c.UsedCount, rec))
            {
                x.P("scale_late g=" + I2S(g) + " k=" + I2S(k) + " count=" + I2S(count));
                if (!c.Lag)
                    LoaderLag(x, c, "scale_late");
                return;
            }
            c.Records.Add(rec);
            x.P("scale_rx g=" + I2S(g) + " k=" + I2S(k) + " count=" + I2S(count) + " from=" + I2S(from));
            if (c.Holding && c.HoldG == g && c.HoldK == k)
                ScaleLoad(I, x, c, g, k, a => true, true);
        }

        /// <summary>The load gate's count: the key's confirmed record, else a
        /// hold of at most ASM_STAMP_WAIT_S for one on its way, else unscaled
        /// (and LAG_OUT since V11). Every key at or below it is consumed.</summary>
        private static void ScaleLoad(Impl I, Ctx x, Loader c, int g, int k, Func<int, bool> keptAtLoad,
                                      bool fromHold)
        {
            List<ScaleRecord> use = c.Records;
            if (I.ScaleJudgeAtLoad)
                use = c.Records.FindAll(r => keptAtLoad(r.From));
            var d = I.ScaleDecision(use, g, k, true);
            if (d.Count >= 0)
            {
                c.Holding = false;
                c.Loaded = d.Count;
                c.LastWhy = null;
                c.UsedG = g; c.UsedK = k; c.UsedCount = d.Count;
                x.P("scale_apply g=" + I2S(g) + " k=" + I2S(k) + " count=" + I2S(d.Count));
                I.ConsumeScale(c.Records, g, k);
                return;
            }
            if (d.Why == "none" && !fromHold && !I.ScaleNoHold)
            {
                c.Holding = true;
                c.HoldG = g; c.HoldK = k;
                x.P("scale_hold g=" + I2S(g) + " k=" + I2S(k));
                return;
            }
            c.Holding = false;
            c.Loaded = -1;
            c.LastWhy = d.Why;
            x.P("scale_refused why=" + d.Why);
            I.ConsumeScale(c.Records, g, k);
            if (d.LagOut && !I.ScaleNoHold && !c.Lag)
                LoaderLag(x, c, "scale");
        }

        private static void ScaleHoldEnd(Impl I, Ctx x, Loader c)
        {
            if (c.Holding)
                ScaleLoad(I, x, c, c.HoldG, c.HoldK, a => true, true);
        }

        private static void ScaleSwitch(Impl I, Ctx x, Loader c, int to)
        {
            c.Master = to;
            if (I.ScaleClearAtSwitch)
                c.Records.Clear();
            x.P("master_switch to=" + I2S(to));
        }

        private static void K42e(Impl I, Ctx x)
        {
            var grants = new List<GrantEntry>
            {
                new GrantEntry(0, 1, 's'), new GrantEntry(1, 2, 's'), new GrantEntry(4, 5, 'l'),
            };
            var server = new List<EpochEntry> { new EpochEntry(3, 4), new EpochEntry(4, 5) };
            var rec = new EpochRecord { N = 2, Chain = ChainOf(Lobby8, server, 2), Entries = new List<EpochEntry>(server) };

            // an unkept current master U (5) raises {game 2, k 3, count 7}; U is kept by the load
            var c = new Loader { Master = 5 };
            ScaleRx(I, x, c, 5, 2, 3, 7, I.KeptSender(5, grants, rec, 1), true);
            c.Latch = 5;
            ScaleLoad(I, x, c, 2, 3, a => I.KeptSender(a, grants, rec, 2), false);
            ScaleHoldEnd(I, x, c);
            x.Ok(c.Loaded == -1, "e: the unkept master's count is refused at the dispatch and never loaded");
            x.Ok(c.Lag && c.LagWhy == "scale" && c.LastWhy == "none",
                 "e: a load whose count never arrives is unscaled in LAG_OUT (why=none, lag_out why=scale)");

            // a kept sender's record serves its key's load and is consumed
            c = new Loader { Master = 1, Latch = 1 };
            ScaleRx(I, x, c, 1, 2, 3, 5, true, true);
            ScaleLoad(I, x, c, 2, 3, a => true, false);
            x.Ok(c.Loaded == 5, "e: the record for (2, 3) serves the load for (2, 3)");
            ScaleLoad(I, x, c, 2, 4, a => true, false);
            ScaleHoldEnd(I, x, c);
            x.Ok(c.Loaded == -1 && c.LastWhy == "none",
                 "e: the record is consumed, so the next load with no fresh record is unscaled (why=none)");

            // a record for (2, 2) at the load for (2, 3)
            c = new Loader { Master = 1, Latch = 1 };
            ScaleRx(I, x, c, 1, 2, 2, 5, true, true);
            ScaleLoad(I, x, c, 2, 3, a => true, false);
            ScaleHoldEnd(I, x, c);
            x.Ok(c.Loaded == -1 && c.LastWhy == "stale", "e: a record for (2, 2) at the load for (2, 3) is stale");

            // a record taken before any granted list
            c = new Loader { Master = 1, Latch = 1 };
            ScaleRx(I, x, c, 1, 2, 3, 5, true, false);
            ScaleLoad(I, x, c, 2, 3, a => true, false);
            ScaleHoldEnd(I, x, c);
            x.Ok(c.Loaded == -1 && c.LastWhy == "unconfirmed",
                 "e: a record taken before any granted list is refused unconfirmed");
            c = new Loader { Master = 1, Latch = 1 };
            ScaleRx(I, x, c, 1, 2, 3, 5, true, false);
            foreach (var r in c.Records)
                if (IsKindS(r.From, grants))
                    r.Confirmed = true;
            x.P("granted_read confirms=" + I2S(c.Records.Count));
            ScaleLoad(I, x, c, 2, 3, a => true, false);
            x.Ok(c.Loaded == 5, "e: once a granted list names its sender kind s, it serves");

            // a master switch between the record and the load, in either order
            foreach (bool countFirst in new[] { true, false })
            {
                c = new Loader { Master = 1, Latch = 1 };
                if (countFirst)
                {
                    ScaleRx(I, x, c, 1, 2, 3, 5, true, true);
                    ScaleSwitch(I, x, c, 2);
                }
                else
                {
                    ScaleSwitch(I, x, c, 2);
                    ScaleRx(I, x, c, 1, 2, 3, 5, true, true);
                }
                ScaleLoad(I, x, c, 2, 3, a => true, false);
                ScaleHoldEnd(I, x, c);
                x.Ok(c.Loaded == 5, "e: the load uses LatchMaster's record whichever order the switch and the count take");
            }

            // a count on its way: the load holds, and one arriving inside the hold serves
            c = new Loader { Master = 1, Latch = 1 };
            ScaleLoad(I, x, c, 2, 3, a => true, false);
            ScaleRx(I, x, c, 1, 2, 3, 5, true, true);
            ScaleHoldEnd(I, x, c);
            x.Ok(c.Loaded == 5 && !c.Lag, "e: a count that arrives within the hold serves the load");

            // two confirmed records that differ for one key
            c = new Loader { Master = 1, Latch = 1 };
            ScaleRx(I, x, c, 1, 2, 3, 5, true, true);
            ScaleSwitch(I, x, c, 2);
            ScaleRx(I, x, c, 2, 2, 3, 6, true, true);
            ScaleLoad(I, x, c, 2, 3, a => true, false);
            x.Ok(c.Loaded == -1 && c.LastWhy == "conflict" && c.Lag,
                 "e: two confirmed records that differ load unscaled in LAG_OUT");

            // a record that differs from the count a load already used
            c = new Loader { Master = 1, Latch = 1 };
            ScaleRx(I, x, c, 1, 2, 3, 5, true, true);
            ScaleLoad(I, x, c, 2, 3, a => true, false);
            ScaleSwitch(I, x, c, 2);
            ScaleRx(I, x, c, 2, 2, 3, 6, true, true);
            x.Ok(c.Loaded == 5 && c.Lag && c.LagWhy == "scale_late",
                 "e: a later record that differs from the used count starts LAG_OUT (why=scale_late)");

            x.Ok(ScaleTag(2, 3, 5, 1) == "2:3:5:1", "e: the snapshot's scale carries (g, k, count, sender)");
        }

        // ---------------------------------------------------------------- K45: the simulated room

        private sealed class Cl
        {
            internal string Name;
            internal int Actor;
            internal char Kind;
            internal bool Gone;
            internal bool ReadGranted = true;
            internal EpochRecord Rec = new EpochRecord();
            internal int Applied;
            internal string AppliedChain = "0";
            internal int Point;
            internal int LastPair = -1;
            internal bool PairedAny;
            internal bool Acked;
            internal readonly List<Stamp> Held = new List<Stamp>();
            internal readonly List<int> HeldAt = new List<int>();
            internal int CallIn = -1;
            internal bool Holding;
            internal bool Decided;
            internal PairResult Decision;
            internal Stamp PairedStamp;
            internal bool Lag;
            internal bool LagAtLoad;
            internal int LagG = -1;
            internal int LagK = -1;
            internal string LagWhy;
            internal string CrLag;
            internal readonly HashSet<int> LagGames = new HashSet<int>();
            internal readonly HashSet<int> LagPosts = new HashSet<int>();
            internal int Deaths;
            internal readonly List<int> Present = new List<int>();
            internal int SeenMaster;
            internal int Signalled = -1;
            internal string EpochRefusal;
            internal string StampRefusal;
            internal int Superseded;
            internal readonly List<Proposal> Acks = new List<Proposal>();

            internal bool HoldsGrant { get { return Kind == 's' || Kind == 'l'; } }
        }

        private sealed class Sim
        {
            internal readonly Impl I;
            internal readonly Ctx X;
            internal int G = 1;
            internal int K = 1;
            internal readonly List<EpochEntry> Server = new List<EpochEntry>();
            internal readonly List<GrantEntry> Grants = new List<GrantEntry>();
            internal readonly SortedDictionary<int, Cl> All = new SortedDictionary<int, Cl>();
            internal readonly Dictionary<int, int> Ready = new Dictionary<int, int>();
            internal int Master = 1;
            internal List<int> LastMissing = new List<int>();
            internal readonly HashSet<int> EverMissing = new HashSet<int>();
            internal int Commits;

            internal Sim(Impl i, Ctx x) { I = i; X = x; }

            internal Cl Add(string name, int actor, char kind, int slot)
            {
                var c = new Cl { Name = name, Actor = actor, Kind = kind, SeenMaster = Master };
                if (kind == 's' || kind == 'l')
                    Grants.Add(new GrantEntry(slot, actor, kind));
                if (kind == 'l')
                    Server.Add(new EpochEntry(slot, actor));
                foreach (var o in All.Values)
                {
                    o.Present.Add(actor);
                    o.Present.Sort();
                    c.Present.Add(o.Actor);
                }
                c.Present.Add(actor);
                c.Present.Sort();
                All[actor] = c;
                return c;
            }

            internal Cl this[int actor] { get { return All[actor]; } }

            internal void P(Cl c, string line) { X.P(c.Name + " " + line); }

            internal List<Cl> Others(Cl m)
            {
                var l = new List<Cl>();
                foreach (var c in All.Values)
                    if (!c.Gone && c != m)
                        l.Add(c);
                return l;
            }

            internal List<Cl> Live()
            {
                var l = new List<Cl>();
                foreach (var c in All.Values)
                    if (!c.Gone)
                        l.Add(c);
                return l;
            }

            internal void Answer(Cl c, int n)
            {
                var entries = Server.GetRange(0, n);
                string chain = ChainOf(Lobby8, entries, n);
                string d = I.RecordDecision(c.Rec, Lobby8, n, chain, entries);
                if (d == "rx")
                {
                    c.Rec = new EpochRecord { N = n, Chain = chain, Entries = new List<EpochEntry>(entries) };
                    P(c, "epoch_rx n=" + I2S(n));
                }
                else if (d == "bad")
                    P(c, "epoch_bad n=" + I2S(n));
            }

            /// <summary>A state reached before the fixture starts: epoch n
            /// applied and paired, its last pairing with the current master.</summary>
            internal void Prior(Cl c, int n)
            {
                if (c.Rec.N < n)
                    Answer(c, n);
                c.Applied = n;
                c.Point = n;
                c.AppliedChain = ChainOf(Lobby8, c.Rec.Entries, n) ?? "0";
                c.LastPair = Master;
                c.PairedAny = true;
            }

            internal void SetMaster(Cl m)
            {
                Master = m.Actor;
                foreach (var c in All.Values)
                    c.SeenMaster = m.Actor;
            }

            internal bool KeptOn(Cl c, int a)
            {
                return I.KeptActorTest(Gate.Started, c.HoldsGrant, a, Grants, c.Rec, c.Point);
            }

            internal bool Fenced(Cl m)
            {
                bool mk = I.MasterKeptTest(Gate.Started, m.HoldsGrant, m.ReadGranted, m.Actor, Grants, m.Rec, m.Point);
                return MasterFencedValue(mk, m.Lag);
            }

            internal void Signal(Cl c)
            {
                if (c.Gone || !c.HoldsGrant)
                    return;
                int peerMax = 0;
                foreach (var kv in Ready)
                    if (kv.Key != c.Actor && kv.Value > peerMax)
                        peerMax = kv.Value;
                int r = I.ReadyEpoch(c.Rec, c.Present, c.Present, peerMax);
                if (r > 0 && r != c.Signalled)
                {
                    c.Signalled = r;
                    Ready[c.Actor] = r;
                    P(c, "ready n=" + I2S(r));
                }
            }

            internal void SignalAll()
            {
                foreach (var c in All.Values)
                    Signal(c);
            }

            internal Proposal? Propose(Cl m)
            {
                m.Acks.Clear();
                if (Fenced(m))
                {
                    P(m, "propose_skip fenced=1");
                    return null;
                }
                int selfReady = I.ReadyEpoch(m.Rec, m.Present, m.Present, 0);
                int nStar = I.BarrierEpoch(m.Rec, Grants, m.Present, Ready, m.Actor, selfReady);
                int basis = I.ProposeAgainstApplied ? m.Applied : m.Point;
                if (!I.MayPropose(nStar, basis, IsKindS(m.Actor, Grants)))
                    return null;
                P(m, "epoch_propose n=" + I2S(nStar));
                return new Proposal
                {
                    Lobby8 = Lobby8, N = nStar, Chain = ChainOf(Lobby8, m.Rec.Entries, nStar), G = G, K = K,
                    From = m.Actor,
                };
            }

            internal void OnEpoch(Cl c, Proposal p)
            {
                if (c.Gone || !c.HoldsGrant)
                    return;
                int dm = c.SeenMaster;
                bool mk = I.MasterKeptTest(Gate.Started, c.HoldsGrant, c.ReadGranted, dm, Grants, c.Rec, c.Point);
                string why = I.ValidateEpoch(p, dm, mk, Lobby8, c.Rec, c.Applied, c.AppliedChain, G, K, true,
                                             c.Present);
                if (why != null)
                {
                    c.EpochRefusal = why;
                    P(c, "epoch_refused why=" + why + " n=" + I2S(p.N) + " from=" + I2S(p.From));
                    return;
                }
                c.Acked = true;
                P(c, "epoch_ack n=" + I2S(p.N));
                Cl m;
                if (All.TryGetValue(p.From, out m) && !m.Gone)
                {
                    var ack = p;
                    ack.From = c.Actor;
                    m.Acks.Add(ack);
                }
                if (I.ApplyAtProposal)
                {
                    c.Applied = Math.Max(c.Applied, p.N);
                    c.Point = Math.Max(c.Point, p.N);
                    c.AppliedChain = ChainOf(Lobby8, c.Rec.Entries, c.Applied) ?? "0";
                }
            }

            internal Stamp StampOf(Cl m, Proposal? p)
            {
                bool complete = false;
                List<int> missing = new List<int>();
                int nStar = p.HasValue ? p.Value.N : 0;
                if (p.HasValue)
                    complete = I.AckComplete(BarrierSet(m.Rec, Grants, nStar), m.Present, m.Acks, p.Value, m.Actor,
                                             out missing);
                string result;
                int n;
                bool apply;
                I.StampDecision(p.HasValue, nStar, complete, m.Point, out result, out n, out apply);
                LastMissing = missing ?? new List<int>();
                foreach (int a in LastMissing)
                    EverMissing.Add(a);
                if (result == "unacked")
                    P(m, "epoch_unacked n=" + I2S(nStar) + " missing={" + Ints(LastMissing) + "}");
                if (apply)
                {
                    Commits++;
                    m.Applied = Math.Max(m.Applied, n);
                    m.Point = n;
                    m.AppliedChain = ChainOf(Lobby8, m.Rec.Entries, m.Applied) ?? "0";
                    P(m, "kept src=epoch n=" + I2S(n));
                }
                else
                    P(m, "kept src=carry n=" + I2S(m.Point));
                m.LastPair = m.Actor;
                m.PairedAny = true;
                m.CallIn = m.Actor;
                m.Decided = true;
                P(m, "stamp_tx result=" + result + " n=" + I2S(n));
                return new Stamp
                {
                    Lobby8 = Lobby8, G = G, K = K, N = n, Chain = ChainOf(Lobby8, m.Rec.Entries, n),
                    Result = result, From = m.Actor,
                };
            }

            /// <summary>A client that took the master role: whatever it holds
            /// from another sender is dropped at its own call-in.</summary>
            internal void TakeOver(Cl m)
            {
                foreach (var s in m.Held)
                    if (s.From != m.Actor)
                        P(m, "stamp_superseded from=" + I2S(s.From) + " callin=" + I2S(m.Actor));
                m.Held.Clear();
                m.HeldAt.Clear();
            }

            private string StampWhy(Cl c, Stamp s, int callIn)
            {
                bool ks = I.KeptSender(s.From, Grants, c.Rec, c.Point);
                return I.ValidateStamp(s, callIn, ks, IsKindS(s.From, Grants), Lobby8, c.Rec, c.Applied,
                                       c.AppliedChain, G, K, true);
            }

            internal void OnStamp(Cl c, Stamp s)
            {
                if (c.Gone || !c.HoldsGrant)
                    return;
                if (c.CallIn < 0)
                {
                    c.Held.Add(s);
                    c.HeldAt.Add(c.SeenMaster);
                    return;
                }
                int accept = c.CallIn;
                if (I.DispatchMasterStamp && s.From == c.SeenMaster)
                    accept = s.From;
                string why = StampWhy(c, s, accept);
                if (why != null)
                {
                    c.StampRefusal = why;
                    P(c, "stamp_refused why=" + why + " from=" + I2S(s.From));
                    return;
                }
                if (c.Holding)
                {
                    P(c, "stamp_rx waited_ms=1000");
                    Pair(c, s);
                    return;
                }
                if (c.Decided)
                {
                    P(c, "stamp_rx late=1 from=" + I2S(s.From));
                    var r = LateStampDecision(c.Decision, c.PairedStamp, s);
                    if (r.Kind == PairKind.LagOut && !c.Lag)
                        StartLag(c, r.Why, false);
                }
            }

            internal void OnCallIn(Cl c, int from)
            {
                if (c.Gone || !c.HoldsGrant)
                    return;
                c.CallIn = from;
                Stamp mine = null;
                bool conflict = false;
                for (int i = 0; i < c.Held.Count; i++)
                {
                    var s = c.Held[i];
                    int accept = from;
                    if (I.DispatchMasterStamp && s.From == c.HeldAt[i])
                        accept = s.From;
                    if (s.From != accept)
                    {
                        c.Superseded++;
                        P(c, "stamp_superseded from=" + I2S(s.From) + " callin=" + I2S(from));
                        continue;
                    }
                    string why = StampWhy(c, s, accept);
                    if (why != null)
                    {
                        c.StampRefusal = why;
                        P(c, "stamp_refused why=" + why + " from=" + I2S(s.From));
                        continue;
                    }
                    if (mine == null)
                        mine = s;
                    else if (!mine.SameAs(s))
                        conflict = true;
                }
                c.Held.Clear();
                c.HeldAt.Clear();
                if (conflict)
                {
                    Settle(c, I.PairDecision(mine, true, from, c.LastPair, c.Acked, c.Point, c.Applied, c.Rec), null);
                    return;
                }
                if (mine != null)
                {
                    P(c, "stamp_rx waited_ms=0");
                    Pair(c, mine);
                    return;
                }
                if (I.NoHold)
                {
                    Settle(c, new PairResult { Kind = PairKind.Carry, PointEpoch = c.Point, EpochApplied = c.Applied },
                           null);
                    return;
                }
                c.Holding = true;
                P(c, "callin_hold from=" + I2S(from));
            }

            internal void HoldEnd(Cl c)
            {
                if (c.Gone || !c.HoldsGrant || !c.Holding)
                    return;
                c.Holding = false;
                Settle(c, I.PairDecision(null, false, c.CallIn, c.LastPair, c.Acked, c.Point, c.Applied, c.Rec), null);
            }

            private void Pair(Cl c, Stamp s)
            {
                Settle(c, I.PairDecision(s, false, c.CallIn, c.LastPair, c.Acked, c.Point, c.Applied, c.Rec), s);
            }

            private void Settle(Cl c, PairResult r, Stamp s)
            {
                c.Holding = false;
                c.Decided = true;
                c.Decision = r;
                c.PairedStamp = s;
                switch (r.Kind)
                {
                    case PairKind.Apply:
                    case PairKind.Carry:
                    case PairKind.CarryDown:
                        c.Point = r.PointEpoch;
                        c.Applied = r.EpochApplied;
                        c.AppliedChain = ChainOf(Lobby8, c.Rec.Entries, c.Applied) ?? "0";
                        P(c, r.Kind == PairKind.Apply ? "kept src=epoch n=" + I2S(c.Point)
                             : (r.Kind == PairKind.Carry ? "kept src=carry n=" + I2S(c.Point)
                                : "kept src=carry down=1 n=" + I2S(c.Point)));
                        break;
                    case PairKind.StampLate:
                        P(c, "stamp_late n=" + I2S(c.Point));
                        break;
                    case PairKind.LagOut:
                        StartLag(c, r.Why, false);
                        c.LastPair = -1;
                        return;
                }
                c.LastPair = c.CallIn;
                c.PairedAny = true;
                if (c.Lag && s != null && I.LagOutEnds("callin", c.LagAtLoad && c.LagG == G && c.LagK == K))
                    EndLag(c, "callin");
            }

            internal void StartLag(Cl c, string why, bool atLoad)
            {
                if (!c.Lag)
                {
                    c.Lag = true;
                    c.LagAtLoad = atLoad;
                    c.LagG = G;
                    c.LagK = K;
                }
                c.LagWhy = why;
                c.Deaths++;
                c.CrLag = LagValue(Lobby8, G, K);
                c.LagGames.Add(G);
                P(c, "lag_out why=" + why + " g=" + I2S(G) + " k=" + I2S(K) + " dies=1 credit=0");
                if (c.LagPosts.Add(G))
                    P(c, "lag_post g=" + I2S(G));
            }

            internal void EndLag(Cl c, string why)
            {
                if (!c.Lag)
                    return;
                c.Lag = false;
                c.CrLag = null;
                P(c, "lag_out_end why=" + why);
            }

            internal void DispatchLeave(Cl at, Cl who)
            {
                at.Present.Remove(who.Actor);
                if (at.SeenMaster == who.Actor)
                    at.SeenMaster = Master;
            }

            internal void Leave(Cl who, int newMaster)
            {
                who.Gone = true;
                if (Master == who.Actor && newMaster > 0)
                    Master = newMaster;
            }

            internal void LeaveAll(Cl who, int newMaster)
            {
                Leave(who, newMaster);
                foreach (var c in All.Values)
                    if (!c.Gone)
                        DispatchLeave(c, who);
            }

            private void ResetPoint()
            {
                foreach (var c in All.Values)
                {
                    c.Acked = false;
                    c.CallIn = -1;
                    c.Holding = false;
                    c.Decided = false;
                    c.PairedStamp = null;
                    c.Held.Clear();
                    c.HeldAt.Clear();
                    c.Acks.Clear();
                }
            }

            internal void NextPoint()
            {
                K++;
                ResetPoint();
            }

            internal void NextGame(int startMaster, bool firstOfSitting)
            {
                foreach (var c in All.Values)
                    if (!c.Gone && c.Lag && I.LagOutEnds("game_end", false))
                        EndLag(c, "game_end");
                G++;
                K = 1;
                ResetPoint();
                foreach (var c in All.Values)
                {
                    if (c.Gone)
                        continue;
                    c.LastPair = LastPairAtGameStart(c.LastPair, c.PairedAny, firstOfSitting, startMaster);
                    if (c.Lag)
                    {
                        c.LagGames.Add(G);
                        c.CrLag = LagValue(Lobby8, G, K);
                        P(c, "lag_game g=" + I2S(G));
                        if (c.LagPosts.Add(G))
                            P(c, "lag_post g=" + I2S(G));
                    }
                }
            }

            internal int[] Indices(Cl c)
            {
                var flags = new bool[c.Present.Count];
                for (int i = 0; i < flags.Length; i++)
                    flags[i] = KeptOn(c, c.Present[i]);
                return I.PairIndices(flags);
            }

            /// <summary>The fixture-wide assertion (K45): every compliant client
            /// whose own actor is kept and which is not in LAG_OUT keeps the
            /// call-in master's set; a late seat not yet kept keeps a prefix of
            /// it and sits out; one in LAG_OUT plays nothing of the point.</summary>
            internal void Check(Cl m, string tag)
            {
                foreach (var c in All.Values)
                {
                    if (c.Gone || !c.HoldsGrant || c == m || c.Lag)
                        continue;
                    if (KeptOn(c, c.Actor))
                        X.Ok(c.Point == m.Point, tag + ": " + c.Name + " keeps the call-in master's set");
                    else
                        X.Ok(c.Point <= m.Point, tag + ": " + c.Name + " keeps a prefix of it and sits out");
                }
            }

            internal void StdPoint(Cl m, string tag)
            {
                var p = Propose(m);
                var others = Others(m);
                if (p.HasValue)
                    foreach (var c in others)
                        OnEpoch(c, p.Value);
                var st = StampOf(m, p);
                foreach (var c in others)
                {
                    OnStamp(c, st);
                    OnCallIn(c, m.Actor);
                    HoldEnd(c);
                }
                Check(m, tag);
            }
        }

        /// <summary>M (1), A (2) and B (3) of kind s; L1 (4) and, when asked,
        /// L2 (5) of kind l, admitted as epochs 1 and 2. M is the master.</summary>
        private static Sim World(Impl I, Ctx x, bool withL2)
        {
            var s = new Sim(I, x);
            s.Add("M", 1, 's', 0);
            s.Add("A", 2, 's', 1);
            s.Add("B", 3, 's', 2);
            s.Add("L1", 4, 'l', 3);
            if (withL2)
                s.Add("L2", 5, 'l', 4);
            s.SetMaster(s[1]);
            return s;
        }

        // ---------------------------------------------------------------- K45 fixtures i to x

        private static void K45i(Impl I, Ctx x)
        {
            var s = World(I, x, false);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4];
            s.Answer(M, 1);
            s.Answer(A, 1);
            s.Answer(L1, 1);
            s.SignalAll();
            x.Ok(B.Signalled < 0, "i: B, whose own record lacks epoch 1, signals nothing");
            var p = s.Propose(M);
            x.Ok(!p.HasValue, "i: the barrier stays at 0 and the master proposes nothing");
            var st = s.StampOf(M, p);
            foreach (var c in s.Others(M))
            {
                s.OnStamp(c, st);
                s.OnCallIn(c, M.Actor);
                s.HoldEnd(c);
            }
            foreach (var c in s.Live())
                x.Ok(c.Point == 0, "i: every client carries (kept src=carry)");
            s.NextPoint();
            s.Answer(B, 1);
            s.Signal(B);
            x.Ok(B.Signalled == 1, "i: B signals once its own answer brings epoch 1");
            s.StdPoint(M, "i");
            foreach (var c in s.Live())
                x.Ok(c.Point == 1 && c.Applied == 1, "i: every client applies epoch 1");
        }

        private static void K45ii(Impl I, Ctx x)
        {
            var s = World(I, x, false);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4];
            s.Answer(M, 1);
            s.Answer(B, 1);
            s.Answer(L1, 1);
            s.Answer(A, 1);
            s.Answer(A, 0);
            x.Ok(A.Rec.N == 1, "ii: a delayed older answer carrying no epoch changes nothing; A keeps epoch 1");
            s.SignalAll();
            x.Ok(A.Signalled == 1, "ii: A signals epoch 1");
            s.StdPoint(M, "ii");
            foreach (var c in s.Live())
                x.Ok(c.Point == 1, "ii: A applies epoch 1 with every other client");
        }

        private static readonly string[] StampLeaveOrders = { "SXsc", "SsXc", "SscX", "sSXc", "sScX", "scSX" };

        private static void RunOrder(Sim s, Cl r, string order, Cl oldMaster, Stamp oldStamp, Cl newMaster,
                                     Stamp newStamp)
        {
            foreach (char e in order)
            {
                if (e == 'S') s.OnStamp(r, oldStamp);
                else if (e == 'X') s.DispatchLeave(r, oldMaster);
                else if (e == 's') s.OnStamp(r, newStamp);
                else s.OnCallIn(r, newMaster.Actor);
            }
            s.HoldEnd(r);
        }

        private static void K45iii(Impl I, Ctx x)
        {
            foreach (string order in StampLeaveOrders)
            {
                var s = World(I, x, true);
                Cl M = s[1], A = s[2], B = s[3], L1 = s[4], L2 = s[5];
                foreach (var c in s.All.Values)
                    s.Prior(c, 1);
                foreach (var c in s.All.Values)
                    s.Answer(c, 2);
                s.LeaveAll(L1, 0);
                s.SignalAll();
                var p = s.Propose(M);
                x.Ok(p.HasValue && p.Value.N == 2, "iii: the barrier reads present actors only, so epoch 2 is proposed");
                foreach (var c in s.Others(M))
                    s.OnEpoch(c, p.Value);
                x.Ok(A.Acked && B.Acked && L2.Acked,
                     "iii: every present member acknowledges epoch 2, L1's entry matching no body");
                var sM = s.StampOf(M, p);
                x.Ok(sM.Result == "commit", "iii: the master commits epoch 2");
                s.Leave(M, A.Actor);
                s.OnStamp(A, sM);
                s.DispatchLeave(A, M);
                s.TakeOver(A);
                var sA = s.StampOf(A, null);
                x.Ok(sA.Result == "carry" && sA.N == 1, "iii: the new master's own stamp names its PointEpoch");
                foreach (var r in new[] { B, L2 })
                    RunOrder(s, r, order, M, sM, A, sA);
                s.Check(A, "iii " + order);
                x.Ok(!B.Lag && B.Point == A.Point, "iii: B pairs the new master's own stamp (" + order + ")");
            }
            var grants = new List<GrantEntry>
            {
                new GrantEntry(0, 12, 's'), new GrantEntry(1, 13, 's'), new GrantEntry(2, 11, 'l'),
                new GrantEntry(3, 14, 's'),
            };
            var keptSet = new HashSet<int> { 11, 12, 13 };
            Func<int, bool> kept = a => keptSet.Contains(a);
            Func<int, bool> none = a => false;
            var f1 = I.FenceTarget(14, new List<int> { 10, 11, 12, 13, 14 }, grants, true, kept, none, false);
            x.P("master_fence to=" + I2S(f1.To) + " why=" + f1.Why);
            x.Ok(f1.To == 12, "iii: over present actors whose lowest is unkept, the lowest kept kind-s one");
            var f2 = I.FenceTarget(14, new List<int> { 10, 11, 14 }, grants, true, kept, none, false);
            x.P("master_fence to=" + I2S(f2.To) + " why=" + f2.Why);
            x.Ok(f2.To == 11, "iii: else the lowest kept one");
            var f3 = I.FenceTarget(14, new List<int> { 10, 11, 12, 14 }, grants, true, a => true, none, false);
            x.Ok(f3.To == 12, "iii: before the start, the lowest kind-s one");
            var f4 = I.FenceTarget(14, new List<int> { 10, 14 }, grants, true, kept, none, false);
            x.Ok(f4.To == -1, "iii: none when none is acceptable");
        }

        private static void K45iv(Impl I, Ctx x)
        {
            var s = World(I, x, true);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4], L2 = s[5];
            foreach (var c in s.All.Values)
                s.Prior(c, 1);
            foreach (var c in s.All.Values)
                s.Answer(c, 2);
            s.SignalAll();
            var p = s.Propose(M);
            x.Ok(p.HasValue, "iv: the master proposes epoch 2");
            foreach (var c in s.Others(M))
                s.OnEpoch(c, p.Value);
            var st = s.StampOf(M, p);
            x.Ok(st.Result == "commit" && st.N == 2, "iv: the master commits epoch 2");
            s.Leave(B, 0);
            int[] idxM = null;
            if (I.MasterPairsAtRaise)
                idxM = s.Indices(M);
            s.DispatchLeave(M, B);
            if (idxM == null)
                idxM = s.Indices(M);
            x.P("M pair_indices " + Ints(idxM));
            foreach (var r in new[] { A, L1, L2 })
            {
                s.DispatchLeave(r, B);
                s.OnStamp(r, st);
                s.OnCallIn(r, M.Actor);
                s.HoldEnd(r);
                var idx = s.Indices(r);
                x.P(r.Name + " pair_indices " + Ints(idx));
                x.Ok(SameInts(idx, idxM), "iv: PairIndices over the kept bodies is the same on every present client");
            }
            s.Check(M, "iv");
        }

        private static void K45v(Impl I, Ctx x)
        {
            var s = World(I, x, true);
            Cl M = s[1];
            Cl R = s.Add("R", 6, '-', 5);
            R.ReadGranted = false;
            R.SeenMaster = M.Actor;
            foreach (var c in s.All.Values)
                if (c.HoldsGrant)
                    s.Answer(c, 1);
            s.SignalAll();
            s.StdPoint(M, "v point 1");
            foreach (var c in s.All.Values)
                if (c.HoldsGrant)
                    x.Ok(c.Point == 1, "v: epoch 1 applies everywhere");
            s.NextPoint();
            foreach (var c in s.All.Values)
                if (c.HoldsGrant)
                    s.Answer(c, 2);
            s.SignalAll();
            s.StdPoint(M, "v point 2");
            foreach (var c in s.All.Values)
                if (c.HoldsGrant)
                    x.Ok(c.Point == 2 && c.Applied == 2, "v: epoch 2 applies everywhere, after epoch 1");
            x.Ok(s.Commits == 2, "v: both points commit, so R is never waited for");
            x.Ok(R.Signalled < 0 && !s.Ready.ContainsKey(R.Actor), "v: R sends no EVT_READY");
            x.Ok(!R.Acked && R.Point == 0 && R.EpochRefusal == null, "v: R ignores both events");
            x.Ok(!s.EverMissing.Contains(R.Actor), "v: no acknowledgement of R's is ever missing");
        }

        private static void K45vi(Impl I, Ctx x)
        {
            var s = World(I, x, true);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4], L2 = s[5];
            foreach (var c in s.All.Values)
                s.Prior(c, 1);
            s.Answer(A, 2);
            s.Answer(M, 2);
            s.Answer(L1, 2);
            s.Answer(L2, 2);
            s.SetMaster(L2);
            var rogue = new Proposal
            {
                Lobby8 = Lobby8, N = 2, Chain = ChainOf(Lobby8, L2.Rec.Entries, 2), G = s.G, K = s.K, From = L2.Actor,
            };
            s.P(L2, "epoch_propose n=2 barrier=0");
            s.OnEpoch(A, rogue);
            s.OnEpoch(B, rogue);
            x.Ok(A.EpochRefusal == "sender" && B.EpochRefusal == "sender",
                 "vi: A and B both refuse the candidate-listed master (why=sender)");
            foreach (var c in s.Live())
                x.Ok(c.Point == 1 && c.Applied == 1, "vi: no kept set changes");
            foreach (var c in s.Live())
                x.Ok(!I.MasterKeptTest(Gate.Started, c.HoldsGrant, true, L2.Actor, s.Grants, c.Rec, c.Point),
                     "vi: every client finds MasterKept() false for L2");
            var f = I.FenceTarget(L2.Actor, L2.Present, s.Grants, true, a => s.KeptOn(L2, a), a => false, false);
            s.P(L2, "master_fence to=" + I2S(f.To) + " why=" + f.Why);
            x.Ok(f.To == M.Actor, "vi: FenceTarget returns the lowest present kind-s actor");

            s.Answer(B, 2);
            s.SignalAll();
            s.SetMaster(L1);
            s.NextPoint();
            var pL1 = s.Propose(L1);
            x.Ok(!pL1.HasValue, "vi: L1, kept at epoch 1, raises nothing as master with the barrier for 2 met");
            var stL1 = s.StampOf(L1, pL1);
            foreach (var c in s.Others(L1))
            {
                s.OnStamp(c, stL1);
                s.OnCallIn(c, L1.Actor);
                s.HoldEnd(c);
            }
            foreach (var c in s.Live())
                x.Ok(c.Point == 1, "vi: every client carries (kept src=carry) under L1");

            s.SetMaster(M);
            s.NextPoint();
            s.StdPoint(M, "vi");
            foreach (var c in s.Live())
                x.Ok(c.Point == 2, "vi: a kind-s master's epoch 2 applies everywhere");
            foreach (var c in new[] { M, A, B, L1 })
            {
                var again = new Proposal
                {
                    Lobby8 = Lobby8, N = 2, Chain = ChainOf(Lobby8, L2.Rec.Entries, 2), G = s.G, K = s.K,
                    From = L2.Actor,
                };
                bool mk = I.MasterKeptTest(Gate.Started, true, true, L2.Actor, s.Grants, c.Rec, c.Point);
                string why = I.ValidateEpoch(again, L2.Actor, mk, Lobby8, c.Rec, c.Applied, c.AppliedChain, s.G, s.K,
                                             true, c.Present);
                x.Ok(why == null, "vi: once epoch 2 is applied, e1 passes for L2 as master on " + c.Name);
            }
        }

        private static void K45vii(Impl I, Ctx x)
        {
            var g = I.GateValue(false, false, false, false, false, true, false);
            x.P("R gate state=" + GateName(g.State) + " src=" + g.Src);
            x.Ok(g.State == Gate.Started, "vii: a restarted client with no statement reads the room as started");
            var noGrants = new List<GrantEntry>();
            var rec0 = new EpochRecord();
            x.Ok(!I.MasterKeptTest(g.State, false, false, 6, noGrants, rec0, 0),
                 "vii: R finds MasterKept() false for itself");
            var pair = new List<int> { 6, 7 };
            var handed = new Dictionary<int, bool> { { 6, false }, { 7, false } };
            int master = 6, moves = 0;
            for (int step = 0; step < 6; step++)
            {
                var f = I.FenceTarget(master, pair, noGrants, false, a => false, a => false, handed[master]);
                if (f.To < 0)
                    break;
                x.P((master == 6 ? "R" : "R2") + " master_fence to=" + I2S(f.To) + " why=" + f.Why);
                handed[master] = true;
                master = f.To;
                moves++;
            }
            x.Ok(moves >= 1, "vii: R hands the role to the next present actor above its own (why=no_grant_next)");
            x.Ok(moves <= 2, "vii: the role moves at most once from each of R and R2, then rests");
            var alone = I.FenceTarget(6, new List<int> { 6 }, noGrants, false, a => false, a => false, false);
            x.Ok(alone.To < 0, "vii: alone in the room, R keeps the role");
            var grants = new List<GrantEntry>
            {
                new GrantEntry(0, 1, 's'), new GrantEntry(1, 2, 's'), new GrantEntry(3, 4, 'l'),
            };
            var fg = I.FenceTarget(6, new List<int> { 2, 4, 6, 7 }, grants, false, a => false, a => false, true);
            x.P("R master_fence to=" + I2S(fg.To) + " why=" + fg.Why);
            x.Ok(fg.To == 2 && fg.Why == "no_grant",
                 "vii: with a granted list read, the lowest named present actor, kind s first, whatever it did before");

            var s = World(I, x, true);
            Cl L2 = s[5];
            foreach (var c in s.All.Values)
            {
                s.Prior(c, 1);
                s.Answer(c, 2);
            }
            s.SetMaster(L2);
            int recorded = 0;
            foreach (var c in s.Others(L2))
            {
                bool ks = I.KeptSender(L2.Actor, s.Grants, c.Rec, c.Point);
                string why = I.ScaleRecord(Lobby8, Lobby8, L2.Actor, c.SeenMaster, -1, ks);
                if (why == null)
                    recorded++;
                else
                    s.P(c, "scale_refused why=" + why);
            }
            x.Ok(recorded == 0, "vii: L2's EVT_SCALE is refused at the dispatch before any client applied epoch 2");
            foreach (var c in s.All.Values)
            {
                c.Applied = 2;
                c.Point = 2;
                c.AppliedChain = ChainOf(Lobby8, c.Rec.Entries, 2);
            }
            recorded = 0;
            int others = 0;
            foreach (var c in s.Others(L2))
            {
                others++;
                bool ks = I.KeptSender(L2.Actor, s.Grants, c.Rec, c.Point);
                if (I.ScaleRecord(Lobby8, Lobby8, L2.Actor, c.SeenMaster, -1, ks) == null)
                    recorded++;
            }
            x.Ok(recorded == others, "vii: after every client applied epoch 2, the same event is recorded everywhere");
            var mRec = s[1].Rec;
            x.Ok(I.KeptSender(2, s.Grants, mRec, 1) && I.KeptSender(4, s.Grants, mRec, 1)
                 && !I.KeptSender(5, s.Grants, mRec, 1) && !I.KeptSender(9, s.Grants, mRec, 1),
                 "vii: KeptSender holds for a kind-s actor or one of the first PointEpoch entries, and no other");
        }

        private static void K45viii(Impl I, Ctx x)
        {
            var s = World(I, x, false);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4];
            foreach (var c in s.All.Values)
                s.Answer(c, 1);
            s.SignalAll();
            var p = s.Propose(M);
            x.Ok(p.HasValue && p.Value.N == 1, "viii: the master proposes epoch 1");
            s.OnEpoch(A, p.Value);
            s.OnEpoch(L1, p.Value);
            var st = s.StampOf(M, p);
            x.Ok(st.Result == "unacked" && s.LastMissing.Count == 1 && s.LastMissing[0] == B.Actor,
                 "viii: without B's acknowledgement by 2 s the master stamps unacked (missing={B})");
            s.OnEpoch(B, p.Value);
            foreach (var c in s.Others(M))
            {
                s.OnStamp(c, st);
                s.OnCallIn(c, M.Actor);
                s.HoldEnd(c);
            }
            foreach (var c in s.Live())
                x.Ok(c.Applied == 0, "viii: no client applies epoch 1");
            foreach (var c in s.Live())
                x.Ok(!s.KeptOn(c, L1.Actor), "viii: L1 stays quarantined everywhere");
            s.NextPoint();
            s.StdPoint(M, "viii");
            foreach (var c in s.Live())
                x.Ok(c.Point == 1, "viii: at the next boundary every member acknowledges and the stamp commits");
            s.NextPoint();
            var wrong = new Proposal { Lobby8 = "0badf00d", N = 1, Chain = p.Value.Chain, G = s.G, K = s.K, From = M.Actor };
            s.OnEpoch(A, wrong);
            x.Ok(!A.Acked && A.EpochRefusal == "lobby", "viii: a client whose proposal failed a check sends no acknowledgement");
            var q = new Proposal { Lobby8 = Lobby8, N = 1, Chain = p.Value.Chain, G = 1, K = 1, From = M.Actor };
            var other = q;
            other.N = 2;
            other.From = B.Actor;
            var outsider = q;
            outsider.From = 9;
            var mine = q;
            mine.From = A.Actor;
            List<int> miss;
            bool done = I.AckComplete(new List<int> { 1, 2, 3 }, new List<int> { 1, 2, 3, 9 },
                                      new List<Proposal> { mine, other, outsider }, q, 1, out miss);
            x.Ok(!done && miss.Count == 1 && miss[0] == 3,
                 "viii: an acknowledgement for another (n, chain, g, k), or from outside the barrier set, is not counted");
        }

        private static void K45ix(Impl I, Ctx x)
        {
            var s = World(I, x, false);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4];
            foreach (var c in s.All.Values)
                s.Answer(c, 1);
            s.SignalAll();
            var p = s.Propose(M);
            foreach (var c in s.Others(M))
                s.OnEpoch(c, p.Value);
            var st = s.StampOf(M, p);
            s.OnStamp(A, st);
            s.OnCallIn(A, M.Actor);
            x.Ok(A.Point == 1, "ix: a stamp before the call-in applies epoch 1 at the call-in (waited_ms=0)");
            s.OnCallIn(B, M.Actor);
            s.OnStamp(B, st);
            x.Ok(B.Point == 1, "ix: a call-in first is held and applied when the stamp arrives within the hold");
            s.OnCallIn(L1, M.Actor);
            s.HoldEnd(L1);
            x.Ok(L1.Lag && L1.LagWhy == "timeout",
                 "ix: no stamp by the hold's end after an acknowledgement: LAG_OUT (why=timeout)");
            s.OnStamp(L1, st);
            x.Ok(L1.Lag && L1.Point == 0 && L1.Applied == 0,
                 "ix: a valid stamp after the hold prints late=1 and changes nothing for that point");

            // a stamp below the applied epoch converges the point down
            var d = World(I, x, false);
            foreach (var c in d.All.Values)
                d.Prior(d[c.Actor], 1);
            d[1].Point = 0;
            var down = d.StampOf(d[1], null);
            d.OnStamp(d[2], down);
            d.OnCallIn(d[2], 1);
            x.Ok(d[2].Point == 0 && d[2].Applied == 1 && d[2].Decision.Kind == PairKind.CarryDown,
                 "ix: a stamp below the applied epoch converges the point down");

            // two valid stamps of the call-in's master that differ
            var t = World(I, x, false);
            foreach (var c in t.All.Values)
                t.Answer(c, 1);
            t.SignalAll();
            var tp = t.Propose(t[1]);
            foreach (var c in t.Others(t[1]))
                t.OnEpoch(c, tp.Value);
            var st1 = t.StampOf(t[1], tp);
            var st2 = new Stamp
            {
                Lobby8 = Lobby8, G = st1.G, K = st1.K, N = 0, Chain = "0", Result = "carry", From = st1.From,
            };
            t.OnStamp(t[2], st1);
            t.OnStamp(t[2], st2);
            t.OnCallIn(t[2], 1);
            x.Ok(t[2].Lag && t[2].LagWhy == "conflict",
                 "ix: two valid stamps of the call-in's master that differ start LAG_OUT (why=conflict)");

            // s1: a stamp that is not the call-in master's
            var forged = new Stamp
            {
                Lobby8 = Lobby8, G = st1.G, K = st1.K, N = 1, Chain = st1.Chain, Result = "commit", From = 3,
            };
            t.OnCallIn(t[3], 1);
            t.OnStamp(t[3], forged);
            x.Ok(t[3].StampRefusal == "sender", "ix: a stamp from a client that is not CallInMaster fails s1 after the call-in");
            t.OnStamp(t[3], st1);
            x.Ok(t[3].Point == 1, "ix: the call-in master's own stamp then pairs");
            t.OnStamp(t[4], forged);
            t.OnStamp(t[4], st1);
            t.OnCallIn(t[4], 1);
            x.Ok(t[4].Superseded == 1 && t[4].Point == 1,
                 "ix: a stamp held from another sender is dropped at the call-in (stamp_superseded)");
            var cl = t[2];
            var unkept = new Stamp { Lobby8 = Lobby8, G = 1, K = 1, N = 0, Chain = "0", Result = "carry", From = 5 };
            x.Ok(I.ValidateStamp(unkept, 5, false, false, Lobby8, cl.Rec, 0, "0", 1, 1, true) == "sender",
                 "ix: a stamp from a call-in master that is not kept fails s1");
            var lCommit = new Stamp { Lobby8 = Lobby8, G = 1, K = 1, N = 1, Chain = st1.Chain, Result = "commit", From = 4 };
            x.Ok(I.ValidateStamp(lCommit, 4, true, false, Lobby8, cl.Rec, 0, "0", 1, 1, true) == "sender",
                 "ix: a stamp that commits while its sender is not kind s fails s1");
            var otherPoint = new Stamp { Lobby8 = Lobby8, G = 1, K = 2, N = 1, Chain = st1.Chain, Result = "commit", From = 1 };
            x.Ok(I.ValidateStamp(otherPoint, 1, true, true, Lobby8, cl.Rec, 0, "0", 1, 1, true) == "boundary",
                 "ix: a stamp for another (g, k) fails s3");

            // a stamp held with no call-in, its master gone, pairs with no later master's call-in
            var h = World(I, x, false);
            foreach (var c in h.All.Values)
                h.Answer(c, 1);
            h.SignalAll();
            var hp = h.Propose(h[1]);
            foreach (var c in h.Others(h[1]))
                h.OnEpoch(c, hp.Value);
            var hs = h.StampOf(h[1], hp);
            h.Leave(h[1], 2);
            h.OnStamp(h[2], hs);
            h.DispatchLeave(h[2], h[1]);
            h.TakeOver(h[2]);
            var hs2 = h.StampOf(h[2], null);
            RunOrder(h, h[3], "SXsc", h[1], hs, h[2], hs2);
            x.Ok(h[3].Superseded == 1 && h[3].Point == h[2].Point && !h[3].Lag,
                 "ix: a stamp held with no call-in, its master gone, pairs with no later master's call-in");
        }

        private static string Tenths(int t)
        {
            return I2S(t / 10) + "." + I2S(t % 10);
        }

        private static string RunFence(Impl I, Ctx x, int landsAt, int keptAt, out int endTenths, out int tries)
        {
            tries = 0;
            for (int t = 0; t <= 200; t++)
            {
                bool landed = landsAt >= 0 && tries > 0 && t >= landsAt;
                bool kept = keptAt >= 0 && t >= keptAt;
                var act = I.FenceStep(t / 10.0, tries, landed, kept);
                if (act == FenceAct.Try)
                {
                    tries++;
                    x.P("master_fence try=" + I2S(tries) + " at=" + Tenths(t));
                    continue;
                }
                if (act == FenceAct.Done || act == FenceAct.Kept || act == FenceAct.Expired)
                {
                    endTenths = t;
                    string res = act == FenceAct.Done ? "done" : (act == FenceAct.Kept ? "kept" : "expired");
                    x.P("master_fence result=" + res + " at=" + Tenths(t));
                    return res;
                }
            }
            endTenths = 201;
            x.P("master_fence result=held at=20.1");
            return "held";
        }

        private static void K45x(Impl I, Ctx x)
        {
            int end, tries;
            x.Ok(RunFence(I, x, 2, -1, out end, out tries) == "done" && end == 2,
                 "x: a switch that lands after the first try ends done at 0.2 s");
            x.Ok(RunFence(I, x, 40, -1, out end, out tries) == "done" && end == 40,
                 "x: after the second try, done at 4.0 s");
            x.Ok(RunFence(I, x, 89, -1, out end, out tries) == "done" && end == 89,
                 "x: after the third try, done at 8.9 s");
            string never = RunFence(I, x, -1, -1, out end, out tries);
            x.Ok(never == "expired" && end == 90 && tries == 3,
                 "x: a switch that never lands: three tries 3 s apart, then expired at 9 s");
            x.P("exit why=fence_expired release=1 leave_queue=0");
            x.Ok(RunFence(I, x, -1, 50, out end, out tries) == "kept", "x: one that becomes kept meanwhile ends kept");
            x.Ok(!MasterFencedValue(true, false), "x: a kept master is never fenced");
            x.Ok(MasterFencedValue(true, true), "x: a master in LAG_OUT is fenced");
            string lagOfA = LagValue(Lobby8, 1, 2);
            var all3 = new List<GrantEntry> { new GrantEntry(0, 1, 's'), new GrantEntry(1, 2, 's'), new GrantEntry(2, 3, 's') };
            var f = I.FenceTarget(1, new List<int> { 1, 2, 3 }, all3, true, a => true,
                                  a => a == 2 && LagNames(lagOfA, Lobby8, 1, 2), false);
            x.Ok(f.To == 3, "x: FenceTarget skips an actor whose cr_lag names this lobby, game and point");
        }

        // ---------------------------------------------------------------- K45 fixture xi: the orders of sec8.5

        private static readonly string[] Timings = { "before", "window", "beyond", "never" };

        /// <summary>The boundary model's orders_for (sec8.5): the arrival
        /// orders of P, S and C at one receiver that causality allows.</summary>
        private static List<string> OrdersFor(bool ackOnTime, string st)
        {
            var res = new List<string>();
            string msgs = st == "never" ? "PC" : "PSC";
            foreach (string perm in Perms(msgs))
            {
                int p = perm.IndexOf('P'), c = perm.IndexOf('C'), s = perm.IndexOf('S');
                if (ackOnTime && (p > c || (s >= 0 && p > s)))
                    continue;
                if (st == "before" && s > c)
                    continue;
                if ((st == "window" || st == "beyond") && s < c)
                    continue;
                res.Add(perm);
            }
            return res;
        }

        private struct Outcome
        {
            internal bool Lag;
            internal int Set;
            internal int Applied;
            internal string Why;
        }

        /// <summary>One receiver's point over the real functions: M (1)
        /// proposes epoch 1 and stamps masterN; X (3) is a kind-s client that
        /// is not the master and sends a commit when a position is given.</summary>
        private static Outcome N7Receiver(Impl I, Ctx quiet, string perm, string st, int roguePos, int masterN)
        {
            var s = new Sim(I, quiet);
            Cl M = s.Add("M", 1, 's', 0), R = s.Add("R", 2, 's', 1);
            s.Add("X", 3, 's', 2);
            s.Add("L", 4, 'l', 3);
            s.SetMaster(M);
            s.Answer(R, 1);
            R.LastPair = M.Actor;
            R.PairedAny = true;
            var p = new Proposal { Lobby8 = Lobby8, N = 1, Chain = ChainOf(Lobby8, s.Server, 1), G = 1, K = 1, From = 1 };
            var stamp = new Stamp
            {
                Lobby8 = Lobby8, G = 1, K = 1, N = masterN, Chain = ChainOf(Lobby8, s.Server, masterN),
                Result = masterN == 1 ? "commit" : "unacked", From = 1,
            };
            var rogue = new Stamp
            {
                Lobby8 = Lobby8, G = 1, K = 1, N = 1, Chain = ChainOf(Lobby8, s.Server, 1), Result = "commit", From = 3,
            };
            string q = roguePos >= 0 ? perm.Insert(roguePos, "R") : perm;
            if (st == "beyond")
                q = q.Insert(q.IndexOf('S'), "H");
            else if (st == "never")
                q = q + "H";
            foreach (char e in q)
            {
                if (e == 'P') s.OnEpoch(R, p);
                else if (e == 'S') s.OnStamp(R, stamp);
                else if (e == 'C') s.OnCallIn(R, M.Actor);
                else if (e == 'R') s.OnStamp(R, rogue);
                else s.HoldEnd(R);
            }
            s.HoldEnd(R);
            return new Outcome { Lag = R.Lag, Set = R.Point, Applied = R.Applied, Why = R.Lag ? R.LagWhy : null };
        }

        private static void K45xiN7(Impl I, Ctx x)
        {
            var quiet = Ctx.Quiet();
            for (int rogue = 0; rogue < 2; rogue++)
            {
                long runs = 0, i1 = 0, i2 = 0, i6 = 0;
                for (int mask = 0; mask < 8; mask++)
                {
                    var ack = new[] { (mask & 1) != 0, (mask & 2) != 0, (mask & 4) != 0 };
                    bool all = ack[0] && ack[1] && ack[2];
                    string res;
                    int masterN;
                    bool apply;
                    I.StampDecision(true, 1, all, 0, out res, out masterN, out apply);
                    var per = new List<Outcome>[3];
                    for (int i = 0; i < 3; i++)
                    {
                        per[i] = new List<Outcome>();
                        foreach (string st in Timings)
                            foreach (string perm in OrdersFor(ack[i], st))
                            {
                                if (rogue == 0)
                                    per[i].Add(N7Receiver(I, quiet, perm, st, -1, masterN));
                                else
                                    for (int rp = 0; rp <= perm.Length; rp++)
                                        per[i].Add(N7Receiver(I, quiet, perm, st, rp, masterN));
                            }
                    }
                    foreach (var a in per[0])
                        foreach (var b in per[1])
                            foreach (var c in per[2])
                            {
                                runs++;
                                bool v1 = false, v2 = false, v6 = false;
                                foreach (var o in new[] { a, b, c })
                                {
                                    if (!o.Lag && o.Set != masterN) v1 = true;
                                    if (o.Set > masterN || o.Applied > masterN) v2 = true;
                                    if (!all && o.Set != masterN) v6 = true;
                                }
                                if (v1) i1++;
                                if (v2) i2++;
                                if (v6) i6++;
                            }
                }
                x.P((rogue == 0 ? "n7" : "n7 rogue") + " runs=" + I2S(runs) + " I1=" + I2S(i1) + " I2=" + I2S(i2)
                    + " I6=" + I2S(i6));
                x.Ok(runs == (rogue == 0 ? 3375 : 185193),
                     "xi: the model's enumeration sizes (3,375, and 185,193 with the rogue stamp)");
                x.Ok(i1 == 0, "xi: no receiver that plays the point holds a set other than the master's"
                              + (rogue == 0 ? "" : " (rogue stamp)"));
                x.Ok(i2 == 0, "xi: no receiver is ahead of what the master committed" + (rogue == 0 ? "" : " (rogue stamp)"));
                x.Ok(i6 == 0, "xi: no receiver diverges when the master did not commit" + (rogue == 0 ? "" : " (rogue stamp)"));
            }
        }

        /// <summary>The boundary model's count_client (sec8.5) over the real
        /// rules: X is EVT_SCALE from M1 (count 5), N is M1's latch of the
        /// point, W the switch to M2, D the load (after N); `window` says a
        /// count that follows the load arrives inside its hold.</summary>
        private static int CountCase(Impl I, string order, bool window, out bool lag)
        {
            var recs = new List<ScaleRecord>();
            int master = 1, latch = -1;
            bool held = false;
            lag = false;
            foreach (char m in order)
            {
                if (m == 'W')
                {
                    master = 2;
                    if (I.ScaleClearAtSwitch)
                        recs.Clear();
                }
                else if (m == 'N')
                    latch = master;
                else if (m == 'X')
                {
                    bool ok = I.ScaleRecord(Lobby8, Lobby8, 1, master, latch, true) == null;
                    if (held)
                    {
                        if (ok && window)
                        {
                            recs.Add(new ScaleRecord { Game = 2, K = 3, Count = 5, From = 1, Confirmed = true });
                            var d1 = I.ScaleDecision(recs, 2, 3, true);
                            if (d1.Count >= 0)
                                return d1.Count;
                        }
                        lag = I.ScaleDecision(new List<ScaleRecord>(), 2, 3, true).LagOut;
                        return 0;
                    }
                    if (ok)
                        recs.Add(new ScaleRecord { Game = 2, K = 3, Count = 5, From = 1, Confirmed = true });
                }
                else if (m == 'D')
                {
                    var d = I.ScaleDecision(recs, 2, 3, true);
                    if (d.Count >= 0)
                        return d.Count;
                    if (I.ScaleNoHold)
                        return 0;
                    held = true;
                }
            }
            if (held)
                lag = I.ScaleDecision(recs, 2, 3, true).LagOut;
            return 0;
        }

        private static void K45xiCount(Impl I, Ctx x)
        {
            var cases = new List<KeyValuePair<string, bool>>();
            foreach (string o in Perms("XNWD"))
                if (o.IndexOf('N') < o.IndexOf('D'))
                {
                    cases.Add(new KeyValuePair<string, bool>(o, true));
                    cases.Add(new KeyValuePair<string, bool>(o, false));
                }
            var scale = new int[cases.Count];
            var lagged = new bool[cases.Count];
            int lagCount = 0;
            for (int i = 0; i < cases.Count; i++)
            {
                scale[i] = CountCase(I, cases[i].Key, cases[i].Value, out lagged[i]);
                if (lagged[i])
                    lagCount++;
            }
            int pairs = 0, playSplit = 0;
            for (int a = 0; a < cases.Count; a++)
                for (int b = 0; b < cases.Count; b++)
                {
                    pairs++;
                    if (!lagged[a] && !lagged[b] && scale[a] != scale[b])
                        playSplit++;
                }
            x.P("count cases=" + I2S(cases.Count) + " pairs=" + I2S(pairs) + " play_split=" + I2S(playSplit)
                + " lag_out=" + I2S(lagCount));
            x.Ok(cases.Count == 24 && pairs == 576, "xi: 24 client cases, 576 pairs of clients");
            x.Ok(playSplit == 0, "xi: every client that plays the point loads the same scale");
            x.Ok(lagCount == 9, "xi: a load without its count is LAG_OUT (9 of the 24 client cases)");
        }

        // ---------------------------------------------------------------- K45 fixture xii

        private static void K45xiia(Impl I, Ctx x)
        {
            foreach (string order in StampLeaveOrders)
            {
                var s = World(I, x, false);
                Cl M = s[1], A = s[2], B = s[3], L1 = s[4];
                foreach (var c in s.All.Values)
                    s.Answer(c, 1);
                s.SignalAll();
                var p = s.Propose(M);
                foreach (var c in s.Others(M))
                    s.OnEpoch(c, p.Value);
                var sM = s.StampOf(M, p);
                x.Ok(sM.Result == "commit", "xii a: M1 stamps commit for (1, 1)");
                s.Leave(M, A.Actor);
                s.OnStamp(A, sM);
                s.DispatchLeave(A, M);
                s.TakeOver(A);
                var sA = s.StampOf(A, null);
                foreach (var r in new[] { B, L1 })
                {
                    RunOrder(s, r, order, M, sM, A, sA);
                    x.Ok(!r.Lag && r.Point == A.Point,
                         "xii a: " + r.Name + " drops M1's stamp and pairs M2's own (" + order + ")");
                }
            }
        }

        private static void K45xiib(Impl I, Ctx x)
        {
            var s = World(I, x, true);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4], L2 = s[5];
            foreach (var c in s.All.Values)
                s.Prior(c, 1);
            foreach (var c in s.All.Values)
                s.Answer(c, 2);
            s.SignalAll();
            var p = s.Propose(M);
            x.Ok(p.HasValue && p.Value.N == 2, "xii b: the master proposes epoch 2");
            s.OnEpoch(B, p.Value);
            var st = s.StampOf(M, p);
            x.Ok(st.Result == "unacked" && st.N == 1, "xii b: without every acknowledgement it stamps unacked (n=1)");
            s.OnCallIn(A, M.Actor);
            s.HoldEnd(A);
            x.Ok(!A.Lag && A.Decision.Kind == PairKind.StampLate && A.Point == 1,
                 "xii b: no acknowledgement sent and the last pairing with this master: stamp_late, PointEpoch unchanged");
            s.OnCallIn(B, M.Actor);
            s.HoldEnd(B);
            x.Ok(B.Lag && B.LagWhy == "timeout", "xii b: the same receiver having acknowledged: LAG_OUT (why=timeout)");
            L1.LastPair = 9;
            s.OnCallIn(L1, M.Actor);
            s.HoldEnd(L1);
            x.Ok(L1.Lag && L1.LagWhy == "timeout", "xii b: its last pairing with another master: LAG_OUT (why=timeout)");
            s.NextPoint();
            s.OnCallIn(B, M.Actor);
            s.HoldEnd(B);
            x.Ok(B.Lag && B.Decision.Kind == PairKind.LagOut, "xii b: LastPairMaster cleared by LAG_OUT: LAG_OUT again");

            var f = World(I, x, false);
            Cl F = f[2];
            foreach (var c in f.All.Values)
                f.Answer(c, 1);
            F.LastPair = -1;
            F.PairedAny = false;
            f.G = 0;
            f.NextGame(1, true);
            x.Ok(F.LastPair == 1, "xii b: a start-roster seat that paired nothing takes the master of its first game's start");
            f.OnCallIn(F, 1);
            f.HoldEnd(F);
            x.Ok(!F.Lag && F.Decision.Kind == PairKind.StampLate, "xii b: so its first undisputed point takes stamp_late");
            int before = F.LastPair, point = F.Point;
            f.NextGame(3, false);
            x.Ok(F.LastPair == before && F.Point == point, "xii b: a game's start changes neither LastPairMaster nor PointEpoch");
        }

        private static void K45xiic(Impl I, Ctx x)
        {
            var s = World(I, x, true);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4], L2 = s[5];
            foreach (var c in s.All.Values)
                s.Prior(c, 1);
            foreach (var c in s.All.Values)
                s.Answer(c, 2);
            foreach (var c in new[] { A, L2 })
            {
                c.Applied = 2;
                c.Point = 2;
                c.AppliedChain = ChainOf(Lobby8, c.Rec.Entries, 2);
            }
            s.SignalAll();
            var p = s.Propose(M);
            x.Ok(p.HasValue && p.Value.N == 2, "xii c: the master, at PointEpoch 1, proposes epoch 2");
            foreach (var c in new[] { A, L1, L2 })
                s.OnEpoch(c, p.Value);
            var st = s.StampOf(M, p);
            x.Ok(st.Result == "unacked" && st.N == 1, "xii c: B's acknowledgement missing, the stamp names 1");
            foreach (var c in s.Others(M))
            {
                s.OnStamp(c, st);
                s.OnCallIn(c, M.Actor);
                s.HoldEnd(c);
            }
            x.Ok(A.Point == 1 && A.Applied == 2 && A.Decision.Kind == PairKind.CarryDown,
                 "xii c: a receiver whose EpochApplied is 2 converges down to 1 (kept src=carry down=1)");
            x.Ok(!s.KeptOn(A, L2.Actor), "xii c: it sits L2 out of that point on its own screen");
            x.Ok(L2.Point == 1 && !s.KeptOn(L2, L2.Actor), "xii c: L2's own body sits out on its own screen");
            s.Check(M, "xii c");
            s.SetMaster(A);
            s.NextPoint();
            s.SignalAll();
            var again = s.Propose(A);
            x.Ok(again.HasValue && again.Value.N == 2,
                 "xii c: a master whose PointEpoch is 1 and whose EpochApplied is 2 proposes 2 again");
            foreach (var c in s.Others(A))
                s.OnEpoch(c, again.Value);
            var st2 = s.StampOf(A, again);
            x.Ok(st2.Result == "commit", "xii c: e3 accepts it on every member and the stamp commits");
            foreach (var c in s.Others(A))
            {
                s.OnStamp(c, st2);
                s.OnCallIn(c, A.Actor);
                s.HoldEnd(c);
            }
            foreach (var c in s.Live())
                x.Ok(c.Point == 2, "xii c: every client applies 2 at the next commit of it");
        }

        private static void K45xiid(Impl I, Ctx x)
        {
            var s = World(I, x, true);
            Cl M = s[1], A = s[2], B = s[3], L1 = s[4], L2 = s[5];
            foreach (var c in s.All.Values)
                s.Prior(c, 1);
            foreach (var c in s.All.Values)
                s.Answer(c, 2);
            s.SignalAll();
            var p = s.Propose(M);
            foreach (var c in s.Others(M))
                s.OnEpoch(c, p.Value);
            var st = s.StampOf(M, p);
            foreach (var c in s.Others(M))
            {
                if (c != A)
                    s.OnStamp(c, st);
                s.OnCallIn(c, M.Actor);
                s.HoldEnd(c);
            }
            x.Ok(A.Lag && A.Deaths == 1, "xii d: a receiver whose hold ends in LAG_OUT prints lag_out and its player dies");
            x.Ok(MasterFencedValue(s.KeptOn(A, A.Actor), A.Lag), "xii d: it sends no master decision (MasterMaySend() false)");
            x.Ok(A.CrLag == LagValue(Lobby8, 1, 1) && A.LagPosts.Count == 1,
                 "xii d: it sets LagGame and cr_lag and POSTs the lag step once for the game");
            var lagged = new Dictionary<int, string> { { A.Actor, A.CrLag } };
            var f = I.FenceTarget(M.Actor, M.Present, s.Grants, true, a => s.KeptOn(M, a),
                                  a => lagged.ContainsKey(a) && LagNames(lagged[a], Lobby8, s.G, s.K), false);
            x.Ok(f.To == B.Actor, "xii d: FenceTarget on every other client skips it for that point");
            s.Check(M, "xii d");
            s.NextPoint();
            var st2 = s.StampOf(M, null);
            s.OnCallIn(A, M.Actor);
            s.HoldEnd(A);
            x.Ok(A.Lag && A.Deaths == 2, "xii d: at a later call-in it cannot pair, lag_out again and its player dies again");
            int reporter = I.ElectReporter(new List<int> { A.Actor, B.Actor, M.Actor },
                                           a => s[a].LagGames.Contains(1), a => false);
            x.P("reporter g=1 elected=" + I2S(reporter));
            x.Ok(reporter == B.Actor, "xii d: the election skips a candidate lagged in the game, so its report builder files none");
            s.NextGame(M.Actor, false);
            x.Ok(A.Lag, "xii d: a game's end does not end it");
            x.Ok(A.LagGames.Contains(2) && A.LagPosts.Contains(2) && A.CrLag == LagValue(Lobby8, 2, 1),
                 "xii d: a game it enters while in it is lagged too");
            s.SignalAll();
            var st3 = s.StampOf(M, null);
            s.OnStamp(A, st3);
            s.OnCallIn(A, M.Actor);
            x.Ok(!A.Lag, "xii d: the call-in of a later point that it pairs with a valid stamp ends it (why=callin)");
            s.NextPoint();
            s.StartLag(A, "scale", true);
            var st4 = s.StampOf(M, null);
            s.OnStamp(A, st4);
            s.OnCallIn(A, M.Actor);
            x.Ok(A.Lag, "xii d: a LAG_OUT that starts at a point's load is not ended by that point's own call-in");
            s.NextPoint();
            var st5 = s.StampOf(M, null);
            s.OnStamp(A, st5);
            s.OnCallIn(A, M.Actor);
            x.Ok(!A.Lag, "xii d: the next point's paired call-in ends it");
            s.StartLag(A, "timeout", false);
            if (I.LagOutEnds("room_exit", false))
                s.EndLag(A, "room_exit");
            x.Ok(!A.Lag, "xii d: the room exit ends it (why=room_exit)");
            x.Ok(st2 != null, "xii d: the master stamped every point");
        }

        private static readonly string[] Orphans = { "none", "before_c", "after_c" };

        private struct N9Opt
        {
            internal bool Same;
            internal int C0;
            internal string Perm;
            internal string St;
            internal int PInHold;
            internal string Orphan;
        }

        /// <summary>The boundary model's v11_options (sec8.5).</summary>
        private static List<N9Opt> N9Options(bool ackOnTime)
        {
            var opts = new List<N9Opt>();
            var priors = new[] { new KeyValuePair<bool, int>(true, 1), new KeyValuePair<bool, int>(false, 0),
                                 new KeyValuePair<bool, int>(false, 1), new KeyValuePair<bool, int>(false, 2) };
            foreach (var pr in priors)
                foreach (string st in Timings)
                    foreach (string perm in OrdersFor(ackOnTime, st))
                    {
                        bool lateP = perm.IndexOf('P') > perm.IndexOf('C') && (st == "beyond" || st == "never");
                        foreach (int pin in lateP ? new[] { 1, 0 } : new[] { -1 })
                            foreach (string orphan in Orphans)
                                opts.Add(new N9Opt { Same = pr.Key, C0 = pr.Value, Perm = perm, St = st, PInHold = pin,
                                                     Orphan = orphan });
                    }
            return opts;
        }

        private static bool LateEligible(N9Opt o)
        {
            bool acked = o.Perm.IndexOf('P') < o.Perm.IndexOf('C') || o.PInHold == 1;
            return (o.St == "beyond" || o.St == "never") && !acked && o.Same;
        }

        /// <summary>One receiver's point of the N9 enumeration over the real
        /// ValidateStamp and PairDecision: the call-in master M (1), at
        /// PointEpoch 1, proposes 2 and stamps masterN; an earlier master O (3)
        /// left a commit of 2 for the same (g, k).</summary>
        private static Outcome N9Receiver(Impl I, Ctx quiet, N9Opt o, int masterN)
        {
            var s = new Sim(I, quiet);
            Cl M = s.Add("M", 1, 's', 0), R = s.Add("R", 2, 's', 1);
            s.Add("O", 3, 's', 2);
            s.Add("L1", 4, 'l', 3);
            s.Add("L2", 5, 'l', 4);
            s.SetMaster(M);
            s.Answer(R, 2);
            R.Applied = o.C0;
            R.Point = o.C0;
            R.AppliedChain = ChainOf(Lobby8, R.Rec.Entries, o.C0) ?? "0";
            R.LastPair = o.Same ? M.Actor : 9;
            R.PairedAny = true;
            var p = new Proposal { Lobby8 = Lobby8, N = 2, Chain = ChainOf(Lobby8, s.Server, 2), G = 1, K = 1, From = 1 };
            var stamp = new Stamp
            {
                Lobby8 = Lobby8, G = 1, K = 1, N = masterN, Chain = ChainOf(Lobby8, s.Server, masterN),
                Result = masterN == 2 ? "commit" : "unacked", From = 1,
            };
            var orphan = new Stamp
            {
                Lobby8 = Lobby8, G = 1, K = 1, N = 2, Chain = ChainOf(Lobby8, s.Server, 2), Result = "commit", From = 3,
            };
            string q = o.Perm;
            if (o.St == "beyond" || o.St == "never")
            {
                bool pAfterC = q.IndexOf('P') > q.IndexOf('C');
                if (pAfterC)
                    q = q.Remove(q.IndexOf('P'), 1);
                q = o.St == "beyond" ? q.Insert(q.IndexOf('S'), "H") : q + "H";
                if (pAfterC)
                {
                    int h = q.IndexOf('H');
                    q = o.PInHold == 1 ? q.Insert(h, "P") : q.Insert(h + 1, "P");
                }
            }
            if (o.Orphan == "before_c")
                q = q.Insert(q.IndexOf('C'), "O");
            else if (o.Orphan == "after_c")
                q = q.Insert(q.IndexOf('C') + 1, "O");
            foreach (char e in q)
            {
                if (e == 'P') s.OnEpoch(R, p);
                else if (e == 'S') s.OnStamp(R, stamp);
                else if (e == 'C') s.OnCallIn(R, M.Actor);
                else if (e == 'H') s.HoldEnd(R);
                else
                {
                    // the orphan was sent while O was master, and is dispatched as such before the call-in
                    int seen = R.SeenMaster;
                    if (R.CallIn < 0)
                        R.SeenMaster = 3;
                    s.OnStamp(R, orphan);
                    R.SeenMaster = seen;
                }
            }
            s.HoldEnd(R);
            string why = R.Lag ? R.LagWhy : (R.Decided && R.Decision.Kind == PairKind.StampLate ? "stamp_late" : null);
            return new Outcome { Lag = R.Lag, Set = R.Point, Applied = R.Applied, Why = why };
        }

        private static void K45xiie(Impl I, Ctx x)
        {
            var quiet = Ctx.Quiet();
            var optsFor = new Dictionary<bool, List<N9Opt>> { { true, N9Options(true) }, { false, N9Options(false) } };
            var outs = new Dictionary<string, List<Outcome>>();
            foreach (bool ackv in new[] { true, false })
                foreach (int mn in new[] { 1, 2 })
                {
                    var list = new List<Outcome>();
                    foreach (var o in optsFor[ackv])
                        list.Add(N9Receiver(I, quiet, o, mn));
                    outs[(ackv ? "t" : "f") + I2S(mn)] = list;
                }
            // the election among A (2) and B (3), then M (1), over their LAG_OUT flags
            var elected = new int[2, 2];
            for (int la = 0; la < 2; la++)
                for (int lb = 0; lb < 2; lb++)
                {
                    bool lagA = la == 1, lagB = lb == 1;
                    elected[la, lb] = I.ElectReporter(new List<int> { 2, 3, 1 },
                                                      a => (a == 2 && lagA) || (a == 3 && lagB), a => false);
                }
            long runs = 0, orphanRuns = 0, i7 = 0, i8 = 0, lagOut = 0, lateCount = 0, above = 0, lateForfeit = 0,
                 outcomes = 0;
            for (int mask = 0; mask < 8; mask++)
            {
                var ack = new[] { (mask & 1) != 0, (mask & 2) != 0, (mask & 4) != 0 };
                bool all = ack[0] && ack[1] && ack[2];
                string res;
                int masterN;
                bool apply;
                I.StampDecision(true, 2, all, 1, out res, out masterN, out apply);
                var o0 = outs[(ack[0] ? "t" : "f") + I2S(masterN)];
                var o1 = outs[(ack[1] ? "t" : "f") + I2S(masterN)];
                var o2 = outs[(ack[2] ? "t" : "f") + I2S(masterN)];
                var p0 = optsFor[ack[0]];
                var p1 = optsFor[ack[1]];
                var p2 = optsFor[ack[2]];
                for (int r = 0; r < 3; r++)
                {
                    var oo = r == 0 ? o0 : (r == 1 ? o1 : o2);
                    var pp = r == 0 ? p0 : (r == 1 ? p1 : p2);
                    for (int i = 0; i < oo.Count; i++)
                    {
                        outcomes++;
                        if (oo[i].Lag) lagOut++;
                        if (oo[i].Why == "stamp_late") lateCount++;
                        if (oo[i].Why == "stamp_above") above++;
                        if (LateEligible(pp[i]) && oo[i].Lag && oo[i].Why != "stamp_above") lateForfeit++;
                    }
                }
                // every execution of the product, literally: receiver A's option
                // times B's times the third receiver's
                var ok2 = new bool[o2.Count];
                var orph2 = new bool[o2.Count];
                for (int c = 0; c < o2.Count; c++)
                {
                    ok2[c] = o2[c].Lag || o2[c].Set == masterN;
                    orph2[c] = p2[c].Orphan != "none";
                }
                for (int a = 0; a < o0.Count; a++)
                {
                    var ra = o0[a];
                    bool okA = ra.Lag || ra.Set == masterN;
                    bool orphA = p0[a].Orphan != "none";
                    for (int b = 0; b < o1.Count; b++)
                    {
                        var rb = o1[b];
                        bool okAB = okA && (rb.Lag || rb.Set == masterN);
                        bool orphAB = orphA || p1[b].Orphan != "none";
                        int e = elected[ra.Lag ? 1 : 0, rb.Lag ? 1 : 0];
                        bool bad8 = (e == 2 && ra.Set != masterN) || (e == 3 && rb.Set != masterN);
                        for (int c = 0; c < o2.Count; c++)
                        {
                            runs++;
                            if (orphAB || orph2[c])
                                orphanRuns++;
                            if (!(okAB && ok2[c]))
                                i7++;
                            if (bad8)
                                i8++;
                        }
                    }
                }
            }
            x.P("n9 runs=" + I2S(runs) + " orphan_runs=" + I2S(orphanRuns) + " I7=" + I2S(i7) + " I8=" + I2S(i8));
            x.P("n9 outcomes=" + I2S(outcomes) + " lag_out=" + I2S(lagOut) + " stamp_late=" + I2S(lateCount)
                + " stamp_above=" + I2S(above) + " late_forfeit=" + I2S(lateForfeit));
            x.Ok(runs == 10077696, "xii e: the N9 enumeration runs 10,077,696 executions");
            x.Ok(i7 == 0, "xii e: I7, every receiver that plays the point holds the call-in master's set");
            x.Ok(i8 == 0, "xii e: I8, the elected reporter of a game did not lag in it");
            x.Ok(lateForfeit == 0, "xii e: no receiver that sent no acknowledgement and last paired this master forfeits");
            x.Ok(above == 0, "xii e: no stamp_above under a compliant master");
            var fifo = N9Receiver(I, quiet, new N9Opt { Same = true, C0 = 1, Perm = "PSC", St = "before", PInHold = -1,
                                                       Orphan = "none" }, 2);
            x.Ok(!fifo.Lag && fifo.Set == 2 && fifo.Why == null,
                 "xii e: with the premises true, a receiver pairs epoch 2 and plays, with no LAG_OUT and no stamp_late");
        }
    }
}
