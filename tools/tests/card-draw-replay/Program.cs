using System;
using System.Collections.Generic;
using System.Text.Json;
using CompetitiveRounds;
using Photon.Pun;

namespace CardDrawReplay
{
    /// <summary>Scripted replays through the REAL plugin/CardDrawEvidence.cs:
    /// the hook side's bounded copies, the drain on the tick, the seal at the
    /// dispatch (CD-M1), the room facts frozen before a reset or NOT-RUN
    /// (CD-M2), a first-phase fault kept (CD-M3), a census per game and the
    /// pool states (CD-M4), the quitting path's closing file (F3), the tick's
    /// combat hold. Each case runs in its own process:
    ///   CardReplayTests CASE
    /// Exit 0 only when the case passes.</summary>
    internal static class Program
    {
        private const string SEAT = "76561190000000001", OTHER = "76561190000000002";
        private const string ROOM = "ranked_room1";
        private const int ME = 1, OPP = 2;

        private static void Check(bool ok, string what) { if (!ok) throw new Exception(what); }
        private static void Eq<T>(T want, T got, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(want, got)) throw new Exception(what + ": want " + want + ", got " + got);
        }

        // -- the world ------------------------------------------------------------------

        private static CardChoice _choice;
        private static Player _me, _opp;
        private static int _nextView = 5000;

        private static CardInfo[] Pool(int n, string tag = "", bool collision = false)
        {
            var gunCat = new CardCategory { name = "Gun" };
            var other = new CardCategory { name = collision ? "Gun" : "Block" };
            var a = new CardInfo[n];
            for (int i = 0; i < n; i++)
            {
                a[i] = new CardInfo { rarity = (CardInfo.Rarity)(i % 3), categories = new[] { i % 2 == 0 ? gunCat : other } };
                a[i].gameObject.name = "Card" + i + tag;
            }
            return a;
        }

        private static Player NewPlayer(int id, int actor, bool mine, int team)
        {
            var view = new PhotonView { ViewID = 100 + id, IsMine = mine, ControllerActorNr = actor };
            var data = new CharacterData { view = view };
            return new Player { data = data, PlayerID = id, TeamID = team };
        }

        private static void World()
        {
            PhotonNetwork.CurrentRoom.Name = ROOM;
            _me = NewPlayer(0, ME, true, 0);
            _opp = NewPlayer(1, OPP, false, 1);
            PlayerManager.instance.players.Add(_me);
            PlayerManager.instance.players.Add(_opp);
            _choice = new CardChoice { cards = Pool(10) };
            _choice.transform.childCount = 5;
            CardChoice.instance = _choice;
            // the room predicate is the tick's (F4): a tick evaluates it before any phase
            CardDrawEvidence.Tick();
        }

        private static void Phase(int pickrId)
        {
            _choice.pickrID = pickrId;
            CardDrawEvidence.PhaseStarted(_choice);
        }

        /// <summary>A network spawn of pool card `src` by `creator`; its view id.</summary>
        private static int Spawn(int src, int creator)
        {
            var card = new CardInfo { sourceCard = src >= 0 ? _choice.cards[src] : null };
            var v = new PhotonView { ViewID = ++_nextView, CreatorActorNr = creator };
            card.Attach(v); v.Attach(card);
            PhotonNetwork.Views[v.ViewID] = v;
            CardDrawEvidence.CardAwake(card);
            return v.ViewID;
        }

        private static int[] Hand(int picker, params int[] srcs)
        {
            int actor = picker == 0 ? ME : OPP;
            var ids = new int[srcs.Length];
            for (int i = 0; i < srcs.Length; i++) ids[i] = Spawn(srcs[i], actor);
            return ids;
        }

        private static void Pick(int[] ids, int at, int pickId)
        {
            HitEvidence.RpcSender = pickId == 0 ? ME : OPP;
            CardDrawEvidence.EndPick(ids, ids[at], 0, pickId);
            CardDrawEvidence.DonePicking();
        }

        private static int Apply(int src, int toActor, int outcome)
        {
            var stats = new ApplyCardStats();
            var info = new CardInfo { sourceCard = _choice.cards[src] };
            var v = new PhotonView { ViewID = ++_nextView };
            stats.Attach(info); stats.Attach(v);
            CardDrawEvidence.PickApplied(stats, new[] { toActor }, outcome);
            return v.ViewID;
        }

        private static void Dispatch(string round = "_123456_r3")
        {
            CardDrawEvidence.Dispatch(SEAT, OTHER, ROOM + round, true);
        }

        private static JsonElement Record(string body)
        {
            var env = JsonDocument.Parse(body).RootElement;
            return JsonDocument.Parse(env.GetProperty("record").GetString()).RootElement;
        }

        private static JsonElement Last()
        {
            Check(SeatEvidence.Queued.Count > 0, "a record was queued");
            return Record(SeatEvidence.Queued[SeatEvidence.Queued.Count - 1]);
        }

        private static string Raw(JsonElement r, string key) { return r.GetProperty(key).GetRawText(); }

        private static int Cost(JsonElement r, int collector, int column) { return r.GetProperty("cost")[collector][column].GetInt32(); }

        // -- cases ---------------------------------------------------------------------------

        /// <summary>CD-M1: the dispatch seals the game. Only completed
        /// applications are applications; nothing reported after the dispatch
        /// reaches the record. The live room facts ride when no reset came.</summary>
        private static void Seal()
        {
            RoomRules.SameCards = true; FfaCardSequence.ActiveThisGame = false; RoomRules.LatchedProp = "ff=1;sc=1";
            Phase(0);
            var h = Hand(0, 1, 2, 3, 4, 5);
            int vid = Apply(2, ME, CardDrawEvidenceCore.APPLY_DONE);
            Apply(3, ME, CardDrawEvidenceCore.APPLY_SKIPPED);
            Apply(4, ME, CardDrawEvidenceCore.APPLY_FAULTED);
            Pick(h, 1, 0);
            Dispatch();
            // after the dispatch, before the tick: none of this is the game's
            Apply(7, ME, CardDrawEvidenceCore.APPLY_DONE);
            Spawn(8, ME);
            CardDrawEvidence.Tick();
            Eq(1, SeatEvidence.Queued.Count, "one record");
            var r = Last();
            Eq("[[0,2,0," + vid + "]]", Raw(r, "ap"), "ap holds only the completed application");
            Eq("[1,1]", Raw(r, "apx"), "one skipped, one that threw");
            Eq(1, r.GetProperty("tot")[0][4].GetInt32(), "one application counted");
            foreach (var c in r.GetProperty("cards").EnumerateArray()) Check(c[0].GetInt32() != 7 && c[0].GetInt32() != 8, "nothing after the dispatch is named");
            Eq(1, r.GetProperty("hd").GetArrayLength(), "one hand");
            Eq("[1,2]", Raw(r, "sc"), "the live rule and verdict");
            Eq("ff=1;sc=1", r.GetProperty("prof")[8].GetString(), "the live rules record");
            Eq(0, r.GetProperty("inc").GetInt32(), "complete");
        }

        /// <summary>CD-M3: a fault in the first phase's capture is kept, and no
        /// later phase is taken as the first.</summary>
        private static void FirstFault()
        {
            PlayerManager.ThrowOnId = true;
            Phase(0);
            PlayerManager.ThrowOnId = false;
            Phase(1);
            var h = Hand(1, 1, 2, 3, 4, 5);
            Pick(h, 0, 1);
            Dispatch();
            CardDrawEvidence.Tick();
            var r = Last();
            Eq(5, r.GetProperty("inc").GetInt32(), "first phase not captured, a collector fault");
            Eq("[]", Raw(r, "po"), "no player order from a later phase");
            Eq("[null,null]", Raw(r, "held0"), "no held cards from a later phase");
            Eq(1, Cost(r, 0, 3), "the fault counted in C1's row");
            Eq(1, r.GetProperty("hd").GetArrayLength(), "the later phase's hand kept");
        }

        /// <summary>CD-M3: a fault before the game was known marks the next
        /// game's first phase as not captured.</summary>
        private static void OrphanFault()
        {
            VanillaCardSequence.ThrowOnGame = true;
            Phase(0);
            VanillaCardSequence.ThrowOnGame = false;
            Phase(0);
            var h = Hand(0, 1, 2, 3, 4, 5);
            Pick(h, 0, 0);
            Dispatch();
            CardDrawEvidence.Tick();
            var r = Last();
            Eq(1, r.GetProperty("inc").GetInt32() & 1, "the first phase marked not captured");
            Eq("[]", Raw(r, "po"), "no player order");
        }

        /// <summary>CD-M2: the room facts frozen before the room reset ride in
        /// the record; a second reset site does not overwrite them.</summary>
        private static void Freeze()
        {
            RoomRules.SameCards = true; FfaCardSequence.ActiveThisGame = true; VanillaCardSequence.SharedSlotsServed = 3;
            RoomRules.LatchedProp = "ff=1;sc=1";
            Phase(0);
            var h = Hand(0, 1, 2, 3, 4, 5);
            Pick(h, 0, 0);
            CardDrawEvidence.FreezeRoomFacts();
            RoomRules.SameCards = false; FfaCardSequence.ActiveThisGame = false; VanillaCardSequence.SharedSlotsServed = 0;
            RoomRules.LatchedProp = "ff=1;sc=0";
            CardDrawEvidence.FreezeRoomFacts();      // the other reset site
            CardDrawEvidence.RoomExit();
            Dispatch();
            CardDrawEvidence.Tick();
            var r = Last();
            Eq("[1,1]", Raw(r, "sc"), "the rule and verdict as they stood");
            Eq("ff=1;sc=1", r.GetProperty("prof")[8].GetString(), "the rules record as it stood");
        }

        /// <summary>CD-M2: a game cut short with no freeze reads NOT-RUN, never
        /// the reset room's values.</summary>
        private static void NotRun()
        {
            RoomRules.SameCards = false; RoomRules.LatchedProp = "ff=1;sc=0";
            Phase(0);
            var h = Hand(0, 1, 2, 3, 4, 5);
            Pick(h, 0, 0);
            CardDrawEvidence.RoomExit();
            Dispatch();
            CardDrawEvidence.Tick();
            var r = Last();
            Eq("[-1,-1]", Raw(r, "sc"), "not read");
            Eq("", r.GetProperty("prof")[8].GetString(), "no rules record");
        }

        /// <summary>CD-M4: every game binds to a census of its own pool.</summary>
        private static void CensusPerGame()
        {
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            Dispatch();
            CardDrawEvidence.Tick();
            string d1 = Last().GetProperty("pool")[1].GetString();
            _choice.cards = Pool(10, "b");
            VanillaCardSequence.GameValue = 2;
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            Dispatch("_123456_r4");
            CardDrawEvidence.Tick();
            Eq(2, SeatEvidence.Queued.Count, "two records");
            var r2 = Last();
            Eq(64, r2.GetProperty("pool")[1].GetString().Length, "a digest");
            Check(r2.GetProperty("pool")[1].GetString() != d1, "the second game's census is its own pool's");
            Eq("ok", r2.GetProperty("pool")[2].GetString(), "ok");
            Check(Raw(r2, "cards").Contains("Card1b"), "its names from its own pool");
        }

        /// <summary>CD-M4: a collision is in the record; a pool that changed
        /// during the game (another array, or the same array's content) reads
        /// changed.</summary>
        private static void CensusStates()
        {
            _choice.cards = Pool(10, "", true);
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            Dispatch();
            CardDrawEvidence.Tick();
            Eq("collision", Last().GetProperty("pool")[2].GetString(), "a category name collision");
            // another array mid-game
            _choice.cards = Pool(10);
            VanillaCardSequence.GameValue = 2;
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            CardDrawEvidence.Tick();
            _choice.cards = Pool(10, "x");
            Phase(1);
            Pick(Hand(1, 1, 2, 3, 4, 5), 0, 1);
            Dispatch("_123456_r4");
            CardDrawEvidence.Tick();
            Eq("changed", Last().GetProperty("pool")[2].GetString(), "the pool array changed");
            // the same array's content changed between the census and the build
            VanillaCardSequence.GameValue = 3;
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            CardDrawEvidence.Tick();
            _choice.cards[9].rarity = CardInfo.Rarity.Rare;
            _choice.cards[9].gameObject.name = "Renamed";
            Dispatch("_123456_r5");
            CardDrawEvidence.Tick();
            Eq(3, SeatEvidence.Queued.Count, "three records");
            Eq("changed", Last().GetProperty("pool")[2].GetString(), "the pool content changed");
        }

        /// <summary>F3: the quitting path writes a closing file and never the
        /// queue; the tick builds nothing while combat is live.</summary>
        private static void QuitSpools()
        {
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            Dispatch();
            SeatEvidence.Combat = true;
            CardDrawEvidence.Tick();
            Eq(0, SeatEvidence.Queued.Count + SeatEvidence.Spooled.Count, "nothing while combat is live");
            CardDrawEvidence.FlushOnQuit();
            Eq(1, SeatEvidence.Spooled.Count, "kept in a closing file");
            Eq(0, SeatEvidence.Queued.Count, "the queue untouched on the quitting path");
            Eq(1, Record(SeatEvidence.Spooled[0]).GetProperty("hd").GetArrayLength(), "the game's hand");
        }

        /// <summary>F4: the hook side's buffer is bounded; a game whose events
        /// overflowed is still sealed and recorded, marked incomplete.</summary>
        private static void RingBounded()
        {
            Phase(0);
            for (int i = 0; i < 300; i++) Spawn(i % 10, ME);
            Dispatch();
            CardDrawEvidence.Tick();
            Eq(1, SeatEvidence.Queued.Count, "recorded");
            Eq(2, Last().GetProperty("inc").GetInt32() & 2, "events lost");
        }

        // -- fix pass 3 -------------------------------------------------------------------

        /// <summary>CD-M4: a category that becomes a distinct object with the
        /// same name during the game (the name digest unchanged) reads
        /// collision in the record, never ok.</summary>
        private static void CensusFinalCollision()
        {
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            CardDrawEvidence.Tick();
            _choice.cards[2].categories = new[] { new CardCategory { name = "Gun" } };
            Dispatch();
            CardDrawEvidence.Tick();
            Eq(1, SeatEvidence.Queued.Count, "recorded");
            Eq("collision", Last().GetProperty("pool")[2].GetString(), "the final census's collision");
        }

        /// <summary>CD-M4: a collision the game's first census found stays in
        /// the record when the pool no longer collides at the build (the
        /// colliding category replaced by the shared object): no later reading
        /// returns a game to ok.</summary>
        private static void CensusInitialCollision()
        {
            _choice.cards = Pool(10, "", true);
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            CardDrawEvidence.Tick();
            var gun = _choice.cards[0].categories[0];
            for (int i = 1; i < _choice.cards.Length; i += 2) _choice.cards[i].categories = new[] { gun };
            Dispatch();
            CardDrawEvidence.Tick();
            Eq(1, SeatEvidence.Queued.Count, "recorded");
            Eq("collision", Last().GetProperty("pool")[2].GetString(), "the first census's collision kept");
        }

        /// <summary>F4: the phase hook reads a room verdict the tick computed;
        /// it scans nothing itself. In a room the tick has not evaluated yet
        /// the hook collects nothing; after a tick it collects.</summary>
        private static void GatePrecomputed()
        {
            int s0 = RoomActors.Scans;
            Check(s0 >= 1, "the tick scanned the room");
            Phase(0);
            Phase(1);
            Phase(0);
            Eq(s0, RoomActors.Scans, "no room scan in the phase hook");
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            Dispatch();
            CardDrawEvidence.Tick();
            Eq(1, SeatEvidence.Queued.Count, "the first room's game recorded");
            // a new room before any tick: nothing collected
            PhotonNetwork.CurrentRoom.Name = "ranked_room2";
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            CardDrawEvidence.Dispatch(SEAT, OTHER, "ranked_room2_123456_r3", true);
            CardDrawEvidence.Tick();
            Eq(1, SeatEvidence.Queued.Count, "a room the tick had not evaluated collects nothing");
            // the tick evaluated it: the next game collects
            VanillaCardSequence.GameValue = 2;
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            CardDrawEvidence.Dispatch(SEAT, OTHER, "ranked_room2_123456_r4", true);
            CardDrawEvidence.Tick();
            Eq(2, SeatEvidence.Queued.Count, "collected once the tick evaluated the room");
        }

        /// <summary>CD-M3 (fix pass 4): a phase the gate skipped marks every later
        /// capture of the SAME physical game incomplete: a phase before the
        /// gate, then the gate, then a later phase of that game. A skip in an
        /// earlier game of the room marks nothing in the next game.</summary>
        private static void GateSameGameTransition()
        {
            // an earlier game's skipped phase: the next game in that room is whole
            PhotonNetwork.CurrentRoom.Name = "ranked_room2";
            VanillaCardSequence.GameValue = 1;
            Phase(0);
            CardDrawEvidence.Tick();
            VanillaCardSequence.GameValue = 2;
            Phase(0);
            Pick(Hand(0, 1, 2, 3, 4, 5), 0, 0);
            CardDrawEvidence.Dispatch(SEAT, OTHER, "ranked_room2_123456_r3", true);
            CardDrawEvidence.Tick();
            Eq(1, SeatEvidence.Queued.Count, "the next game recorded");
            Eq(0, Last().GetProperty("inc").GetInt32(), "a skip in an earlier game marks nothing");
            // the same game: its first phase before the gate, a later phase after it
            PhotonNetwork.CurrentRoom.Name = "ranked_room3";
            VanillaCardSequence.GameValue = 3;
            Phase(0);
            CardDrawEvidence.Tick();
            Phase(1);
            var h = Hand(1, 1, 2, 3, 4, 5);
            Pick(h, 0, 1);
            CardDrawEvidence.Dispatch(SEAT, OTHER, "ranked_room3_123456_r3", true);
            CardDrawEvidence.Tick();
            Eq(2, SeatEvidence.Queued.Count, "the later phase recorded");
            var r = Last();
            Eq(1, r.GetProperty("inc").GetInt32(), "the first phase marked not captured, nothing else");
            Eq("[]", Raw(r, "po"), "no player order from a later phase");
            Eq("[null,null]", Raw(r, "held0"), "no held cards from a later phase");
            Eq(1, r.GetProperty("hd").GetArrayLength(), "the later phase's hand kept");
        }

        /// <summary>F4: the build lookup (reflection) is the tick's: no hook
        /// and no dispatch looks it up, and the record carries it.</summary>
        private static void BuildOnTick()
        {
            Phase(0);
            var h = Hand(0, 1, 2, 3, 4, 5);
            Apply(2, ME, CardDrawEvidenceCore.APPLY_DONE);
            Pick(h, 0, 0);
            Dispatch();
            Eq(0, PeerBuild.Calls, "no build lookup in a hook or the dispatch");
            CardDrawEvidence.Tick();
            Check(PeerBuild.Calls >= 1, "the tick looked the build up");
            var p = Last().GetProperty("prof");
            Eq("1.41.0", p[4].GetString(), "the version");
            Eq("STANDALONE", p[5].GetString(), "the variant");
            Eq("abc1234", p[6].GetString(), "the commit");
        }

        private static readonly Dictionary<string, Action> Cases = new Dictionary<string, Action>
        {
            { "seal", Seal }, { "first_fault", FirstFault }, { "orphan_fault", OrphanFault }, { "freeze", Freeze },
            { "not_run", NotRun }, { "census_per_game", CensusPerGame }, { "census_states", CensusStates },
            { "quit_spools", QuitSpools }, { "ring_bounded", RingBounded },
            // fix pass 3
            { "census_final_collision", CensusFinalCollision }, { "gate_precomputed", GatePrecomputed },
            { "build_on_tick", BuildOnTick }, { "census_initial_collision", CensusInitialCollision },
            // fix pass 4
            { "gate_same_game_transition", GateSameGameTransition },
        };

        private static int Main(string[] args)
        {
            if (args.Length == 1 && args[0] == "list") { foreach (var k in Cases.Keys) Console.WriteLine(k); return 0; }
            Action a;
            if (args.Length != 1 || !Cases.TryGetValue(args[0], out a)) { Console.WriteLine("usage: CardReplayTests CASE | list"); return 2; }
            try
            {
                World();
                a();
                Console.WriteLine("PASS " + args[0]);
                return 0;
            }
            catch (Exception ex)
            {
                Console.WriteLine("FAIL " + args[0] + ": " + ex.Message);
                return 1;
            }
        }
    }
}
