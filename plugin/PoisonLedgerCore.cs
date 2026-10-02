// PoisonLedgerCore.cs -- the pure decisions of poison convergence v3 (bugs 406
// and 407): the room-common life epoch and the classification of a stream
// against it, the receiver ledger (each committed tick applied at most once),
// the catch-up summary, the start-claim decisions on both ends, and the
// activation rule. No Unity, Photon or Harmony type appears here, so
// tools/tests/poison-ledger compiles this exact file and drives it; PoisonSync
// feeds it what the game and the network say and executes what it returns.
//
// Design record: ai-collab/v1410/POISON-CONVERGENCE-DESIGN-V2.md as amended by
// POISON-CONVERGENCE-AMENDMENTS-V3.md and -V4.md (local notes, not shipped).

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
        internal const int HeldCeilingPerView = 1024;         // nothing is evicted: past this a new record is refused

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
        private bool _pointAdopted;   // the latest point came from an ACTIVATE, not from this seat's own RPC
        private bool _broken;         // V4 B4: an unstamped boundary was seen; no record is created again
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

        /// <summary>This seat executed a point boundary RPC with this stamp.
        /// The latest stamp wins; executing the one it had adopted makes the
        /// point this seat's own (A1's rule applies to it from then on).</summary>
        internal void NotePointBoundary(int ts)
        {
            if (_hasPoint && !After(ts, _point)) { if (ts == _point) _pointAdopted = false; return; }
            _point = ts; _hasPoint = true; _pointAdopted = false;
        }

        /// <summary>V4 B1: the point epoch named by the current master's
        /// ACTIVATE. The seat takes it when it holds no boundary or an older
        /// one (the stamp is the boundary RPC's own), and remembers that it did
        /// not execute that RPC itself.</summary>
        internal void AdoptPoint(int ts)
        {
            if (_hasPoint && !After(ts, _point)) return;
            _point = ts; _hasPoint = true; _pointAdopted = true;
        }

        /// <summary>This seat's point epoch: the latest point boundary it holds.</summary>
        internal LifeEpoch PointEpoch { get { return _hasPoint ? LifeEpoch.At(_point) : default(LifeEpoch); } }

        /// <summary>A life lies in this seat's current point: before the first
        /// boundary any life does; after it, the boundary's own stamp or a later
        /// (Phoenix) one.</summary>
        internal bool InPoint(LifeEpoch s)
        {
            if (!_hasPoint) return true;
            return s.Set && (s.Ts == _point || After(s.Ts, _point));
        }

        /// <summary>V4 B2: a seat that adopted its point (it had not executed
        /// that boundary RPC when the ACTIVATE arrived, as a joiner has not)
        /// and has never revived the view takes the view's life from
        /// the owner's own record, when that life lies in the point. A seat
        /// that executed the boundary RPC itself keeps A1's rule.</summary>
        private void AdoptLife(int view, LifeEpoch s)
        {
            if (!_pointAdopted || !s.Set || !InPoint(s)) return;
            var l = Life(view);
            if (l.FenceState != 0) return;
            if (After(s.Ts, _point)) NotePhoenixBoundary(view, s.Ts);
            l.FenceState = 2; l.Fence = s.Ts;
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

        private int CountForView(int view)
        {
            int n = 0;
            foreach (var r in _recs.Values) if (r.View == view) n++;
            return n;
        }

        private void Retire(Rec r, string why)
        {
            if (r.Retired != null) return;
            r.Retired = why;
            if (why == "revive" || why == "stale-verdict" || why == "epoch-broken") r.PendingDropped += r.Pending.Count;
            _recs.Remove(Key(r.View, r.Stream));
            RetiredLog.Add(r);
        }

        /// <summary>No record is ever evicted (V4 B5): a record leaves by
        /// retirement only (stale, revive, unstamped boundary, room exit). Past
        /// the per-view ceiling, or once an unstamped boundary was seen, a new
        /// record is refused and the stream is not applied on this seat.</summary>
        private Rec Create(int view, int stream, LifeEpoch s, object payload)
        {
            if (_broken || CountForView(view) >= HeldCeilingPerView) return null;
            AdoptLife(view, s);
            var r = new Rec { View = view, Stream = stream, Life = s, Payload = payload, Seq = ++_seq };
            r.Cls0 = Classify(view, s);
            _recs[Key(view, stream)] = r;
            return r;
        }

        /// <summary>V4 B4: a boundary seen without its stamp. Every record held
        /// for the views it ends (view &lt; 0: every view) retires now with its
        /// pending ticks dropped, and no record is created again in this room.</summary>
        internal void Break(int view)
        {
            _broken = true;
            var gone = new List<Rec>();
            foreach (var r in _recs.Values) if (view < 0 || r.View == view) gone.Add(r);
            foreach (var r in gone) Retire(r, "epoch-broken");
        }

        internal bool Broken { get { return _broken; } }

        /// <summary>Fix pass 2 (H2): one fence (a point boundary, a Phoenix
        /// boundary or a revive) as its hook records it. record() returns true
        /// when the fence is recorded. False (the boundary RPC carried no
        /// stamp) or a fault inside it is a fence this seat could not record:
        /// every held record of the views that fence ends (view &lt; 0: every
        /// view) retires now with its pending ticks dropped, and no record is
        /// created again in the room (Break), so nothing held from before the
        /// fence can move health after it. True when recorded.</summary>
        internal bool Fence(int view, Func<bool> record)
        {
            bool ok;
            try { ok = record(); } catch { ok = false; }
            if (!ok) Break(view);
            return ok;
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
            _pointAdopted = false;
            _broken = false;
            _openUntil.Clear();
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
        internal int Sender, ClaimId, VictimView, ProjView, ProjOwner, PoisonChildren;
        internal long ProjInstance, NowMs;
        internal bool GateOn, SenderAcked, VictimFound, VictimIsMine, ProjFound, Live, VictimFenceKnown;
        internal string GateWhy;
        internal LifeEpoch ShooterEpoch, VictimEpoch;
    }

    internal sealed class ClaimCore
    {
        internal const int ClaimsPerRollingSecond = 32;
        internal const long RollingWindowMs = 1000;
        // V4 B5: marks are durable for the room. Past either bound the seat
        // stops sending (pair marks) or stops starting claims (starts): it
        // never forgets a mark.
        internal const int StartedCap = 16384;
        internal const int PairCap = 16384;

        private int _nextClaimId;
        private readonly HashSet<long> _sentPairs = new HashSet<long>();
        private readonly Queue<long> _sendTimes = new Queue<long>();

        private readonly Dictionary<int, int> _highWater = new Dictionary<int, int>();
        private readonly Dictionary<int, Queue<long>> _recvTimes = new Dictionary<int, Queue<long>>();
        private readonly Dictionary<long, StartPath> _started = new Dictionary<long, StartPath>();
        private bool _saturated;      // no claim starts again in this room
        private int _claimStarts;

        internal static long PairKey(long projInstance, int victimView) { return (projInstance << 32) ^ (uint)victimView; }

        /// <summary>The shooter's decision for one local-only poison arm. Every
        /// arm gets a claim id. Null means "raise it now"; anything else is the
        /// drop reason. The pair is marked BEFORE the raise and never cleared,
        /// so a refused or failed send is never retried; past PairCap marks an
        /// arm sends nothing.</summary>
        internal string ShooterArm(bool v3On, string offWhy, bool ownerAcked, bool victimFenceKnown, long projInstance,
                                   int victimView, long nowMs, out int claimId)
        {
            claimId = ++_nextClaimId;
            if (!v3On) return "v3-off:" + (offWhy ?? "unknown");
            if (!ownerAcked) return "owner-not-acked";
            if (!victimFenceKnown) return "no-life";
            long key = PairKey(projInstance, victimView);
            if (_sentPairs.Contains(key)) return "pair-marked";
            if (_sentPairs.Count >= PairCap) return "pair-cap";
            _sentPairs.Add(key);
            while (_sendTimes.Count > 0 && _sendTimes.Peek() <= nowMs - RollingWindowMs) _sendTimes.Dequeue();
            if (_sendTimes.Count >= ClaimsPerRollingSecond) return "rate";
            _sendTimes.Enqueue(nowMs);
            return null;
        }

        /// <summary>The sender's claim id is consumed: "dup" for an id at or
        /// below the sender's high water, else null (the high water moves to it).</summary>
        private string Consume(int sender, int claimId)
        {
            int hw;
            if (_highWater.TryGetValue(sender, out hw) && !PoisonLedgerCore.After(claimId, hw)) return "dup";
            _highWater[sender] = claimId;
            return null;
        }

        /// <summary>A claim the rate admission let through, past its type
        /// checks (V4 B6): the id is consumed first, then the facts are
        /// collected; a fault while collecting is the terminal result
        /// "fault:&lt;type&gt;". Every path returns one named result, and a
        /// repeat of the id is "dup" whatever the first got. The rate is not
        /// read here: fix pass 2 (M2) takes it in AdmitRate, ahead of every
        /// per-claim step, so nowMs only names the receive time.</summary>
        internal string Handle(int sender, int claimId, long nowMs, Func<ClaimFacts> collect, out ClaimFacts facts)
        {
            facts = null;
            string dup = Consume(sender, claimId);
            if (dup != null) return dup;
            try { facts = collect(); }
            catch (Exception ex) { return "fault:" + ex.GetType().Name; }
            if (facts == null) return "fault:no-facts";
            return Decide(facts);
        }

        /// <summary>A claim with its facts already in hand, behind the same rate
        /// admission as Receive: past the rate it is "rate" (counted, its id
        /// consumed), else Handle.</summary>
        internal string VictimDecide(ClaimFacts f)
        {
            int sender = f.Sender;
            if (!AdmitRate(sender, f.NowMs))
            {
                Refuse(sender, f.NowMs, new object[] { V3Wire.TypeClaim, V3Wire.Protocol, f.VictimView, f.ProjView, f.ClaimId });
                return "rate";
            }
            ClaimFacts got;
            return Handle(sender, f.ClaimId, f.NowMs, () => f, out got);
        }

        // ── Received claims: the rate first, then one line each (fix pass 2, M1, M2) ──

        /// <summary>The claims of one sender past the rate in one aligned
        /// second: their count, the first and the last payload (their tuples
        /// are read only when the line is written), and the sender's running
        /// total for the room.</summary>
        private sealed class Excess
        {
            internal long Second;
            internal int Count;
            internal object[] First, Last;
            internal long Total;
        }

        private readonly Dictionary<int, Excess> _excess = new Dictionary<int, Excess>();
        private long _roomExcess;

        /// <summary>The claim evidence lines, in order, for the shell to write
        /// and clear: one per claim Receive admitted, one per sender and aligned
        /// second that had claims past the rate (VictimDecide writes none).</summary>
        internal readonly List<string> Lines = new List<string>();

        /// <summary>The aligned second a receive time lies in.</summary>
        internal static long SecondOf(long ms)
        {
            return ms >= 0 ? ms / RollingWindowMs : (ms - (RollingWindowMs - 1)) / RollingWindowMs;
        }

        /// <summary>A payload field as the tuple shows it: -1 unless the
        /// payload carries an int there.</summary>
        internal static int Field(object[] a, int i)
        {
            return a != null && i < a.Length && a[i] is int ? (int)a[i] : -1;
        }

        /// <summary>Fix pass 2 (M2): the receive-side admission, per sender and
        /// per room, taken before any per-claim step. At most
        /// ClaimsPerRollingSecond claims of one sender are admitted in any
        /// rolling second (the window holds admitted claims only, so excess
        /// traffic never extends it). False: refused.</summary>
        internal bool AdmitRate(int sender, long nowMs)
        {
            Queue<long> q;
            if (!_recvTimes.TryGetValue(sender, out q)) { q = new Queue<long>(); _recvTimes[sender] = q; }
            while (q.Count > 0 && q.Peek() <= nowMs - RollingWindowMs) q.Dequeue();
            if (q.Count >= ClaimsPerRollingSecond) return false;
            q.Enqueue(nowMs);
            return true;
        }

        /// <summary>A claim past the rate: its terminal result is "rate". Its
        /// id is consumed when the payload carries one (a repeat is "dup"), and
        /// it is counted in the sender's aggregate for its aligned second; that
        /// aggregate is one line, written by the first FlushRate after its
        /// second ends (the shell's upkeep, about once a second; the next
        /// admitted claim; or that sender's next claim past the rate in a later
        /// second), or at room exit.</summary>
        private void Refuse(int sender, long nowMs, object[] a)
        {
            if (a != null && a.Length > 4 && a[4] is int) Consume(sender, (int)a[4]);
            Excess x;
            if (!_excess.TryGetValue(sender, out x)) { x = new Excess(); _excess[sender] = x; }
            long sec = SecondOf(nowMs);
            if (x.Count > 0 && x.Second != sec) Flush(sender, x);
            if (x.Count == 0) { x.Second = sec; x.First = a; }
            x.Count++;
            x.Last = a;
            x.Total++;
            _roomExcess++;
        }

        private void Flush(int sender, Excess x)
        {
            Lines.Add(ClaimLine.Rate(sender, x.Second, x.Count, x.First, x.Last, x.Total, _roomExcess));
            x.Count = 0;
            x.First = null;
            x.Last = null;
        }

        /// <summary>Writes the aggregate of every sender whose second has ended
        /// before nowMs's (every pending one when all: room exit).</summary>
        internal void FlushRate(long nowMs, bool all)
        {
            long sec = SecondOf(nowMs);
            foreach (var kv in _excess)
                if (kv.Value.Count > 0 && (all || kv.Value.Second < sec)) Flush(kv.Key, kv.Value);
        }

        /// <summary>One claim event that reached the dispatcher (fix pass 2, M1
        /// and M2), end to end. The rate admission comes first, before any
        /// per-claim step, a truncated payload included. An admitted claim gets
        /// exactly one line: its tuple (sender, claim, projectile, victim; -1
        /// for a field the payload does not carry as an int) and one named
        /// terminal result -- "malformed" for a payload short of its nine typed
        /// elements, "fault:&lt;type&gt;" for a fault anywhere, else Handle's
        /// result, where start(claim id) runs a started claim and names the
        /// streams it opened. fill() is the fact collection Handle runs after
        /// the id is consumed.</summary>
        internal void Receive(int sender, object[] a, long nowMs, Action<ClaimFacts> fill, Func<int, string> start)
        {
            if (!AdmitRate(sender, nowMs)) { Refuse(sender, nowMs, a); return; }
            FlushRate(nowMs, false);
            int victim = -1, proj = -1, claimId = -1;
            string outcome;
            try
            {
                victim = Field(a, 2);
                proj = Field(a, 3);
                claimId = Field(a, 4);
                if (a == null || a.Length < 9 || !(a[2] is int) || !(a[3] is int) || !(a[4] is int) || !(a[5] is int)
                    || !(a[6] is byte) || !(a[7] is int) || !(a[8] is bool))
                    outcome = ClaimLine.Outcome("malformed");
                else
                {
                    var shooterEpoch = (bool)a[8] ? LifeEpoch.At((int)a[7]) : default(LifeEpoch);
                    int v = victim, p = proj, id = claimId;
                    ClaimFacts f;
                    string result = Handle(sender, claimId, nowMs, () =>
                    {
                        var c = new ClaimFacts
                        {
                            Sender = sender, ClaimId = id, VictimView = v, ProjView = p, NowMs = nowMs,
                            ShooterEpoch = shooterEpoch,
                        };
                        fill(c);
                        return c;
                    }, out f);
                    outcome = result == "started" ? start(claimId) : ClaimLine.Outcome(result);
                }
            }
            catch (Exception ex) { outcome = ClaimLine.Outcome("fault:" + ex.GetType().Name); }
            Lines.Add(ClaimLine.Recv(sender, claimId, proj, victim, outcome));
        }

        private string Decide(ClaimFacts f)
        {
            if (!f.GateOn) return "gate:" + (f.GateWhy ?? "unknown");
            if (!f.SenderAcked) return "sender-not-acked";
            if (!f.VictimFound || !f.VictimIsMine) return "not-victim";
            if (!f.ProjFound) return "no-projectile";
            if (f.ProjOwner != f.Sender) return "not-owner";
            if (f.PoisonChildren <= 0) return "no-poison";
            if (!f.Live) return "not-live";
            if (!f.VictimFenceKnown || !f.ShooterEpoch.SameAs(f.VictimEpoch)) return "fence";
            if (!TryStart(f.ProjInstance, f.VictimView, StartPath.Claim)) return _saturated ? "start-refused" : "dup-broadcast";
            return "started";
        }

        /// <summary>The one start decision both paths share, per (projectile
        /// instance, victim view), durable for the room. A claim starts only an
        /// untouched pair and is recorded before it starts. A broadcast hit
        /// proceeds on an untouched pair or one broadcast hits already started
        /// (a bullet that hits twice poisons twice, as in vanilla), and loses
        /// only to a claim. Past StartedCap a broadcast on an untouched pair
        /// proceeds unrecorded and the seat is saturated: no claim starts again,
        /// so no claim can follow an unrecorded broadcast.</summary>
        internal bool TryStart(long projInstance, int victimView, StartPath path)
        {
            long key = PairKey(projInstance, victimView);
            StartPath had;
            if (_started.TryGetValue(key, out had))
                return path == StartPath.Broadcast && had == StartPath.Broadcast;
            if (path == StartPath.Claim)
            {
                if (_saturated || _started.Count >= StartedCap) { _saturated = true; return false; }
                _started[key] = path;
                _claimStarts++;
                return true;
            }
            if (_started.Count >= StartedCap) { _saturated = true; return true; }
            _started[key] = path;
            return true;
        }

        /// <summary>The poison-effect prefix faulted before its start decision.
        /// With a claim started in this room the effect is skipped (it may be
        /// that claim's pair); otherwise it runs as vanilla, unrecorded, and the
        /// seat is saturated so no claim can start after it.</summary>
        internal bool FaultBeforeStart()
        {
            if (_claimStarts > 0) return false;
            _saturated = true;
            return true;
        }

        internal bool Saturated { get { return _saturated; } }

        internal void Clear()
        {
            _sentPairs.Clear(); _sendTimes.Clear();
            _highWater.Clear(); _recvTimes.Clear(); _started.Clear();
            _saturated = false; _claimStarts = 0;
            _excess.Clear(); _roomExcess = 0; Lines.Clear();
        }
    }

    // ── Activation (A2b): an acknowledged roster of FIGHTERS; rooms stay open ─

    internal sealed class ActivationCore
    {
        /// <summary>An activation not fully acknowledged by then is killed on
        /// this seat, so the master can offer a fresh one.</summary>
        internal const long AckTimeoutMs = 15000;

        private int _master = -1, _aid;
        private LifeEpoch _epoch;                    // V4 B1: the point the activation is bound to
        private bool _hasAckedPoint;                 // this seat acknowledged an activation at _ackedPoint
        private LifeEpoch _ackedPoint;
        private int[] _roster;                       // the fighters, sorted
        private readonly HashSet<int> _acks = new HashSet<int>();
        private bool _killed;
        private string _killWhy;
        private long _receivedMs;

        internal int Aid { get { return _roster != null ? _aid : 0; } }
        internal int RosterSize { get { return _roster != null ? _roster.Length : 0; } }
        internal bool Live { get { return _roster != null && !_killed; } }
        internal LifeEpoch Epoch { get { return _epoch; } }

        /// <summary>Live and bound to this point epoch.</summary>
        internal bool BoundTo(LifeEpoch point) { return Live && _epoch.SameAs(point); }

        /// <summary>An ACTIVATE counts only from the actor who is master when it
        /// arrives; it replaces any earlier activation and its acknowledgements,
        /// and it is bound to the master's point epoch.</summary>
        internal bool OnActivate(int sender, int currentMaster, int aid, int[] fighters, LifeEpoch point, long nowMs)
        {
            if (sender != currentMaster || fighters == null || fighters.Length == 0) return false;
            _master = sender; _aid = aid; _epoch = point;
            _roster = (int[])fighters.Clone();
            Array.Sort(_roster);
            _acks.Clear();
            _killed = false; _killWhy = null;
            _receivedMs = nowMs;
            return true;
        }

        /// <summary>An acknowledgement of the current activation, from a fighter
        /// or a spectator. A spectator's acknowledgement only makes it a v3
        /// addressee; it is never required. True the first time this sender
        /// acknowledges this activation (the victim then replays to it).</summary>
        internal bool OnAck(int sender, int master, int aid)
        {
            if (_roster == null || master != _master || aid != _aid) return false;
            return _acks.Add(sender);
        }

        /// <summary>This seat sent its acknowledgement of the current activation.</summary>
        internal void NoteSelfAck() { if (_roster != null) { _ackedPoint = _epoch; _hasAckedPoint = true; } }

        /// <summary>V4 B1: a seat creates a new v3 record only when it has
        /// acknowledged an activation bound to its current point epoch.</summary>
        internal bool AcceptsAt(LifeEpoch point) { return _hasAckedPoint && _ackedPoint.SameAs(point); }

        /// <summary>A player entered or left the room, or a cr_pois3 property
        /// changed: v3 is off on this seat from now until a fresh activation is
        /// acknowledged by every fighter present.</summary>
        internal void OnRoomEvent(string why) { Kill(why); }

        /// <summary>A seat acknowledges only an exact match: its point epoch is
        /// the activation's, the fighters it sees equal the roster, and every
        /// one carries cr_pois3.</summary>
        internal bool ShouldAck(int[] fighters, Func<int, bool> cap3, LifeEpoch point)
        {
            if (_roster == null || _killed || fighters == null) return false;
            if (!point.SameAs(_epoch)) return false;
            var f = (int[])fighters.Clone();
            Array.Sort(f);
            if (f.Length != _roster.Length) return false;
            for (int i = 0; i < f.Length; i++) if (f[i] != _roster[i] || !cap3(f[i])) return false;
            return true;
        }

        /// <summary>The v3 decision, re-read at every use. A fighter without
        /// cr_pois3, a fighter set different from the roster, or a point epoch
        /// different from the one the activation is bound to (the next point
        /// boundary) kills the activation on this seat. Spectators play no part.</summary>
        internal bool Evaluate(int[] fighters, Func<int, bool> cap3, long nowMs, LifeEpoch point, out string why)
        {
            if (fighters != null)
                foreach (int a in fighters)
                    if (!cap3(a)) { Kill("cap-missing actor=" + a); why = "cap-missing actor=" + a; return false; }
            if (_roster == null) { why = "no-activation"; return false; }
            if (_killed) { why = "killed:" + _killWhy; return false; }
            if (!point.SameAs(_epoch)) { Kill("point-boundary"); why = "killed:" + _killWhy; return false; }
            if (fighters == null || !SameSet(fighters, _roster)) { Kill("roster-change"); why = "killed:" + _killWhy; return false; }
            int acked = 0;
            foreach (int a in _roster) if (_acks.Contains(a)) acked++;
            if (acked < _roster.Length)
            {
                if (nowMs - _receivedMs >= AckTimeoutMs) { Kill("ack-timeout"); why = "killed:" + _killWhy; return false; }
                why = "not-acked " + acked + "/" + _roster.Length;
                return false;
            }
            why = "on a=" + _aid + " fighters=" + _roster.Length;
            return true;
        }

        private static bool SameSet(int[] a, int[] sortedB)
        {
            var x = (int[])a.Clone();
            Array.Sort(x);
            if (x.Length != sortedB.Length) return false;
            for (int i = 0; i < x.Length; i++) if (x[i] != sortedB[i]) return false;
            return true;
        }

        /// <summary>The present actors that acknowledged the live activation:
        /// the only actors a LIFE message or a summary is addressed to.</summary>
        internal int[] AckedPresent(int[] present)
        {
            var r = new List<int>();
            if (Live && present != null)
                foreach (int a in present) if (_acks.Contains(a) && !r.Contains(a)) r.Add(a);
            r.Sort();
            return r.ToArray();
        }

        internal bool IsAcked(int actor) { return Live && _acks.Contains(actor); }

        private void Kill(string why)
        {
            if (_roster == null || _killed) return;
            _killed = true;
            _killWhy = why;
        }

        internal void Clear()
        {
            _master = -1; _aid = 0; _roster = null; _acks.Clear(); _killed = false; _killWhy = null;
            _epoch = default(LifeEpoch); _hasAckedPoint = false; _ackedPoint = default(LifeEpoch);
        }
    }

    // ── Addressing (A2b): who a v3-only message may reach ───────────────────

    internal static class V3Targets
    {
        /// <summary>Present actors carrying cr_pois3=1: the ACTIVATE and ACK
        /// addressees. An actor this seat has not seen join is in no list here,
        /// so nothing v3-only is ever addressed to it.</summary>
        internal static int[] Capable(int[] present, Func<int, bool> cap3)
        {
            var r = new List<int>();
            if (present != null) foreach (int a in present) if (cap3(a)) r.Add(a);
            r.Sort();
            return r.ToArray();
        }

        /// <summary>The master offers an activation only for fighters that all
        /// carry cr_pois3, and only when no join or leave is settling.</summary>
        internal static bool ShouldOffer(int[] fighters, Func<int, bool> cap3, bool settled)
        {
            if (!settled || fighters == null || fighters.Length == 0) return false;
            foreach (int a in fighters) if (!cap3(a)) return false;
            return true;
        }
    }

    // ── The LIFE message inbox (A2b: the epoch rides its own type) ───────────

    internal sealed class EpochInbox
    {
        internal const int Cap = 256;
        private readonly Dictionary<long, LifeEpoch> _byKey = new Dictionary<long, LifeEpoch>();
        private readonly Queue<long> _order = new Queue<long>();

        /// <summary>A LIFE message from the view's owner. It is raised just
        /// before that stream's header on the same reliable channel.</summary>
        internal void Note(int view, int stream, LifeEpoch e)
        {
            long k = PoisonLedgerCore.Key(view, stream);
            if (!_byKey.ContainsKey(k)) _order.Enqueue(k);
            _byKey[k] = e;
            while (_order.Count > Cap) _byKey.Remove(_order.Dequeue());
        }

        /// <summary>At the header: true (once) when this seat holds the
        /// stream's LIFE message. Otherwise the header is today's.</summary>
        internal bool Take(int view, int stream, out LifeEpoch e)
        {
            long k = PoisonLedgerCore.Key(view, stream);
            if (!_byKey.TryGetValue(k, out e)) return false;
            _byKey.Remove(k);
            return true;
        }

        internal int Count { get { return _byKey.Count; } }

        internal void Clear() { _byKey.Clear(); _order.Clear(); }
    }

    // ── Retained point state and replay (V4 B3) ─────────────────────────────

    /// <summary>One stream the victim's seat authored, replayed only while
    /// its life and point are the view's current ones.</summary>
    internal sealed class Kept
    {
        internal int View, Stream;
        internal LifeEpoch Life;
        internal object Payload;                     // the shell's header data
        internal readonly List<int> Committed = new List<int>();
        internal readonly List<int> Blocked = new List<int>();
        internal readonly HashSet<int> Holders = new HashSet<int>();   // actors that hold the stream as v3
        internal int[] PresentAtStart;               // a non-holder among them took today's path
        internal bool Closed;

        /// <summary>Tick count named by a summary: one past the last tick sent.</summary>
        internal int Ticks
        {
            get
            {
                int n = 0;
                foreach (int k in Committed) if (k + 1 > n) n = k + 1;
                foreach (int k in Blocked) if (k + 1 > n) n = k + 1;
                return n;
            }
        }
    }

    /// <summary>The victim's seat keeps, per own view, every v3 stream of its
    /// current life in the current point, and replays each to an actor that
    /// acknowledges late: once per actor and stream, never to a holder, never
    /// to an actor that was present at the stream's start without holding it
    /// (it handled the stream by today's path).</summary>
    internal sealed class PointRetainer
    {
        internal const int MaxKeptPerLife = 256;

        private sealed class ViewKept
        {
            internal LifeEpoch Point, Life;
            internal readonly List<Kept> Streams = new List<Kept>();
        }

        private readonly Dictionary<int, ViewKept> _views = new Dictionary<int, ViewKept>();

        /// <summary>A new v3 stream. A different point or life than the one kept
        /// for the view starts a fresh list. Null past MaxKeptPerLife: the
        /// stream is then today's everywhere.</summary>
        internal Kept Begin(int view, int stream, LifeEpoch point, LifeEpoch life, int[] holders, int[] presentAtStart,
                            object payload)
        {
            ViewKept v;
            if (!_views.TryGetValue(view, out v) || !v.Point.SameAs(point) || !v.Life.SameAs(life))
            {
                v = new ViewKept { Point = point, Life = life };
                _views[view] = v;
            }
            if (v.Streams.Count >= MaxKeptPerLife) return null;
            var k = new Kept { View = view, Stream = stream, Life = life, Payload = payload, PresentAtStart = presentAtStart };
            if (holders != null) foreach (int a in holders) k.Holders.Add(a);
            v.Streams.Add(k);
            return k;
        }

        /// <summary>A stream that did not become v3 after all (its LIFE message
        /// could not be sent) leaves the list.</summary>
        internal void Drop(Kept k)
        {
            ViewKept v;
            if (k != null && _views.TryGetValue(k.View, out v)) v.Streams.Remove(k);
        }

        /// <summary>A tick that went out, in the stream's catch-up state. Only
        /// indices a receiver can hold are kept ([0, MaxTick): every ledger
        /// ignores the rest), so a stream retains at most MaxTick ticks.</summary>
        internal static void Note(Kept k, int tick, bool blocked)
        {
            if (tick < 0 || tick >= PoisonLedgerCore.MaxTick) return;
            (blocked ? k.Blocked : k.Committed).Add(tick);
        }

        /// <summary>The stream's end: its summary goes to the holders still
        /// present, never to this seat.</summary>
        internal static int[] CloseTargets(Kept k, int[] presentNow, int self)
        {
            k.Closed = true;
            var r = new List<int>();
            if (presentNow != null)
                foreach (int a in presentNow)
                    if (a != self && k.Holders.Contains(a) && !r.Contains(a)) r.Add(a);
            r.Sort();
            return r.ToArray();
        }

        internal static bool ShouldReplay(Kept k, int actor)
        {
            if (k.Holders.Contains(actor)) return false;
            return k.PresentAtStart == null || Array.IndexOf(k.PresentAtStart, actor) < 0;
        }

        /// <summary>The streams to replay to an actor that just acknowledged an
        /// activation bound to this point: only those of the view's CURRENT life
        /// in this point, each marked as held by that actor.</summary>
        internal List<Kept> ReplayFor(int actor, int self, int view, LifeEpoch point, LifeEpoch currentLife)
        {
            var r = new List<Kept>();
            ViewKept v;
            if (actor == self || !_views.TryGetValue(view, out v)) return r;
            if (!v.Point.SameAs(point) || !v.Life.SameAs(currentLife)) return r;
            foreach (var k in v.Streams)
                if (ShouldReplay(k, actor)) { k.Holders.Add(actor); r.Add(k); }
            return r;
        }

        /// <summary>A replay that could not be sent: the actor does not hold it.</summary>
        internal static void Unmark(Kept k, int actor) { k.Holders.Remove(actor); }

        internal List<int> Views() { return new List<int>(_views.Keys); }

        internal int CountFor(int view)
        {
            ViewKept v;
            return _views.TryGetValue(view, out v) ? v.Streams.Count : 0;
        }

        internal void Clear() { _views.Clear(); }
    }

    // ── The victim's send sequence of one stream (fix pass 2, H1) ──────────

    /// <summary>One stream's raises on the victim's seat, in order: LIFE (v3
    /// only, to the acknowledged actors present), the header (tick 0's
    /// verdict, to all), the ticks (to all), then the close summary (to the
    /// holders still present) and any replay (to one late acknowledger). A
    /// seat's record of a stream is created by its header, or later by its
    /// summary or a replay; a tick finds no record without one of them. So
    /// when the header was not sent the victim retires the stream -- out of
    /// the retained state, so no replay or summary names it -- and sends no
    /// later tick: no seat ever holds it, and every seat leaves that stream's
    /// health unchanged. A fence this seat could not record retires its open
    /// streams the same way (Retire).</summary>
    internal sealed class StreamSend
    {
        internal readonly int View;
        internal Kept Kept;                          // the retained v3 stream; null when the stream is today's
        internal bool Retired;
        internal string RetiredWhy;

        internal StreamSend(int view, Kept kept) { View = view; Kept = kept; }

        internal bool V3 { get { return Kept != null && !Retired; } }

        /// <summary>Whether the stream's next tick goes out.</summary>
        internal bool MaySendTick { get { return !Retired; } }

        /// <summary>Tick 0's LIFE raise. Not sent: no seat holds the LIFE, so
        /// the stream is today's on every seat and leaves the retained state;
        /// its header still goes to all. True while the stream is v3.</summary>
        internal bool AfterLife(PointRetainer ret, bool sent)
        {
            if (!sent && Kept != null) { ret.Drop(Kept); Kept = null; }
            return V3;
        }

        /// <summary>Tick 0's header raise. Not sent: the stream is retired
        /// (the class note). True while the stream may send its next tick.</summary>
        internal bool AfterHeader(PointRetainer ret, bool sent)
        {
            if (!sent) Retire(ret, "header-send-failed");
            return MaySendTick;
        }

        /// <summary>A tick raise (tick 0 is the header): the retained state
        /// names only ticks that went out, and nothing of a retired stream.</summary>
        internal void AfterTick(int tick, bool blocked, bool sent)
        {
            if (sent && Kept != null && !Retired) PointRetainer.Note(Kept, tick, blocked);
        }

        /// <summary>Nothing more is sent for this stream: no tick, no summary,
        /// no replay (it leaves the retained state).</summary>
        internal void Retire(PointRetainer ret, string why)
        {
            if (Retired) return;
            Retired = true;
            RetiredWhy = why;
            if (Kept != null) { ret.Drop(Kept); Kept = null; }
        }
    }

    // ── Hooks contain their own faults (V4 B7) ──────────────────────────────

    internal static class HookGuard
    {
        /// <summary>A postfix, a finalizer's side effect or a callback step: a
        /// fault inside stays inside, so the attached game method's result and
        /// exception are untouched. Independent steps take one Run each.</summary>
        internal static void Run(Action body)
        {
            try { body(); } catch { }
        }

        /// <summary>A prefix that may skip the game method. decide() returns
        /// true to run it, false to skip. A fault inside decide() returns
        /// onFault(the exception) (true when onFault itself faults). The
        /// follow-up (evidence, logging, arming) runs after the decision and can
        /// never change it.</summary>
        internal static bool Prefix(Func<bool> decide, Func<Exception, bool> onFault, Action<bool> after)
        {
            bool run;
            try { run = decide(); }
            catch (Exception ex)
            {
                try { run = onFault != null ? onFault(ex) : true; } catch { run = true; }
            }
            if (after != null) { try { after(run); } catch { } }
            return run;
        }
    }

    // ── The SILENT line's arm (V4 B8) ───────────────────────────────────────

    internal static class SilentArm
    {
        /// <summary>The arm marker for a stream started inside a poison effect
        /// of a broadcast hit; a positive value is a local-only arm's claim id;
        /// zero is a stream started outside any poison effect.</summary>
        internal const int Broadcast = -1;

        internal static string Label(int arm)
        {
            if (arm > 0) return "local-only c=" + arm;
            return arm == Broadcast ? "broadcast" : "direct";
        }
    }

    // ── v3 wire (event 47, Protocol 2): the payloads, one place ─────────────

    internal static class V3Wire
    {
        internal const byte Protocol = 2;
        internal const byte TypeClaim = 2, TypeSummary = 3, TypeActivate = 4, TypeAck = 5, TypeLife = 6;

        internal static object[] Life(int view, int stream, LifeEpoch e)
        {
            return new object[] { TypeLife, Protocol, view, stream, e.Ts, e.Set };
        }

        internal static object[] Claim(int victimView, int projView, int claimId, int hitTs, byte nPoison, LifeEpoch e)
        {
            return new object[] { TypeClaim, Protocol, victimView, projView, claimId, hitTs, nPoison, e.Ts, e.Set };
        }

        internal static object[] Summary(int view, int stream, LifeEpoch e, float sliceX, float sliceY,
                                         float r, float g, float b, int attacker, bool lethal, byte damageSource,
                                         int ticks, byte[] committed, byte[] blocked, int seq)
        {
            return new object[]
            {
                TypeSummary, Protocol, view, stream, e.Ts, e.Set, sliceX, sliceY, r, g, b, attacker, lethal, damageSource,
                ticks, committed, blocked, seq
            };
        }

        internal static object[] Activate(int aid, int[] fighters, LifeEpoch point)
        {
            return new object[] { TypeActivate, Protocol, aid, fighters, point.Ts, point.Set };
        }

        internal static object[] Ack(int aid, int master)
        {
            return new object[] { TypeAck, Protocol, aid, master };
        }
    }

    // ── Claim evidence lines (V4 B6) ────────────────────────────────────────

    internal static class ClaimLine
    {
        internal static string Arm(int from, int claimId, int projView, int victimView, string outcome)
        {
            return "[POISON-CLAIM] arm from=" + from + " c=" + claimId + " proj=" + projView + " victim=" + victimView
                + " outcome=" + outcome;
        }

        internal static string Recv(int from, int claimId, int projView, int victimView, string outcome)
        {
            return "[POISON-CLAIM] recv from=" + from + " c=" + claimId + " proj=" + projView + " victim=" + victimView
                + " outcome=" + outcome;
        }

        /// <summary>Fix pass 2 (M2): one sender's claims past the rate in one
        /// aligned second, as one line: their count, the first and the last
        /// tuple, the sender's running total and the room's.</summary>
        internal static string Rate(int from, long second, int excess, object[] first, object[] last, long total,
                                    long roomTotal)
        {
            return "[POISON-CLAIM] rate from=" + from + " second=" + second + " excess=" + excess
                + " first=(" + Tuple(first) + ") last=(" + Tuple(last) + ") total=" + total + " room_total=" + roomTotal
                + " outcome=drop reason=rate";
        }

        private static string Tuple(object[] a)
        {
            return "c=" + ClaimCore.Field(a, 4) + " proj=" + ClaimCore.Field(a, 3) + " victim=" + ClaimCore.Field(a, 2);
        }

        /// <summary>A result as its outcome field: "started" stays, every other
        /// result is a named drop.</summary>
        internal static string Outcome(string result)
        {
            if (result == "started" || result == "sent" || result == "send-failed") return result;
            return "drop reason=" + (string.IsNullOrEmpty(result) ? "unnamed" : result);
        }
    }
}
