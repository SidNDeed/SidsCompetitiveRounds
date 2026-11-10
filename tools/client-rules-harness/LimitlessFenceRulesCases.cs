using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    using R = LimitlessFenceRules;

    /// <summary>
    /// Ask 16(a) lane 2: LimitlessFenceRules, executed (suite `fencerules`).
    /// The cases are written against a bundle of the rules' functions, so the
    /// same cases run on the real rules and on mutants of them; each mutant
    /// must turn its named cases red (#391). Every case prints its name.
    /// </summary>
    internal static class LimitlessFenceRulesCases
    {
        internal sealed class Result
        {
            internal int Run, Fail;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        internal sealed class Fns
        {
            internal Func<bool, bool, bool, int, int, int, int, bool> MaySend = R.MaySend;
            internal Func<int, int, string, R.GidLedger, bool, bool> MayResume = R.MayResume;
            internal Func<R.DecisionInputs, R.Decision> Decide = R.DecideContinuation;
            internal Func<IList<string>, string, IList<string>, string, int, int, bool> MustEnd = R.MustEnd;
            internal Func<R.HandlerInputs, R.Outcome> Handle = R.HandleFenceMessage;
            internal Func<int[], IList<int>, bool> RosterMatches = R.RosterMatches;
            internal Func<IList<int>, int> EndTarget = R.EndTarget;
            internal Func<R.State, bool, R.State> NextState = R.NextState;
            internal Func<bool, R.State, bool, bool> RefuseRawRound = R.RefuseRawRound;
            internal Func<R.Record, int[], int[], object[]> Encode = R.EncodeRecord;
            internal Func<bool, bool, string, R.GidLedger, bool> ShouldMint = R.ShouldMint;
            internal Action<R.GidLedger, string> End = (l, g) => l.EndGid(g);
            internal Func<R.GidLedger, string, bool> StartGame = (l, g) => l.AtOwnGameStart(g);
        }

        private const string G1 = "0123456789abcdef";
        private const string G2 = "fedcba9876543210";
        private const string V1 = "1-4e4806419fa25528";
        private const string V0 = "1-0000000000000000";

        private static R.Record Rec()
        {
            return new R.Record
            {
                Gid = G1, Target = 55, End = true, BaseWinner = 1, BaseWinnerRounds = 5, BaseOtherRounds = 3,
                BaseTarget = 5, Spectatable = true,
            };
        }

        private static readonly int[] Args = { 0, 1, 2, 3, 4, 5 };
        private static readonly int[] Roster = { 3, 1, 2 };

        private static object[] With(object[] o, int slot, object value)
        {
            var c = (object[])o.Clone();
            c[slot] = value;
            return c;
        }

        private static bool Decodes(object[] o)
        {
            R.Record r;
            int[] ro, ar;
            return R.TryDecodeRecord(o, out r, out ro, out ar);
        }

        private static R.DecisionInputs Ok()
        {
            return new R.DecisionInputs
            {
                MaySend = true, LiveGid = G1, HasRecord = false,
                FighterOptIns = new[] { G1, G1 }, ActorCapabilities = new[] { V1, V1, V1 }, MasterVersion = V1,
                HoldHasHeldSeat = false, HoldHasPendingCut = false, SeriesFollows = false,
            };
        }

        private static R.DecisionInputs Edit(Action<R.DecisionInputs> change)
        {
            var d = Ok();
            change(d);
            return d;
        }

        private static R.GidLedger LiveLedger(string gid)
        {
            var l = new R.GidLedger();
            l.AdoptRelayed(gid);
            return l;
        }

        private static R.HandlerInputs H(Action<R.HandlerInputs> change)
        {
            var h = new R.HandlerInputs
            {
                SenderIsMasterNow = true, MessageGid = G1, Ledger = LiveLedger(G1), HasRecord = false,
                RecordEnded = false, TransitionGuardDrops = false, DecisionRoster = new[] { 1, 2, 3 },
                OwnFighterRoster = new[] { 3, 2, 1 },
            };
            change(h);
            return h;
        }

        private static List<KeyValuePair<string, bool>> Cases(Fns f)
        {
            var c = new List<KeyValuePair<string, bool>>();
            Action<string, bool> add = (n, ok) => c.Add(new KeyValuePair<string, bool>(n, ok));

            // identity (4.2)
            add("gid: 16 lowercase hex is a gid", R.IsGid(G1));
            add("gid: uppercase, 15 or 17 characters, a non-hex letter or null is not",
                !R.IsGid("0123456789ABCDEF") && !R.IsGid("0123456789abcde") && !R.IsGid("0123456789abcdef0")
                && !R.IsGid("0123456789abcdeg") && !R.IsGid(null));
            add("gid: eight bytes give their lowercase hex",
                R.GidOf(new byte[] { 0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef }) == G1
                && R.GidOf(new byte[7]) == null);
            var led = new R.GidLedger();
            bool adopted = led.AdoptRelayed(G1);
            f.End(led, G1);
            add("ledger: an ended gid is never live again", adopted && !led.IsLiveGid(G1) && !led.AdoptRelayed(G1) && led.Current == null);
            var led2 = new R.GidLedger();
            led2.AdoptRelayed(G1);
            bool second = f.StartGame(led2, G2);
            add("ledger: a game start ends the previous gid and adopts the room's",
                second && led2.IsLiveGid(G2) && !led2.AdoptRelayed(G1));
            var led3 = new R.GidLedger();
            led3.AdoptRelayed(G1);
            f.End(led3, G1);
            add("ledger: a start finds only a value it ended and holds no gid", !f.StartGame(led3, G1) && led3.Current == null);
            var led4 = LiveLedger(G1);
            led4.ExitRoom();
            add("ledger: room exit forgets every gid", led4.Current == null && led4.AdoptRelayed(G1));
            var ended = new R.GidLedger();
            ended.AdoptRelayed(G1);
            f.End(ended, G1);
            add("mint: the master mints over a value it has ended", f.ShouldMint(true, true, G1, ended));
            add("mint: a value this seat has not ended is adopted, not replaced", !f.ShouldMint(true, true, G2, ended));
            add("mint: a malformed or absent room value is minted over",
                f.ShouldMint(true, true, null, new R.GidLedger()) && f.ShouldMint(true, true, "x", new R.GidLedger()));
            add("mint: never by a seat that is not master, nor before its own start",
                !f.ShouldMint(false, true, G1, ended) && !f.ShouldMint(true, false, G1, ended));
            add("mint: never while the seat holds a live gid", !f.ShouldMint(true, true, G2, LiveLedger(G1)));

            // the carrier (F11)
            var enc = f.Encode(Rec(), Roster, Args);
            R.Record back;
            int[] bro, bar;
            bool dec = R.TryDecodeRecord(enc, out back, out bro, out bar);
            var want = Rec();
            add("carrier: the gid round-trips", dec && back.Gid == want.Gid);
            add("carrier: the target round-trips", dec && back.Target == want.Target);
            add("carrier: the end flag round-trips", dec && back.End == want.End);
            add("carrier: the base winner round-trips", dec && back.BaseWinner == want.BaseWinner);
            add("carrier: the winner's rounds round-trip", dec && back.BaseWinnerRounds == want.BaseWinnerRounds);
            add("carrier: the other side's rounds round-trip", dec && back.BaseOtherRounds == want.BaseOtherRounds);
            add("carrier: the base target round-trips", dec && back.BaseTarget == want.BaseTarget);
            add("carrier: the spectatable flag round-trips", dec && back.Spectatable == want.Spectatable);
            add("carrier: the roster round-trips", dec && bro != null && bro.Length == 3 && bro[0] == 3 && bro[2] == 2);
            add("carrier: the round's arguments round-trip", dec && bar != null && bar.Length == 6 && bar[5] == 5);
            var good = R.EncodeRecord(Rec(), Roster, Args);
            bool everyNullRefused = true, everyTypeRefused = true;
            for (int i = 0; i < R.WireSlots; i++)
            {
                if (Decodes(With(good, i, null))) everyNullRefused = false;
                if (Decodes(With(good, i, 1.5f))) everyTypeRefused = false;
            }
            add("carrier: a missing field refuses the whole carrier, slot by slot", everyNullRefused);
            add("carrier: a mistyped field refuses the whole carrier, slot by slot", everyTypeRefused);
            add("carrier: a short or long carrier, or another version, is refused",
                !Decodes(new object[R.WireSlots - 1]) && !Decodes(new object[R.WireSlots + 1]) && !Decodes(With(good, 0, 2)));
            add("carrier: a target or base target below 1, or a negative count, is refused",
                !Decodes(With(good, 2, 0)) && !Decodes(With(good, 7, 0)) && !Decodes(With(good, 5, -1)));
            add("carrier: five arguments, or a roster with 0, a negative or a repeated actor, is refused",
                !Decodes(With(good, 10, new int[5])) && !Decodes(With(good, 9, new[] { 0 }))
                && !Decodes(With(good, 9, new[] { -2 })) && !Decodes(With(good, 9, new[] { 4, 4 })));
            add("carrier: the mirror's form (no roster, no arguments) decodes", Decodes(R.EncodeRecord(Rec(), null, null)));

            // targets and states (5.1, 4.3)
            add("target: a live record plays to base + 50", R.ContinueTarget(5) == 55);
            add("end target: 7-2 ends at 3", f.EndTarget(new[] { 7, 2 }) == 3);
            add("end target: FFA 8, 3 and 1 ends at 2", f.EndTarget(new[] { 8, 3, 1 }) == 2);
            add("end target: no sides reads 1", f.EndTarget(new int[0]) == 1 && f.EndTarget(null) == 1);
            bool everySideEnds = true;
            foreach (var s in new[] { new[] { 7, 2 }, new[] { 0, 0 }, new[] { 9, 9 }, new[] { 8, 3, 1 } })
            {
                int t = f.EndTarget(s);
                foreach (var n in s)
                    if (n + 1 < t) everySideEnds = false;
            }
            add("end target: whichever side completes the next round reaches it", everySideEnds);
            add("state: live with the end flag becomes terminating", f.NextState(R.State.Live, true) == R.State.Terminating);
            add("state: live without it stays live", f.NextState(R.State.Live, false) == R.State.Live);
            add("state: terminating never goes back to live", f.NextState(R.State.Terminating, false) == R.State.Terminating);
            add("state: ended stays ended", f.NextState(R.State.Ended, false) == R.State.Ended
                                           && f.NextState(R.State.Ended, true) == R.State.Ended);

            // authority (4.4, 4.5)
            add("MaySend: master, live gid, open record, same epoch and handoff count", f.MaySend(true, true, false, 4, 4, 2, 2));
            add("MaySend: a seat that is no longer master refuses", !f.MaySend(false, true, false, 4, 4, 2, 2));
            add("MaySend: a gid that is not live refuses", !f.MaySend(true, false, false, 4, 4, 2, 2));
            add("MaySend: an ended record refuses", !f.MaySend(true, true, true, 4, 4, 2, 2));
            add("MaySend: a new physical game since scheduling refuses", !f.MaySend(true, true, false, 5, 4, 2, 2));
            add("MaySend: a handoff since scheduling refuses", !f.MaySend(true, true, false, 4, 4, 3, 2));
            add("MayResume: same epoch and the captured gid still live", f.MayResume(4, 4, G1, LiveLedger(G1), false));
            add("MayResume: a new physical game refuses", !f.MayResume(5, 4, G1, LiveLedger(G1), false));
            add("MayResume: a replaced gid refuses", !f.MayResume(4, 4, G1, LiveLedger(G2), false));
            add("MayResume: an ended record refuses", !f.MayResume(4, 4, G1, LiveLedger(G1), true));
            add("MayResume: an item with no gid runs without one", f.MayResume(4, 4, null, new R.GidLedger(), false));
            add("MayClean: cleanup reads the epoch only", R.MayClean(4, 4) && !R.MayClean(5, 4));
            add("raw round: a live record refuses a call the fence did not make", f.RefuseRawRound(true, R.State.Live, false));
            add("raw round: a terminating record refuses it too", f.RefuseRawRound(true, R.State.Terminating, false));
            add("raw round: the fence's own call passes", !f.RefuseRawRound(true, R.State.Live, true));
            add("raw round: with no record, or an ended one, raw calls run as today",
                !f.RefuseRawRound(false, R.State.Live, false) && !f.RefuseRawRound(true, R.State.Ended, false));

            // the decision (4.7)
            add("decision: all five hold, so the game continues", f.Decide(Ok()) == R.Decision.Continue);
            add("decision: no MaySend decides no", f.Decide(Edit(d => d.MaySend = false)) == R.Decision.NotMaySend);
            add("decision: no live gid decides no", f.Decide(Edit(d => d.LiveGid = null)) == R.Decision.NoLiveGid);
            add("decision: a seat that holds a record decides no", f.Decide(Edit(d => d.HasRecord = true)) == R.Decision.HasRecord);
            add("decision: no fighters decides no", f.Decide(Edit(d => d.FighterOptIns = new string[0])) == R.Decision.NoFighters);
            add("decision: a fighter not opted in decides no", f.Decide(Edit(d => d.FighterOptIns = new[] { G1, null })) == R.Decision.OptIn);
            add("decision: an opt-in for another gid decides no", f.Decide(Edit(d => d.FighterOptIns = new[] { G1, G2 })) == R.Decision.OptIn);
            add("decision: a spectator at another version decides no",
                f.Decide(Edit(d => d.ActorCapabilities = new[] { V1, V1, V0 })) == R.Decision.Capability);
            add("decision: an actor without the capability decides no",
                f.Decide(Edit(d => d.ActorCapabilities = new[] { V1, null, V1 })) == R.Decision.Capability);
            add("decision: a held seat decides no", f.Decide(Edit(d => d.HoldHasHeldSeat = true)) == R.Decision.Hold);
            add("decision: a pending cut decides no", f.Decide(Edit(d => d.HoldHasPendingCut = true)) == R.Decision.Hold);
            add("decision: a following rated game decides no (D5)", f.Decide(Edit(d => d.SeriesFollows = true)) == R.Decision.Series);
            add("re-read: unchanged inputs do not end", !f.MustEnd(new[] { G1, G1 }, G1, new[] { V1, V1 }, V1, 2, 2));
            add("re-read: a handoff since the decision ends", f.MustEnd(new[] { G1, G1 }, G1, new[] { V1, V1 }, V1, 3, 2));
            add("re-read: a cleared opt-in ends", f.MustEnd(new[] { G1, null }, G1, new[] { V1, V1 }, V1, 2, 2));
            add("re-read: a changed capability ends", f.MustEnd(new[] { G1, G1 }, G1, new[] { V1, V0 }, V1, 2, 2));

            // the handler (4.7)
            add("handler: a valid decision on a seat with no record creates it", f.Handle(H(h => { })) == R.Outcome.Create);
            add("handler: the sender test comes first",
                f.Handle(H(h => { h.SenderIsMasterNow = false; h.TransitionGuardDrops = true; h.RecordEnded = true; })) == R.Outcome.RefuseNotMaster);
            add("handler: another gid is not covered", f.Handle(H(h => h.MessageGid = G2)) == R.Outcome.RefuseUncovered);
            add("handler: an ended record is not covered", f.Handle(H(h => { h.HasRecord = true; h.RecordEnded = true; })) == R.Outcome.RefuseUncovered);
            add("handler: the transition guard drops before the record changes",
                f.Handle(H(h => { h.HasRecord = true; h.TransitionGuardDrops = true; })) == R.Outcome.DropTransition);
            add("handler: a seat with a record updates it", f.Handle(H(h => h.HasRecord = true)) == R.Outcome.Update);
            add("handler: a roster that differs applies vanilla's round",
                f.Handle(H(h => h.OwnFighterRoster = new[] { 1, 2 })) == R.Outcome.ApplyAsVanilla);
            add("handler: no record and no roster is not covered",
                f.Handle(H(h => h.DecisionRoster = new int[0])) == R.Outcome.RefuseUncovered);
            add("roster: the same set in another order matches", f.RosterMatches(new[] { 1, 2, 3 }, new[] { 3, 1, 2 }));
            add("roster: a subset or a superset does not match",
                !f.RosterMatches(new[] { 1, 2 }, new[] { 1, 2, 3 }) && !f.RosterMatches(new[] { 1, 2, 3, 4 }, new[] { 1, 2, 3 }));
            add("roster: a duplicate entry never matches", !f.RosterMatches(new[] { 1, 1 }, new[] { 1, 2 }));
            add("roster: an empty roster never matches", !f.RosterMatches(new int[0], new int[0]));
            return c;
        }

        private static readonly string[] SlotName =
        {
            null, "the gid", "the target", "the end flag", "the base winner", "the winner's rounds",
            "the other side's rounds", "the base target", "the spectatable flag", "the roster", "the round's arguments",
        };

        private static readonly string[] SlotCase =
        {
            null, "carrier: the gid round-trips", "carrier: the target round-trips", "carrier: the end flag round-trips",
            "carrier: the base winner round-trips", "carrier: the winner's rounds round-trip",
            "carrier: the other side's rounds round-trip", "carrier: the base target round-trips",
            "carrier: the spectatable flag round-trips", "carrier: the roster round-trips",
            "carrier: the round's arguments round-trip",
        };

        /// <summary>A carrier that loses one field: the slot keeps a valid value
        /// of its type, so the decoder still accepts it, and only the round trip
        /// can see the loss.</summary>
        private static object[] Omit(object[] o, int slot)
        {
            object[] lost = { null, "0000000000000000", 1, false, 0, 0, 0, 1, false, new int[0], new int[0] };
            return With(o, slot, lost[slot]);
        }

        internal static Result Run()
        {
            var r = new Result();
            foreach (var kv in Cases(new Fns()))
                Check(r, "real: " + kv.Key, kv.Value, kv.Value ? "holds" : "broken");

            Control(r, "MaySend ignores the handoff count",
                    Cases(new Fns { MaySend = (m, g, e, en, ec, hn, hc) => R.MaySend(m, g, e, en, ec, hc, hc) }),
                    "MaySend: a handoff since scheduling refuses");
            Control(r, "MaySend ignores the epoch",
                    Cases(new Fns { MaySend = (m, g, e, en, ec, hn, hc) => R.MaySend(m, g, e, ec, ec, hn, hc) }),
                    "MaySend: a new physical game since scheduling refuses");
            Control(r, "MaySend ignores the record's end",
                    Cases(new Fns { MaySend = (m, g, e, en, ec, hn, hc) => R.MaySend(m, g, false, en, ec, hn, hc) }),
                    "MaySend: an ended record refuses");
            Control(r, "MayResume reads the epoch only",
                    Cases(new Fns { MayResume = (en, ec, cg, l, e) => en == ec }),
                    "MayResume: a replaced gid refuses", "MayResume: an ended record refuses");
            Control(r, "MayResume waits for a gid",
                    Cases(new Fns { MayResume = (en, ec, cg, l, e) => cg == null ? (en == ec && l != null && l.IsLiveGid(l.Current)) : R.MayResume(en, ec, cg, l, e) }),
                    "MayResume: an item with no gid runs without one");
            Control(r, "the decision ignores the capability",
                    Cases(new Fns { Decide = d => { d.ActorCapabilities = new[] { d.MasterVersion }; return R.DecideContinuation(d); } }),
                    "decision: a spectator at another version decides no", "decision: an actor without the capability decides no");
            Control(r, "the decision ignores the hold",
                    Cases(new Fns { Decide = d => { d.HoldHasHeldSeat = false; d.HoldHasPendingCut = false; return R.DecideContinuation(d); } }),
                    "decision: a held seat decides no", "decision: a pending cut decides no");
            Control(r, "the decision ignores D5",
                    Cases(new Fns { Decide = d => { d.SeriesFollows = false; return R.DecideContinuation(d); } }),
                    "decision: a following rated game decides no (D5)");
            Control(r, "the decision ignores the opt-ins",
                    Cases(new Fns { Decide = d => { d.FighterOptIns = new[] { d.LiveGid }; return R.DecideContinuation(d); } }),
                    "decision: a fighter not opted in decides no", "decision: an opt-in for another gid decides no");
            Control(r, "the re-read ignores the handoff count",
                    Cases(new Fns { MustEnd = (o, g, c, v, hn, hd) => R.MustEnd(o, g, c, v, hd, hd) }),
                    "re-read: a handoff since the decision ends");
            Control(r, "the handler tests the transition guard first",
                    Cases(new Fns { Handle = h => h.TransitionGuardDrops ? R.Outcome.DropTransition : R.HandleFenceMessage(h) }),
                    "handler: the sender test comes first");
            Control(r, "the handler creates without the roster comparison",
                    Cases(new Fns { Handle = h => { var o = R.HandleFenceMessage(h); return o == R.Outcome.ApplyAsVanilla ? R.Outcome.Create : o; } }),
                    "handler: a roster that differs applies vanilla's round");
            Control(r, "the handler takes a message without a roster as a decision",
                    Cases(new Fns { Handle = h => { var o = R.HandleFenceMessage(h); return o == R.Outcome.RefuseUncovered && !h.HasRecord && h.Ledger.IsLiveGid(h.MessageGid) && !h.RecordEnded ? R.Outcome.Create : o; } }),
                    "handler: no record and no roster is not covered");
            Control(r, "the handler applies an ended record's message",
                    Cases(new Fns { Handle = h => { h.RecordEnded = false; return R.HandleFenceMessage(h); } }),
                    "handler: an ended record is not covered");
            Control(r, "the roster ignores duplicates",
                    Cases(new Fns
                    {
                        RosterMatches = (d, o) =>
                        {
                            if (d == null || o == null || d.Length == 0) return false;
                            var m = new HashSet<int>(o);
                            if (m.Count != o.Count || m.Count != d.Length) return false;
                            foreach (var a in d)
                                if (!m.Contains(a)) return false;
                            return true;
                        },
                    }),
                    "roster: a duplicate entry never matches");
            Control(r, "the end target is the leader's plus one",
                    Cases(new Fns
                    {
                        EndTarget = s =>
                        {
                            if (s == null || s.Count == 0) return 1;
                            int mx = 0;
                            foreach (var n in s) mx = Math.Max(mx, n);
                            return mx + 1;
                        },
                    }),
                    "end target: 7-2 ends at 3", "end target: whichever side completes the next round reaches it");
            Control(r, "an empty side list ends at 0",
                    Cases(new Fns { EndTarget = s => s == null || s.Count == 0 ? 0 : R.EndTarget(s) }),
                    "end target: no sides reads 1");
            Control(r, "terminating goes back to live",
                    Cases(new Fns { NextState = (s, e) => s == R.State.Ended ? s : (e ? R.State.Terminating : R.State.Live) }),
                    "state: terminating never goes back to live");
            Control(r, "a terminating record lets raw calls through",
                    Cases(new Fns { RefuseRawRound = (h, s, fc) => h && s == R.State.Live && !fc }),
                    "raw round: a terminating record refuses it too");
            Control(r, "the mint ignores the ended test",
                    Cases(new Fns { ShouldMint = (m, a, v, l) => m && a && !(l != null && l.IsLiveGid(l.Current)) }),
                    "mint: a value this seat has not ended is adopted, not replaced");
            Control(r, "the terminal path forgets the gid",
                    Cases(new Fns { End = (l, g) => { } }),
                    "ledger: an ended gid is never live again");
            Control(r, "a game start keeps the previous gid",
                    Cases(new Fns { StartGame = (l, g) => l.AdoptRelayed(g) }),
                    "ledger: a game start ends the previous gid and adopts the room's");
            for (int i = 1; i < R.WireSlots; i++)
            {
                int slot = i;
                Control(r, "the carrier drops " + SlotName[slot],
                        Cases(new Fns { Encode = (rec, ro, ar) => Omit(R.EncodeRecord(rec, ro, ar), slot) }),
                        SlotCase[slot]);
            }
            return r;
        }

        private static void Check(Result r, string name, bool ok, string got)
        {
            r.Run++;
            if (!ok) r.Fail++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append((char)10);
        }

        private static void Control(Result r, string mutant, List<KeyValuePair<string, bool>> cases, params string[] mustFail)
        {
            var failed = new HashSet<string>();
            foreach (var kv in cases)
                if (!kv.Value) failed.Add(kv.Key);
            bool ok = true;
            foreach (var name in mustFail)
                if (!failed.Contains(name)) ok = false;
            Check(r, "mutant (" + mutant + ") is caught by its named cases", ok,
                  failed.Count == 0 ? "no case failed" : string.Join("; ", new List<string>(failed).ToArray()));
        }
    }
}
