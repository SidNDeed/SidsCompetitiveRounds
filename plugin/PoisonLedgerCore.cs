// PoisonLedgerCore.cs -- the pure decisions of poison convergence v3 (bugs 406
// and 407): the room-common life epoch and the classification of a stream
// against it, the receiver ledger (each committed tick applied at most once),
// the catch-up summary, the start-claim decisions on both ends, and the
// activation rule. No Unity, Photon or Harmony type appears here, so
// tools/tests/poison-ledger compiles this exact file and drives it; PoisonSync
// feeds it what the game and the network say and executes what it returns.
//
// Design record: ai-collab/v1410/POISON-CONVERGENCE-DESIGN-V2.md as amended by
// POISON-CONVERGENCE-AMENDMENTS-V3.md (local notes, not shipped).

using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>The life a stream belongs to, named by the send stamp of the
    /// boundary RPC the victim's seat had seen when it last revived its own
    /// view. Set=false is "revived before any boundary in this room". The
    /// stamp is PUN's own RPC send stamp, one number on every seat.</summary>
    internal struct LifeEpoch
    {
        internal bool Set;
        internal int Ts;

        internal static LifeEpoch At(int ts) { return new LifeEpoch { Set = true, Ts = ts }; }

        internal bool SameAs(LifeEpoch o) { return Set == o.Set && (!Set || Ts == o.Ts); }

        public override string ToString() { return Set ? Ts.ToString(System.Globalization.CultureInfo.InvariantCulture) : "none"; }
    }

    internal enum LifeClass { Current, Next, Ending, Stale }

    /// <summary>What the shell does with a tick the ledger releases. The ledger
    /// marks the tick applied BEFORE calling either method, so an exception
    /// inside loses that tick on this seat and never applies it twice.</summary>
    internal interface ILedgerApplier
    {
        /// <summary>On time, the replica live: today's application.</summary>
        void Regular(PoisonLedgerCore.Rec rec, int tick);

        /// <summary>Late (deferred or caught up): the correction funnel only --
        /// a non-lethal health movement and the victim's own bar.</summary>
        void Corrective(PoisonLedgerCore.Rec rec, int tick);
    }

    internal sealed class PoisonLedgerCore
    {
        internal const int MaxTick = 1024;                    // tick indices outside [0, 1024) are ignored
        internal const int EvictTerminalAbovePerView = 128;   // only terminal records are ever evicted
        internal const int NonTerminalCeilingPerView = 1024;  // memory backstop: a new header is refused past it

        /// <summary>Wrap-safe ordering of two server-clock stamps (PoisonSync.ServerTsAfter's rule).</summary>
        internal static bool After(int a, int b) { unchecked { return (a - b) > 0; } }

        // ── Life state per view, on this seat ──────────────────────────────

        internal sealed class ViewLife
        {
            internal bool HasPhoenix;
            internal int Phoenix;
            internal int FenceState;   // 0: never revived here, 1: revived before any boundary, 2: revived at Fence
            internal int Fence;
        }

        private bool _hasPoint;
        private int _point;
        private readonly Dictionary<int, ViewLife> _lives = new Dictionary<int, ViewLife>();

        private ViewLife Life(int view)
        {
            ViewLife l;
            if (!_lives.TryGetValue(view, out l)) { l = new ViewLife(); _lives[view] = l; }
            return l;
        }

        /// <summary>The latest boundary this seat has seen for the view: the
        /// room-wide point-over or the view's own Phoenix, whichever is later.</summary>
        internal bool BoundaryFor(int view, out int b)
        {
            ViewLife l;
            bool hasPhoenix = _lives.TryGetValue(view, out l) && l.HasPhoenix;
            if (_hasPoint && hasPhoenix) { b = After(l.Phoenix, _point) ? l.Phoenix : _point; return true; }
            if (_hasPoint) { b = _point; return true; }
            if (hasPhoenix) { b = l.Phoenix; return true; }
            b = 0;
            return false;
        }

        internal void NotePointBoundary(int ts)
        {
            if (!_hasPoint || After(ts, _point)) { _point = ts; _hasPoint = true; }
        }

        internal void NotePhoenixBoundary(int view, int ts)
        {
            var l = Life(view);
            if (!l.HasPhoenix || After(ts, l.Phoenix)) { l.Phoenix = ts; l.HasPhoenix = true; }
        }

        /// <summary>The life this seat's replica of the view is in; false while
        /// this seat has never revived it (the victim then stamps no v3 header).</summary>
        internal bool FenceOf(int view, out LifeEpoch e)
        {
            ViewLife l;
            e = default(LifeEpoch);
            if (!_lives.TryGetValue(view, out l) || l.FenceState == 0) return false;
            e = l.FenceState == 2 ? LifeEpoch.At(l.Fence) : default(LifeEpoch);
            return true;
        }

        /// <summary>Classification of a stream of life S against this seat's
        /// boundary and fence for the view. Stamps only, never a receipt time.</summary>
        internal LifeClass Classify(int view, LifeEpoch s)
        {
            int b;
            if (!BoundaryFor(view, out b)) return LifeClass.Current;
            ViewLife l = Life(view);
            bool fenceAtB = l.FenceState == 2 && l.Fence == b;
            if (s.Set && s.Ts == b) return fenceAtB ? LifeClass.Current : LifeClass.Next;
            if (s.Set && After(s.Ts, b)) return LifeClass.Next;
            // S is older than the latest boundary: a life that boundary ended.
            if (l.FenceState == 2 && (!s.Set || After(l.Fence, s.Ts))) return LifeClass.Stale;
            return LifeClass.Ending;
        }

        // ── The ledger ────────────────────────────────────────────────────

        internal sealed class Rec
        {
            internal int View, Stream, Seq;
            internal LifeEpoch Life;
            internal LifeClass Cls0;
            internal object Payload;                 // the shell's own header data
            internal readonly HashSet<int> Committed = new HashSet<int>();
            internal readonly HashSet<int> Blocked = new HashSet<int>();
            internal readonly HashSet<int> Applied = new HashSet<int>();
            internal readonly SortedSet<int> Pending = new SortedSet<int>();
            internal int Filled, CatchUp, AfterSignal, PendingDropped, Duplicates, OutOfRange, Exceptions, SummaryMismatch;
            internal bool SummarySeen;
            internal string Retired;                 // null while held

            internal bool Terminal { get { return SummarySeen && Pending.Count == 0; } }
        }

        private readonly Dictionary<long, Rec> _recs = new Dictionary<long, Rec>();
        private int _seq;

        /// <summary>Records this ledger removed since the shell last drained
        /// them, each with Retired set: the shell writes one evidence line per
        /// record from this list.</summary>
        internal readonly List<Rec> RetiredLog = new List<Rec>();

        internal static long Key(int view, int stream) { return ((long)view << 32) ^ (uint)stream; }

        internal Rec Find(int view, int stream)
        {
            Rec r;
            return _recs.TryGetValue(Key(view, stream), out r) ? r : null;
        }

        internal int Count { get { return _recs.Count; } }

        private int CountForView(int view, bool nonTerminalOnly)
        {
            int n = 0;
            foreach (var r in _recs.Values)
                if (r.View == view && (!nonTerminalOnly || !r.Terminal)) n++;
            return n;
        }

        private void Retire(Rec r, string why)
        {
            if (r.Retired != null) return;
            r.Retired = why;
            if (why == "revive" || why == "stale-verdict") r.PendingDropped += r.Pending.Count;
            _recs.Remove(Key(r.View, r.Stream));
            RetiredLog.Add(r);
        }

        /// <summary>Above the per-view count, evict that view's TERMINAL records,
        /// oldest first. A record that is current, next, ending, pending or
        /// unapplied is never evicted here: it leaves by retirement only.</summary>
        private void EvictTerminal(int view)
        {
            int total = CountForView(view, false);
            if (total <= EvictTerminalAbovePerView) return;
            var victims = new List<Rec>();
            foreach (var r in _recs.Values)
                if (r.View == view && r.Terminal) victims.Add(r);
            victims.Sort((a, b) => a.Seq.CompareTo(b.Seq));
            for (int i = 0; i < victims.Count && total > EvictTerminalAbovePerView; i++, total--)
                Retire(victims[i], "evict");
        }

        private Rec Create(int view, int stream, LifeEpoch s, object payload)
        {
            if (CountForView(view, true) >= NonTerminalCeilingPerView) return null;
            var r = new Rec { View = view, Stream = stream, Life = s, Payload = payload, Seq = ++_seq };
            r.Cls0 = Classify(view, s);
            _recs[Key(view, stream)] = r;
            EvictTerminal(view);
            return r;
        }

        /// <summary>A v3 header: creates the record if absent (a repeat never
        /// overwrites one) and treats the header as tick 0's verdict. Null when
        /// this seat refused to hold a new record (the memory backstop).</summary>
        internal Rec OnHeader(int view, int stream, LifeEpoch s, bool blocked0, object payload, bool live, ILedgerApplier ap)
        {
            Rec r = Find(view, stream);
            if (r == null)
            {
                r = Create(view, stream, s, payload);
                if (r == null) return null;
            }
            else r.Duplicates++;
            OnVerdict(r, 0, blocked0, live, ap);
            return r;
        }

        /// <summary>A v3 tick. False when this seat holds no record for the
        /// stream (missed header, retired or refused): nothing is applied.</summary>
        internal bool OnTick(int view, int stream, int tick, bool blocked, bool live, ILedgerApplier ap)
        {
            Rec r = Find(view, stream);
            if (r == null) return false;
            OnVerdict(r, tick, blocked, live, ap);
            return true;
        }

        private void OnVerdict(Rec r, int k, bool blocked, bool live, ILedgerApplier ap)
        {
            if (k < 0 || k >= MaxTick) { r.OutOfRange++; return; }
            if (r.Committed.Contains(k) || r.Blocked.Contains(k) || r.Applied.Contains(k)) { r.Duplicates++; return; }
            if (blocked) { r.Blocked.Add(k); return; }          // consumed, as today
            r.Committed.Add(k);
            LifeClass cls = Classify(r.View, r.Life);
            if (cls == LifeClass.Ending) r.AfterSignal++;
            if (cls == LifeClass.Stale) { Retire(r, "stale-verdict"); return; }
            if (cls == LifeClass.Next) { r.Pending.Add(k); return; }
            if (!live) { r.Pending.Add(k); return; }
            if (cls == LifeClass.Current) Fill(r.View, true, ap);   // earlier deferred ticks first
            r.Applied.Add(k);
            try { ap.Regular(r, k); } catch { r.Exceptions++; }
        }

        /// <summary>The victim's end-of-stream catch-up: every committed tick
        /// this seat does not hold goes to Pending and only Fill applies it, so
        /// a summary for a life this seat is no longer in is never applied.</summary>
        internal Rec OnSummary(int view, int stream, LifeEpoch s, int ticks, byte[] committed, byte[] blocked,
                               object payload, bool live, ILedgerApplier ap)
        {
            Rec r = Find(view, stream);
            if (r == null)
            {
                r = Create(view, stream, s, payload);
                if (r == null) return null;
            }
            if (!r.Life.SameAs(s)) { r.SummaryMismatch++; return r; }
            r.SummarySeen = true;
            int n = ticks < 0 ? 0 : (ticks > MaxTick ? MaxTick : ticks);
            for (int k = 0; k < n; k++)
            {
                bool c = Bit(committed, k), bl = Bit(blocked, k);
                if (c == bl) continue;                               // neither, or malformed both
                if (r.Committed.Contains(k) || r.Blocked.Contains(k) || r.Applied.Contains(k)) continue;
                if (bl) { r.Blocked.Add(k); continue; }
                r.Committed.Add(k);
                r.Pending.Add(k);
                r.CatchUp++;
            }
            if (Classify(view, r.Life) == LifeClass.Stale) { Retire(r, "stale-verdict"); return r; }
            Fill(view, live, ap);
            return r;
        }

        internal static bool Bit(byte[] mask, int k)
        {
            if (mask == null || k < 0 || (k >> 3) >= mask.Length) return false;
            return (mask[k >> 3] & (1 << (k & 7))) != 0;
        }

        internal static byte[] Mask(IEnumerable<int> ticks, int count)
        {
            var m = new byte[(Math.Max(0, Math.Min(count, MaxTick)) + 7) / 8];
            foreach (int k in ticks)
                if (k >= 0 && (k >> 3) < m.Length) m[k >> 3] |= (byte)(1 << (k & 7));
            return m;
        }

        /// <summary>Corrective application of every pending tick of the view's
        /// CURRENT records, in tick order, while the replica is live. Never a
        /// NEXT, ENDING or STALE record.</summary>
        internal int Fill(int view, bool live, ILedgerApplier ap)
        {
            if (!live) return 0;
            var mine = new List<Rec>();
            foreach (var r in _recs.Values)
                if (r.View == view && r.Pending.Count > 0 && Classify(view, r.Life) == LifeClass.Current) mine.Add(r);
            mine.Sort((a, b) => a.Seq.CompareTo(b.Seq));
            int n = 0;
            foreach (var r in mine)
            {
                var ticks = new List<int>(r.Pending);
                foreach (int k in ticks)
                {
                    r.Pending.Remove(k);
                    r.Applied.Add(k);
                    r.Filled++;
                    n++;
                    try { ap.Corrective(r, k); } catch { r.Exceptions++; }
                }
            }
            return n;
        }

        /// <summary>A local Revive of the view: the replica now lives in the
        /// life after the latest boundary this seat has seen. Records of an
        /// older life retire; next-life records become current (Fill applies
        /// them once the replica is live).</summary>
        internal void OnRevive(int view)
        {
            var l = Life(view);
            int b;
            if (BoundaryFor(view, out b)) { l.FenceState = 2; l.Fence = b; }
            else l.FenceState = 1;
            var stale = new List<Rec>();
            foreach (var r in _recs.Values)
                if (r.View == view && Classify(view, r.Life) == LifeClass.Stale) stale.Add(r);
            foreach (var r in stale) Retire(r, "revive");
        }

        /// <summary>Views holding pending ticks (the shell's per-frame fill).</summary>
        internal List<int> ViewsWithPending()
        {
            var v = new List<int>();
            foreach (var r in _recs.Values)
                if (r.Pending.Count > 0 && !v.Contains(r.View)) v.Add(r.View);
            return v;
        }

        /// <summary>Room exit: every held record retires (one evidence line
        /// each), then all state goes.</summary>
        internal void Clear()
        {
            foreach (var r in new List<Rec>(_recs.Values)) Retire(r, "room-exit");
            _recs.Clear();
            _lives.Clear();
            _hasPoint = false;
            _point = 0;
            _openUntil.Clear();
        }

        // ── Header parsing (pure) ──────────────────────────────────────────

        /// <summary>A header is v3 only with BOTH trailing elements present and
        /// typed: index 15 an int stamp and index 16 a bool. Anything else is
        /// today's 15-element header and today's path.</summary>
        internal static bool TryV3Epoch(int length, object e15, object e16, out LifeEpoch s)
        {
            s = default(LifeEpoch);
            if (length < 17 || !(e15 is int) || !(e16 is bool)) return false;
            s = (bool)e16 ? LifeEpoch.At((int)e15) : default(LifeEpoch);
            return true;
        }

        // ── Victim-side admission bound (deterministic at the authority) ────

        internal const int MaxOpenV3StreamsPerVictim = 64;
        private readonly List<long> _openUntil = new List<long>();

        /// <summary>The victim stamps v3 on at most 64 concurrently open streams
        /// (each held until its scheduled end plus one second); past that its
        /// header is today's, which every receiver then treats as today's.</summary>
        internal bool AdmitV3Stream(long nowMs, long untilMs)
        {
            _openUntil.RemoveAll(u => u < nowMs);
            if (_openUntil.Count >= MaxOpenV3StreamsPerVictim) return false;
            _openUntil.Add(untilMs);
            return true;
        }
    }

    // ── Start claims ───────────────────────────────────────────────────────

    internal enum StartPath { Claim, Broadcast }

    internal sealed class ClaimFacts
    {
        internal int Sender, ClaimId, VictimView, ProjOwner, PoisonChildren;
        internal long ProjInstance, NowMs;
        internal bool GateOn, VictimFound, VictimIsMine, ProjFound, Live, VictimFenceKnown;
        internal string GateWhy;
        internal LifeEpoch ShooterEpoch, VictimEpoch;
    }

    internal sealed class ClaimCore
    {
        internal const int ClaimsPerRollingSecond = 32;
        internal const long RollingWindowMs = 1000;
        internal const int StartedCap = 4096;
        internal const int PairCap = 4096;

        private int _nextClaimId;
        private readonly HashSet<long> _sentPairs = new HashSet<long>();
        private readonly Queue<long> _sentPairOrder = new Queue<long>();
        private readonly Queue<long> _sendTimes = new Queue<long>();

        private readonly Dictionary<int, int> _highWater = new Dictionary<int, int>();
        private readonly Dictionary<int, Queue<long>> _recvTimes = new Dictionary<int, Queue<long>>();
        private readonly Dictionary<long, StartPath> _started = new Dictionary<long, StartPath>();
        private readonly Queue<long> _startedOrder = new Queue<long>();

        internal static long PairKey(long projInstance, int victimView) { return (projInstance << 32) ^ (uint)victimView; }

        /// <summary>The shooter's decision for one local-only poison arm. Every
        /// arm gets a claim id. Null means "raise it now"; anything else is the
        /// drop reason. The pair is marked BEFORE the raise and never cleared,
        /// so a refused or failed send is never retried.</summary>
        internal string ShooterArm(bool v3On, string offWhy, bool victimFenceKnown, long projInstance, int victimView,
                                   long nowMs, out int claimId)
        {
            claimId = ++_nextClaimId;
            if (!v3On) return "v3-off:" + (offWhy ?? "unknown");
            if (!victimFenceKnown) return "no-life";
            long key = PairKey(projInstance, victimView);
            if (_sentPairs.Contains(key)) return "pair-marked";
            _sentPairs.Add(key);
            _sentPairOrder.Enqueue(key);
            while (_sentPairOrder.Count > PairCap) _sentPairs.Remove(_sentPairOrder.Dequeue());
            while (_sendTimes.Count > 0 && _sendTimes.Peek() <= nowMs - RollingWindowMs) _sendTimes.Dequeue();
            if (_sendTimes.Count >= ClaimsPerRollingSecond) return "rate";
            _sendTimes.Enqueue(nowMs);
            return null;
        }

        /// <summary>The victim's decision for one syntactically valid claim.
        /// The sender's claim id is consumed FIRST, so every claim has a
        /// terminal result before this returns and a repeat is "dup" whatever
        /// the first one's result was. "started" means start it now.</summary>
        internal string VictimDecide(ClaimFacts f)
        {
            int hw;
            if (_highWater.TryGetValue(f.Sender, out hw) && !PoisonLedgerCore.After(f.ClaimId, hw)) return "dup";
            _highWater[f.Sender] = f.ClaimId;

            Queue<long> q;
            if (!_recvTimes.TryGetValue(f.Sender, out q)) { q = new Queue<long>(); _recvTimes[f.Sender] = q; }
            while (q.Count > 0 && q.Peek() <= f.NowMs - RollingWindowMs) q.Dequeue();
            q.Enqueue(f.NowMs);
            bool overRate = q.Count > ClaimsPerRollingSecond;

            if (!f.GateOn) return "gate:" + (f.GateWhy ?? "unknown");
            if (!f.VictimFound || !f.VictimIsMine) return "not-victim";
            if (!f.ProjFound) return "no-projectile";
            if (f.ProjOwner != f.Sender) return "not-owner";
            if (f.PoisonChildren <= 0) return "no-poison";
            if (!f.Live) return "not-live";
            if (!f.VictimFenceKnown || !f.ShooterEpoch.SameAs(f.VictimEpoch)) return "fence";
            if (overRate) return "rate";
            if (!TryStart(f.ProjInstance, f.VictimView, StartPath.Claim)) return "dup-broadcast";
            return "started";
        }

        /// <summary>The one start decision both paths share, per (projectile
        /// instance, victim view). A claim starts only an untouched pair. A
        /// broadcast hit proceeds on an untouched pair or one broadcast hits
        /// already started (a bullet that hits twice poisons twice, as in
        /// vanilla), and loses only to a claim.</summary>
        internal bool TryStart(long projInstance, int victimView, StartPath path)
        {
            long key = PairKey(projInstance, victimView);
            StartPath had;
            if (!_started.TryGetValue(key, out had))
            {
                _started[key] = path;
                _startedOrder.Enqueue(key);
                while (_startedOrder.Count > StartedCap) _started.Remove(_startedOrder.Dequeue());
                return true;
            }
            return path == StartPath.Broadcast && had == StartPath.Broadcast;
        }

        internal void Clear()
        {
            _sentPairs.Clear(); _sentPairOrder.Clear(); _sendTimes.Clear();
            _highWater.Clear(); _recvTimes.Clear(); _started.Clear(); _startedOrder.Clear();
        }
    }

    // ── Activation: an acknowledged exact roster while joins are closed ─────

    internal sealed class ActivationCore
    {
        /// <summary>An activation not fully acknowledged by then is killed on
        /// this seat, so the master can offer a fresh one.</summary>
        internal const long AckTimeoutMs = 15000;

        private int _master = -1, _aid;
        private int[] _roster;
        private readonly HashSet<int> _acks = new HashSet<int>();
        private bool _killed;
        private string _killWhy;
        private long _receivedMs;

        internal int Aid { get { return _roster != null ? _aid : 0; } }
        internal int RosterSize { get { return _roster != null ? _roster.Length : 0; } }
        internal bool Live { get { return _roster != null && !_killed; } }

        /// <summary>An ACTIVATE counts only from the actor who is master when it
        /// arrives; it replaces any earlier activation.</summary>
        internal bool OnActivate(int sender, int currentMaster, int aid, int[] roster, long nowMs)
        {
            if (sender != currentMaster || roster == null || roster.Length == 0) return false;
            _master = sender; _aid = aid;
            _roster = (int[])roster.Clone();
            Array.Sort(_roster);
            _acks.Clear();
            _killed = false; _killWhy = null;
            _receivedMs = nowMs;
            return true;
        }

        internal void OnAck(int sender, int master, int aid)
        {
            if (_roster == null || master != _master || aid != _aid) return;
            if (Array.IndexOf(_roster, sender) >= 0) _acks.Add(sender);
        }

        /// <summary>A seat acknowledges only an exact match: the room closed,
        /// its present actors equal to the roster, every one carrying cr_pois3.</summary>
        internal bool ShouldAck(bool roomClosed, int[] present, Func<int, bool> cap3)
        {
            if (_roster == null || _killed || !roomClosed || present == null) return false;
            var p = (int[])present.Clone();
            Array.Sort(p);
            if (p.Length != _roster.Length) return false;
            for (int i = 0; i < p.Length; i++) if (p[i] != _roster[i] || !cap3(p[i])) return false;
            return true;
        }

        /// <summary>The v3 decision, re-read at every use. A cap missing on a
        /// present actor, an open room, or a present actor outside the roster
        /// kills the activation for good on this seat.</summary>
        internal bool Evaluate(bool roomClosed, int[] present, Func<int, bool> cap3, long nowMs, out string why)
        {
            if (present != null)
                foreach (int a in present)
                    if (!cap3(a)) { Kill("cap-missing actor=" + a); why = "cap-missing actor=" + a; return false; }
            if (!roomClosed) { Kill("room-open"); why = "room-open"; return false; }
            if (_roster == null) { why = "no-activation"; return false; }
            if (_killed) { why = "killed:" + _killWhy; return false; }
            if (present != null)
                foreach (int a in present)
                    if (Array.IndexOf(_roster, a) < 0) { Kill("roster-change actor=" + a); why = "killed:" + _killWhy; return false; }
            int acked = 0;
            foreach (int a in _roster) if (_acks.Contains(a)) acked++;
            if (acked < _roster.Length)
            {
                // A roster actor that left before acknowledging, or acks that
                // never completed, can never arm this activation: retire it.
                foreach (int a in _roster)
                    if (!_acks.Contains(a) && present != null && Array.IndexOf(present, a) < 0)
                    { Kill("unacked-left actor=" + a); why = "killed:" + _killWhy; return false; }
                if (nowMs - _receivedMs >= AckTimeoutMs) { Kill("ack-timeout"); why = "killed:" + _killWhy; return false; }
                why = "not-acked " + acked + "/" + _roster.Length;
                return false;
            }
            why = "on a=" + _aid + " roster=" + _roster.Length;
            return true;
        }

        private void Kill(string why)
        {
            if (_roster == null || _killed) return;
            _killed = true;
            _killWhy = why;
        }

        internal void Clear()
        {
            _master = -1; _aid = 0; _roster = null; _acks.Clear(); _killed = false; _killWhy = null;
        }
    }
}
