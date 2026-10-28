// RJ readmission P1 (V3 T1.1, T1.2): the ordered-effect-trace twin run.
// OldReducer is ApplyManifestPick as it stood at the lane base; NewReducer is
// the split one from the tree under test (or a mutant copy). Both are the REAL
// method bodies, extracted by run_rj.py and compiled against Stubs.cs. A case
// passes when the two traces are equal element by element: every event, in
// order, with the state snapshot at that event (yield observers included).
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds
{
    internal static class TraceProgram
    {
        private static readonly string[] Names = { "AA", "BB", "CC", "DD", "EE", "FF", "GG" };

        private static void SetupPool()
        {
            CardChoice.instance = new CardChoice { cards = Names.Select(n => new CardInfo(n)).ToArray() };
            CardChoice.instance.cards[2].rarity = CardInfo.Rarity.Rare;
        }

        private static CardInfo Card(string n) { return CardChoice.instance.cards.First(c => c.gameObject.name == n); }

        private static Player Body(int pid, bool mine, string nick)
        {
            var p = new Player
            {
                PlayerID = pid, TeamID = pid, gameObject = new GameObject("P" + pid),
                data = new CharacterData { view = new PhotonView { IsMine = mine, Owner = new OwnerStub { NickName = nick } } }
            };
            ReducerBase.Fighters[pid] = p;
            return p;
        }

        private static void Roster(int count)
        {
            ApiClient.FfaLockedRoster = new List<ApiClient.TeamQueueMember>();
            for (int i = 0; i < count; i++)
                ApiClient.FfaLockedRoster.Add(new ApiClient.TeamQueueMember { steam_id = "s" + i, display_name = "Seat" + i });
        }

        /// <summary>One fixture: the world before the apply, the call, the inject.</summary>
        private sealed class Fixture
        {
            internal int Pid;
            internal string Card;
            internal string Inject = "";
            internal Action Setup;
        }

        private static readonly Dictionary<string, Fixture> Fixtures = new Dictionary<string, Fixture>
        {
            // a five-card rolling deck, a remote body
            ["rolling"] = new Fixture { Pid = 2, Card = "FF", Setup = () =>
            {
                Body(2, false, "Seat2");
                ReducerBase.SeedDeck(2, new[] { "AA", "BB", "CC", "DD", "EE" }.Select(Card));
                ReducerBase.SeedHistory(2, new[] { "AA", "BB", "CC", "DD", "EE" });
            } },
            ["local"] = new Fixture { Pid = 1, Card = "CC", Setup = () =>
            {
                Body(1, true, "Seat1");
                ReducerBase.SeedDeck(1, new[] { "AA", "BB" }.Select(Card));
                ReducerBase.SeedHistory(1, new[] { "AA", "BB" });
            } },
            ["remote"] = new Fixture { Pid = 3, Card = "BB", Setup = () =>
            {
                Body(3, false, "Seat3");
                ReducerBase.SeedDeck(3, new[] { "AA" }.Select(Card));
            } },
            ["unknown"] = new Fixture { Pid = 3, Card = "ZZ", Setup = () => { Body(3, false, "Seat3"); } },
            ["quarantined"] = new Fixture { Pid = 4, Card = "AA", Setup = () =>
            {
                Body(4, false, "Seat4");
                FfaLateEntry.Quarantined.Add(4);
            } },
            ["nobody"] = new Fixture { Pid = 5, Card = "AA", Setup = () =>
            {
                ReducerBase.SeedDeck(5, new[] { "AA", "BB", "CC", "DD", "EE" }.Select(Card));
            } },
            // T1.2: a rolling LOCAL deck (every physical statement and the
            // local-pick bookkeeping reached), clean and with each injected throw
            ["rolling_local"] = new Fixture { Pid = 1, Card = "GG", Setup = RollingLocal },
            ["throw_replay"] = new Fixture { Pid = 1, Card = "GG", Inject = "replay", Setup = RollingLocal },
            ["throw_apply"] = new Fixture { Pid = 1, Card = "GG", Inject = "apply", Setup = RollingLocal },
            ["throw_audit"] = new Fixture { Pid = 1, Card = "GG", Inject = "audit", Setup = RollingLocal },
            ["throw_rebuild"] = new Fixture { Pid = 1, Card = "GG", Inject = "rebuild", Setup = RollingLocal },
        };

        private static void RollingLocal()
        {
            Body(1, true, "Seat1");
            ReducerBase.SeedDeck(1, new[] { "AA", "BB", "CC", "DD", "EE" }.Select(Card));
            ReducerBase.SeedHistory(1, new[] { "AA", "BB", "CC", "DD", "EE" });
        }

        /// <summary>Runs a coroutine to its end the way Unity does: a yielded
        /// IEnumerator runs nested before its parent resumes; every other
        /// yield is a frame, recorded with the state at that instant.</summary>
        private static List<string> Drive(IEnumerator it)
        {
            var stack = new Stack<IEnumerator>();
            stack.Push(it);
            try
            {
                while (stack.Count > 0)
                {
                    var top = stack.Peek();
                    if (!top.MoveNext()) { stack.Pop(); continue; }
                    if (top.Current is IEnumerator nested) { stack.Push(nested); continue; }
                    Trace.Event("yield");
                }
                Trace.Event("end");
            }
            catch (Exception ex)
            {
                Trace.Event("exception " + ex.GetType().Name + " " + ex.Message);
            }
            return new List<string>(Trace.Events);
        }

        private static List<string> RunOne(bool useNew, Fixture f, bool bodiless, bool withBody)
        {
            ReducerBase.ResetState();
            Trace.Events.Clear();
            SetupPool();
            Roster(8);
            Trace.Inject = "";
            f.Setup();
            if (!withBody) ReducerBase.Fighters.Remove(f.Pid);
            Trace.Inject = f.Inject;
            var it = useNew ? NewReducer.Run(f.Pid, f.Card, 7, bodiless) : OldReducer.Run(f.Pid, f.Card, 7, false);
            var t = Drive(it);
            Trace.Inject = "";
            return t;
        }

        private static readonly string[] Physical =
            { "baseline ", "replay_start ", "replay_end ", "apply_card ", "diag ", "rebuild_views ", "cr_cards ", "yield",
              "info [FFA-GUNAUDIT]" };

        /// <summary>The logical projection of a trace: the physical events and
        /// yields removed, and the bar-suppression set (a body-side flag) cut
        /// from every snapshot.</summary>
        private static List<string> Logical(List<string> t)
        {
            var o = new List<string>();
            foreach (var e in t)
            {
                if (Physical.Any(p => e.StartsWith(p, StringComparison.Ordinal))) continue;
                int cut = e.IndexOf(" rebuilds[", StringComparison.Ordinal);
                o.Add(cut >= 0 ? e.Substring(0, cut) : e);
            }
            return o;
        }

        private static bool Compare(string name, List<string> a, List<string> b)
        {
            int n = Math.Max(a.Count, b.Count);
            for (int i = 0; i < n; i++)
            {
                string x = i < a.Count ? a[i] : "<none>";
                string y = i < b.Count ? b[i] : "<none>";
                if (x != y)
                {
                    Console.WriteLine("FAIL " + name + " at element " + i);
                    Console.WriteLine("  old: " + x);
                    Console.WriteLine("  new: " + y);
                    return false;
                }
            }
            if (a.Count < 2)
            {
                Console.WriteLine("FAIL " + name + " vacuous trace (" + a.Count + " elements)");
                return false;
            }
            Console.WriteLine("PASS " + name + " (" + a.Count + " elements equal)");
            return true;
        }

        /// <summary>V3 P2 step 8: a bodiless apply's pick toast reads
        /// "{name} (away) got {card}" where a bodied apply reads "{name}
        /// picked {card}". Every other element is unchanged, so the expected
        /// trace is the old projection with that one wording swapped.</summary>
        private static List<string> Away(List<string> t)
        {
            return t.Select(e => e.Replace(" picked ", " (away) got ")).ToList();
        }

        /// <summary>The positive signal: the bodiless trace carries the away
        /// wording at least once, so a swap that matched nothing cannot pass.</summary>
        private static bool AwayText(string name, List<string> t)
        {
            if (t.Any(e => e.Contains(" (away) got "))) return true;
            Console.WriteLine("FAIL " + name + ": no \"(away) got\" toast in the bodiless trace");
            return false;
        }

        private static IEnumerator ReplayReset(bool fail)
        {
            if (fail) throw new InvalidOperationException("reset");
            yield return null;
        }

        private static bool ReplayCase(string name)
        {
            ReducerBase.ResetState();
            SetupPool();
            PhotonNetwork.CurrentRoom = new object();
            FfaAssembly.RoomLobbyId = "lobbyA";
            FfaAssembly.RoomName = "roomA";
            var body = Body(2, false, "Seat2");
            body.data.view.OwnerActorNr = 7;
            var replay = new FfaReplay.ReadmitReplayOutcome
            {
                Lobby = "lobbyA", Room = "roomA", Slot = 2, Epoch = 1, Actor = 7,
                Generation = FfaReplay.Generation, Body = body, RoomIdentity = PhotonNetwork.CurrentRoom,
            };
            Func<bool> prepared = () => FfaReplay.ReadmitReplayPrepared(replay, "lobbyA", "roomA", 2, 1, 7);
            bool ok = true;
            if (name == "H1.identity")
            {
                replay.State = FfaReplay.ReadmitReplayState.Completed;
                ok = prepared()
                    && !FfaReplay.ReadmitReplayReady(replay, "lobbyB", "roomA", 2, 1, 7)
                    && !FfaReplay.ReadmitReplayReady(replay, "lobbyA", "roomB", 2, 1, 7)
                    && !FfaReplay.ReadmitReplayReady(replay, "lobbyA", "roomA", 3, 1, 7)
                    && !FfaReplay.ReadmitReplayReady(replay, "lobbyA", "roomA", 2, 2, 7)
                    && !FfaReplay.ReadmitReplayReady(replay, "lobbyA", "roomA", 2, 1, 8);
            }
            else if (name == "H1.entered" || name == "H1.ack")
            {
                ReadmitAdmissionBase.ResetAdmission(prepared);
                if (name == "H1.ack") FfaReplayAdmission.Propose();
                Action dispatch = name == "H1.entered"
                    ? (Action)(() => FfaReplayAdmission.Entered(1)) : () => FfaReplayAdmission.Ack();
                dispatch();
                ok = ReadmitAdmissionBase.AckCount == 0 && FfaReadmit.Entered == 0 && !ReadmitAdmissionBase._lateEntered;
                replay.State = FfaReplay.ReadmitReplayState.Failed;
                dispatch();
                ok &= ReadmitAdmissionBase.AckCount == 0 && FfaReadmit.Entered == 0 && !ReadmitAdmissionBase._lateEntered;
                replay.State = FfaReplay.ReadmitReplayState.Completed;
                dispatch();
                ok &= name == "H1.entered" ? FfaReadmit.Entered == 1 && ReadmitAdmissionBase._lateEntered
                    : ReadmitAdmissionBase.AckCount == 1;
                if (name == "H1.entered")
                {
                    ReadmitAdmissionBase.ResetAdmission(prepared);
                    ReadmitAdmissionBase.ActorKept = false;
                    dispatch();
                    ok &= FfaReadmit.Entered == 0 && !ReadmitAdmissionBase._lateEntered;
                }
            }
            else if (name == "H1.ack_identity")
            {
                replay.State = FfaReplay.ReadmitReplayState.Completed;
                ReadmitAdmissionBase.ResetAdmission(prepared);
                FfaReplayAdmission.Propose();
                FfaReplayAdmission.Ack();
                ok = ReadmitAdmissionBase.AckCount == 1
                    && !ReadmitAdmissionBase._replayProposal.HasValue && ReadmitAdmissionBase._replayAck == null;
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 1;

                replay.State = FfaReplay.ReadmitReplayState.Running;
                ReadmitAdmissionBase.ResetAdmission(prepared);
                FfaReplayAdmission.Propose();
                var oldAck = ReadmitAdmissionBase._replayAck;
                FfaReplayAdmission.Propose(ReadmitAdmissionBase.ProposalEvent(2, "c2"));
                replay.State = FfaReplay.ReadmitReplayState.Completed;
                ok &= oldAck != null && !oldAck() && ReadmitAdmissionBase.AckCount == 0;
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 1 && ReadmitAdmissionBase.AckPayload != null
                    && (int)ReadmitAdmissionBase.AckPayload[1] == 2 && (string)ReadmitAdmissionBase.AckPayload[2] == "c2"
                    && !ReadmitAdmissionBase._replayProposal.HasValue && ReadmitAdmissionBase._replayAck == null;
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 1;

                replay.State = FfaReplay.ReadmitReplayState.Running;
                ReadmitAdmissionBase.ResetAdmission(prepared);
                var foreign = ReadmitAdmissionBase.ProposalEvent();
                FfaReplayAdmission.Propose(foreign);
                foreign.Sender = 4;
                replay.State = FfaReplay.ReadmitReplayState.Completed;
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 0 && ReadmitAdmissionBase._replayProposal.HasValue;
                foreign.Sender = 3;
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 1;

                replay.State = FfaReplay.ReadmitReplayState.Running;
                ReadmitAdmissionBase.ResetAdmission(prepared);
                FfaReplayAdmission.Propose();
                var equalAck = ReadmitAdmissionBase._replayAck;
                FfaReplayAdmission.Propose(ReadmitAdmissionBase.ProposalEvent());
                replay.State = FfaReplay.ReadmitReplayState.Completed;
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 1 && equalAck != null && !equalAck();
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 1;
            }
            else if (name == "H1.master_ack")
            {
                ReadmitAdmissionBase.ResetAdmission(prepared);
                ok = !FfaReplayAdmission.MasterAck(prepared());
                replay.State = FfaReplay.ReadmitReplayState.Completed;
                ok &= FfaReplayAdmission.MasterAck(prepared());
                FfaLateRules.AllAcks = false;
                ok &= !FfaReplayAdmission.MasterAck(prepared());
            }
            else if (name == "H1.prepare_throw")
            {
                ReadmitAdmissionBase.ResetAdmission(() => { throw new InvalidOperationException("prepare"); });
                ok = !FfaReplayAdmission.Prepare(1) && !FfaReplayAdmission.IsKeptActor(7);
                FfaReplayAdmission.Propose();
                FfaReplayAdmission.Ack();
                ok &= ReadmitAdmissionBase.AckCount == 0 && !FfaReplayAdmission.MasterAck(FfaReplayAdmission.Prepare(1));
            }
            else if (name == "H1.legacy_kept_exception")
            {
                ReadmitAdmissionBase.ResetAdmission(() => { throw new InvalidOperationException("prepare"); });
                FfaAssembly.ReadmitLobby = false;
                FfaLateRules.KeptThrows = true;
                ok = FfaReplayAdmission.IsKeptActor(7);
            }
            else if (name == "H1.normal_late")
            {
                ReadmitAdmissionBase.ResetAdmission(prepared);
                FfaReadmit.Readmitted = false;
                FfaReplayAdmission.Entered(1);
                ok = FfaAssembly.LateEntered == 1 && FfaReadmit.Entered == 0 && ReadmitAdmissionBase._lateEntered;
            }
            else
            {
                var cards = name == "H1.empty" ? new List<CardInfo>() : new List<CardInfo> { Card("AA"), Card("BB") };
                if (name == "H1.missing") cards[0] = new CardInfo("ZZ");
                replay.Cards = cards;
                if (name == "H1.body_missing") body.gameObject = null;
                ReducerBase.SeedDeck(2, cards);
                var applied = new List<string>();
                int rebuilds = 0, yields = 0;
                bool changed = false;
                var run = FfaReplay.ReadmitReplaySteps(replay, () => FfaReplay.Current(replay),
                    ReplayReset(name == "H1.reset_throw"), cards, card =>
                    {
                        if (name == "H1.apply_throw") throw new InvalidOperationException("apply");
                        if (name == "H1.apply_false") return false;
                        applied.Add(card.gameObject.name);
                        return true;
                    }, () => rebuilds++);
                while (run.MoveNext())
                {
                    yields++;
                    // This assertion includes the frame after the final apply.
                    ok &= replay.State == FfaReplay.ReadmitReplayState.Running && !prepared();
                    ok &= !FfaReplayAdmission.ReadmitBoundaryReady(prepared());
                    ok &= !FfaReplayAdmission.ReadmitEnteredReady(true, true, prepared());
                    if (applied.Count == 1 && !changed)
                    {
                        if (name == "H1.room_change") FfaAssembly.RoomName = "roomB";
                        if (name == "H1.room_incarnation") PhotonNetwork.CurrentRoom = new object();
                        if (name == "H1.replaced_work") FfaReplay.CancelReadmitReplay(replay);
                        if (name == "H1.body_replaced") Body(2, false, "Replacement");
                        if (name == "H1.invalidated") FfaReplay.InvalidateReadmitReplays();
                        if (name == "H1.deck_changed") ReducerBase.SeedDeck(2, new[] { Card("AA"), Card("BB"), Card("CC") });
                        changed = true;
                    }
                }
                bool success = name == "H1.delayed" || name == "H1.empty" || name == "H1.admitted_grant";
                if (success)
                {
                    ok &= prepared() && rebuilds == 1 && yields == cards.Count + 1;
                    ok &= applied.SequenceEqual(cards.Select(c => c.gameObject.name));
                    if (name == "H1.admitted_grant")
                    {
                        ok &= FfaReplay.CommitReadmitReplay(replay, "lobbyA", "roomA", 2, 1, 7);
                        ReducerBase.SeedDeck(2, new[] { Card("AA"), Card("BB"), Card("CC") });
                        ok &= prepared() && replay.Admitted;
                    }
                }
                else
                {
                    ok &= replay.State == FfaReplay.ReadmitReplayState.Failed && !prepared() && rebuilds == 0;
                    int expected = name == "H1.room_change" || name == "H1.body_replaced" || name == "H1.invalidated"
                        || name == "H1.deck_changed" || name == "H1.room_incarnation" || name == "H1.replaced_work" ? 1 : 0;
                    ok &= applied.Count == expected;
                }
            }
            Console.WriteLine((ok ? "PASS " : "FAIL ") + name);
            return ok;
        }

        private static bool Case(string name)
        {
            if (name.StartsWith("H1.", StringComparison.Ordinal)) return ReplayCase(name);
            if (name == "bodiless")
            {
                // The P2 path: the new reducer with bodiless true and NO body,
                // against the old reducer's logical projection on the same
                // deck WITH a body. The roster name equals the nickname here.
                var f = Fixtures["rolling"];
                var oldT = Logical(RunOne(false, f, false, true));
                var newT = RunOne(true, f, true, false);
                bool noPhysical = !newT.Any(e => Physical.Any(p => e.StartsWith(p, StringComparison.Ordinal)));
                if (!noPhysical) { Console.WriteLine("FAIL bodiless: a physical event or yield in the bodiless trace"); return false; }
                return AwayText("bodiless", newT) && Compare("bodiless", Away(oldT), Logical(newT));
            }
            if (name == "bodiless_plain")
            {
                var f = Fixtures["remote"];
                var oldT = Logical(RunOne(false, f, false, true));
                var newT = RunOne(true, f, true, false);
                return AwayText("bodiless_plain", newT) && Compare("bodiless_plain", Away(oldT), Logical(newT));
            }
            Fixture fx;
            if (!Fixtures.TryGetValue(name, out fx)) { Console.WriteLine("FAIL unknown case " + name); return false; }
            var o = RunOne(false, fx, false, true);
            var nw = RunOne(true, fx, false, true);
            if (Environment.GetEnvironmentVariable("RJ_TRACE_DUMP") == "1")
                foreach (var e in nw) Console.WriteLine("  | " + e);
            return Compare(name, o, nw);
        }

        internal static readonly string[] All =
        {
            "rolling", "local", "remote", "unknown", "quarantined", "nobody",
            "rolling_local", "throw_replay", "throw_apply", "throw_audit", "throw_rebuild",
            "bodiless", "bodiless_plain", "H1.delayed", "H1.empty", "H1.missing",
            "H1.apply_throw", "H1.apply_false", "H1.reset_throw", "H1.room_change",
            "H1.body_replaced", "H1.body_missing", "H1.invalidated", "H1.deck_changed", "H1.identity",
            "H1.admitted_grant", "H1.room_incarnation", "H1.replaced_work", "H1.entered", "H1.ack", "H1.master_ack", "H1.normal_late", "H1.prepare_throw", "H1.legacy_kept_exception",
        };

        private static int Main(string[] args)
        {
            var names = args.Length == 0 || args[0] == "all" ? All : args;
            int pass = 0;
            foreach (var n in names) if (Case(n)) pass++;
            Console.WriteLine("cases: " + pass + " of " + names.Length + " pass");
            return pass == names.Length ? 0 : 1;
        }
    }
}
