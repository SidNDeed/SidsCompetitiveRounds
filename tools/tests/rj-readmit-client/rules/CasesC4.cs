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

    // Boundary stubs for the extracted FfaReadmit discovery and poll adapters.
    // Offer decisions and fallback dispatch are the production method bodies.
    internal class ReadmitOfferAdapterBase
    {
        internal static FfaReadmitEntryRules.RdmClient State;
        protected static bool _discovered, _discoveryInFlight;
        internal static int Probes;
        internal static void Reset(FfaReadmitEntryRules.RdmState state, string lobby, int n)
        {
            State = new FfaReadmitEntryRules.RdmClient { State = state, Lobby = lobby, N = n };
            _discovered = _discoveryInFlight = false;
            Probes = 0;
        }
        protected static float Now() { return 100f; }
        protected static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }
        protected static void Ladder(FfaReadmitEntryRules.RdmState before, bool selfKept, string extra) { }
        protected static class MatchTracker { internal static string LocalSteamId = "1001"; }
        protected static class NativeUI { internal static void MarkDirty() { } }
        protected static class Plugin
        {
            internal static readonly Logger Log = new Logger();
            internal sealed class Logger { internal void LogWarning(string message) { } }
        }
        protected static class ApiClient
        {
            internal static bool IsFfaQueuePolling = false;
            internal static void FfaReadmitOffer(string sid, Action<bool, string> done) { done(true, "offer"); }
            internal static void FfaProbeServerState() { Probes++; }
        }
        protected static class FfaAssembly
        {
            internal static string Members(string response) { return response; }
            internal static string ExtractJsonString(string response, string key) { return "lobbyA"; }
            internal static int ExtractJsonInt(string response, string key, int fallback)
            {
                return key == "hold_s" ? 90 : 1;
            }
        }
    }
}
