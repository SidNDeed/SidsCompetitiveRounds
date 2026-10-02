using System;
using System.Collections.Generic;
using System.Linq;
using CompetitiveRounds;

namespace PoisonLedgerTests
{
    /// <summary>Cases over plugin/PoisonLedgerCore.cs (poison convergence v3,
    /// bugs 406/407). Usage: PoisonLedgerTests [case ...] (no argument: every
    /// case). Exit 0 only when every selected case passes. run_tests.py builds
    /// mutated copies of the core and requires each case's own mutant to turn
    /// it red while a named control stays green.</summary>
    internal static class Program
    {
        private const int V = 1001, U = 2002;

        private static void Check(bool ok, string what) { if (!ok) throw new Exception(what); }

        private static void Eq<T>(T want, T got, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(want, got)) throw new Exception(what + ": want " + want + ", got " + got);
        }

        /// <summary>Records every release the ledger makes, in order:
        /// R(stream).(tick) for a regular apply, C(stream).(tick) for a
        /// corrective one.</summary>
        private sealed class Ap : ILedgerApplier
        {
            internal readonly List<string> Calls = new List<string>();
            internal int ThrowOnRegularTick = -1;

            public void Regular(PoisonLedgerCore.Rec r, int t)
            {
                Calls.Add("R" + r.Stream + "." + t);
                if (t == ThrowOnRegularTick) throw new InvalidOperationException("apply threw");
            }

            public void Corrective(PoisonLedgerCore.Rec r, int t) { Calls.Add("C" + r.Stream + "." + t); }

            internal string Seen { get { return string.Join(",", Calls); } }
            internal int Regulars { get { return Calls.Count(c => c[0] == 'R'); } }
        }

        private static LifeEpoch E(int ts) { return LifeEpoch.At(ts); }

        private static byte[] M(int count, params int[] ticks) { return PoisonLedgerCore.Mask(ticks, count); }

        // ── V2 cases 1-26 (15 and 19 restated by amendments A1 and A4) ─────

        // 1. A repeated verdict applies once.
        private static void DupVerdict()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.OnHeader(V, 1, default(LifeEpoch), false, null, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            Eq("R1.0,R1.1", ap.Seen, "each tick once");
            Eq(1, l.Find(V, 1).Duplicates, "the repeat is counted");
        }

        // 2. A repeated header never overwrites the record nor re-applies tick 0.
        private static void DupHeader()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.OnHeader(V, 1, default(LifeEpoch), false, "first", true, ap);
            l.OnHeader(V, 1, default(LifeEpoch), false, "second", true, ap);
            Eq("R1.0", ap.Seen, "tick 0 once");
            Eq("first", (string)l.Find(V, 1).Payload, "the record keeps its first header");
        }

        // 3. Ticks out of order each apply once.
        private static void OutOfOrder()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.OnHeader(V, 1, default(LifeEpoch), false, null, true, ap);
            l.OnTick(V, 1, 3, false, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(V, 1, 2, false, true, ap);
            Eq("R1.0,R1.3,R1.1,R1.2", ap.Seen, "every tick once, in arrival order");
        }

        // 4. A blocked tick is consumed: never applied by a fill or a catch-up.
        private static void BlockedNeverFilled()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.OnHeader(V, 1, E(100), true, null, false, ap);
            l.OnTick(V, 1, 1, false, false, ap);
            l.Fill(V, true, ap);
            l.OnSummary(V, 1, E(100), 2, M(2, 1), M(2, 0), null, true, ap);
            Eq("C1.1", ap.Seen, "only the committed tick, once");
        }

        // 5. A slow seat that saw the boundary but has not revived: the new
        //    life's ticks wait, then fill through the funnel, never regular.
        private static void SlowSeatHeaderBeforeRevive()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100);
            l.OnHeader(V, 1, E(100), false, null, false, ap);
            l.OnTick(V, 1, 1, false, false, ap);
            l.OnTick(V, 1, 2, false, false, ap);
            Eq("", ap.Seen, "nothing before the revive");
            Eq(LifeClass.Next, l.Classify(V, E(100)), "next life");
            l.OnRevive(V);
            l.Fill(V, true, ap);
            Eq("C1.0,C1.1,C1.2", ap.Seen, "all filled, corrective only");
        }

        // 6. The header after this seat's revive is the current life: applied.
        private static void SlowSeatHeaderAfterRevive()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            Eq("R1.0", ap.Seen, "current life applied on time");
        }

        // 7. After the revive into a new life, the old life's tail is never applied.
        private static void StaleTailAfterRevive()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            l.NotePointBoundary(200); l.OnRevive(V);
            Check(!l.OnTick(V, 1, 1, false, true, ap), "the old record retired at the revive");
            l.OnHeader(V, 2, E(100), false, null, true, ap);
            Eq("R1.0", ap.Seen, "no old-life tick after the revive");
        }

        // 8. Between the signal and the revive: live ticks apply as today, a
        //    deferred one is never filled and retires with the revive.
        private static void EndingWindow()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            l.NotePointBoundary(200);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(V, 1, 2, false, false, ap);
            l.Fill(V, true, ap);
            Eq("R1.0,R1.1", ap.Seen, "ending ticks: live applied, deferred never filled");
            var r = l.Find(V, 1);
            l.OnRevive(V);
            Eq(1, r.PendingDropped, "the deferred tick retires with the record");
        }

        // 9. A live replica that has seen the boundary but not revived defers
        //    the next life's ticks (a spectator between point-over and Move).
        private static void NextDeferred()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.NotePointBoundary(200);
            l.OnHeader(V, 1, E(200), false, null, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            Eq("", ap.Seen, "deferred although live");
            l.OnRevive(V);
            l.Fill(V, true, ap);
            Eq("C1.0,C1.1", ap.Seen, "filled after the revive");
        }

        // 10. Phoenix is a boundary for its own view only.
        private static void Phoenix()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V); l.OnRevive(U);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            l.OnHeader(U, 5, E(100), false, null, true, ap);
            l.NotePhoenixBoundary(V, 150);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(U, 5, 1, false, true, ap);
            Eq(LifeClass.Current, l.Classify(U, E(100)), "the other view is untouched");
            l.OnRevive(V);
            l.OnHeader(V, 2, E(150), false, null, true, ap);
            Eq("R1.0,R5.0,R1.1,R5.1,R2.0", ap.Seen, "old life as today, new life current");
            Check(l.Find(V, 1) == null, "the old life retired at the Phoenix revive");
        }

        // 11. A point-over with no revive after it: ending, applied as today.
        private static void SpuriousPointOver()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            l.NotePointBoundary(200);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(V, 1, 2, false, false, ap);
            l.Fill(V, true, ap);
            l.OnHeader(V, 2, E(100), false, null, true, ap);
            Eq("R1.0,R1.1,R2.0", ap.Seen, "live ticks as today, nothing filled");
        }

        // 12. Several revives after one boundary never re-apply a tick.
        private static void MultiReviveOneBoundary()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(V, 1, 2, false, true, ap);
            l.OnRevive(V);
            l.OnTick(V, 1, 3, false, true, ap);
            l.OnTick(V, 1, 4, false, true, ap);
            l.Fill(V, true, ap);
            Eq("R1.0,R1.1,R1.2,R1.3,R1.4", ap.Seen, "each tick once across revives");
        }

        // 13. A seat that has seen no boundary (a late joiner) applies as today.
        private static void LateJoinerUnset()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            Eq(LifeClass.Current, l.Classify(V, E(500)), "no boundary seen: current");
            l.OnHeader(V, 1, E(500), false, null, true, ap);
            Eq("R1.0", ap.Seen, "applied");
        }

        // 14. Stamps compare across the int wrap.
        private static void Wrap()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            int p1 = int.MaxValue - 10, p2 = unchecked(int.MinValue + 10);
            l.NotePointBoundary(p1); l.OnRevive(V);
            l.OnHeader(V, 1, E(p1), false, null, true, ap);
            l.NotePointBoundary(p2); l.OnRevive(V);
            l.OnHeader(V, 2, E(p2), false, null, true, ap);
            l.OnHeader(V, 3, E(p1), false, null, true, ap);
            Eq("R1.0,R2.0", ap.Seen, "the wrapped stamp is the later one");
        }

        // 15. (restated by A1) A watcher whose boundary arrives after the new
        //     life's header converges: next, then filled. Receipt time plays no part.
        private static void LateBoundaryConverges()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.OnHeader(V, 2, E(300), false, null, true, ap);
            l.OnTick(V, 2, 1, false, true, ap);
            l.OnTick(V, 2, 2, false, true, ap);
            Eq("", ap.Seen, "held while this seat has not seen the boundary");
            l.NotePointBoundary(300); l.OnRevive(V);
            l.Fill(V, true, ap);
            Eq("C2.0,C2.1,C2.2", ap.Seen, "nothing lost");
        }

        // 16. A tick whose apply throws is lost on this seat, never applied twice.
        private static void ExceptionAtMostOnce()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap { ThrowOnRegularTick = 1 };
            l.OnHeader(V, 1, default(LifeEpoch), false, null, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            l.Fill(V, true, ap);
            Eq("R1.0,R1.1", ap.Seen, "once");
            Eq(1, l.Find(V, 1).Exceptions, "counted");
        }

        // 17. A corrective tick is consumed whatever its apply did (a rule
        //     refusal moves nothing): never retried.
        private static void RuleRefusalConsumed()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100);
            l.OnHeader(V, 1, E(100), false, null, false, ap);
            l.OnTick(V, 1, 1, false, false, ap);
            l.OnRevive(V);
            l.Fill(V, true, ap);
            l.Fill(V, true, ap);
            Eq("C1.0,C1.1", ap.Seen, "each corrective once");
        }

        // 18. Tick indices outside [0, 1024) are ignored.
        private static void IndexRange()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.OnHeader(V, 1, default(LifeEpoch), false, null, true, ap);
            l.OnTick(V, 1, -1, false, true, ap);
            l.OnTick(V, 1, 1024, false, true, ap);
            l.OnTick(V, 1, 1023, false, true, ap);
            Eq("R1.0,R1.1023", ap.Seen, "in range only");
            Eq(2, l.Find(V, 1).OutOfRange, "two ignored");
        }

        // 19. (restated by A4) Above 128 records on a view only terminal ones
        //     are evicted; a held record and another view's are never touched.
        private static void PerViewCap()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.OnHeader(V, 1, default(LifeEpoch), false, null, false, ap);   // pending: never evictable
            l.OnHeader(U, 1, default(LifeEpoch), false, null, true, ap);
            for (int s = 2; s <= 140; s++)
            {
                l.OnHeader(V, s, default(LifeEpoch), false, null, true, ap);
                l.OnSummary(V, s, default(LifeEpoch), 1, M(1, 0), M(1), null, true, ap);
            }
            Check(l.Find(V, 1) != null, "the held record survives");
            Check(l.Find(U, 1) != null, "another view's record survives");
            Eq(129, l.Count, "128 on the view plus the other view's one");
            Eq("evict", l.RetiredLog[0].Retired, "evicted as terminal");
        }

        // 20. (restated by A2b) A header is v3 only on a seat holding that
        //     stream's LIFE message; every other header is today's, and a LIFE
        //     message is consumed by its own stream's header once.
        private static void LifeMessageRequired()
        {
            var inbox = new EpochInbox(); LifeEpoch e;
            Check(!inbox.Take(V, 1, out e), "no LIFE message: today's header");
            inbox.Note(V, 2, E(500));
            Check(!inbox.Take(V, 1, out e), "another stream's LIFE message does not count");
            Check(!inbox.Take(U, 2, out e), "another view's LIFE message does not count");
            Check(inbox.Take(V, 2, out e) && e.Set && e.Ts == 500, "its own stream");
            Check(!inbox.Take(V, 2, out e), "consumed once");
            for (int s = 0; s < EpochInbox.Cap + 10; s++) inbox.Note(V, 100 + s, E(1));
            Eq(EpochInbox.Cap, inbox.Count, "bounded");
        }

        // 21. Two seats, one slow, end with the same applied set.
        private static void TwoSeatConvergence()
        {
            var a = new PoisonLedgerCore(); var b = new PoisonLedgerCore();
            var apA = new Ap(); var apB = new Ap();
            a.NotePointBoundary(100); a.OnRevive(V); b.NotePointBoundary(100); b.OnRevive(V);
            a.NotePointBoundary(200); a.OnRevive(V);
            b.NotePointBoundary(200);                         // still in Move
            foreach (var x in new[] { Tuple.Create(a, apA, true), Tuple.Create(b, apB, false) })
            {
                x.Item1.OnHeader(V, 7, E(200), false, null, x.Item3, x.Item2);
                for (int t = 1; t <= 4; t++) x.Item1.OnTick(V, 7, t, t == 2, x.Item3, x.Item2);
            }
            b.OnRevive(V);
            b.Fill(V, true, apB);
            Eq("R7.0,R7.1,R7.3,R7.4", apA.Seen, "the fast seat on time");
            Eq("C7.0,C7.1,C7.3,C7.4", apB.Seen, "the slow seat by the funnel");
            Check(a.Find(V, 7).Applied.SetEquals(b.Find(V, 7).Applied), "same applied set");
        }

        // 22. The same claim twice: started, then a durable dup.
        private static void ClaimStartsOnce()
        {
            var c = new ClaimCore();
            var f = Facts(2, 1, 77);
            Eq("started", c.VictimDecide(f), "first");
            Eq("dup", c.VictimDecide(f), "repeat");
        }

        // 23. Claim first, broadcast second: the broadcast's poison is skipped.
        private static void ClaimThenBroadcast()
        {
            var c = new ClaimCore();
            Eq("started", c.VictimDecide(Facts(2, 1, 77)), "claim");
            Check(!c.TryStart(77, V, StartPath.Broadcast), "the broadcast loses only its poison");
        }

        // 24. A claim naming another life is refused.
        private static void ClaimPreviousLife()
        {
            var c = new ClaimCore();
            var f = Facts(2, 1, 77); f.ShooterEpoch = E(100); f.VictimEpoch = E(200);
            Eq("fence", c.VictimDecide(f), "previous life");
            var g = Facts(2, 2, 78); g.VictimFenceKnown = false;
            Eq("fence", c.VictimDecide(g), "victim life unknown");
        }

        // 25. A claim for a projectile the sender does not own is refused.
        private static void ClaimNotOwner()
        {
            var c = new ClaimCore();
            var f = Facts(2, 1, 77); f.ProjOwner = 3;
            Eq("not-owner", c.VictimDecide(f), "not the owner");
        }

        // 26. A claim while the replica is not live is dropped, not deferred.
        private static void ClaimNotLive()
        {
            var c = new ClaimCore();
            var f = Facts(2, 1, 77); f.Live = false;
            Eq("not-live", c.VictimDecide(f), "dropped");
            f.Live = true;
            Eq("dup", c.VictimDecide(f), "never retried");
        }

        // ── A1: catch-up and the room-common epoch ────────────────────────

        // 27. A mid-life joiner missed the header: the summary supplies the
        //     committed ticks, blocked ones are never applied.
        private static void SummaryLateJoiner()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            Check(!l.OnTick(V, 4, 1, false, true, ap), "ticks without a header are not applied");
            l.OnSummary(V, 4, E(100), 4, M(4, 0, 1, 3), M(4, 2), null, true, ap);
            Eq("C4.0,C4.1,C4.3", ap.Seen, "committed, by the funnel");
            Eq(3, l.Find(V, 4).CatchUp, "counted as catch-up");
        }

        // 28. A summary of a life this seat has revived past applies nothing.
        private static void SummaryOlderEpochRefused()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V);
            l.NotePointBoundary(200); l.OnRevive(V);
            l.OnSummary(V, 4, E(100), 3, M(3, 0, 1, 2), M(3), null, true, ap);
            Eq("", ap.Seen, "an older epoch is refused");
            Check(l.Find(V, 4) == null, "and retired");
        }

        // 29. A summary after every tick arrived adds nothing, twice over.
        private static void SummaryIdempotent()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.OnHeader(V, 1, default(LifeEpoch), false, null, true, ap);
            l.OnTick(V, 1, 1, false, true, ap);
            l.OnTick(V, 1, 2, true, true, ap);
            l.OnSummary(V, 1, default(LifeEpoch), 3, M(3, 0, 1), M(3, 2), null, true, ap);
            l.OnSummary(V, 1, default(LifeEpoch), 3, M(3, 0, 1), M(3, 2), null, true, ap);
            Eq("R1.0,R1.1", ap.Seen, "nothing extra");
            Check(l.Find(V, 1).Terminal, "terminal");
        }

        // 30. Boundaries arriving in either order give the same classification.
        private static void BoundaryStampOrderIndependent()
        {
            var x = new PoisonLedgerCore(); var y = new PoisonLedgerCore();
            var apX = new Ap(); var apY = new Ap();
            x.NotePointBoundary(100); x.NotePointBoundary(200);
            y.NotePointBoundary(200); y.NotePointBoundary(100);
            x.OnRevive(V); y.OnRevive(V);
            foreach (var p in new[] { Tuple.Create(x, apX), Tuple.Create(y, apY) })
            {
                p.Item1.OnHeader(V, 1, E(200), false, null, true, p.Item2);
                p.Item1.OnHeader(V, 2, E(100), false, null, true, p.Item2);
            }
            Eq("R1.0", apX.Seen, "seat x");
            Eq(apX.Seen, apY.Seen, "seat y agrees");
        }

        // ── A2b: activation over the acknowledged FIGHTERS; rooms stay open ──
        // Actors 1 and 2 are fighters (1 is master), 3 joins (a spectator or
        // a fighter), 9 is a spectator already present.

        private static readonly int[] F12 = { 1, 2 };
        private static readonly int[] F123 = { 1, 2, 3 };
        private static bool All(int a) { return true; }

        private static ActivationCore Armed(int aid, int[] fighters, params int[] extraAcks)
        {
            var a = new ActivationCore();
            a.OnActivate(1, 1, aid, fighters, 0);
            foreach (int x in fighters) a.OnAck(x, 1, aid);
            foreach (int x in extraAcks) a.OnAck(x, 1, aid);
            return a;
        }

        // 31. Every fighter must acknowledge; a spectator's ack is optional.
        private static void ActivationRequiresAllAcks()
        {
            var a = new ActivationCore(); string w;
            a.OnActivate(1, 1, 7, F12, 0);
            Check(!a.Evaluate(F12, All, 10, out w), "no acks");
            a.OnAck(1, 1, 7); a.OnAck(9, 1, 7);
            Check(!a.Evaluate(F12, All, 10, out w) && w == "not-acked 1/2", "one fighter and a spectator: " + w);
            a.OnAck(2, 1, 8);
            Check(!a.Evaluate(F12, All, 10, out w), "an ack for another activation does not count");
            a.OnAck(2, 1, 7);
            Check(a.Evaluate(F12, All, 10, out w), "both fighters: " + w);
            Eq("1,2,9", string.Join(",", a.AckedPresent(new[] { 1, 2, 9 })), "the acknowledged spectator is an addressee");
        }

        // 32. Any entered/left/cap-change event kills v3 on the observing seat
        //     until a fresh activation is acknowledged; the old acks never count.
        private static void ActivationKilledByRoomEvent()
        {
            var a = Armed(7, F12); string w;
            Check(a.Evaluate(F12, All, 10, out w), "armed");
            a.OnRoomEvent("player-entered actor=3");
            Check(!a.Evaluate(F12, All, 10, out w) && w == "killed:player-entered actor=3", "event: " + w);
            Eq(0, a.AckedPresent(F12).Length, "nothing is addressed while off");
            a.OnAck(1, 1, 7); a.OnAck(2, 1, 7);
            Check(!a.Evaluate(F12, All, 20, out w), "re-acks of the old activation do not revive it: " + w);
            a.OnActivate(1, 1, 8, F12, 30); a.OnAck(1, 1, 8); a.OnAck(2, 1, 8);
            Check(a.Evaluate(F12, All, 40, out w), "fresh activation: " + w);
        }

        // 33. A fighter without cr_pois3 turns v3 off and gets no ack anywhere.
        private static void ActivationCapMissing()
        {
            var fresh = new ActivationCore(); string w;
            Check(!fresh.Evaluate(F12, x => x != 2, 10, out w) && w == "cap-missing actor=2", "before any activation: " + w);
            var a = Armed(7, F12);
            Check(!a.Evaluate(F12, x => x != 2, 10, out w), "armed, then a fighter's cap missing");
            Check(!a.Evaluate(F12, All, 10, out w), "sticky: " + w);
            var b = new ActivationCore();
            b.OnActivate(1, 1, 9, F12, 0);
            Check(!b.ShouldAck(F12, x => x != 2), "no ack with a fighter's cap missing");
        }

        // 34. An OLD spectator (no cr_pois3) joins: before this seat observes
        //     it, it is in no list, so nothing v3-only can be addressed to it;
        //     after, the event kills v3, the re-offer over the same fighters
        //     acks, and v3 is on again with the spectator never addressed.
        private static void JoinUnseenOldSpectator()
        {
            Func<int, bool> cap = x => x != 3;
            var a = Armed(7, F12); string w;
            Eq("1,2", string.Join(",", V3Targets.Capable(F12, cap)), "unseen: not in the present list");
            a.OnRoomEvent("player-entered actor=3");
            int[] present = { 1, 2, 3 };
            Check(V3Targets.ShouldOffer(F12, cap, true), "the fighters still all carry cr_pois3");
            a.OnActivate(1, 1, 8, F12, 50);
            Eq("1,2", string.Join(",", V3Targets.Capable(present, cap)), "ACTIVATE/ACK addressees exclude it");
            a.OnAck(1, 1, 8); a.OnAck(2, 1, 8);
            Check(a.Evaluate(F12, cap, 60, out w), "an old spectator does not block the fighters: " + w);
            Eq("1,2", string.Join(",", a.AckedPresent(present)), "LIFE/summary addressees exclude it");
        }

        // 35. An ack only for the exact fighter roster.
        private static void AckRequiresExactRoster()
        {
            var a = new ActivationCore();
            a.OnActivate(1, 1, 7, F123, 0);
            Check(a.ShouldAck(new[] { 3, 1, 2 }, All), "exact, any order");
            Check(!a.ShouldAck(new[] { 1, 2 }, All), "subset");
            Check(!a.ShouldAck(new[] { 1, 2, 3, 4 }, All), "superset");
        }

        // 36. Only the current master's ACTIVATE counts.
        private static void ActivationMasterOnly()
        {
            var a = new ActivationCore(); string w;
            Check(!a.OnActivate(2, 1, 7, F12, 0), "not the master");
            Check(!a.Evaluate(F12, All, 10, out w) && w == "no-activation", w);
        }

        // 37. An activation not fully acknowledged in time is retired.
        private static void ActivationAckTimeout()
        {
            var a = new ActivationCore(); string w;
            a.OnActivate(1, 1, 7, F12, 0);
            a.OnAck(1, 1, 7);
            Check(!a.Evaluate(F12, All, 14999, out w) && w == "not-acked 1/2", "before the timeout: " + w);
            Check(!a.Evaluate(F12, All, 15000, out w) && w == "killed:ack-timeout", "at the timeout: " + w);
            Check(!a.Live, "retired");
        }

        // 47. An OLD fighter joins: once observed, v3 is off, the master offers
        //     nothing, and no claim is sent; before, it is addressed nothing.
        private static void JoinUnseenOldFighter()
        {
            Func<int, bool> cap = x => x != 3;
            var a = Armed(7, F12); string w;
            Eq("1,2", string.Join(",", a.AckedPresent(F12)), "unseen: addressed nothing");
            a.OnRoomEvent("player-entered actor=3");
            Check(!V3Targets.ShouldOffer(F123, cap, true), "no offer while a fighter lacks cr_pois3");
            Check(!a.Evaluate(F123, cap, 10, out w) && w == "cap-missing actor=3", w);
            var c = new ClaimCore(); int id;
            Eq("v3-off:" + w, c.ShooterArm(false, w, true, true, 5, V, 0, out id), "no claim sent");
            var f = Facts(2, 1, 77); f.GateOn = false; f.GateWhy = w;
            Eq("gate:" + w, c.VictimDecide(f), "none accepted");
        }

        // 48. A NEW fighter joins: v3 is off until a fresh activation over the
        //     three fighters is acknowledged by all three.
        private static void JoinUnseenNewFighter()
        {
            var a = Armed(7, F12); string w;
            a.OnRoomEvent("player-entered actor=3");
            Check(V3Targets.ShouldOffer(F123, All, true), "offered over three fighters");
            Check(!V3Targets.ShouldOffer(F123, All, false), "not while the join is settling");
            a.OnActivate(1, 1, 8, F123, 100);
            a.OnAck(3, 1, 8);
            Check(!a.Evaluate(F123, All, 110, out w) && w == "not-acked 1/3", "the earlier acks do not carry over: " + w);
            a.OnAck(1, 1, 8); a.OnAck(2, 1, 8);
            Check(a.Evaluate(F123, All, 120, out w), "all three: " + w);
        }

        // 49. A fighter leaving turns v3 off even before the event is seen.
        private static void FighterLeave()
        {
            var a = Armed(7, F123); string w;
            Check(!a.Evaluate(F12, All, 10, out w) && w == "killed:roster-change", "fighter gone: " + w);
            Check(!a.Evaluate(F123, All, 20, out w), "sticky: " + w);
        }

        // 50. A cr_pois3 change kills; a fighter whose value is no longer 1
        //     neither acks nor lets the master offer.
        private static void PropertyFlip()
        {
            Func<int, bool> flipped = x => x != 2;
            var a = Armed(7, F12); string w;
            a.OnRoomEvent("cap-change actor=2");
            Check(!a.Evaluate(F12, All, 10, out w), "the event kills: " + w);
            a.OnActivate(1, 1, 8, F12, 20);
            Check(!a.ShouldAck(F12, flipped), "no ack while a fighter reads cr_pois3 != 1");
            Check(!V3Targets.ShouldOffer(F12, flipped, true), "no offer either");
        }

        // 51. Readmission: the fighter leaves and comes back under its actor
        //     number; a late ack from the previous activation never counts.
        private static void Readmission()
        {
            var a = Armed(7, F12); string w;
            a.OnRoomEvent("player-left actor=2");
            a.OnRoomEvent("player-entered actor=2");
            a.OnActivate(1, 1, 8, F12, 100);
            a.OnAck(1, 1, 8);
            a.OnAck(2, 1, 7);
            Check(!a.Evaluate(F12, All, 110, out w) && w == "not-acked 1/2", "the old ack: " + w);
            a.OnAck(2, 1, 8);
            Check(a.Evaluate(F12, All, 120, out w), "re-acknowledged: " + w);
        }

        // 52. A join during an active stream: the joiner gets that stream's
        //     catch-up only once it has acknowledged (it never saw the header).
        private static void JoinDuringActiveStream()
        {
            int[] life = { 1, 2 }, atStart = { 1, 2 };
            Eq("2", string.Join(",", V3Targets.SummaryTargets(life, atStart, new[] { 1, 2, 3 }, new int[0], 1)),
                "not acknowledged: not caught up");
            Eq("2,3", string.Join(",", V3Targets.SummaryTargets(life, atStart, new[] { 1, 2, 3 }, new[] { 1, 2, 3 }, 1)),
                "acknowledged: caught up");
            Eq("3", string.Join(",", V3Targets.SummaryTargets(life, atStart, new[] { 1, 3 }, new[] { 1, 3 }, 1)),
                "a LIFE addressee that left is dropped");
        }

        // 53. An actor present at the start WITHOUT the LIFE message handled
        //     the stream by today's path: never caught up on top of it.
        private static void TodayPathSeatNotCaughtUp()
        {
            int[] life = { 1, 2 }, atStart = { 1, 2, 9 };
            Eq("2", string.Join(",", V3Targets.SummaryTargets(life, atStart, new[] { 1, 2, 9 }, new[] { 1, 2, 9 }, 1)),
                "the spectator that acked after the start is excluded");
        }

        // 54. The shooter claims only toward an acknowledged victim owner.
        private static void ClaimOwnerNotAcked()
        {
            var c = new ClaimCore(); int id;
            Eq("owner-not-acked", c.ShooterArm(true, null, false, true, 5, V, 0, out id), "unacknowledged owner");
            Eq(null, c.ShooterArm(true, null, true, true, 6, V, 0, out id), "acknowledged owner");
        }

        // 55. The victim accepts claims only from an acknowledged sender.
        private static void ClaimSenderNotAcked()
        {
            var c = new ClaimCore();
            var f = Facts(2, 1, 77); f.SenderAcked = false;
            Eq("sender-not-acked", c.VictimDecide(f), "refused");
            Eq("started", c.VictimDecide(Facts(2, 2, 78)), "acknowledged sender");
        }

        // ── A3: the funnel ───────────────────────────────────────────────

        // 38. Caught-up ticks are corrective, never regular.
        private static void CatchupNeverRegular()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.OnHeader(V, 1, default(LifeEpoch), false, null, true, ap);
            l.OnSummary(V, 1, default(LifeEpoch), 3, M(3, 0, 1, 2), M(3), null, true, ap);
            Eq("R1.0,C1.1,C1.2", ap.Seen, "late ticks by the funnel");
        }

        // ── A4: bounds ───────────────────────────────────────────────────

        // 39. Past 1024 held records on a view a new header is refused; nothing held is evicted.
        private static void CeilingRefusesNew()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            for (int s = 1; s <= PoisonLedgerCore.NonTerminalCeilingPerView; s++)
                l.OnHeader(V, s, default(LifeEpoch), false, null, false, ap);
            Check(l.OnHeader(V, 5000, default(LifeEpoch), false, null, false, ap) == null, "refused");
            Check(l.Find(V, 1) != null, "the oldest held record survives");
            Check(l.OnHeader(U, 1, default(LifeEpoch), false, null, false, ap) != null, "another view unaffected");
        }

        // 40. The victim stamps v3 on at most 64 open streams.
        private static void VictimAdmissionBound()
        {
            var l = new PoisonLedgerCore();
            for (int i = 0; i < PoisonLedgerCore.MaxOpenV3StreamsPerVictim; i++)
                Check(l.AdmitV3Stream(0, 5000), "open " + i);
            Check(!l.AdmitV3Stream(10, 5000), "the 65th open stream is today's");
            Check(l.AdmitV3Stream(6000, 9000), "after they end");
        }

        // ── A5: durable claim results, one TryStart ─────────────────────────

        // 41. A rate-refused claim is a terminal result: its repeat is a dup.
        private static void ClaimRateRefusalDurable()
        {
            var c = new ClaimCore();
            for (int i = 1; i <= ClaimCore.ClaimsPerRollingSecond; i++)
            {
                var f = Facts(2, i, 100 + i); f.NowMs = 1000;
                Eq("started", c.VictimDecide(f), "claim " + i);
            }
            var r = Facts(2, 33, 133); r.NowMs = 1000;
            Eq("rate", c.VictimDecide(r), "the 33rd in a second");
            r.NowMs = 5000;
            Eq("dup", c.VictimDecide(r), "repeated later: dup, never started");
            var n = Facts(2, 34, 134); n.NowMs = 5000;
            Eq("started", c.VictimDecide(n), "a new claim later");
        }

        // 42. Broadcast first, claim second: the claim is refused.
        private static void BroadcastThenClaim()
        {
            var c = new ClaimCore();
            Check(c.TryStart(77, V, StartPath.Broadcast), "broadcast starts");
            Eq("dup-broadcast", c.VictimDecide(Facts(2, 1, 77)), "claim refused");
        }

        // 43. A bullet that hits twice by broadcast poisons twice (vanilla).
        private static void BroadcastRepeatAllowed()
        {
            var c = new ClaimCore();
            Check(c.TryStart(77, V, StartPath.Broadcast), "first hit");
            Check(c.TryStart(77, V, StartPath.Broadcast), "second hit");
            Check(c.TryStart(77, U, StartPath.Broadcast), "another victim");
        }

        // ── A6: sender-side limits ────────────────────────────────────────

        // 44. One claim per projectile and victim; an off gate or an unknown life sends none.
        private static void SenderPairMarked()
        {
            var c = new ClaimCore(); int id1, id2, id3, id4;
            Eq(null, c.ShooterArm(true, null, true, true, 10, V, 0, out id1), "first");
            Eq("pair-marked", c.ShooterArm(true, null, true, true, 10, V, 1, out id2), "second");
            Check(id2 == id1 + 1, "every arm gets an id");
            Eq("v3-off:no-activation", c.ShooterArm(false, "no-activation", true, true, 11, V, 2, out id3), "gate off");
            Eq("no-life", c.ShooterArm(true, null, true, false, 12, V, 3, out id4), "life unknown");
        }

        // 45. At most 32 sends per rolling second.
        private static void SenderRate32()
        {
            var c = new ClaimCore(); int id;
            for (int i = 0; i < ClaimCore.ClaimsPerRollingSecond; i++)
                Eq(null, c.ShooterArm(true, null, true, true, 100 + i, V, i, out id), "send " + i);
            Eq("rate", c.ShooterArm(true, null, true, true, 500, V, 500, out id), "the 33rd");
            Eq(null, c.ShooterArm(true, null, true, true, 501, V, 1000, out id), "a second later, a new pair");
        }

        // 46. A refused or failed send is never retried for that pair.
        private static void SenderNoRetryAfterFail()
        {
            var c = new ClaimCore(); int id;
            Eq(null, c.ShooterArm(true, null, true, true, 1, V, 0, out id), "raised (its send failed)");
            Eq("pair-marked", c.ShooterArm(true, null, true, true, 1, V, 10, out id), "not retried");
            for (int i = 0; i < ClaimCore.ClaimsPerRollingSecond - 1; i++) c.ShooterArm(true, null, true, true, 100 + i, V, 20, out id);
            Eq("rate", c.ShooterArm(true, null, true, true, 999, V, 30, out id), "rate-refused");
            Eq("pair-marked", c.ShooterArm(true, null, true, true, 999, V, 5000, out id), "not retried after the window");
        }

        private static ClaimFacts Facts(int sender, int claimId, long proj)
        {
            return new ClaimFacts
            {
                Sender = sender, ClaimId = claimId, VictimView = V, ProjOwner = sender, PoisonChildren = 1,
                ProjInstance = proj, NowMs = 1000, GateOn = true, SenderAcked = true, VictimFound = true, VictimIsMine = true,
                ProjFound = true, Live = true, VictimFenceKnown = true, ShooterEpoch = E(100), VictimEpoch = E(100),
            };
        }

        private static readonly Dictionary<string, Action> Cases = new Dictionary<string, Action>
        {
            { "dup_verdict", DupVerdict },
            { "dup_header", DupHeader },
            { "out_of_order", OutOfOrder },
            { "blocked_never_filled", BlockedNeverFilled },
            { "slow_seat_header_before_revive", SlowSeatHeaderBeforeRevive },
            { "slow_seat_header_after_revive", SlowSeatHeaderAfterRevive },
            { "stale_tail_after_revive", StaleTailAfterRevive },
            { "ending_window", EndingWindow },
            { "next_deferred", NextDeferred },
            { "phoenix", Phoenix },
            { "spurious_point_over", SpuriousPointOver },
            { "multi_revive_one_boundary", MultiReviveOneBoundary },
            { "late_joiner_unset", LateJoinerUnset },
            { "wrap", Wrap },
            { "late_boundary_converges", LateBoundaryConverges },
            { "exception_at_most_once", ExceptionAtMostOnce },
            { "rule_refusal_consumed", RuleRefusalConsumed },
            { "index_range", IndexRange },
            { "per_view_cap", PerViewCap },
            { "life_message_required", LifeMessageRequired },
            { "two_seat_convergence", TwoSeatConvergence },
            { "claim_starts_once", ClaimStartsOnce },
            { "claim_then_broadcast", ClaimThenBroadcast },
            { "claim_previous_life", ClaimPreviousLife },
            { "claim_not_owner", ClaimNotOwner },
            { "claim_not_live", ClaimNotLive },
            { "summary_late_joiner", SummaryLateJoiner },
            { "summary_older_epoch_refused", SummaryOlderEpochRefused },
            { "summary_idempotent", SummaryIdempotent },
            { "boundary_stamp_order_independent", BoundaryStampOrderIndependent },
            { "activation_requires_all_acks", ActivationRequiresAllAcks },
            { "activation_killed_by_room_event", ActivationKilledByRoomEvent },
            { "activation_cap_missing", ActivationCapMissing },
            { "join_unseen_old_spectator", JoinUnseenOldSpectator },
            { "ack_requires_exact_roster", AckRequiresExactRoster },
            { "activation_master_only", ActivationMasterOnly },
            { "activation_ack_timeout", ActivationAckTimeout },
            { "catchup_never_regular", CatchupNeverRegular },
            { "ceiling_refuses_new", CeilingRefusesNew },
            { "victim_admission_bound", VictimAdmissionBound },
            { "claim_rate_refusal_durable", ClaimRateRefusalDurable },
            { "broadcast_then_claim", BroadcastThenClaim },
            { "broadcast_repeat_allowed", BroadcastRepeatAllowed },
            { "sender_pair_marked", SenderPairMarked },
            { "sender_rate_32", SenderRate32 },
            { "sender_no_retry_after_fail", SenderNoRetryAfterFail },
            { "join_unseen_old_fighter", JoinUnseenOldFighter },
            { "join_unseen_new_fighter", JoinUnseenNewFighter },
            { "fighter_leave", FighterLeave },
            { "property_flip", PropertyFlip },
            { "readmission", Readmission },
            { "join_during_active_stream", JoinDuringActiveStream },
            { "today_path_seat_not_caught_up", TodayPathSeatNotCaughtUp },
            { "claim_owner_not_acked", ClaimOwnerNotAcked },
            { "claim_sender_not_acked", ClaimSenderNotAcked },
        };

        private static int Main(string[] args)
        {
            var names = args.Length > 0 ? args : Cases.Keys.ToArray();
            int failed = 0;
            foreach (var n in names)
            {
                Action a;
                if (!Cases.TryGetValue(n, out a)) { Console.WriteLine("UNKNOWN " + n); failed++; continue; }
                try { a(); Console.WriteLine("PASS " + n); }
                catch (Exception ex) { Console.WriteLine("FAIL " + n + ": " + ex.Message); failed++; }
            }
            Console.WriteLine("cases " + names.Length + ", failed " + failed);
            return failed == 0 ? 0 : 1;
        }
    }
}
