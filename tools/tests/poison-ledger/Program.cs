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
            a.OnActivate(1, 1, aid, fighters, P0, 0);
            foreach (int x in fighters) a.OnAck(x, 1, aid);
            foreach (int x in extraAcks) a.OnAck(x, 1, aid);
            return a;
        }

        // 31. Every fighter must acknowledge; a spectator's ack is optional.
        private static void ActivationRequiresAllAcks()
        {
            var a = new ActivationCore(); string w;
            a.OnActivate(1, 1, 7, F12, P0, 0);
            Check(!a.Evaluate(F12, All, 10, P0, out w), "no acks");
            a.OnAck(1, 1, 7); a.OnAck(9, 1, 7);
            Check(!a.Evaluate(F12, All, 10, P0, out w) && w == "not-acked 1/2", "one fighter and a spectator: " + w);
            a.OnAck(2, 1, 8);
            Check(!a.Evaluate(F12, All, 10, P0, out w), "an ack for another activation does not count");
            a.OnAck(2, 1, 7);
            Check(a.Evaluate(F12, All, 10, P0, out w), "both fighters: " + w);
            Eq("1,2,9", string.Join(",", a.AckedPresent(new[] { 1, 2, 9 })), "the acknowledged spectator is an addressee");
        }

        // 32. Any entered/left/cap-change event kills v3 on the observing seat
        //     until a fresh activation is acknowledged; the old acks never count.
        private static void ActivationKilledByRoomEvent()
        {
            var a = Armed(7, F12); string w;
            Check(a.Evaluate(F12, All, 10, P0, out w), "armed");
            a.OnRoomEvent("player-entered actor=3");
            Check(!a.Evaluate(F12, All, 10, P0, out w) && w == "killed:player-entered actor=3", "event: " + w);
            Eq(0, a.AckedPresent(F12).Length, "nothing is addressed while off");
            a.OnAck(1, 1, 7); a.OnAck(2, 1, 7);
            Check(!a.Evaluate(F12, All, 20, P0, out w), "re-acks of the old activation do not revive it: " + w);
            a.OnActivate(1, 1, 8, F12, P0, 30); a.OnAck(1, 1, 8); a.OnAck(2, 1, 8);
            Check(a.Evaluate(F12, All, 40, P0, out w), "fresh activation: " + w);
        }

        // 33. A fighter without cr_pois3 turns v3 off and gets no ack anywhere.
        private static void ActivationCapMissing()
        {
            var fresh = new ActivationCore(); string w;
            Check(!fresh.Evaluate(F12, x => x != 2, 10, P0, out w) && w == "cap-missing actor=2", "before any activation: " + w);
            var a = Armed(7, F12);
            Check(!a.Evaluate(F12, x => x != 2, 10, P0, out w), "armed, then a fighter's cap missing");
            Check(!a.Evaluate(F12, All, 10, P0, out w), "sticky: " + w);
            var b = new ActivationCore();
            b.OnActivate(1, 1, 9, F12, P0, 0);
            Check(!b.ShouldAck(F12, x => x != 2, P0), "no ack with a fighter's cap missing");
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
            a.OnActivate(1, 1, 8, F12, P0, 50);
            Eq("1,2", string.Join(",", V3Targets.Capable(present, cap)), "ACTIVATE/ACK addressees exclude it");
            a.OnAck(1, 1, 8); a.OnAck(2, 1, 8);
            Check(a.Evaluate(F12, cap, 60, P0, out w), "an old spectator does not block the fighters: " + w);
            Eq("1,2", string.Join(",", a.AckedPresent(present)), "LIFE/summary addressees exclude it");
        }

        // 35. An ack only for the exact fighter roster.
        private static void AckRequiresExactRoster()
        {
            var a = new ActivationCore();
            a.OnActivate(1, 1, 7, F123, P0, 0);
            Check(a.ShouldAck(new[] { 3, 1, 2 }, All, P0), "exact, any order");
            Check(!a.ShouldAck(new[] { 1, 2 }, All, P0), "subset");
            Check(!a.ShouldAck(new[] { 1, 2, 3, 4 }, All, P0), "superset");
        }

        // 36. Only the current master's ACTIVATE counts.
        private static void ActivationMasterOnly()
        {
            var a = new ActivationCore(); string w;
            Check(!a.OnActivate(2, 1, 7, F12, P0, 0), "not the master");
            Check(!a.Evaluate(F12, All, 10, P0, out w) && w == "no-activation", w);
        }

        // 37. An activation not fully acknowledged in time is retired.
        private static void ActivationAckTimeout()
        {
            var a = new ActivationCore(); string w;
            a.OnActivate(1, 1, 7, F12, P0, 0);
            a.OnAck(1, 1, 7);
            Check(!a.Evaluate(F12, All, 14999, P0, out w) && w == "not-acked 1/2", "before the timeout: " + w);
            Check(!a.Evaluate(F12, All, 15000, P0, out w) && w == "killed:ack-timeout", "at the timeout: " + w);
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
            Check(!a.Evaluate(F123, cap, 10, P0, out w) && w == "cap-missing actor=3", w);
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
            a.OnActivate(1, 1, 8, F123, P0, 100);
            a.OnAck(3, 1, 8);
            Check(!a.Evaluate(F123, All, 110, P0, out w) && w == "not-acked 1/3", "the earlier acks do not carry over: " + w);
            a.OnAck(1, 1, 8); a.OnAck(2, 1, 8);
            Check(a.Evaluate(F123, All, 120, P0, out w), "all three: " + w);
        }

        // 49. A fighter leaving turns v3 off even before the event is seen.
        private static void FighterLeave()
        {
            var a = Armed(7, F123); string w;
            Check(!a.Evaluate(F12, All, 10, P0, out w) && w == "killed:roster-change", "fighter gone: " + w);
            Check(!a.Evaluate(F123, All, 20, P0, out w), "sticky: " + w);
        }

        // 50. A cr_pois3 change kills; a fighter whose value is no longer 1
        //     neither acks nor lets the master offer.
        private static void PropertyFlip()
        {
            Func<int, bool> flipped = x => x != 2;
            var a = Armed(7, F12); string w;
            a.OnRoomEvent("cap-change actor=2");
            Check(!a.Evaluate(F12, All, 10, P0, out w), "the event kills: " + w);
            a.OnActivate(1, 1, 8, F12, P0, 20);
            Check(!a.ShouldAck(F12, flipped, P0), "no ack while a fighter reads cr_pois3 != 1");
            Check(!V3Targets.ShouldOffer(F12, flipped, true), "no offer either");
        }

        // 51. Readmission: the fighter leaves and comes back under its actor
        //     number; a late ack from the previous activation never counts.
        private static void Readmission()
        {
            var a = Armed(7, F12); string w;
            a.OnRoomEvent("player-left actor=2");
            a.OnRoomEvent("player-entered actor=2");
            a.OnActivate(1, 1, 8, F12, P0, 100);
            a.OnAck(1, 1, 8);
            a.OnAck(2, 1, 7);
            Check(!a.Evaluate(F12, All, 110, P0, out w) && w == "not-acked 1/2", "the old ack: " + w);
            a.OnAck(2, 1, 8);
            Check(a.Evaluate(F12, All, 120, P0, out w), "re-acknowledged: " + w);
        }

        // 52. (restated by V4 B3) A join during an active stream: the joiner
        //     gets that stream's catch-up once it acknowledges (it never saw
        //     the header), and is a holder of its close summary from then on.
        private static void JoinDuringActiveStream()
        {
            var ret = new PointRetainer();
            var k = ret.Begin(V, 1, E(100), E(100), new[] { 1, 2 }, new[] { 1, 2 }, null);
            Eq("2", string.Join(",", PointRetainer.CloseTargets(k, new[] { 1, 2, 3 }, 1)),
                "not acknowledged: not caught up");
            Eq("1", Streams(ret.ReplayFor(3, 1, V, E(100), E(100))), "acknowledged: replayed");
            Eq("2,3", string.Join(",", PointRetainer.CloseTargets(k, new[] { 1, 2, 3, 4 }, 1)),
                "holders only; an actor that never held it gets nothing");
            Eq("3", string.Join(",", PointRetainer.CloseTargets(k, new[] { 1, 3 }, 1)), "a holder that left is dropped");
        }

        // 53. (restated by V4 B3) An actor present at the start WITHOUT the
        //     LIFE message handled the stream by today's path: never caught up
        //     on top of it, by replay or by the close summary.
        private static void TodayPathSeatNotCaughtUp()
        {
            var ret = new PointRetainer();
            var k = ret.Begin(V, 1, E(100), E(100), new[] { 1, 2 }, new[] { 1, 2, 9 }, null);
            Eq(0, ret.ReplayFor(9, 1, V, E(100), E(100)).Count, "the spectator that acked after the start");
            Eq("2", string.Join(",", PointRetainer.CloseTargets(k, new[] { 1, 2, 9 }, 1)), "excluded from the close");
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
            for (int s = 1; s <= PoisonLedgerCore.HeldCeilingPerView; s++)
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

        // ── V4 (fix pass 1) ──────────────────────────────────────────────

        private static readonly LifeEpoch P0 = default(LifeEpoch);

        private static string Streams(IEnumerable<Kept> ks) { return string.Join(",", ks.Select(k => k.Stream)); }

        private static void Deliver(PoisonLedgerCore l, Kept k, Ap ap)
        {
            int n = k.Ticks;
            l.OnSummary(k.View, k.Stream, k.Life, n, PoisonLedgerCore.Mask(k.Committed, n),
                PoisonLedgerCore.Mask(k.Blocked, n), null, true, ap);
        }

        // 56. F1: an actor that acknowledges late gets the victim's retained
        //     streams of the current life once, applies each missing tick
        //     once, and is never replayed to again.
        private static void LateAckerReplay()
        {
            var ret = new PointRetainer();
            LifeEpoch P = E(100), L = E(100);
            var k1 = ret.Begin(V, 1, P, L, new[] { 1, 2 }, new[] { 1, 2 }, null);
            foreach (int t in new[] { 0, 1, 3 }) PointRetainer.Note(k1, t, false);
            PointRetainer.Note(k1, 2, true);
            Eq("2", string.Join(",", PointRetainer.CloseTargets(k1, new[] { 1, 2 }, 1)), "closed before the join");
            var k2 = ret.Begin(V, 2, P, L, new[] { 1, 2 }, new[] { 1, 2 }, null);
            PointRetainer.Note(k2, 0, false); PointRetainer.Note(k2, 1, false);

            var late = new PoisonLedgerCore(); var ap = new Ap();
            late.AdoptPoint(100);
            var replay = ret.ReplayFor(3, 1, V, P, L);
            Eq("1,2", Streams(replay), "both retained streams");
            foreach (var k in replay) Deliver(late, k, ap);
            late.OnTick(V, 2, 2, false, true, ap);
            PointRetainer.Note(k2, 2, false);
            Eq("2,3", string.Join(",", PointRetainer.CloseTargets(k2, new[] { 1, 2, 3 }, 1)), "the late seat is a holder");
            Deliver(late, k2, ap);
            Eq("C1.0,C1.1,C1.3,C2.0,C2.1,R2.2", ap.Seen, "each missing tick once, the blocked one never");
            Eq(0, ret.ReplayFor(3, 1, V, P, L).Count, "a holder is never replayed to again");
            Eq(0, ret.ReplayFor(1, 1, V, P, L).Count, "nor this seat");
        }

        // 57. F1: a seat that executed no boundary RPC takes the point epoch
        //     from the ACTIVATE; the previous point's life is never applied.
        private static void NoBoundarySeatAdopts()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.AdoptPoint(100);
            Check(l.PointEpoch.SameAs(E(100)), "adopted");
            Check(!l.InPoint(E(50)) && !l.InPoint(P0) && l.InPoint(E(100)) && l.InPoint(E(150)), "in point");
            l.OnSummary(V, 1, E(50), 2, M(2, 0, 1), M(2), null, true, ap);
            l.OnSummary(V, 2, E(100), 2, M(2, 0, 1), M(2), null, true, ap);
            Eq("C2.0,C2.1", ap.Seen, "the previous point's life is never applied");
            l.AdoptPoint(80);
            Check(l.PointEpoch.SameAs(E(100)), "an older point is not adopted");
        }

        // 58. F1 (B2): such a seat takes the view's life from the owner's own
        //     record (a Phoenix life inside the point included); a seat that
        //     executed the boundary itself keeps A1's rule.
        private static void JoinerTakesOwnerLife()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.AdoptPoint(100);
            l.OnSummary(V, 1, E(150), 2, M(2, 0, 1), M(2), null, true, ap);
            Eq("C1.0,C1.1", ap.Seen, "the owner's life, applied");
            LifeEpoch f;
            Check(l.FenceOf(V, out f) && f.SameAs(E(150)), "fence taken from the owner");
            var own = new PoisonLedgerCore(); var ap2 = new Ap();
            own.NotePointBoundary(100);
            own.OnSummary(V, 1, E(150), 2, M(2, 0, 1), M(2), null, true, ap2);
            Eq("", ap2.Seen, "held until this seat's own revive");
            var both = new PoisonLedgerCore(); var ap3 = new Ap();
            both.AdoptPoint(100); both.NotePointBoundary(100);
            both.OnSummary(V, 1, E(150), 2, M(2, 0, 1), M(2), null, true, ap3);
            Eq("", ap3.Seen, "a seat that then executes the boundary itself keeps A1's rule too");
        }

        // 59. F1: only the view's current life in the current point is
        //     retained and replayed.
        private static void RetainedCurrentLifeOnly()
        {
            var ret = new PointRetainer();
            Check(ret.Begin(V, 1, E(100), E(100), new[] { 1 }, new[] { 1 }, null) != null, "kept");
            Eq("1", Streams(ret.ReplayFor(3, 1, V, E(100), E(100))), "the current life");
            ret.Begin(V, 2, E(100), E(150), new[] { 1 }, new[] { 1 }, null);
            Eq(1, ret.CountFor(V), "the previous life's streams are gone");
            Eq(0, ret.ReplayFor(4, 1, V, E(100), E(100)).Count, "a previous life is never replayed");
            Eq("2", Streams(ret.ReplayFor(4, 1, V, E(100), E(150))), "only the current life");
            Eq(0, ret.ReplayFor(5, 1, V, E(200), E(150)).Count, "nor at another point");
        }

        // 60. F1: the retained state is bounded per view and life.
        private static void RetainedBounded()
        {
            var ret = new PointRetainer();
            for (int s = 0; s < PointRetainer.MaxKeptPerLife; s++)
                Check(ret.Begin(V, s, E(1), E(1), new[] { 1 }, new[] { 1 }, null) != null, "kept " + s);
            Check(ret.Begin(V, 9999, E(1), E(1), new[] { 1 }, new[] { 1 }, null) == null, "past the bound the stream is today's");
            Check(ret.Begin(U, 1, E(1), E(1), new[] { 1 }, new[] { 1 }, null) != null, "another view");
            Check(ret.Begin(V, 10000, E(1), E(2), new[] { 1 }, new[] { 1 }, null) != null, "a new life starts fresh");
        }

        // 76. F1: a retained stream keeps only tick indices a receiver can
        //     hold, so its bytes are bounded by MaxTick whatever its length.
        private static void RetainedTicksBounded()
        {
            var ret = new PointRetainer();
            var k = ret.Begin(V, 1, E(1), E(1), new[] { 1 }, new[] { 1 }, null);
            for (int t = 0; t < PoisonLedgerCore.MaxTick + 500; t++) PointRetainer.Note(k, t, t % 7 == 3);
            PointRetainer.Note(k, -1, false);
            Eq(PoisonLedgerCore.MaxTick, k.Committed.Count + k.Blocked.Count, "at most MaxTick ticks kept");
            Eq(PoisonLedgerCore.MaxTick, k.Ticks, "the summary names the receivable range");
        }

        // 61. F1: a seat creates a new v3 record only after acknowledging an
        //     activation bound to its current point.
        private static void AcceptBoundToPoint()
        {
            var a = new ActivationCore();
            a.OnActivate(1, 1, 7, F12, E(100), 0);
            Check(!a.AcceptsAt(E(100)), "nothing before this seat's own ack");
            a.NoteSelfAck();
            Check(a.AcceptsAt(E(100)), "at the acknowledged point");
            Check(!a.AcceptsAt(E(200)), "not at the next point");
            Check(!a.AcceptsAt(P0), "nor with no point");
        }

        // 62. F1: a seat acknowledges only at the activation's own point.
        private static void AckBoundToPoint()
        {
            var a = new ActivationCore();
            a.OnActivate(1, 1, 7, F12, E(100), 0);
            Check(!a.ShouldAck(F12, All, E(200)), "no ack at another point");
            Check(!a.ShouldAck(F12, All, P0), "nor with no point");
            Check(a.ShouldAck(F12, All, E(100)), "at the activation's point");
        }

        // 63. F2: a boundary without its stamp retires every held record of
        //     the views it ends, pending ticks dropped; nothing of that life
        //     moves health afterwards.
        private static void UnstampedBoundaryRetires()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V); l.OnRevive(U);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            l.OnTick(V, 1, 1, false, false, ap);
            l.OnHeader(U, 2, E(100), false, null, true, ap);
            l.Break(V);
            Check(l.Find(V, 1) == null, "the view's held record retired");
            Eq("epoch-broken", l.RetiredLog[0].Retired, "named");
            Eq(1, l.RetiredLog[0].PendingDropped, "its pending tick dropped");
            Check(!l.OnTick(V, 1, 2, false, true, ap), "a later tick of it moves nothing");
            l.Fill(V, true, ap);
            Eq("R1.0,R2.0", ap.Seen, "nothing of that life after the boundary");
            Check(l.Find(U, 2) != null, "another view's record stays");
        }

        // 64. F2: after an unstamped boundary no record is created again in
        //     the room.
        private static void BrokenRefusesLater()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.Break(-1);
            Check(l.Broken, "broken");
            Check(l.OnHeader(V, 1, P0, false, null, true, ap) == null, "no new header record");
            Check(l.OnSummary(U, 2, E(5), 1, M(1, 0), M(1), null, true, ap) == null, "no new summary record");
            Eq("", ap.Seen, "nothing applied");
            l.Clear();
            Check(l.OnHeader(V, 1, P0, false, null, true, ap) != null, "the next room starts clean");
        }

        // 65. F3 (restates 19): current, terminal records at the ceiling are
        //     never evicted; the new record is refused instead.
        private static void HeldNeverEvicted()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            for (int s = 1; s <= PoisonLedgerCore.HeldCeilingPerView; s++)
            {
                l.OnHeader(V, s, P0, false, null, true, ap);
                l.OnSummary(V, s, P0, 1, M(1, 0), M(1), null, true, ap);
            }
            Check(l.OnHeader(V, 5000, P0, false, null, true, ap) == null, "past the ceiling a new record is refused");
            Check(l.Find(V, 1) != null, "the oldest current record is never evicted");
            Eq(0, l.RetiredLog.Count, "nothing retired");
            Eq(PoisonLedgerCore.HeldCeilingPerView, l.Count, "all held");
        }

        // 66. F4: sender pair marks are durable for the room; past the bound
        //     the seat sends nothing.
        private static void PairMarksDurable()
        {
            var c = new ClaimCore(); int id;
            for (int i = 0; i < ClaimCore.PairCap; i++)
                Eq(null, c.ShooterArm(true, null, true, true, i, V, i * 40L, out id), "send " + i);
            long now = ClaimCore.PairCap * 40L + 5000;
            Eq("pair-cap", c.ShooterArm(true, null, true, true, 999999, V, now, out id), "a new pair past the bound: no send");
            Eq("pair-marked", c.ShooterArm(true, null, true, true, 0, V, now + 10, out id), "the first pair is never forgotten");
            Eq("pair-cap", c.ShooterArm(true, null, true, true, 999999, V, now + 20, out id), "and stays refused");
        }

        // 67. F4: start results are durable for the room; past the bound no
        //     claim starts, so no second stream can follow an unrecorded one.
        private static void StartDurable()
        {
            var c = new ClaimCore();
            Check(c.TryStart(0, V, StartPath.Claim), "first claim starts");
            for (int i = 1; i < ClaimCore.StartedCap; i++) c.TryStart(i, V, StartPath.Broadcast);
            Check(!c.TryStart(0, V, StartPath.Broadcast), "the first pair's claim is never forgotten");
            Check(c.TryStart(99999, V, StartPath.Broadcast), "past the bound a broadcast proceeds as vanilla");
            Check(c.Saturated, "and the seat is saturated");
            Check(!c.TryStart(99999, V, StartPath.Claim), "no claim follows the unrecorded broadcast");
            Check(!c.TryStart(123456, V, StartPath.Claim), "no claim starts again");
            Check(!c.TryStart(0, V, StartPath.Broadcast), "still never forgotten");
            Eq("start-refused", c.VictimDecide(Facts(2, 1, 777777)), "named");
        }

        // 68. F5: the claim id is consumed before any lookup; a throwing
        //     lookup is that id's one terminal result.
        private static void ClaimFaultTerminal()
        {
            var c = new ClaimCore(); ClaimFacts got;
            Eq("fault:InvalidOperationException",
                c.Handle(2, 5, 1000, () => { throw new InvalidOperationException("lookup"); }, out got), "terminal");
            Eq("dup", c.Handle(2, 5, 1000, () => Facts(2, 5, 77), out got), "its repeat is a dup, never started");
            Eq("fault:no-facts", c.Handle(2, 6, 1000, () => null, out got), "no facts");
            Eq("started", c.Handle(2, 7, 1000, () => Facts(2, 7, 78), out got), "the next claim");
        }

        // 69. F7: every result is named and every line carries the tuple.
        private static void ClaimTerminalEveryPath()
        {
            var c = new ClaimCore(); ClaimFacts got;
            var results = new List<string>();
            var tweaks = new List<Action<ClaimFacts>>
            {
                f => f.GateOn = false, f => f.SenderAcked = false, f => f.VictimFound = false, f => f.ProjFound = false,
                f => f.ProjOwner = 9, f => f.PoisonChildren = 0, f => f.Live = false, f => f.VictimFenceKnown = false,
                f => { },
            };
            int id = 1;
            foreach (var t in tweaks)
            {
                var f = Facts(2, id, 500 + id); t(f);
                results.Add(c.Handle(2, id, 1000, () => f, out got));
                id++;
            }
            results.Add(c.Handle(2, 1, 1000, () => Facts(2, 1, 1), out got));
            results.Add(c.Handle(2, 99, 1000, () => { throw new ArgumentException(); }, out got));
            foreach (var r in results) Check(!string.IsNullOrEmpty(r), "a named result");
            Eq("gate:unknown,sender-not-acked,not-victim,no-projectile,not-owner,no-poison,not-live,fence,started,dup,fault:ArgumentException",
                string.Join(",", results), "every path");
            Eq("drop reason=rate", ClaimLine.Outcome("rate"), "a drop names its reason");
            Eq("drop reason=unnamed", ClaimLine.Outcome(null), "never an empty reason");
            Eq("sent", ClaimLine.Outcome("sent"), "sent");
            Eq("[POISON-CLAIM] recv from=2 c=5 proj=10 victim=1001 outcome=drop reason=malformed",
                ClaimLine.Recv(2, 5, 10, V, ClaimLine.Outcome("malformed")), "the tuple");
            Eq("[POISON-CLAIM] arm from=3 c=6 proj=10 victim=1001 outcome=drop reason=fault:NullReferenceException",
                ClaimLine.Arm(3, 6, 10, V, ClaimLine.Outcome("fault:NullReferenceException")), "the arm tuple");
        }

        // 70. F8 (M6): once the shared TryStart refuses the broadcast poison,
        //     a fault in the diagnostic after it never runs the effect.
        private static void RefusedStartStands()
        {
            var c = new ClaimCore();
            Eq("started", c.VictimDecide(Facts(2, 1, 77)), "a claim started the pair");
            int afterRan = 0;
            bool run = HookGuard.Prefix(() => c.TryStart(77, V, StartPath.Broadcast), ex => true,
                r => { afterRan++; throw new InvalidOperationException("diagnostic"); });
            Check(!run, "the refusal stands although the diagnostic threw");
            Eq(1, afterRan, "the diagnostic ran once");
            Check(HookGuard.Prefix(() => true, ex => false, r => { throw new Exception(); }), "a run stands too");
        }

        // 71. F8 (M7): a postfix step that throws stays inside its guard and
        //     the next step still runs.
        private static void PhoenixPostfixContained()
        {
            var steps = new List<string>();
            HookGuard.Run(() => { steps.Add("boundary"); throw new NullReferenceException(); });
            HookGuard.Run(() => steps.Add("flush"));
            Eq("boundary,flush", string.Join(",", steps), "contained, and the next step runs");
        }

        // 72. F8: a fault before the start decision never starts a second
        //     stream: skipped once a claim started, else vanilla with the seat
        //     saturated so no claim starts after it.
        private static void PrefixFaultNoSecondStream()
        {
            var c = new ClaimCore();
            Eq("started", c.VictimDecide(Facts(2, 1, 77)), "a claim started");
            Check(!HookGuard.Prefix(() => { throw new InvalidOperationException(); }, ex => c.FaultBeforeStart(), null),
                "skipped once a claim started");
            var d = new ClaimCore();
            Check(HookGuard.Prefix(() => { throw new InvalidOperationException(); }, ex => d.FaultBeforeStart(), null),
                "with no claim started it runs as vanilla");
            Check(d.Saturated, "saturated");
            Eq("start-refused", d.VictimDecide(Facts(2, 1, 88)), "no claim starts after it");
            Check(HookGuard.Prefix(() => { throw new Exception(); }, ex => { throw new Exception(); }, null),
                "a faulting fault handler runs the method");
        }

        // 73. F9: the SILENT line names its arm unambiguously.
        private static void SilentArmLabel()
        {
            Eq("local-only c=5", SilentArm.Label(5), "local-only");
            Eq("broadcast", SilentArm.Label(SilentArm.Broadcast), "broadcast");
            Eq("direct", SilentArm.Label(0), "outside any poison effect");
        }

        // 74. F10: the point boundary is a real invalidation on every seat;
        //     the re-take over the new point turns v3 on again.
        private static void RetakeInvalidates()
        {
            foreach (int self in new[] { 1, 2 })
            {
                var l = new PoisonLedgerCore(); l.NotePointBoundary(100);
                var a = new ActivationCore(); string w;
                a.OnActivate(1, 1, 7, F12, l.PointEpoch, 0);
                a.OnAck(1, 1, 7); a.OnAck(2, 1, 7); a.NoteSelfAck();
                Check(a.Evaluate(F12, All, 10, l.PointEpoch, out w), "seat " + self + " on at point 100: " + w);
                l.NotePointBoundary(200);
                Check(!a.Evaluate(F12, All, 20, l.PointEpoch, out w) && w == "killed:point-boundary",
                    "seat " + self + " the boundary kills: " + w);
                Check(!a.AcceptsAt(l.PointEpoch), "no new record at the next point under the old ack");
                Eq(0, a.AckedPresent(F12).Length, "nothing is addressed");
                a.OnAck(1, 1, 7); a.OnAck(2, 1, 7);
                Check(!a.Evaluate(F12, All, 30, l.PointEpoch, out w), "old acks never revive it: " + w);
                a.OnActivate(1, 1, 8, F12, l.PointEpoch, 40);
                Check(a.ShouldAck(F12, All, l.PointEpoch), "the re-take is acknowledged");
                a.OnAck(1, 1, 8); a.OnAck(2, 1, 8); a.NoteSelfAck();
                Check(a.Evaluate(F12, All, 50, l.PointEpoch, out w), "seat " + self + " on at point 200: " + w);
                Check(a.AcceptsAt(E(200)), "accepts at the new point");
            }
        }

        // F6: Protocol16 sizes of every v3 payload, element by element
        //     (array header 3; byte, bool 2; int, float 5; int[] 5+4n; byte[] 5+n).
        private static int Sz(object o)
        {
            if (o is byte || o is bool) return 2;
            if (o is int || o is float) return 5;
            if (o is int[]) return 5 + 4 * ((int[])o).Length;
            if (o is byte[]) return 5 + ((byte[])o).Length;
            var arr = o as object[];
            if (arr != null) { int n = 3; foreach (var x in arr) n += Sz(x); return n; }
            throw new Exception("unsized " + (o == null ? "null" : o.GetType().Name));
        }

        // 75. F6: the notes' traffic terms are the payloads' own sizes.
        private static void TrafficFormula()
        {
            Eq(24, Sz(V3Wire.Life(V, 1, E(5))), "LIFE");
            Eq(36, Sz(V3Wire.Claim(V, 7, 1, 5, 1, E(5))), "claim");
            Eq(17, Sz(V3Wire.Ack(7, 1)), "ACK");
            for (int r = 1; r <= 8; r++)
                Eq(24 + 4 * r, Sz(V3Wire.Activate(1, new int[r], E(5))), "ACTIVATE r=" + r);
            for (int n = 0; n <= 40; n++)
            {
                var m = PoisonLedgerCore.Mask(new int[0], n);
                Eq(78 + 2 * ((n + 7) / 8), Sz(V3Wire.Summary(V, 1, E(5), 0f, 0f, 0f, 0f, 0f, 1, false, 0, n, m, m, 1)),
                    "summary n=" + n);
            }
            Check(V3Wire.Life(V, 1, E(5)).Length < 7 && V3Wire.Activate(1, new int[2], E(5)).Length < 7
                && V3Wire.Ack(1, 1).Length < 7, "v1.40.3 drops every short v3 payload");
        }

        // ── Fix pass 2 ───────────────────────────────────────────────────

        // 77. H1: LIFE goes out, the header's raise fails, later tick raises
        //     would succeed. The victim retires the stream -- no later tick, no
        //     summary, no replay -- so the victim, a LIFE holder and a late
        //     acknowledger all leave the stream's health unchanged.
        private static void HeaderFailureRetires()
        {
            var ret = new PointRetainer();
            LifeEpoch P = E(100), L = E(100);
            var seat = new PoisonLedgerCore[4]; var ap = new Ap[4]; var inbox = new EpochInbox[4];
            for (int i = 1; i <= 3; i++)
            {
                seat[i] = new PoisonLedgerCore(); ap[i] = new Ap(); inbox[i] = new EpochInbox();
                seat[i].NotePointBoundary(100); seat[i].OnRevive(V);
            }
            var send = new StreamSend(V, ret.Begin(V, 1, P, L, new[] { 1, 2 }, new[] { 1, 2 }, null));
            inbox[1].Note(V, 1, L); inbox[2].Note(V, 1, L);           // LIFE to actors 1 (the victim) and 2: sent
            Check(send.AfterLife(ret, true), "v3 after its LIFE");
            send.AfterHeader(ret, false);                             // the header's raise fails: no seat gets it
            send.AfterTick(0, false, false);
            int ticksSent = 0;
            for (int t = 1; t <= 3; t++)
            {
                if (!send.MaySendTick) break;
                ticksSent++;
                for (int i = 1; i <= 3; i++) seat[i].OnTick(V, 1, t, false, true, ap[i]);
                send.AfterTick(t, false, true);
            }
            if (send.Kept != null && !send.Retired)                   // CloseV3: a kept, unretired stream only
                foreach (int a in PointRetainer.CloseTargets(send.Kept, new[] { 1, 2, 3 }, 1)) Deliver(seat[a], send.Kept, ap[a]);
            foreach (var k in ret.ReplayFor(3, 1, V, P, L)) Deliver(seat[3], k, ap[3]);   // actor 3 acknowledges late
            Eq("||", ap[1].Seen + "|" + ap[2].Seen + "|" + ap[3].Seen, "every seat leaves the stream's health unchanged");
            Eq(0, ticksSent, "no later tick");
            Eq(0, ret.CountFor(V), "out of the retained state");
            Check(inbox[2].Count == 1 && seat[2].Find(V, 1) == null, "the holder's LIFE names a stream it never holds");
        }

        // 78. H2: a fence this seat could not record -- a fault while recording
        //     it, or no stamp -- retires every held record of the views it ends
        //     before any later tick can move health; a recorded fence retires
        //     nothing of the current life.
        private static void FenceUnrecordedRetires()
        {
            var l = new PoisonLedgerCore(); var ap = new Ap();
            l.NotePointBoundary(100); l.OnRevive(V); l.OnRevive(U);
            l.OnHeader(V, 1, E(100), false, null, true, ap);
            l.OnTick(V, 1, 1, false, false, ap);                      // pending: the replica is not live
            l.OnHeader(U, 2, E(100), false, null, true, ap);
            Check(l.Fence(V, () => { l.OnRevive(V); return true; }), "a recorded revive fence");
            Check(l.Find(V, 1) != null && !l.Broken, "retires nothing of the current life");
            Check(!l.Fence(V, () => { throw new InvalidOperationException("revive"); }), "a fault while recording");
            Check(l.Find(V, 1) == null && l.Broken, "the view's held record retired");
            Eq(1, l.RetiredLog[0].PendingDropped, "its pending tick dropped");
            Check(!l.OnTick(V, 1, 2, false, true, ap), "a later tick of it moves nothing");
            l.Fill(V, true, ap);
            Check(l.Find(U, 2) != null, "another view's record stays");
            Check(!l.Fence(-1, () => false), "a point boundary without its stamp");
            Check(l.Find(U, 2) == null, "every view's record retired");
            Eq("R1.0,R2.0", ap.Seen, "nothing after the unrecorded fences");
        }

        // 79. H2 and the send sweep: an open stream retired by a fence this
        //     seat could not record sends nothing more -- no tick, and it is out
        //     of the retained state, so no summary or replay names it. A stream
        //     whose LIFE was not sent is today's everywhere and still sends.
        private static void RetiredStreamSendsNothing()
        {
            var ret = new PointRetainer();
            var send = new StreamSend(V, ret.Begin(V, 1, E(100), E(100), new[] { 1, 2 }, new[] { 1, 2 }, null));
            Check(send.AfterLife(ret, true) && send.AfterHeader(ret, true), "a live v3 stream");
            send.AfterTick(0, false, true); send.AfterTick(1, false, true);
            send.Retire(ret, "epoch-broken");
            Check(!send.MaySendTick && !send.V3, "nothing more is sent");
            Check(send.Kept == null, "no summary");
            Eq(0, ret.ReplayFor(3, 1, V, E(100), E(100)).Count, "no replay");
            Eq("epoch-broken", send.RetiredWhy, "named");
            var noLife = new StreamSend(V, ret.Begin(V, 2, E(100), E(100), new[] { 1, 2 }, new[] { 1, 2 }, null));
            Check(!noLife.AfterLife(ret, false) && noLife.Kept == null && noLife.MaySendTick,
                "LIFE not sent: today's everywhere, its header and ticks still go out");
            Eq(0, ret.CountFor(V), "and it leaves the retained state");
            var today = new StreamSend(V, null);
            Check(!today.AfterHeader(ret, false) && !today.MaySendTick, "any stream whose header failed sends nothing more");
        }

        private static object[] ClaimEv(int id, int proj) { return V3Wire.Claim(V, proj, id, 5, 1, E(100)); }

        // 80. M1: a current-protocol claim shorter than its nine typed elements
        //     gets exactly one line: its tuple as far as the payload carries it
        //     and the named result "malformed". Truncated claims count toward
        //     the rate before any parsing, like any other claim.
        private static void TruncatedClaimTerminal()
        {
            var c = new ClaimCore();
            int filled = 0, started = 0;
            Action<ClaimFacts> fill = f => filled++;
            Func<int, string> start = id => { started++; return "started streams=none"; };
            object T = V3Wire.TypeClaim, P = V3Wire.Protocol;
            c.Receive(2, new object[] { T, P }, 1000, fill, start);
            c.Receive(2, new object[] { T, P, V }, 1000, fill, start);
            c.Receive(2, new object[] { T, P, V, 10 }, 1000, fill, start);
            c.Receive(2, new object[] { T, P, V, 10, 7, 5 }, 1000, fill, start);
            Eq("[POISON-CLAIM] recv from=2 c=-1 proj=-1 victim=-1 outcome=drop reason=malformed|"
                + "[POISON-CLAIM] recv from=2 c=-1 proj=-1 victim=1001 outcome=drop reason=malformed|"
                + "[POISON-CLAIM] recv from=2 c=-1 proj=10 victim=1001 outcome=drop reason=malformed|"
                + "[POISON-CLAIM] recv from=2 c=7 proj=10 victim=1001 outcome=drop reason=malformed",
                string.Join("|", c.Lines), "one line each, the tuple as far as present");
            Eq(0, filled + started, "no fact collection, nothing started");
            c.Lines.Clear();
            for (int i = 0; i < 40; i++) c.Receive(3, new object[] { T, P }, 2000 + i, fill, start);
            Eq(ClaimCore.ClaimsPerRollingSecond, c.Lines.Count, "truncated claims are admitted by the rate first");
            c.FlushRate(3000, false);
            Eq(ClaimCore.ClaimsPerRollingSecond + 1, c.Lines.Count, "the excess is one aggregate line");
            Eq("[POISON-CLAIM] rate from=3 second=2 excess=8 first=(c=-1 proj=-1 victim=-1) last=(c=-1 proj=-1 victim=-1)"
                + " total=8 room_total=8 hw=-1 outcome=drop reason=rate", c.Lines[c.Lines.Count - 1], "counted, the tuples as far as present");
        }

        // 81. M2: ten times the rate from one sender, two seconds running.
        //     Within the rate each claim has its own line; past it each is
        //     refused "rate" and counted: one aggregate line per sender and
        //     aligned second with the first and last tuple and the running
        //     totals. Every claim is on its own line or in a counted aggregate,
        //     another sender is admitted on its own, and the line bytes are bounded.
        private static void ClaimRateBounded()
        {
            var c = new ClaimCore();
            int filled = 0;
            Action<ClaimFacts> fill = f => { filled++; f.GateOn = false; f.GateWhy = "test"; };
            Func<int, string> start = id => "started streams=none";
            int R = ClaimCore.ClaimsPerRollingSecond, N = 10 * R, id = 0;
            for (int s = 1; s <= 2; s++)
                for (int i = 0; i < N; i++) { id++; c.Receive(2, ClaimEv(id, 500 + id), s * 1000L + i * 3, fill, start); }
            c.Receive(3, ClaimEv(1, 9), 2500, fill, start);
            c.FlushRate(3000, false);
            var recv = c.Lines.Where(x => x.StartsWith("[POISON-CLAIM] recv ")).ToList();
            var rate = c.Lines.Where(x => x.StartsWith("[POISON-CLAIM] rate ")).ToList();
            Eq(2 * (R + 1) + 1, c.Lines.Count, "exactly R own lines and one aggregate per second, plus the other sender's");
            Eq(2 * R + 1, recv.Count, "own lines");
            Eq(2 * R + 1, filled, "facts collected for admitted claims only");
            Eq("[POISON-CLAIM] rate from=2 second=1 excess=288 first=(c=33 proj=533 victim=1001) last=(c=320 proj=820 victim=1001)"
                + " total=288 room_total=288 hw=320 outcome=drop reason=rate", rate[0], "the first second's aggregate");
            Eq("[POISON-CLAIM] rate from=2 second=2 excess=288 first=(c=353 proj=853 victim=1001) last=(c=640 proj=1140 victim=1001)"
                + " total=576 room_total=576 hw=640 outcome=drop reason=rate", rate[1], "the second's");
            Eq(2 * N, (recv.Count - 1) + 288 + 288, "every claim of the sender is on its own line or counted");
            Check(recv.Last().StartsWith("[POISON-CLAIM] recv from=3 c=1 "), "another sender is admitted on its own");
            Eq(95, ClaimLine.Recv(int.MinValue, int.MinValue, int.MinValue, int.MinValue, "").Length, "an own line: 95 bytes + its outcome");
            var ext = new object[] { null, null, int.MinValue, int.MinValue, int.MinValue };
            Eq(ClaimLine.RateMax, ClaimLine.Rate(int.MinValue, long.MinValue, int.MaxValue, ext, ext, long.MaxValue, long.MaxValue,
                int.MinValue).Length, "an aggregate line: at most RateMax bytes");
        }

        // ── Fix pass 3 (M2): every state that decides a claim's result is on a line ──

        // 82. A claim past the rate moves the sender's high water; a later
        //     claim within the rate that it makes a "dup" names that high water
        //     and the aggregate that counts it, and that aggregate carries hw=.
        //     A high water moved by a claim with its own line is named as such.
        private static void ClaimDupExplained()
        {
            var c = new ClaimCore();
            Action<ClaimFacts> fill = f => { f.GateOn = false; f.GateWhy = "test"; };
            Func<int, string> start = id => ClaimLine.Started(0, 0, 0, 0, 0, null);
            for (int i = 1; i <= ClaimCore.ClaimsPerRollingSecond; i++) c.Receive(2, ClaimEv(i, 500 + i), 1000 + i, fill, start);
            c.Receive(2, ClaimEv(100, 600), 1500, fill, start);   // past the rate: refused, high water 100
            c.Receive(2, ClaimEv(50, 601), 1600, fill, start);    // past the rate: refused, below the high water
            c.Receive(2, ClaimEv(60, 602), 2100, fill, start);    // within the rate again: decided by the refused 100
            c.Receive(2, ClaimEv(200, 603), 2200, fill, start);   // its own line moves the high water
            c.Receive(2, ClaimEv(150, 604), 2300, fill, start);
            var tail = c.Lines.Skip(ClaimCore.ClaimsPerRollingSecond).ToList();
            Eq("[POISON-CLAIM] rate from=2 second=1 excess=2 first=(c=100 proj=600 victim=1001) last=(c=50 proj=601 victim=1001)"
                + " total=2 room_total=2 hw=100 outcome=drop reason=rate", tail[0], "the aggregate carries the high water it moved");
            Eq("[POISON-CLAIM] recv from=2 c=60 proj=602 victim=1001 outcome=drop reason=dup hw=100 hw_from=rate second=1",
                tail[1], "the dup names the refused claim's high water and its aggregate");
            Eq("[POISON-CLAIM] recv from=2 c=150 proj=604 victim=1001 outcome=drop reason=dup hw=200 hw_from=line",
                tail[3], "a high water from a claim with its own line");
            Eq(4, tail.Count, "one line each");
        }

        // 83. VictimDecide's admitted claims get their one line like Receive's,
        //     so no high-water move is without its line.
        private static void VictimDecideLines()
        {
            var c = new ClaimCore();
            Eq("started", c.VictimDecide(Facts(2, 1, 77)), "started");
            Eq("dup", c.VictimDecide(Facts(2, 1, 77)), "its repeat");
            Eq("[POISON-CLAIM] recv from=2 c=1 proj=0 victim=1001 outcome=started|"
                + "[POISON-CLAIM] recv from=2 c=1 proj=0 victim=1001 outcome=drop reason=dup hw=1 hw_from=line",
                string.Join("|", c.Lines), "one line per admitted claim, the dup's deciding state named");
        }

        // 84. "start-refused" names the saturation that decided it: a poison
        //     prefix fault before any claim, or the durable start cap.
        private static void StartRefusedExplained()
        {
            var c = new ClaimCore();
            Check(c.FaultBeforeStart(), "no claim started: the effect runs and the seat saturates");
            Eq("start-refused", c.VictimDecide(Facts(2, 1, 77)), "refused");
            Check(c.Lines[0].EndsWith("outcome=drop reason=start-refused saturated=prefix-fault starts=0"), "named: " + c.Lines[0]);
            var d = new ClaimCore();
            for (int i = 1; i <= ClaimCore.StartedCap; i++) d.TryStart(i, V, StartPath.Broadcast);
            Check(d.TryStart(ClaimCore.StartedCap + 1, V, StartPath.Broadcast), "past the cap a broadcast proceeds");
            Eq("start-refused", d.VictimDecide(Facts(2, 1, 999999)), "refused");
            Check(d.Lines[0].EndsWith("outcome=drop reason=start-refused saturated=start-cap starts=16384"), "named: " + d.Lines[0]);
        }

        // 86. Every claim past the rate is counted where its aggregate says:
        //     the sender's own total and the room's total across senders.
        private static void RateTotalsCounted()
        {
            var c = new ClaimCore();
            Action<ClaimFacts> fill = f => { f.GateOn = false; f.GateWhy = "test"; };
            Func<int, string> start = id => "started";
            for (int s = 2; s <= 3; s++)
                for (int i = 1; i <= ClaimCore.ClaimsPerRollingSecond + 2; i++) c.Receive(s, ClaimEv(i, i), 1000 + i, fill, start);
            c.FlushRate(2000, false);
            var rate = c.Lines.Where(x => x.StartsWith("[POISON-CLAIM] rate ")).ToList();
            Eq(2, rate.Count, "one aggregate per sender");
            foreach (var r in rate)
                Check(r.Contains(" excess=2 ") && r.Contains(" total=2 room_total=4 hw=34 "), "counted: " + r);
        }

        // 85. Every claim line has a finite length bound (bytes: case 87): the outcome field is
        //     capped, a started claim's outcome counts its streams and children
        //     (no per-stream or per-child list), and an exception type is capped.
        private static void ClaimLineBounded()
        {
            string big = new string('x', 10000);
            Eq(ClaimLine.RecvMax, ClaimLine.Recv(int.MinValue, int.MinValue, int.MinValue, int.MinValue, big).Length, "recv");
            Eq(ClaimLine.RecvMax - 1, ClaimLine.Arm(int.MinValue, int.MinValue, int.MinValue, int.MinValue, big).Length, "arm");
            Eq("started streams=3 first=s10 last=s12 children=4 threw=2 contained=0 first_fault=child:NullReferenceException",
                ClaimLine.Started(3, 10, 4, 2, 0, "child:NullReferenceException"), "one field per fact");
            Eq("started streams=0 children=1 threw=0 contained=0", ClaimLine.Started(0, 10, 1, 0, 0, null), "nothing opened");
            string st = ClaimLine.Started(int.MaxValue, int.MinValue, int.MaxValue, int.MaxValue, int.MaxValue, big);
            Check(st.Length <= ClaimLine.OutcomeMax && st.EndsWith("..."), "an oversized fault name is cut: " + st.Length);
            string wide = ClaimLine.Started(int.MaxValue, int.MinValue, int.MinValue, int.MinValue, int.MaxValue,
                new string('y', ClaimLine.FaultMax));
            Check(wide.Contains(" first_fault="), "the widest outcome carries its fault name");
            Check(wide.Length <= ClaimLine.OutcomeMax && !wide.EndsWith("..."),
                "every number at its widest fits uncut: " + wide.Length);
            Check(ClaimLine.StartFault(big).Length <= ClaimLine.OutcomeMax, "a start fault");
            var c = new ClaimCore();
            c.Receive(2, ClaimEv(1, 9), 1000, f => { f.GateOn = false; f.GateWhy = big; }, id => "started");
            Check(c.Lines[0].Length <= ClaimLine.RecvMax && c.Lines[0].EndsWith("..."),
                "a received claim's line with an oversized reason: " + c.Lines[0].Length);
        }

        // 87. Fix pass 4 (M2): the bound is in encoded bytes. Every claim line
        //     is printable ASCII, so its UTF-8 byte count is its length, even
        //     when a text field carries other characters or a line break.
        private static void ClaimLineAscii()
        {
            string odd = "gate:\u00e9t\u00e9\n\u2713\u0000" + new string('\u4e2d', 400);
            var lines = new List<string>
            {
                ClaimLine.Recv(int.MinValue, int.MinValue, int.MinValue, int.MinValue, odd),
                ClaimLine.Arm(int.MinValue, int.MinValue, int.MinValue, int.MinValue, odd),
                ClaimLine.Recv(1, 2, 3, 4, ClaimLine.Started(1, 2, 3, 1, 1, "child:\u00c9rror\r\n")),
                ClaimLine.Recv(1, 2, 3, 4, ClaimLine.StartFault("T\u00ffpe\n")),
            };
            var c = new ClaimCore();
            c.Receive(2, ClaimEv(1, 9), 1000, f => { f.GateOn = false; f.GateWhy = odd; }, id => "started");
            lines.AddRange(c.Lines);
            foreach (var l in lines)
            {
                Eq(l.Length, System.Text.Encoding.UTF8.GetByteCount(l), "bytes == length: " + l.Length);
                Check(l.Length <= ClaimLine.RecvMax, "within the byte bound: " + l.Length);
                foreach (char ch in l) Check(ch >= ' ' && ch <= '~', "printable ASCII only");
            }
            Eq("drop reason=gate:?t??", ClaimLine.Cap("drop reason=gate:\u00e9t\u00e9\n", 100), "each other character is one '?'");
        }

        // 88. Fix pass 4 (M2): a fault contained inside a claim's start (a
        //     child's prefix, the scheduler, a stream's first step) reaches the
        //     claim's own outcome: counted, and named when it is the first.
        private static void StartedContainedCounted()
        {
            Eq("started streams=1 first=s5 last=s5 children=2 threw=0 contained=3 first_fault=prefix:NullReferenceException",
                ClaimLine.Started(1, 5, 2, 0, 3, "prefix:NullReferenceException"), "contained faults counted and named");
            Eq("started streams=0 children=1 threw=0 contained=1 first_fault=unknown",
                ClaimLine.Started(0, 0, 1, 0, 1, null), "a contained fault with no name is still named as one");
        }

        // Fix pass 5 (M2): the cultures a receiving thread may run under. One
        // with a non-ASCII negative sign (U+2212, as sv-SE writes it), one
        // whose NumberFormatInfo is customized (a long negative and positive
        // sign with non-ASCII letters), and sv-SE itself when this runtime has
        // it. Each must really format -5 otherwise, or the case proves nothing.
        private static void UnderCultures(string what, Action body)
        {
            var saved = System.Globalization.CultureInfo.CurrentCulture;
            var minus = (System.Globalization.CultureInfo)System.Globalization.CultureInfo.InvariantCulture.Clone();
            minus.NumberFormat.NegativeSign = new string((char)0x2212, 1);
            var custom = (System.Globalization.CultureInfo)System.Globalization.CultureInfo.InvariantCulture.Clone();
            custom.NumberFormat.NegativeSign = "neg" + (char)0xE9 + (char)0xE9;
            custom.NumberFormat.PositiveSign = "pos" + (char)0xE9;
            var cultures = new List<System.Globalization.CultureInfo> { minus, custom };
            try
            {
                var sv = new System.Globalization.CultureInfo("sv-SE");
                if ((-5).ToString(sv) != "-5") cultures.Add(sv);
            }
            catch { }
            try
            {
                foreach (var ci in cultures)
                {
                    System.Globalization.CultureInfo.CurrentCulture = ci;
                    Check((-5).ToString() != "-5" && (-5L).ToString() != "-5",
                        what + ": culture " + ci.Name + " formats -5 otherwise");
                    body();
                }
            }
            finally { System.Globalization.CultureInfo.CurrentCulture = saved; }
        }

        private static void Ascii(string line, int max, string what)
        {
            Eq(line.Length, System.Text.Encoding.UTF8.GetByteCount(line), what + ": bytes == length");
            Check(line.Length <= max, what + ": within " + max + " bytes: " + line.Length);
            foreach (char ch in line) Check(ch >= ' ' && ch <= '~', what + ": printable ASCII only");
        }

        // 89. Fix pass 5: N writes every number the same on every seat.
        private static void NumberFormatInvariant()
        {
            UnderCultures("N", () =>
            {
                Eq("-5", ClaimLine.N(-5), "-5");
                Eq("0", ClaimLine.N(0), "0");
                Eq("2147483647", ClaimLine.N(int.MaxValue), "int max");
                Eq("-2147483648", ClaimLine.N(int.MinValue), "int min");
                Eq("-9223372036854775808", ClaimLine.N(long.MinValue), "long min");
                Eq("9223372036854775807", ClaimLine.N(long.MaxValue), "long max");
            });
        }

        // 90. Fix pass 5: an arm line, numeric fields negative, under each culture.
        private static void ArmLineInvariant()
        {
            UnderCultures("arm", () =>
            {
                Eq("[POISON-CLAIM] arm from=-5 c=-2147483648 proj=-1 victim=-7 outcome=sent",
                    ClaimLine.Arm(-5, int.MinValue, -1, -7, "sent"), "arm");
                Ascii(ClaimLine.Arm(int.MinValue, int.MinValue, int.MinValue, int.MinValue, new string('x', 999)),
                    ClaimLine.RecvMax - 1, "arm widest");
            });
        }

        // 91. Fix pass 5: a recv line, numeric fields negative, under each culture.
        private static void RecvLineInvariant()
        {
            UnderCultures("recv", () =>
            {
                Eq("[POISON-CLAIM] recv from=-5 c=-2147483648 proj=-1 victim=-7 outcome=drop reason=malformed",
                    ClaimLine.Recv(-5, int.MinValue, -1, -7, "drop reason=malformed"), "recv");
                Ascii(ClaimLine.Recv(int.MinValue, int.MinValue, int.MinValue, int.MinValue, new string('x', 999)),
                    ClaimLine.RecvMax, "recv widest");
            });
        }

        // 95. Fix pass 5: a dup outcome's own number (the deciding high
        //     water) on a received claim's line, under each culture.
        private static void DupStateInvariant()
        {
            UnderCultures("dup", () =>
            {
                var c = new ClaimCore();
                c.Receive(-3, ClaimEv(-9, 9), 1000, f => { f.GateOn = false; f.GateWhy = "off"; }, id => "started");
                c.Receive(-3, ClaimEv(-9, 9), 1001, f => { f.GateOn = false; f.GateWhy = "off"; }, id => "started");
                Eq(2, c.Lines.Count, "two lines");
                Check(c.Lines[1].EndsWith("outcome=drop reason=dup hw=-9 hw_from=line"), "the dup names its high water: " + c.Lines[1]);
                foreach (var x in c.Lines) Ascii(x, ClaimLine.RecvMax, "received");
            });
        }

        // 92. Fix pass 5: a rate line's own numeric fields negative, under each culture.
        private static void RateLineInvariant()
        {
            UnderCultures("rate", () =>
            {
                var t = new object[] { V3Wire.TypeClaim, V3Wire.Protocol, 3, 2, 1 };
                Eq("[POISON-CLAIM] rate from=-5 second=-2 excess=1 first=(c=1 proj=2 victim=3) last=(c=1 proj=2 victim=3)"
                    + " total=1 room_total=1 hw=-9 outcome=drop reason=rate",
                    ClaimLine.Rate(-5, -2, 1, t, t, 1, 1, -9), "rate");
                var w = new object[] { V3Wire.TypeClaim, V3Wire.Protocol, int.MinValue, int.MinValue, int.MinValue };
                Ascii(ClaimLine.Rate(int.MinValue, long.MinValue, int.MaxValue, w, w, long.MaxValue, long.MaxValue, int.MinValue),
                    ClaimLine.RateMax, "rate widest");
            });
        }

        // 93. Fix pass 5: a rate line's tuples negative (claim, projectile, victim).
        private static void RateTupleInvariant()
        {
            UnderCultures("tuple", () =>
            {
                var t = new object[] { V3Wire.TypeClaim, V3Wire.Protocol, -3, -2, -1 };
                Eq("[POISON-CLAIM] rate from=5 second=2 excess=1 first=(c=-1 proj=-2 victim=-3) last=(c=-1 proj=-2 victim=-3)"
                    + " total=1 room_total=1 hw=9 outcome=drop reason=rate",
                    ClaimLine.Rate(5, 2, 1, t, t, 1, 1, 9), "tuple");
            });
        }

        // 94. Fix pass 5: a started claim's counts and stream ids, under each culture.
        private static void StartedInvariant()
        {
            UnderCultures("started", () =>
            {
                Eq("started streams=1 first=s-4 last=s-4 children=1 threw=0 contained=0",
                    ClaimLine.Started(1, -4, 1, 0, 0, null), "started");
                Eq("started streams=-1 children=-2 threw=-3 contained=-4", ClaimLine.Started(-1, 0, -2, -3, -4, "x"),
                    "negative counts");
            });
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
            { "late_acker_replay", LateAckerReplay },
            { "no_boundary_seat_adopts", NoBoundarySeatAdopts },
            { "joiner_takes_owner_life", JoinerTakesOwnerLife },
            { "retained_current_life_only", RetainedCurrentLifeOnly },
            { "retained_bounded", RetainedBounded },
            { "retained_ticks_bounded", RetainedTicksBounded },
            { "accept_bound_to_point", AcceptBoundToPoint },
            { "ack_bound_to_point", AckBoundToPoint },
            { "unstamped_boundary_retires", UnstampedBoundaryRetires },
            { "broken_refuses_later", BrokenRefusesLater },
            { "held_never_evicted", HeldNeverEvicted },
            { "pair_marks_durable", PairMarksDurable },
            { "start_durable", StartDurable },
            { "claim_fault_terminal", ClaimFaultTerminal },
            { "claim_terminal_every_path", ClaimTerminalEveryPath },
            { "refused_start_stands", RefusedStartStands },
            { "phoenix_postfix_contained", PhoenixPostfixContained },
            { "prefix_fault_no_second_stream", PrefixFaultNoSecondStream },
            { "silent_arm_label", SilentArmLabel },
            { "retake_invalidates", RetakeInvalidates },
            { "traffic_formula", TrafficFormula },
            { "header_failure_retires", HeaderFailureRetires },
            { "fence_unrecorded_retires", FenceUnrecordedRetires },
            { "retired_stream_sends_nothing", RetiredStreamSendsNothing },
            { "truncated_claim_terminal", TruncatedClaimTerminal },
            { "claim_rate_bounded", ClaimRateBounded },
            { "claim_dup_explained", ClaimDupExplained },
            { "victim_decide_lines", VictimDecideLines },
            { "start_refused_explained", StartRefusedExplained },
            { "claim_line_bounded", ClaimLineBounded },
            { "rate_totals_counted", RateTotalsCounted },
            { "claim_line_ascii", ClaimLineAscii },
            { "started_contained_counted", StartedContainedCounted },
            { "number_format_invariant", NumberFormatInvariant },
            { "arm_line_invariant", ArmLineInvariant },
            { "recv_line_invariant", RecvLineInvariant },
            { "rate_line_invariant", RateLineInvariant },
            { "rate_tuple_invariant", RateTupleInvariant },
            { "started_invariant", StartedInvariant },
            { "dup_state_invariant", DupStateInvariant },
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
