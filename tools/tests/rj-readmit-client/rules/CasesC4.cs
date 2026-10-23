// C4: RJ readmission P4, the client half (V3:147-308): the lobby flag pin,
// discovery and the claim / bind / decline / entered machine, kind r entries
// and identity at the master, the roster-sized tail and its digest, the game
// number, registration order, the latch release and departure as death.
// Server-only tests (T4.1 to T4.4, T4.14, T4.15) are the server lane's.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace CompetitiveRounds
{
    internal static class CasesC4
    {
        private static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }

        // ---------------------------------------------------------------- fixtures

        private const string Lobby8 = "1a2b3c4d";
        private const string Token = "9f8e7d6c5b4a39281706f5e4d3c2b1a09f8e7d6c5b4a39281706f5e4d3c2b1a0";

        /// <summary>The server's chain v2 step, written from the wire format
        /// (backend _ffa_epoch_chain, V3 P4.8), not from ChainOf.</summary>
        private static string ServerStep(string prev, int n, int slot, int actor, string kind, int game, string verifier, int v)
        {
            string s = prev + ":" + Lobby8 + ":" + I(n) + ":" + I(slot) + ":" + I(actor);
            if (v == 2) s += ":" + kind + ":" + (game < 0 ? "" : I(game)) + ":" + (verifier ?? "") + ":v2";
            return FfaLateRules.Hex16(FfaLateRules.Fnv64(s));
        }

        /// <summary>An epoch of three rows as the server would send them: a v1
        /// kind l row, a v2 kind l row, then the kind r bind row of slot 1.</summary>
        private static FfaLateRules.EpochRecord ReadmitRecord(int rActor, string verifier, out string serverChain)
        {
            var rows = new[]
            {
                new { Slot = 3, Actor = 7, Kind = "l", Game = -1, V = 1, Ver = (string)null },
                new { Slot = 2, Actor = 8, Kind = "l", Game = 2, V = 2, Ver = (string)null },
                new { Slot = 1, Actor = rActor, Kind = "r", Game = 3, V = 2, Ver = verifier },
            };
            string prev = "0";
            var rec = new FfaLateRules.EpochRecord { N = rows.Length };
            for (int i = 0; i < rows.Length; i++)
            {
                var r = rows[i];
                prev = ServerStep(prev, i + 1, r.Slot, r.Actor, r.Kind, r.Game, r.Ver, r.V);
                rec.Entries.Add(FfaReadmitEntryRules.EpochEntryOf(r.Slot, r.Actor, r.Kind, r.Game, r.V, r.Ver));
            }
            rec.Chain = prev;
            serverChain = prev;
            return rec;
        }

        private static FfaReadmitEntryRules.RdmAnswer Ans(string status, string reason = null, int retry = 0, int n = 1)
        {
            return new FfaReadmitEntryRules.RdmAnswer { Status = status, Reason = reason, Retry = retry, N = n, HoldS = 90 };
        }

        /// <summary>A four-seat roster at a boundary: slot 3 is the held seat,
        /// bodiless, the highest slot, with nonzero rounds, points, points total
        /// and kills (T4.7).</summary>
        private sealed class Table
        {
            internal int[] Rounds = { 1, 0, 2, 3 };
            internal int[] Points = { 1, 2, 0, 1 };
            internal int[] PointsTotal = { 4, 3, 5, 7 };
            internal int[] Kills = { 2, 1, 3, 4 };
            internal List<string>[] Decks =
            {
                new List<string> { "Quick Reload", "Bouncy" },
                new List<string> { "Big Bullet" },
                new List<string> { "Shield Charge", "Poison", "Leach" },
                new List<string> { "BombsAway", "Frost slam" },
            };
            internal List<string>[] History =
            {
                new List<string> { FfaReadmitEntryRules.HistoryEntry(1, false, 1, "Common", "QUICK RELOAD"), FfaReadmitEntryRules.HistoryEntry(2, false, 2, "Common", "BOUNCY") },
                new List<string> { FfaReadmitEntryRules.HistoryEntry(1, false, 1, "Uncommon", "BIG BULLET") },
                new List<string> { FfaReadmitEntryRules.HistoryEntry(1, true, 1, "Rare", "SHIELD CHARGE: MK2"), FfaReadmitEntryRules.HistoryEntry(2, false, 2, "Common", "POISON") },
                new List<string> { FfaReadmitEntryRules.HistoryEntry(1, false, 1, "Rare", "BOMBS AWAY"), FfaReadmitEntryRules.HistoryEntry(3, false, 2, "Uncommon", "FROST SLAM") },
            };
            internal int[] Draw = { 2, 1, 2, 3 };
            internal List<string> Ledger = new List<string> { "NR1", "NR2" };
            internal int Game = 3;

            internal FfaReadmitEntryRules.Tail TailOf(IList<int> slots)
            {
                var t = new FfaReadmitEntryRules.Tail { OfferGame = Game, OfferCycle = 5 };
                foreach (int s in slots)
                {
                    var ts = new FfaReadmitEntryRules.TailSlot
                    {
                        Slot = s, Rounds = Rounds[s], Points = Points[s], PointsTotal = PointsTotal[s], Kills = Kills[s],
                        DrawIndex = Draw[s],
                    };
                    ts.Deck.AddRange(Decks[s]);
                    ts.History.AddRange(History[s]);
                    t.Slots.Add(ts);
                }
                t.Ledger.AddRange(Ledger);
                return t;
            }

            internal Table Copy()
            {
                var c = new Table
                {
                    Rounds = (int[])Rounds.Clone(), Points = (int[])Points.Clone(),
                    PointsTotal = (int[])PointsTotal.Clone(), Kills = (int[])Kills.Clone(),
                    Draw = (int[])Draw.Clone(), Ledger = new List<string>(Ledger), Game = Game,
                };
                c.Decks = Decks.Select(d => new List<string>(d)).ToArray();
                c.History = History.Select(h => new List<string>(h)).ToArray();
                return c;
            }
        }

        private static readonly int[] BodyTeams = { 0, 1, 2 };   // slot 3 has no body

        /// <summary>The master's late tail as SendSnapshot builds it, and the
        /// returner's reading of it (DecodePicks).</summary>
        private static FfaReadmitEntryRules.Tail SendAndRead(Table master, bool readmit)
        {
            var slots = FfaReadmitEntryRules.DigestSlotSet(readmit, 4, BodyTeams);
            int size = FfaReadmitEntryRules.TailSize(readmit, 4, BodyTeams);
            var ptot = new int[size];
            var kl = new int[size];
            for (int t = 0; t < size; t++) { ptot[t] = master.PointsTotal[t]; kl[t] = master.Kills[t]; }
            var picks = FfaReadmitEntryRules.EncodePicks(master.TailOf(slots));
            return FfaReadmitEntryRules.DecodePicks(picks, ptot, kl);
        }

        /// <summary>A kept peer's published digest of the boundary.</summary>
        private static string PeerDigest(Table peer, int g, int k)
        {
            var slots = FfaReadmitEntryRules.DigestSlotSet(true, 4, BodyTeams);
            return FfaReadmitEntryRules.ReadmitDigest(g, k, "12", peer.TailOf(slots));
        }

        private static bool Gate(FfaReadmitEntryRules.Tail tail, int g, Table honestPeer)
        {
            string snap = tail != null ? FfaReadmitEntryRules.ReadmitDigest(g, 4, "12", tail) : "";
            var peers = new List<FfaLateRules.PeerBd>
            {
                new FfaLateRules.PeerBd { Actor = 11, Slot = 0, IsMaster = true, Kept = true, Bd = I(g) + ":4:" + snap },
                new FfaLateRules.PeerBd { Actor = 12, Slot = 1, IsMaster = false, Kept = true, Bd = I(g) + ":4:" + PeerDigest(honestPeer, g, 4) },
            };
            int peer;
            return FfaLateRules.DigestGate(snap, g, 4, g, peers, out peer);
        }

        /// <summary>RecordKillFor's rule (B:plugin/FfaMode.cs:1406-1428) for a
        /// death: the team credited, or -1.</summary>
        private static int KillRule(int sourceTeam, int victimTeam, bool sourceQ, bool victimQ, bool victimLag)
        {
            if (sourceTeam < 0 || sourceTeam == victimTeam) return -1;
            if (sourceQ || victimQ) return -1;
            if (victimLag) return -1;
            return sourceTeam;
        }

        /// <summary>One client's registration: the prefix compacts (a purged
        /// entry is -1 here), takes RegisterIndex, inserts a placeholder there
        /// and vanilla writes the forced index the prefix pointed at it.</summary>
        private static List<int> RegisterOn(IList<int> listWithHoles, int newId, out bool refused)
        {
            var ids = listWithHoles.Where(x => x >= 0).ToList();
            int at = FfaReadmitEntryRules.RegisterIndex(ids, newId);
            refused = at < 0;
            if (refused) return ids;
            ids.Insert(at, -2);
            ids[at] = newId;
            return ids;
        }

        private static void F2DReset(FfaReadmitEntryRules.RdmState state, int n = 3)
        {
            ReadmitOfferAdapter.Reset(state, "lobbyA", n);
            var c = ReadmitOfferAdapter.State;
            c.Slot = 1; c.Token = Token; c.Room = "roomA"; c.Region = "eu";
            c.Game = 4; c.Actor = 42; c.HoldUntil = 80f; c.LastReason = "held";
        }

        private static void F2DAdmit()
        {
            F2DReset(FfaReadmitEntryRules.RdmState.Binding);
            ReadmitOfferAdapter.SendForTest("bind", 42, 0);
            string answer = ReadmitOfferAdapter.Answer("bind-answer", "status", "admitted_late", "n", "3",
                                                       "kind", "r", "game", "4", "actor", "42");
            ReadmitOfferAdapter.DeliverPost(0, true, answer);
            Check.Eq(FfaReadmitEntryRules.RdmState.Admitted, ReadmitOfferAdapter.State.State, "the real bind callback admits");
            Check.True(ReadmitOfferAdapter.PrepareCalls == 1 && ReadmitOfferAdapter.ArmCalls == 1, "the real Act prepares and arms replay");
            Check.Eq(1, ReadmitOfferAdapter.PostBodies.Count, "failed replay posts no entered");
            Check.True(!ReadmitOfferAdapter.PostBodies[0].Contains("\"entered\""), "only bind was posted");
        }

        private static void F2DRecordUnchanged(FfaReadmitEntryRules.RdmState state, int generation = 0)
        {
            var c = ReadmitOfferAdapter.State;
            Check.True(c.State == state && c.Lobby == "lobbyA" && c.N == 3 && c.Slot == 1 && c.Token == Token
                       && c.Room == "roomA" && c.Region == "eu" && c.Game == 4 && c.Actor == 42
                       && c.HoldUntil == 80f && c.LastReason == "held", "every unrelated or inactive record field is untouched");
            bool untouched = generation == 0;
            Check.True(ReadmitOfferAdapter.Discovered == untouched && ReadmitOfferAdapter.DiscoveryInFlight == untouched
                       && ReadmitOfferAdapter.PostInFlight == untouched && ReadmitOfferAdapter.NextBind == (untouched ? 7f : 0f)
                       && ReadmitOfferAdapter.Generation == generation, "unrelated work stays whole; matching inactive work is invalidated");
        }

        // External route bodies are source-censused. Their controls execute the
        // same extracted invalidation; refusal and its nested leave execute here.
        private static void F2ERoute(string route, string lobby = "lobbyA", string room = "roomA")
        {
            switch (route)
            {
                case "escape": ReadmitOfferAdapter.Abandon(null, all: true); break;
                case "leave": ReadmitOfferAdapter.LeaveForTest(lobby); break;
                case "release": ReadmitOfferAdapter.Abandon(lobby); break;
                case "depart": ReadmitOfferAdapter.Abandon(room, byRoom: true); break;
                case "refusal": ReadmitOfferAdapter.RefusalForTest("hold_lapsed", true); break;
                default: throw new CaseFailed("unknown route");
            }
        }

        private static void F2EDelayed(string route)
        {
            foreach (var terminal in new[] { FfaReadmitEntryRules.RdmState.Lapsed, FfaReadmitEntryRules.RdmState.Refused })
            foreach (bool discovery in new[] { false, true })
            foreach (bool ok in new[] { false, true })
            {
                F2DReset(FfaReadmitEntryRules.RdmState.Binding);
                if (discovery)
                {
                    ReadmitOfferAdapter.HoldDiscovery = true;
                    ReadmitOfferAdapter.DiscoverThenProbe();
                }
                else ReadmitOfferAdapter.SendForTest("bind", 42, 0);
                var c = ReadmitOfferAdapter.State;
                c.State = terminal; c.Token = null; c.LastReason = "released";
                F2ERoute(route);
                Check.True(ReadmitOfferAdapter.Generation > 0 && !ReadmitOfferAdapter.Discovered
                           && !ReadmitOfferAdapter.DiscoveryInFlight && !ReadmitOfferAdapter.PostInFlight
                           && ReadmitOfferAdapter.NextBind == 0f, "the matching terminal work is synchronously invalidated");
                long generation = ReadmitOfferAdapter.Generation;
                int probes = ReadmitOfferAdapter.Probes, toasts = ReadmitOfferAdapter.Toasts, polls = ReadmitOfferAdapter.PollCalls;
                string answer = discovery ? ReadmitOfferAdapter.OfferAnswer("late-discovery", "lobbyB", 1)
                    : ReadmitOfferAdapter.Answer("late-bind", "status", "refused", "n", "3", "reason", "departed", "hold_s", "6");
                if (discovery) ReadmitOfferAdapter.DeliverDiscovery(0, ok, answer);
                else ReadmitOfferAdapter.DeliverPost(0, ok, answer);
                Check.True(c.State == terminal && c.Lobby == "lobbyA" && c.N == 3 && c.Token == null
                           && c.Room == "roomA" && c.Slot == 1 && c.Region == "eu" && c.Game == 4 && c.Actor == 42
                           && c.HoldUntil == 80f && c.LastReason == "released", "the released answer changes no record field");
                Check.True(ReadmitOfferAdapter.Generation == generation && !ReadmitOfferAdapter.Discovered
                           && !ReadmitOfferAdapter.DiscoveryInFlight && !ReadmitOfferAdapter.PostInFlight
                           && ReadmitOfferAdapter.NextBind == 0f && ReadmitOfferAdapter.Probes == probes
                           && ReadmitOfferAdapter.Toasts == toasts && ReadmitOfferAdapter.PollCalls == polls
                           && !ReadmitOfferAdapter.QueuePolling, "the released answer changes no flag, clock, probe, toast or poll");
            }
        }

        internal static void Register()
        {
            // ---------------------------------------------------------- C4a (P4.6)
            RulesProgram.Add("C4.C4a.lock_flag_pinned", () =>
            {
                Check.Eq(1, FfaReadmitRules.LockReadmit(1, 1), "a gated lock naming readmit 1 pins true");
                Check.Eq(0, FfaReadmitRules.LockReadmit(1, 0), "readmit 0 pins false");
                Check.Eq(0, FfaReadmitRules.LockReadmit(1, 7), "any other value pins false");
                Check.Eq(0, FfaReadmitRules.LockReadmit(0, 1), "an ungated lock pins false");
                var pin = FfaReadmitRules.PinFromLock(null, "lobbyA", "roomA", FfaReadmitRules.LockReadmit(1, 1));
                Check.True(pin.Flag, "pinned true at lock");
                var again = FfaReadmitRules.PinFromLock(pin, "lobbyA", "roomA", FfaReadmitRules.LockReadmit(1, 0));
                Check.True(again.Flag, "a later payload of the same lobby never unpins it");
            });

            // ---------------------------------------------------------- T4.5 claim and bind (client half)
            RulesProgram.Add("C4.T4.5.claim_bind_entered_sequence", () =>
            {
                var c = new FfaReadmitEntryRules.RdmClient();
                Check.True(FfaReadmitEntryRules.DiscoveryOffers(1, "lobbyA", 1, 90), "a readmissible answer offers the bar");
                FfaReadmitEntryRules.Offer(c, "lobbyA", 1, 1, 90, 0f);
                Check.Eq(FfaReadmitEntryRules.RdmState.Offered, c.State, "offered");
                Check.Eq(90, FfaReadmitEntryRules.SecondsLeft(c, 0f), "the bar counts the hold");
                c.State = FfaReadmitEntryRules.RdmState.Claiming;   // Accept()
                string claimBody = FfaReadmitEntryRules.RequestBody("100", "claim", c.N, 0, "", 0, 50);
                Check.True(claimBody.Contains("\"step\":\"claim\"") && claimBody.Contains("\"n\":1") && !claimBody.Contains("actor"),
                           "the claim names the step and n, no actor");
                var claimed = new FfaReadmitEntryRules.RdmAnswer { Status = "claimed", Token = Token, Room = "roomA", Region = "eu", Slot = 1, N = 1, HoldS = 80 };
                Check.Eq(FfaReadmitEntryRules.RdmNext.JoinRoom, FfaReadmitEntryRules.OnAnswer(c, "claim", claimed, 10f), "claimed joins the room");
                Check.Eq("1:" + Token, FfaReadmitEntryRules.RdtValue(c.N, c.Token), "cr_rdt staged pre-join");
                string bindBody = FfaReadmitEntryRules.RequestBody("100", "bind", c.N, 42, "eu", 0, 60);
                Check.True(bindBody.Contains("\"actor\":42") && bindBody.Contains("\"region\":\"eu\"") && !bindBody.Contains(Token),
                           "the bind carries actor and region and never the token");
                c.State = FfaReadmitEntryRules.RdmState.Binding;
                Check.Eq(FfaReadmitEntryRules.RdmNext.BindAgain,
                         FfaReadmitEntryRules.OnAnswer(c, "bind", Ans("refused", "uncorroborated", 1), 15f), "uncorroborated with retry binds again");
                var admitted = new FfaReadmitEntryRules.RdmAnswer { Status = "admitted_late", Kind = "r", Game = 3, Actor = 42, N = 1, Slot = 1 };
                Check.Eq(FfaReadmitEntryRules.RdmNext.ArmLate, FfaReadmitEntryRules.OnAnswer(c, "bind", admitted, 20f), "admitted kind r arms the late entry");
                Check.Eq(3, c.Game, "the server g is held for the game agreement");
                string entered = FfaReadmitEntryRules.RequestBody("100", "entered", c.N, 42, "", 3, 70);
                Check.True(entered.Contains("\"game\":3") && entered.Contains("\"actor\":42") && entered.Contains("\"n\":1"),
                           "entered carries g, n and X");
                Check.Eq(FfaReadmitEntryRules.RdmNext.Done, FfaReadmitEntryRules.OnAnswer(c, "entered", Ans("entered"), 30f), "entered spends the token");
                Check.True(c.Token == null, "the token is gone after entered");
                // Second drop (step 10): hold n + 1 is offered afresh.
                FfaReadmitEntryRules.Offer(c, "lobbyA", 1, 2, 90, 100f);
                Check.Eq(FfaReadmitEntryRules.RdmState.Offered, c.State, "a second drop is offered hold n + 1");
                Check.Eq(2, c.N, "the new hold's n");
            });

            RulesProgram.Add("C4.H2.cross_lobby_first_hold", () =>
            {
                var c = new FfaReadmitEntryRules.RdmClient { State = FfaReadmitEntryRules.RdmState.Entered, Lobby = "lobbyA", N = 3 };
                Check.Eq(FfaReadmitEntryRules.RdmOffer.Accepted,
                         FfaReadmitEntryRules.Offer(c, "lobbyB", 2, 1, 90, 100f), "another lobby starts at hold one");
                Check.Eq(FfaReadmitEntryRules.RdmState.Offered, c.State, "the terminal record reopens");
                Check.Eq("lobbyB", c.Lobby, "the reopened record names the new lobby");
                Check.Eq(1, c.N, "the new lobby hold number");
            });
            RulesProgram.Add("C4.H2.same_lobby_terminal", () =>
            {
                foreach (int n in new[] { 2, 3 })
                {
                    var c = new FfaReadmitEntryRules.RdmClient { State = FfaReadmitEntryRules.RdmState.Entered, Lobby = "lobbyA", N = 3 };
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Rejected,
                             FfaReadmitEntryRules.Offer(c, "lobbyA", 2, n, 90, 100f), "a repeated or stale terminal hold stays closed");
                    Check.Eq(FfaReadmitEntryRules.RdmState.Entered, c.State, "terminal state kept");
                    Check.Eq(3, c.N, "terminal hold kept");
                }
                var next = new FfaReadmitEntryRules.RdmClient { State = FfaReadmitEntryRules.RdmState.Entered, Lobby = "lobbyA", N = 3 };
                Check.Eq(FfaReadmitEntryRules.RdmOffer.Accepted,
                         FfaReadmitEntryRules.Offer(next, "lobbyA", 2, 4, 90, 100f), "an increasing hold reopens");
            });
            RulesProgram.Add("C4.H2.active_claim_preserved", () =>
            {
                foreach (var state in new[] { FfaReadmitEntryRules.RdmState.Claiming, FfaReadmitEntryRules.RdmState.Claimed,
                                             FfaReadmitEntryRules.RdmState.Binding, FfaReadmitEntryRules.RdmState.Admitted })
                {
                    var c = new FfaReadmitEntryRules.RdmClient { State = state, Lobby = "lobbyA", N = 3, Slot = 1,
                        Token = Token, Room = "roomA", Region = "eu", Game = 4, Actor = 42, HoldUntil = 80f };
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Rejected,
                             FfaReadmitEntryRules.Offer(c, "lobbyB", 2, 1, 90, 100f), "another lobby cannot reset an active claim");
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Rejected,
                             FfaReadmitEntryRules.Offer(c, "lobbyA", 2, 4, 90, 100f), "another hold cannot reset an active claim");
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Held,
                             FfaReadmitEntryRules.Offer(c, "lobbyA", 1, 3, 90, 100f), "the identical active offer is already held");
                    Check.True(c.State == state && c.Lobby == "lobbyA" && c.N == 3 && c.Slot == 1 && c.Token == Token
                               && c.Room == "roomA" && c.Region == "eu" && c.Game == 4 && c.Actor == 42 && c.HoldUntil == 80f,
                               "every active-claim field is untouched");
                }
            });
            RulesProgram.Add("C4.H2.discovery_fallback", () =>
            {
                foreach (var state in new[] { FfaReadmitEntryRules.RdmState.None, FfaReadmitEntryRules.RdmState.Offered,
                                             FfaReadmitEntryRules.RdmState.Claimed, FfaReadmitEntryRules.RdmState.Entered })
                {
                    ReadmitOfferAdapter.Reset(state, "lobbyA", 1);
                    ReadmitOfferAdapter.DiscoverThenProbe();
                    Check.Eq(state == FfaReadmitEntryRules.RdmState.Entered ? 1 : 0, ReadmitOfferAdapter.Probes,
                             "only an accepted, refreshed or held discovery suppresses today's probe");
                }
                ReadmitOfferAdapter.Reset(FfaReadmitEntryRules.RdmState.Claimed, "lobbyB", 1);
                ReadmitOfferAdapter.DiscoverThenProbe();
                Check.Eq(1, ReadmitOfferAdapter.Probes, "a cross-lobby offer rejected during a claim falls back");
                Check.Eq("lobbyB", ReadmitOfferAdapter.State.Lobby, "discovery preserves the active claim");
            });
            RulesProgram.Add("C4.H2.poll_result", () =>
            {
                ReadmitOfferAdapter.Reset(FfaReadmitEntryRules.RdmState.Entered, "lobbyA", 2);
                Check.Eq(FfaReadmitEntryRules.RdmOffer.Accepted,
                         ReadmitOfferAdapter.OfferFromPoll("lobbyB", 2, 1, 90), "poll returns acceptance and reopens State");
                Check.Eq("lobbyB", ReadmitOfferAdapter.State.Lobby, "the same State record now names lobbyB");
                Check.Eq(FfaReadmitEntryRules.RdmOffer.Refreshed,
                         ReadmitOfferAdapter.OfferFromPoll("lobbyB", 2, 1, 80), "poll returns the repeated held offer");
                Check.Eq(FfaReadmitEntryRules.RdmOffer.Rejected,
                         ReadmitOfferAdapter.OfferFromPoll("", 2, 1, 90), "the discovery capability shape still gates the poll");
            });

            // The release routes are censused from their real members by run_rj.py.
            // These schedules execute the real rule, adapter and callback bodies.
            RulesProgram.Add("C4.F2D.admitted_release_cross_lobby", () =>
            {
                F2DAdmit();
                Check.Eq(FfaReadmitEntryRules.RdmNext.None,
                         FfaReadmitEntryRules.Tick(ReadmitOfferAdapter.State, 1000f), "a live admitted attempt outlives the pre-bind deadline");
                Check.Eq(FfaReadmitEntryRules.RdmState.Admitted, ReadmitOfferAdapter.State.State, "the clock did not abandon it");
                ReadmitOfferAdapter.PrimeFlights();
                Check.True(ReadmitOfferAdapter.Abandon("lobbyA"), "the own release abandons the admitted attempt synchronously");
                Check.Eq(FfaReadmitEntryRules.RdmState.Abandoned, ReadmitOfferAdapter.State.State, "abandonment is distinct from entry");
                Check.True(ReadmitOfferAdapter.State.Token == null && ReadmitOfferAdapter.State.Lobby == "lobbyA"
                           && ReadmitOfferAdapter.State.N == 3, "the token is spent and terminal pair retained");
                Check.True(!ReadmitOfferAdapter.Discovered && !ReadmitOfferAdapter.DiscoveryInFlight
                           && !ReadmitOfferAdapter.PostInFlight && ReadmitOfferAdapter.NextBind == 0f
                           && ReadmitOfferAdapter.Generation == 1, "abandonment clears both flights, rearms discovery and clears the bind clock");
                Check.True(!ReadmitOfferAdapter.ClaimedFor("lobbyA") && !ReadmitOfferAdapter.ReadmittedInto("lobbyA"),
                           "an abandoned attempt is neither a live claim nor a successfully entered seat");
                Check.True(!ReadmitOfferAdapter.Abandon("lobbyA") && ReadmitOfferAdapter.Generation == 2,
                           "a repeated release keeps the terminal record and invalidates matching work again");
                ReadmitOfferAdapter.DiscoveryResponse = ReadmitOfferAdapter.OfferAnswer("next-offer", "lobbyB", 1);
                ReadmitOfferAdapter.DiscoverThenProbe();
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Offered
                           && ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.State.N == 1,
                           "discovery accepts another lobby's first hold after release");
                Check.Eq(0, ReadmitOfferAdapter.Probes, "the accepted offer suppresses fallback");
                foreach (var state in new[] { FfaReadmitEntryRules.RdmState.Claiming,
                                             FfaReadmitEntryRules.RdmState.Claimed, FfaReadmitEntryRules.RdmState.Binding })
                {
                    F2DReset(state);
                    Check.True(ReadmitOfferAdapter.Abandon("lobbyA"), "release also ends the own pre-entry claim phase");
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Accepted,
                             ReadmitOfferAdapter.OfferFromPoll("lobbyB", 2, 1, 90), "another lobby opens after each released claim phase");
                }
            });
            RulesProgram.Add("C4.F2D.admitted_departure_cross_lobby", () =>
            {
                F2DAdmit();
                Check.True(ReadmitOfferAdapter.Abandon("roomA", byRoom: true), "departure of the claimed room ends the admitted attempt");
                ReadmitOfferAdapter.DiscoveryResponse = ReadmitOfferAdapter.OfferAnswer("departure-offer", "lobbyB", 1);
                ReadmitOfferAdapter.DiscoverThenProbe();
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Offered
                           && ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.State.N == 1,
                           "discovery accepts another lobby's first hold after departure");
                foreach (var state in new[] { FfaReadmitEntryRules.RdmState.Claiming,
                                             FfaReadmitEntryRules.RdmState.Claimed, FfaReadmitEntryRules.RdmState.Binding })
                {
                    F2DReset(state);
                    Check.True(ReadmitOfferAdapter.Abandon("roomA", byRoom: true), "matching departure also ends each active pre-entry phase");
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Accepted,
                             ReadmitOfferAdapter.OfferFromPoll("lobbyB", 2, 1, 90), "another lobby opens after each departed claim phase");
                }
            });
            RulesProgram.Add("C4.F2D.abandoned_same_lobby_stale", () =>
            {
                foreach (int n in new[] { 2, 3 })
                {
                    F2DAdmit();
                    Check.True(ReadmitOfferAdapter.Abandon("lobbyA"), "release ended the attempt");
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Rejected,
                             ReadmitOfferAdapter.OfferFromPoll("lobbyA", 2, n, 90), "a same or lower terminal hold stays closed");
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Abandoned
                               && ReadmitOfferAdapter.State.Lobby == "lobbyA" && ReadmitOfferAdapter.State.N == 3
                               && ReadmitOfferAdapter.State.Token == null, "stale offers leave the terminal pair and spent token intact");
                }
            });
            RulesProgram.Add("C4.F2D.abandoned_greater_hold", () =>
            {
                F2DAdmit();
                Check.True(ReadmitOfferAdapter.Abandon("lobbyA"), "release ended the attempt");
                Check.Eq(FfaReadmitEntryRules.RdmOffer.Accepted,
                         ReadmitOfferAdapter.OfferFromPoll("lobbyA", 2, 4, 90), "a greater hold reopens the same lobby");
                var c = ReadmitOfferAdapter.State;
                Check.True(c.State == FfaReadmitEntryRules.RdmState.Offered && c.Lobby == "lobbyA" && c.N == 4
                           && c.Slot == 2 && c.HoldUntil == 190f && c.Token == null && c.Room == null && c.Region == null
                           && c.Game == 0 && c.Actor == 0 && c.LastReason == null, "Offer rewrites the whole reversible record");
            });
            RulesProgram.Add("C4.F2D.unrelated_departure", () =>
            {
                foreach (var state in new[] { FfaReadmitEntryRules.RdmState.Claiming, FfaReadmitEntryRules.RdmState.Claimed,
                                             FfaReadmitEntryRules.RdmState.Binding, FfaReadmitEntryRules.RdmState.Admitted })
                {
                    F2DReset(state);
                    ReadmitOfferAdapter.PrimeFlights();
                    Check.True(!ReadmitOfferAdapter.Abandon("lobbyB") && !ReadmitOfferAdapter.Abandon("roomB", byRoom: true),
                               "an unrelated lobby release or room departure ends nothing");
                    Check.True(!ReadmitOfferAdapter.Abandon(null) && !ReadmitOfferAdapter.Abandon("")
                               && !ReadmitOfferAdapter.Abandon(null, byRoom: true) && !ReadmitOfferAdapter.Abandon("", byRoom: true),
                               "an absent identity ends nothing");
                    Check.True(!ReadmitOfferAdapter.Abandon("roomA") && !ReadmitOfferAdapter.Abandon("lobbyA", byRoom: true),
                               "the room and lobby identity domains are not interchangeable");
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Rejected,
                             ReadmitOfferAdapter.OfferFromPoll("lobbyB", 2, 1, 90), "a live attempt still blocks another lobby");
                    F2DRecordUnchanged(state);
                }
                foreach (var state in new[] { FfaReadmitEntryRules.RdmState.None, FfaReadmitEntryRules.RdmState.Offered,
                                             FfaReadmitEntryRules.RdmState.Entered, FfaReadmitEntryRules.RdmState.Refused,
                                             FfaReadmitEntryRules.RdmState.Declined, FfaReadmitEntryRules.RdmState.Lapsed,
                                             FfaReadmitEntryRules.RdmState.Abandoned })
                {
                    F2DReset(state);
                    ReadmitOfferAdapter.PrimeFlights();
                    Check.True(!ReadmitOfferAdapter.Abandon("lobbyA") && !ReadmitOfferAdapter.Abandon("roomA", byRoom: true),
                               "a non-active record keeps its state even while its matching work is invalidated");
                    F2DRecordUnchanged(state, 2);
                    if (state == FfaReadmitEntryRules.RdmState.Entered)
                    {
                        Check.True(ReadmitOfferAdapter.ReadmittedInto("lobbyA"), "successful entry still identifies a readmitted seat");
                        Check.Eq(FfaReadmitEntryRules.RdmOffer.Rejected,
                                 ReadmitOfferAdapter.OfferFromPoll("lobbyA", 1, 3, 90), "successful entered suppression remains intact");
                    }
                }
            });
            RulesProgram.Add("C4.F2D.old_discovery_callback", () =>
            {
                foreach (bool oldOk in new[] { true, false })
                {
                    F2DReset(FfaReadmitEntryRules.RdmState.Admitted);
                    ReadmitOfferAdapter.HoldDiscovery = true;
                    ReadmitOfferAdapter.DiscoverThenProbe();
                    Check.True(ReadmitOfferAdapter.DiscoveryInFlight, "the old discovery is held");
                    Check.True(ReadmitOfferAdapter.Abandon("lobbyA"), "release advances the lifecycle");
                    ReadmitOfferAdapter.DiscoverThenProbe();
                    Check.Eq(2, ReadmitOfferAdapter.DiscoveryCallbacks.Count, "a new discovery starts before the old callback returns");
                    ReadmitOfferAdapter.DeliverDiscovery(0, oldOk, ReadmitOfferAdapter.OfferAnswer("old-offer", "lobbyC", 1));
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Abandoned
                               && ReadmitOfferAdapter.State.Lobby == "lobbyA" && ReadmitOfferAdapter.State.N == 3
                               && ReadmitOfferAdapter.State.Token == null, "the old discovery cannot apply an answer");
                    Check.True(ReadmitOfferAdapter.DiscoveryInFlight && !ReadmitOfferAdapter.Discovered,
                               "the old callback cannot clear or complete the new discovery flight");
                    Check.Eq(0, ReadmitOfferAdapter.Probes, "an old failed discovery cannot dispatch fallback");
                    ReadmitOfferAdapter.DeliverDiscovery(1, true, ReadmitOfferAdapter.OfferAnswer("current-offer", "lobbyB", 1));
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Offered
                               && ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.State.N == 1
                               && !ReadmitOfferAdapter.DiscoveryInFlight && ReadmitOfferAdapter.Discovered,
                               "the current generation discovery is applied normally");
                }
            });
            RulesProgram.Add("C4.F2D.old_post_callback", () =>
            {
                foreach (bool oldOk in new[] { true, false })
                {
                    F2DReset(FfaReadmitEntryRules.RdmState.Claiming, 1);
                    ReadmitOfferAdapter.SendForTest("claim", 0, 0);
                    Check.True(ReadmitOfferAdapter.PostInFlight, "the old claim callback is held");
                    Check.True(ReadmitOfferAdapter.Abandon("lobbyA"), "release ends the old claim");
                    Check.Eq(FfaReadmitEntryRules.RdmOffer.Accepted,
                             ReadmitOfferAdapter.OfferFromPoll("lobbyB", 2, 1, 90), "a different lobby may reuse hold one");
                    ReadmitOfferAdapter.Accept();
                    Check.Eq(2, ReadmitOfferAdapter.PostCallbacks.Count, "the new claim starts before the old callback returns");
                    string oldAnswer = ReadmitOfferAdapter.Answer("old-claim", "status", "claimed", "n", "1",
                                                                  "token", Token, "room", "roomA", "region", "eu", "slot", "1", "hold_s", "90");
                    ReadmitOfferAdapter.DeliverPost(0, oldOk, oldAnswer);
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Claiming
                               && ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.State.N == 1
                               && ReadmitOfferAdapter.State.Token == null && ReadmitOfferAdapter.State.Room == null,
                               "the old answer or failure cannot change the new claim with the same hold number");
                    Check.True(ReadmitOfferAdapter.PostInFlight && ReadmitOfferAdapter.PollCalls == 0,
                               "the old callback cannot clear the new post flight or dispatch an action");
                    string currentAnswer = ReadmitOfferAdapter.Answer("current-claim", "status", "claimed", "n", "1",
                                                                      "token", Token, "room", "roomB", "region", "eu", "slot", "2", "hold_s", "80");
                    ReadmitOfferAdapter.DeliverPost(1, true, currentAnswer);
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Claimed
                               && ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.State.Room == "roomB"
                               && ReadmitOfferAdapter.State.Token == Token && !ReadmitOfferAdapter.PostInFlight
                               && ReadmitOfferAdapter.PollCalls == 1 && ReadmitOfferAdapter.QueuePolling,
                               "the current generation claim is applied and dispatched normally");
                }
            });

            RulesProgram.Add("C4.F2E.escape_roomless_claim", () =>
            {
                ReadmitOfferAdapter.Reset(FfaReadmitEntryRules.RdmState.Claiming, "lobbyA", 1);
                ReadmitOfferAdapter.SendForTest("claim", 0, 0);
                Check.True(ReadmitOfferAdapter.PostInFlight && ReadmitOfferAdapter.State.Room == null,
                           "the roomless claim is in flight when escape runs");
                F2ERoute("escape");
                long generation = ReadmitOfferAdapter.Generation;
                Check.True(generation == 1 && !ReadmitOfferAdapter.PostInFlight, "escape invalidates the roomless flight");
                string answer = ReadmitOfferAdapter.Answer("escaped-claim", "status", "claimed", "n", "1",
                    "token", Token, "room", "roomA", "region", "eu", "slot", "1", "hold_s", "90");
                ReadmitOfferAdapter.DeliverPost(0, true, answer);
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Abandoned
                           && ReadmitOfferAdapter.State.Token == null && ReadmitOfferAdapter.State.Room == null
                           && ReadmitOfferAdapter.Generation == generation && !ReadmitOfferAdapter.PostInFlight
                           && ReadmitOfferAdapter.PollCalls == 0 && !ReadmitOfferAdapter.QueuePolling
                           && ReadmitOfferAdapter.Probes == 0 && ReadmitOfferAdapter.Toasts == 0,
                           "a released claim cannot install a token or re-arm the escape acknowledgement predicate");
                ReadmitOfferAdapter.Reset(FfaReadmitEntryRules.RdmState.Offered, "lobbyA", 1);
                F2ERoute("escape");
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Abandoned,
                           "global escape also closes an offered bar");
            });
            RulesProgram.Add("C4.F2E.lapse_refused_bind", () =>
            {
                F2DReset(FfaReadmitEntryRules.RdmState.Binding);
                ReadmitOfferAdapter.SendForTest("bind", 42, 0);
                ReadmitOfferAdapter.SetRoomForTest("roomA");
                // No queue belief remains: the real Refusal site must do the
                // invalidation before its leave stub receives an absent lobby.
                var next = FfaReadmitEntryRules.Tick(ReadmitOfferAdapter.State, 100f);
                Check.Eq(FfaReadmitEntryRules.RdmNext.Leave, next, "the real rule lapses the binding attempt");
                ReadmitOfferAdapter.ActForTest("lapse", next);
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Lapsed
                           && ReadmitOfferAdapter.State.LastReason == "hold_lapsed" && ReadmitOfferAdapter.Generation == 1
                           && !ReadmitOfferAdapter.PostInFlight && !ReadmitOfferAdapter.DiscoveryInFlight
                           && !ReadmitOfferAdapter.Discovered && ReadmitOfferAdapter.NextBind == 0f
                           && ReadmitOfferAdapter.RoomLeaves == 1 && ReadmitOfferAdapter.QueueLeaves == 1,
                           "real Act Leave and Refusal invalidate before leaving even after Tick set Lapsed");
                long generation = ReadmitOfferAdapter.Generation;
                int toasts = ReadmitOfferAdapter.Toasts;
                string answer = ReadmitOfferAdapter.Answer("lapsed-bind", "status", "refused", "n", "3",
                    "reason", "departed", "hold_s", "6");
                ReadmitOfferAdapter.DeliverPost(0, true, answer);
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Lapsed
                           && ReadmitOfferAdapter.State.LastReason == "hold_lapsed" && ReadmitOfferAdapter.State.HoldUntil == 80f
                           && ReadmitOfferAdapter.State.Token == null && ReadmitOfferAdapter.Generation == generation
                           && !ReadmitOfferAdapter.PostInFlight && !ReadmitOfferAdapter.DiscoveryInFlight
                           && !ReadmitOfferAdapter.Discovered && ReadmitOfferAdapter.NextBind == 0f
                           && ReadmitOfferAdapter.Toasts == toasts && ReadmitOfferAdapter.Probes == 0
                           && ReadmitOfferAdapter.PollCalls == 0, "a refused bind released by lapse has no late effects");
            });
            RulesProgram.Add("C4.F2E.delayed_after_leave", () => F2EDelayed("leave"));
            RulesProgram.Add("C4.F2E.delayed_after_release", () => F2EDelayed("release"));
            RulesProgram.Add("C4.F2E.delayed_after_depart", () => F2EDelayed("depart"));
            RulesProgram.Add("C4.F2E.playing_readmission_kept", () =>
            {
                foreach (string route in new[] { "escape", "leave", "release", "depart", "refusal" })
                {
                    F2DAdmit();
                    ReadmitOfferAdapter.SetEntryFactForTest("lobbyA", 4, true, "lobbyA");
                    ReadmitOfferAdapter.PostEntered(4);
                    Check.True(ReadmitOfferAdapter.PostInFlight, "the completed local entry has a pending entered acknowledgement");
                    F2ERoute(route);
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Admitted
                               && ReadmitOfferAdapter.State.Token == Token && ReadmitOfferAdapter.PostInFlight
                               && ReadmitOfferAdapter.Generation == 0, "every route keeps the playing record and its entered flight");
                    // Departure clears the fact after the route has preserved
                    // the generation; the already held callback still stands.
                    if (route == "depart") ReadmitOfferAdapter.SetEntryFactForTest(null, 0, false, null);
                    string answer = ReadmitOfferAdapter.Answer("entered-ack", "status", "entered", "n", "3");
                    ReadmitOfferAdapter.DeliverPost(1, true, answer);
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Entered
                               && ReadmitOfferAdapter.State.Token == null && !ReadmitOfferAdapter.PostInFlight
                               && ReadmitOfferAdapter.Generation == 0, "the preserved entered answer spends the token normally");
                }
                foreach (int mismatch in new[] { 0, 1, 2, 3 })
                {
                    F2DAdmit();
                    ReadmitOfferAdapter.SetEntryFactForTest(mismatch == 0 ? "lobbyB" : "lobbyA",
                        mismatch == 1 ? 5 : 4, mismatch != 2, mismatch == 3 ? null : "lobbyA");
                    ReadmitOfferAdapter.Abandon("lobbyA");
                    Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Abandoned
                               && ReadmitOfferAdapter.Generation == 1, "another identity, game or incomplete local entry never preserves the record");
                }
            });
            RulesProgram.Add("C4.F2E.unrelated_identity", () =>
            {
                foreach (string route in new[] { "leave", "release", "depart", "refusal" })
                foreach (var state in new[] { FfaReadmitEntryRules.RdmState.Claiming, FfaReadmitEntryRules.RdmState.Claimed,
                                             FfaReadmitEntryRules.RdmState.Binding, FfaReadmitEntryRules.RdmState.Admitted })
                {
                    F2DReset(state);
                    string step = state == FfaReadmitEntryRules.RdmState.Claiming ? "claim"
                        : state == FfaReadmitEntryRules.RdmState.Admitted ? "entered" : "bind";
                    ReadmitOfferAdapter.SendForTest(step, 42, 4);
                    if (route == "refusal")
                    {
                        // Refusal(true) names State.Lobby, so it cannot be an
                        // unrelated terminal route. The shared identity check
                        // and real non-leaving refusal are exercised separately.
                        Check.True(!ReadmitOfferAdapter.Abandon("lobbyB"), "an unrelated refusal identity invalidates nothing");
                        ReadmitOfferAdapter.RefusalForTest("other_lobby", false);
                    }
                    else F2ERoute(route, "lobbyB", "roomB");
                    Check.True(ReadmitOfferAdapter.State.State == state && ReadmitOfferAdapter.State.Lobby == "lobbyA"
                               && ReadmitOfferAdapter.State.Token == Token && ReadmitOfferAdapter.State.Room == "roomA"
                               && ReadmitOfferAdapter.Generation == 0 && ReadmitOfferAdapter.PostInFlight,
                               "another identity leaves the live record and its held callback whole");
                    string status = step == "claim" ? "claimed" : step == "entered" ? "entered" : "admitted_late";
                    string answer = ReadmitOfferAdapter.Answer("unrelated-answer", "status", status, "n", "3",
                        "token", Token, "room", "roomA", "region", "eu", "slot", "1", "kind", "r", "game", "4", "actor", "42");
                    ReadmitOfferAdapter.DeliverPost(0, true, answer);
                    var expected = step == "claim" ? FfaReadmitEntryRules.RdmState.Claimed
                        : step == "entered" ? FfaReadmitEntryRules.RdmState.Entered : FfaReadmitEntryRules.RdmState.Admitted;
                    Check.True(ReadmitOfferAdapter.State.State == expected && !ReadmitOfferAdapter.PostInFlight
                               && ReadmitOfferAdapter.Generation == 0, "the unrelated record applies its current callback normally");
                }
                F2DAdmit();
                ReadmitOfferAdapter.SetEntryFactForTest("lobbyB", 4, true, "lobbyB");
                ReadmitOfferAdapter.Abandon("lobbyA");
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Abandoned,
                           "a completed entry in lobbyB never preserves lobbyA");
            });
            RulesProgram.Add("C4.F2E.new_enrollment_after_escape", () =>
            {
                ReadmitOfferAdapter.Reset(FfaReadmitEntryRules.RdmState.Claiming, "lobbyA", 1);
                ReadmitOfferAdapter.SendForTest("claim", 0, 0);
                F2ERoute("escape");
                ReadmitOfferAdapter.DiscoveryResponse = ReadmitOfferAdapter.OfferAnswer("fresh-offer", "lobbyB", 1);
                ReadmitOfferAdapter.DiscoverThenProbe();
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Offered
                           && ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.Probes == 0,
                           "escape rearms discovery for a genuinely new enrollment");
                ReadmitOfferAdapter.Accept();
                string oldAnswer = ReadmitOfferAdapter.Answer("older-claim", "status", "claimed", "n", "1",
                    "token", Token, "room", "roomA", "hold_s", "90");
                ReadmitOfferAdapter.DeliverPost(0, true, oldAnswer);
                Check.True(ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.PostInFlight
                           && ReadmitOfferAdapter.PollCalls == 0, "the old callback cannot interrupt the new claim");
                string answer = ReadmitOfferAdapter.Answer("fresh-claim", "status", "claimed", "n", "1",
                    "token", Token, "room", "roomB", "region", "eu", "slot", "1", "hold_s", "90");
                ReadmitOfferAdapter.DeliverPost(1, true, answer);
                Check.True(ReadmitOfferAdapter.State.State == FfaReadmitEntryRules.RdmState.Claimed
                           && ReadmitOfferAdapter.State.Lobby == "lobbyB" && ReadmitOfferAdapter.State.Token == Token
                           && ReadmitOfferAdapter.State.Room == "roomB" && ReadmitOfferAdapter.PollCalls == 1
                           && ReadmitOfferAdapter.QueuePolling && !ReadmitOfferAdapter.PostInFlight,
                           "only the new generation claim rearms polling");
            });

            RulesProgram.Add("C4.T4.5.every_refusal_reason_mapped", () =>
            {
                var want = new Dictionary<string, FfaReadmitEntryRules.RefusalClass>
                {
                    { "hold_lapsed", FfaReadmitEntryRules.RefusalClass.Released },
                    { "lobby_closed", FfaReadmitEntryRules.RefusalClass.Ended },
                    { "departed", FfaReadmitEntryRules.RefusalClass.Departed },
                    { "not_held", FfaReadmitEntryRules.RefusalClass.Other },
                    { "other_mode", FfaReadmitEntryRules.RefusalClass.OtherQueue },
                    { "other_lobby", FfaReadmitEntryRules.RefusalClass.OtherQueue },
                    { "uncorroborated", FfaReadmitEntryRules.RefusalClass.Retrying },
                    { "actor_identity_mismatch", FfaReadmitEntryRules.RefusalClass.Identity },
                    { "actor_conflict", FfaReadmitEntryRules.RefusalClass.Identity },
                    { "entered_mismatch", FfaReadmitEntryRules.RefusalClass.Other },
                };
                foreach (var kv in want)
                    Check.Eq(kv.Value, FfaReadmitEntryRules.ClassOf(kv.Key), "reason " + kv.Key);
                foreach (var kv in want)
                {
                    if (kv.Key == "uncorroborated") continue;
                    var held = new FfaReadmitEntryRules.RdmClient { State = FfaReadmitEntryRules.RdmState.Binding, N = 1, Lobby = "lobbyA", Token = Token };
                    Check.Eq(FfaReadmitEntryRules.RdmNext.Leave, FfaReadmitEntryRules.OnAnswer(held, "bind", Ans("refused", kv.Key), 1f),
                             "a held seat refused (" + kv.Key + ") leaves");
                    Check.True(held.Token == null && held.LastReason == kv.Key, "the refusal drops the token and keeps the reason");
                    var claiming = new FfaReadmitEntryRules.RdmClient { State = FfaReadmitEntryRules.RdmState.Claiming, N = 1, Lobby = "lobbyA" };
                    Check.Eq(FfaReadmitEntryRules.RdmNext.Probe, FfaReadmitEntryRules.OnAnswer(claiming, "claim", Ans("refused", kv.Key), 1f),
                             "a refused claim (" + kv.Key + ") holds nothing and probes");
                }
                var lapse = new FfaReadmitEntryRules.RdmClient();
                FfaReadmitEntryRules.Offer(lapse, "lobbyA", 1, 1, 5, 0f);
                Check.Eq(FfaReadmitEntryRules.RdmNext.Probe, FfaReadmitEntryRules.Tick(lapse, 6f), "an unclaimed bar lapses to the probe");
            });

            RulesProgram.Add("C4.T4.5.epoch_v2_parsed_with_kind_and_game", () =>
            {
                string chain;
                var rec = ReadmitRecord(42, FfaReadmitEntryRules.Sha256Hex(Token), out chain);
                Check.Eq(chain, FfaLateRules.ChainOf(Lobby8, rec.Entries, rec.N), "the client chain of a v1 + v2 epoch equals the server's");
                Check.Eq("rx", FfaLateRules.RecordDecision(new FfaLateRules.EpochRecord(), Lobby8, rec.N, chain, rec.Entries),
                         "the record verifies and is taken");
                FfaLateRules.EpochEntry r;
                Check.True(FfaLateRules.KindREntry(rec, 1, -1, out r) && r.Actor == 42 && r.Game == 3, "the kind r entry of slot 1");
            });

            // ---------------------------------------------------------- T4.6 identity at the master
            RulesProgram.Add("C4.T4.6.token_checked_at_master", () =>
            {
                string chain;
                var rec = ReadmitRecord(42, FfaReadmitEntryRules.Sha256Hex(Token), out chain);
                var grants = new List<FfaLateRules.GrantEntry> { new FfaLateRules.GrantEntry(1, 42, 'r'), new FfaLateRules.GrantEntry(1, 43, 'r') };
                Func<int, bool> uidOk = s => s == 1;
                Check.Eq(FfaReadmitEntryRules.LateReq.Accept,
                         FfaReadmitEntryRules.LateRequest(42, grants, null, rec, -1, uidOk, "1:" + Token), "the genuine actor with T passes");
                Check.Eq(FfaReadmitEntryRules.LateReq.RefuseToken,
                         FfaReadmitEntryRules.LateRequest(42, grants, null, rec, -1, uidOk, "1:" + Token.Substring(1) + "0"), "a wrong T is refused");
                Check.Eq(FfaReadmitEntryRules.LateReq.RefuseToken,
                         FfaReadmitEntryRules.LateRequest(42, grants, null, rec, -1, uidOk, null), "no cr_rdt is refused");
                Check.Eq(FfaReadmitEntryRules.LateReq.Ignore,
                         FfaReadmitEntryRules.LateRequest(43, grants, null, rec, -1, uidOk, "1:" + Token), "an actor the kind r entry does not name is ignored");
            });

            RulesProgram.Add("C4.T4.6.identity_duplicate_refused", () =>
            {
                string chain;
                var rec = ReadmitRecord(42, FfaReadmitEntryRules.Sha256Hex(Token), out chain);
                // Actor 43 advertises seat 1's u_id after the old actor left.
                Check.Eq((bool?)true, FfaReadmitEntryRules.KindRUnauthorized(43, 1, rec), "another actor with the seat's identity is unauthorized");
                Check.Eq((bool?)false, FfaReadmitEntryRules.KindRUnauthorized(42, 1, rec), "the bound actor is authorized");
                Check.Eq((bool?)null, FfaReadmitEntryRules.KindRUnauthorized(43, 2, rec), "a slot with no kind r entry is today's rules");
            });

            RulesProgram.Add("C4.T4.6.grant_kind_r_never_inherits_s", () =>
            {
                Check.Eq('r', FfaReadmitEntryRules.GrantKind("s", 1, 42, null, null, true, true),
                         "a rebound start seat's new actor is kind r in a readmission lobby");
                Check.Eq('s', FfaReadmitEntryRules.GrantKind("s", 1, 42, null, null, false, true),
                         "outside one the server's kind stands");
                string chain;
                var rec = ReadmitRecord(42, FfaReadmitEntryRules.Sha256Hex(Token), out chain);
                Check.Eq('r', FfaReadmitEntryRules.GrantKind("l", 1, 42, rec.Entries, null, true, false), "a kind r epoch entry names it r");
            });

            // ---------------------------------------------------------- T4.7 snapshot sized by the roster
            RulesProgram.Add("C4.T4.7.held_highest_slot_carried", () =>
            {
                var master = new Table();
                var tail = SendAndRead(master, true);
                Check.True(tail != null, "the tail decodes");
                int[] r, p, pt, kl;
                FfaReadmitEntryRules.TailArrays(tail, 4, out r, out p, out pt, out kl);
                Check.Seq(master.Rounds, r, "rounds by slot");
                Check.Seq(master.Points, p, "points by slot");
                Check.Seq(master.PointsTotal, pt, "points total by slot, the held slot 3 included");
                Check.Seq(master.Kills, kl, "kills by slot, the held slot 3 included");
                // A scoring transition then game over on the survivor and the
                // returner: both end equal.
                var survivor = master.Copy();
                int[] ret = (int[])r.Clone(), retK = (int[])kl.Clone(), retPt = (int[])pt.Clone();
                survivor.Rounds[3]++; ret[3]++;
                survivor.Kills[3]++; retK[3]++;
                survivor.PointsTotal[3]++; retPt[3]++;
                Check.Seq(survivor.Rounds, ret, "rounds equal after the transition");
                Check.Seq(survivor.Kills, retK, "kills equal after the transition");
                Check.Seq(survivor.PointsTotal, retPt, "points total equal after the transition");
                int winS = Array.IndexOf(survivor.Rounds, survivor.Rounds.Max()), winR = Array.IndexOf(ret, ret.Max());
                Check.Eq(winS, winR, "both name the same winner");
            });

            RulesProgram.Add("C4.T4.7.flag_false_size_today", () =>
            {
                Check.Eq(3, FfaReadmitEntryRules.TailSize(false, 4, BodyTeams), "outside a readmission lobby the size is body-derived");
                Check.Eq(4, FfaReadmitEntryRules.TailSize(true, 4, BodyTeams), "inside one it is the roster's");
            });

            // ---------------------------------------------------------- T4.8 digest
            RulesProgram.Add("C4.T4.8.each_mutation_fails_the_gate", () =>
            {
                var honest = new Table();
                Check.True(Gate(SendAndRead(honest, true), 3, honest), "the honest tail passes");
                var muts = new List<KeyValuePair<string, Action<Table>>>
                {
                    new KeyValuePair<string, Action<Table>>("kills of the held slot", t => t.Kills[3]++),
                    new KeyValuePair<string, Action<Table>>("a history entry", t => t.History[3][0] = FfaReadmitEntryRules.HistoryEntry(1, true, 1, "Rare", "BOMBS AWAY")),
                    new KeyValuePair<string, Action<Table>>("the ledger", t => t.Ledger.RemoveAt(1)),
                    new KeyValuePair<string, Action<Table>>("a deck", t => t.Decks[3][1] = "Poison"),
                };
                for (int s = 0; s < 4; s++)
                {
                    int slot = s;
                    muts.Add(new KeyValuePair<string, Action<Table>>("draw index of slot " + I(s), t => t.Draw[slot]++));
                }
                foreach (var m in muts)
                {
                    var lying = honest.Copy();
                    m.Value(lying);
                    Check.True(!Gate(SendAndRead(lying, true), 3, honest), "a master tail mutating " + m.Key + " fails the gate");
                }
                // The game number: a tail digested under another g.
                string snap = FfaReadmitEntryRules.ReadmitDigest(4, 4, "12", SendAndRead(honest, true));
                Check.True(snap != PeerDigest(honest, 3, 4), "the game number is digest-covered");
            });

            // ---------------------------------------------------------- T4.9 departure as death
            RulesProgram.Add("C4.T4.9.departure_credits_exactly_staying", () =>
            {
                var done = new HashSet<string>();
                Func<FfaReadmitEntryRules.DepartureView> leave = () => new FfaReadmitEntryRules.DepartureView
                {
                    ReadmitLobby = true, BattleOngoing = true, VictimPresent = true, VictimTeam = 3, SourceTeam = 1, Key = "42:3:5",
                };
                var v = leave();
                Check.Eq(KillRule(1, 3, false, false, false), FfaReadmitEntryRules.DepartureCredit(v, done), "leave before death credits the damager");
                Check.Eq(-1, FfaReadmitEntryRules.DepartureCredit(leave(), done), "a duplicate callback credits once");
                var dead = leave(); dead.Key = "42:3:6"; dead.VictimDead = true;
                Check.Eq(-1, FfaReadmitEntryRules.DepartureCredit(dead, done), "simultaneous death and leave: the death already credited");
                var none = leave(); none.Key = "42:3:7"; none.SourceTeam = -1;
                Check.Eq(KillRule(-1, 3, false, false, false), FfaReadmitEntryRules.DepartureCredit(none, done), "no source credits nobody");
                var self = leave(); self.Key = "42:3:8"; self.SourceTeam = 3;
                Check.Eq(KillRule(3, 3, false, false, false), FfaReadmitEntryRules.DepartureCredit(self, done), "a suicide credits nobody");
                var lag = leave(); lag.Key = "42:3:9"; lag.VictimLagOut = true;
                Check.Eq(KillRule(1, 3, false, false, true), FfaReadmitEntryRules.DepartureCredit(lag, done), "a lag-out credits nobody");
                var q = leave(); q.Key = "42:3:10"; q.SourceQuarantined = true;
                Check.Eq(KillRule(1, 3, true, false, false), FfaReadmitEntryRules.DepartureCredit(q, done), "a quarantined source credits nobody");
                var off = leave(); off.Key = "42:3:11"; off.ReadmitLobby = false;
                Check.Eq(-1, FfaReadmitEntryRules.DepartureCredit(off, done), "flag false: nothing runs");
                var idle = leave(); idle.Key = "42:3:12"; idle.BattleOngoing = false;
                Check.Eq(-1, FfaReadmitEntryRules.DepartureCredit(idle, done), "between points: nothing");
            });

            // ---------------------------------------------------------- T4.10 registration
            RulesProgram.Add("C4.T4.10.same_position_any_purge_timing", () =>
            {
                bool ra, rb;
                var a = RegisterOn(new[] { 0, 2, 4 }, 3, out ra);          // purged slots 1 and 3 already
                var b = RegisterOn(new[] { 0, -1, 2, -1, 4 }, 3, out rb);  // not yet purged on this client
                Check.True(!ra && !rb, "neither refuses");
                Check.Seq(new[] { 0, 2, 3, 4 }, a, "sorted, no holes, the live fighters kept");
                Check.Seq(a, b, "both clients register the returner at the same position");
                bool rd;
                RegisterOn(new[] { 0, 2, 3, 4 }, 3, out rd);
                Check.True(rd, "a duplicate PlayerID is refused");
            });

            // ---------------------------------------------------------- T4.11 game number
            RulesProgram.Add("C4.T4.11.three_way_game_agreement", () =>
            {
                Check.True(FfaReadmitEntryRules.GameAgrees(3, 3, 3), "all three agree");
                Check.True(!FfaReadmitEntryRules.GameAgrees(3, 3, 4), "the room disagrees: no spawn");
                Check.True(!FfaReadmitEntryRules.GameAgrees(3, 4, 3), "the server disagrees: no spawn");
                Check.True(!FfaReadmitEntryRules.GameAgrees(4, 3, 3), "the snapshot disagrees: no spawn");
                Check.True(!FfaReadmitEntryRules.GameAgrees(0, 0, 0), "a seat that derives no number holds none");
            });

            // ---------------------------------------------------------- T4.12 latch
            RulesProgram.Add("C4.T4.12.kind_r_grant_releases_latch", () =>
            {
                Check.True(FfaReadmitEntryRules.GrantChangeReleasesLatches(true), "a grant change re-evaluates the latches in a readmission lobby");
                Check.True(!FfaReadmitEntryRules.GrantChangeReleasesLatches(false), "elsewhere a roster write stays the only trigger");
            });

            // ---------------------------------------------------------- step 8, replay at keep
            RulesProgram.Add("C4.T4.7.replay_only_kind_r_once", () =>
            {
                string chain;
                var rec = ReadmitRecord(42, FfaReadmitEntryRules.Sha256Hex(Token), out chain);
                var replayed = new HashSet<int>();
                Check.Eq(1, FfaReadmitEntryRules.ReplaySlotAtKeep(rec, 3, 42, replayed), "the kind r actor's slot is replayed at keep");
                Check.Eq(-1, FfaReadmitEntryRules.ReplaySlotAtKeep(rec, 2, 42, replayed), "not before its entry is stamped");
                Check.Eq(-1, FfaReadmitEntryRules.ReplaySlotAtKeep(rec, 3, 8, replayed), "a kind l seat is never replayed");
                replayed.Add(42);
                Check.Eq(-1, FfaReadmitEntryRules.ReplaySlotAtKeep(rec, 3, 42, replayed), "once");
                FfaReadmitEntryRules.Tail t = SendAndRead(new Table(), true);
                int round, order; bool rolled; string rarity, name;
                Check.True(FfaReadmitEntryRules.ParseHistory(t.SlotOf(2).History[0], out round, out rolled, out order, out rarity, out name)
                           && name == "SHIELD CHARGE: MK2" && rolled && rarity == "Rare", "a history entry round-trips, a colon in the name kept");
            });

            // ---------------------------------------------------------- T4.13 negative control (client half)
            RulesProgram.Add("C4.T4.13.flag_false_today", () =>
            {
                Check.True(!FfaReadmitEntryRules.DiscoveryOffers(0, "lobbyA", 1, 90), "readmissible 0: zero offers");
                Check.Eq(FfaReadmitEntryRules.BeltAct.Refuse, FfaReadmitEntryRules.Belt(false, false, false, false, "true"),
                         "a relaunched seat gets today's continued-without-you refusal");
                Check.Eq(FfaReadmitEntryRules.BeltAct.Wait, FfaReadmitEntryRules.Belt(false, false, false, false, "null"), "unknown waits as today");
                Check.Eq(0, FfaReadmitRules.LockReadmit(1, 0), "the flag stays false");
                Check.Eq(FfaReadmitEntryRules.LateReq.Ignore,
                         FfaReadmitEntryRules.LateRequest(9, new List<FfaLateRules.GrantEntry> { new FfaLateRules.GrantEntry(1, 9, 's') },
                                                          null, null, -1, s => true, null), "no late request from a start seat");
                Check.Eq(FfaReadmitEntryRules.LateReq.Accept,
                         FfaReadmitEntryRules.LateRequest(9, new List<FfaLateRules.GrantEntry> { new FfaLateRules.GrantEntry(1, 9, 'l') },
                                                          new List<FfaLateRules.EpochEntry> { new FfaLateRules.EpochEntry(1, 9) }, null, -1, s => true, null),
                         "a kind l late request is today's rule, no token");
                Check.Seq(new[] { 0, 1, 2 }, FfaReadmitEntryRules.DigestSlotSet(false, 4, BodyTeams), "flag false digests the kept bodies, as today");
                Check.Eq(FfaReadmitEntryRules.BeltAct.Offer, FfaReadmitEntryRules.Belt(false, false, true, false, "true"),
                         "positive twin: a readmissible seat is offered, not refused");
            });
        }
    }

    // Boundary stubs for extracted FfaReadmit members. Decisions stay in the
    // production rule and adapter bodies; callbacks can arrive out of order.
    internal class ReadmitOfferAdapterBase
    {
        internal static FfaReadmitEntryRules.RdmClient State;
        protected static bool _discovered, _discoveryInFlight, _postInFlight;
        protected static long _lifecycleGeneration;
        protected static float _nextBindRt;
        protected const int PostTimeout = 4;
        protected static bool _retryToastShown;
        internal static int Probes, PollCalls, PrepareCalls, ArmCalls, Toasts, RoomLeaves, QueueLeaves;
        internal static string ExpectedLobby;
        internal static bool HoldDiscovery;
        internal static string DiscoveryResponse;
        internal static readonly List<Action<bool, string>> DiscoveryCallbacks = new List<Action<bool, string>>();
        internal static readonly List<Action<bool, string>> PostCallbacks = new List<Action<bool, string>>();
        internal static readonly List<string> PostBodies = new List<string>();
        private static readonly Dictionary<string, Dictionary<string, string>> Responses = new Dictionary<string, Dictionary<string, string>>();
        internal static bool QueuePolling { get { return ApiClient.IsFfaQueuePolling; } }
        internal static bool Discovered { get { return _discovered; } }
        internal static bool DiscoveryInFlight { get { return _discoveryInFlight; } }
        internal static bool PostInFlight { get { return _postInFlight; } }
        internal static long Generation { get { return _lifecycleGeneration; } }
        internal static float NextBind { get { return _nextBindRt; } }
        internal static void Reset(FfaReadmitEntryRules.RdmState state, string lobby, int n)
        {
            State = new FfaReadmitEntryRules.RdmClient { State = state, Lobby = lobby, N = n };
            _discovered = _discoveryInFlight = _postInFlight = false;
            _lifecycleGeneration = 0; _nextBindRt = 0f;
            Probes = PollCalls = PrepareCalls = ArmCalls = Toasts = RoomLeaves = QueueLeaves = 0;
            ExpectedLobby = null; _retryToastShown = false;
            PhotonNetwork.InRoom = false; PhotonNetwork.CurrentRoom = null;
            PhotonNetwork.LocalPlayer = new PlayerStub { ActorNumber = 42 };
            ReadmitOfferAdapter.SetEntryFactForTest(null, 0, false, null);
            HoldDiscovery = false;
            DiscoveryCallbacks.Clear(); PostCallbacks.Clear(); PostBodies.Clear(); Responses.Clear();
            ApiClient.IsFfaQueuePolling = false;
            DiscoveryResponse = OfferAnswer("offer", "lobbyA", 1);
        }
        internal static void PrimeFlights()
        {
            _discovered = _discoveryInFlight = _postInFlight = true;
            _nextBindRt = 7f;
        }
        internal static string Reply(string name, params string[] fields)
        {
            var members = new Dictionary<string, string>();
            for (int i = 0; i < fields.Length; i += 2) members.Add(fields[i], fields[i + 1]);
            Responses.Add(name, members);
            return name;
        }
        internal static string OfferAnswer(string name, string lobby, int n)
        {
            return Reply(name, "readmissible", "1", "lobby_id", lobby, "slot", "1", "n", I(n), "hold_s", "90");
        }
        internal static string Answer(string name, params string[] fields)
        {
            return Reply(name, "readmit", Reply(name + "-fields", fields));
        }
        internal static void DeliverDiscovery(int at, bool ok, string response)
        {
            var callback = DiscoveryCallbacks[at]; DiscoveryCallbacks[at] = null;
            callback(ok, response);
        }
        internal static void DeliverPost(int at, bool ok, string response)
        {
            var callback = PostCallbacks[at]; PostCallbacks[at] = null;
            callback(ok, response);
        }
        protected static float Now() { return 100f; }
        protected static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }
        protected static void Ladder(FfaReadmitEntryRules.RdmState before, bool selfKept, string extra) { }
        internal static void LeaveForTest(string lobby)
        {
            ExpectedLobby = lobby;
            ApiClient.FfaLeaveQueue("test_leave");
        }
        internal static void SetRoomForTest(string room)
        {
            PhotonNetwork.InRoom = room != null;
            PhotonNetwork.CurrentRoom = room == null ? null : new RoomStub { Name = room };
        }
        internal sealed class RoomStub { internal string Name; }
        internal sealed class PlayerStub { internal int ActorNumber; }
        protected struct Color { internal Color(float r, float g, float b) { } }
        protected static class PhotonNetwork
        {
            internal static bool InRoom;
            internal static RoomStub CurrentRoom;
            internal static PlayerStub LocalPlayer;
            internal static void LeaveRoom() { RoomLeaves++; }
        }
        protected static class CompetitiveUI
        {
            internal static void ShowNotification(string message, Color color, float seconds) { Toasts++; }
        }
        protected static class MatchTracker { internal static string LocalSteamId = "1001"; }
        protected static class NativeUI { internal static void MarkDirty() { } }
        protected static class JoinTimeline { internal static int ClientMs() { return 50; } }
        protected class Plugin
        {
            internal static readonly Logger Log = new Logger();
            internal sealed class Logger { internal void LogWarning(string message) { } internal void LogInfo(string message) { } }
        }
        protected static class ApiClient
        {
            internal static bool IsFfaQueuePolling = false;
            internal const string BaseUrl = "https://example.invalid";
            internal static string JsonEscapeFullPublic(string value) { return value; }
            internal static void FfaReadmitOffer(string sid, Action<bool, string> done)
            {
                if (HoldDiscovery) DiscoveryCallbacks.Add(done);
                else done(true, DiscoveryResponse);
            }
            internal static void AsmPost(string url, string body, Action<bool, string> done, int timeout)
            {
                PostBodies.Add(body); PostCallbacks.Add(done);
            }
            internal static void FfaProbeServerState() { Probes++; }
            internal static void FfaStartReadmitPoll() { PollCalls++; IsFfaQueuePolling = true; }
            internal static void FfaLeaveQueue(string label)
            {
                QueueLeaves++;
                ReadmitOfferAdapter.Abandon(ExpectedLobby);
            }
        }
        protected static class FfaAssembly
        {
            internal sealed class Answer
            {
                internal string Route, Step, Lobby, Room, Status;
                internal int Assembly, Game;
                internal float Rt;
            }
            internal static string CurrentRoomName() { return PhotonNetwork.CurrentRoom == null ? null : PhotonNetwork.CurrentRoom.Name; }
            internal static Dictionary<string, string> Members(string response)
            {
                Dictionary<string, string> members;
                return response != null && Responses.TryGetValue(response, out members) ? members : new Dictionary<string, string>();
            }
            internal static string ExtractJsonString(Dictionary<string, string> response, string key)
            {
                string value;
                return response.TryGetValue(key, out value) ? value : null;
            }
            internal static string ExtractJsonRaw(Dictionary<string, string> response, string key) { return ExtractJsonString(response, key); }
            internal static int ExtractJsonInt(Dictionary<string, string> response, string key, int fallback)
            {
                int value;
                return int.TryParse(ExtractJsonString(response, key), NumberStyles.Integer, CultureInfo.InvariantCulture, out value) ? value : fallback;
            }
            internal static string LiveRegionCode() { return "eu"; }
        }
    }

}
