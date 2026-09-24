using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>RJ-DRIFT: the FFA game-number rules, as pure functions.
    ///
    /// Every seat in an FFA room has to key a game's report, its pick
    /// namespace and its card seed with the SAME number. The per-seat counter
    /// (FfaMode.gameNumber) cannot be that number: a seat that relaunches,
    /// joins late, spectates, drops or re-enters restarts or skips it. These
    /// rules derive the number from room state every seat reads alike (the
    /// host's cr_ffa_cyc write, the witnesses, the adverts) and give NO number
    /// where the room does not supply one. A seat with no number is
    /// ineligible to key or file; it never substitutes its own counter.
    ///
    /// Pure: no UnityEngine, no Photon. A Room object is an opaque reference
    /// compared by identity, never by name. FfaMode, GameStateWatcher,
    /// VanillaFixes and SpectatorJoiner call these functions at their sites,
    /// and the client-rules harness runs them through SelfTest: the unit cases
    /// and the SittingModel walks below (design RJ-DRIFT V4 sections 2-5).
    /// NoGame (-1) means "none" everywhere; every game number is 1 or more.</summary>
    internal static class FfaNumberingRules
    {
        internal const int NoGame = -1;

        // ── N9: the advert target and key ────────────────────────────────

        /// <summary>FNV-1a over the UTF-16 code units of the room name, modulo
        /// 1000000: the derivation FfaCardSequence used for its capability
        /// key, so FfaCardSequence.RoomKey() can delegate here unchanged. A
        /// null name is treated as the empty name.</summary>
        internal static int RoomKey(string roomName)
        {
            uint h = 2166136261u;
            string s = roomName ?? "";
            unchecked
            {
                for (int i = 0; i < s.Length; i++) { h ^= s[i]; h *= 16777619u; }
            }
            return (int)(h % 1000000u);
        }

        /// <summary>The key recorded with a join target. It is derived from
        /// the TARGET, never from the room the seat happens to be in when it
        /// records (outside a room that name is empty).</summary>
        internal static int StagedAdvertKey(string target, string current)
        {
            return RoomKey(target);
        }

        /// <summary>The spectator join's target: the join room when it is the
        /// room the grant recorded, else none (and a null target records
        /// nothing).</summary>
        internal static string SpectatorAdvertTarget(string pending, string join)
        {
            return string.Equals(pending, join, StringComparison.Ordinal) ? join : null;
        }

        /// <summary>The cr_ffa_rg value a join stages: "1:" + the recorded key
        /// when one is recorded for exactly this join target, else null, which
        /// deletes the property. A key recorded for another target never rides
        /// this join.</summary>
        internal static string AdvertAtJoin(string recordedTarget, int recordedKey, string joinTarget)
        {
            if (recordedKey < 0 || recordedTarget == null || joinTarget == null) return null;
            if (!string.Equals(recordedTarget, joinTarget, StringComparison.Ordinal)) return null;
            return AdvertValue(recordedKey);
        }

        /// <summary>The advert string for a room key.</summary>
        internal static string AdvertValue(int roomKey)
        {
            return "1:" + roomKey.ToString(CultureInfo.InvariantCulture);
        }

        // ── N1: the key freeze ──────────────────────────────────────────

        /// <summary>The candidate: this seat's own confirmed cr_ffa_cyc write
        /// (the ticket) when it holds a valid one, else the field read back
        /// from the room, else none.</summary>
        internal static int Candidate(bool ticketValid, int ticketGame, int readback)
        {
            return ticketValid && ticketGame >= 1 ? ticketGame : (readback >= 1 ? readback : NoGame);
        }

        /// <summary>HELD: the candidate is 1 or more and equals the ending
        /// master's room game, or the room game of a present fighter that
        /// advertises this room. The caller supplies each value from the seat's
        /// own view (its own RG for itself, a peer's witness otherwise) and
        /// passes only advertising fighters. HELD accepts or refuses the
        /// host's value; it never supplies one. The gate reaches the verdict
        /// text only: N1 is ungated.</summary>
        internal static bool HeldByRoom(int candidate, bool gate, bool masterPresent, int masterGame,
                                        IList<int> fighterGames, out string verdict)
        {
            bool masterHolds = masterPresent && masterGame >= 1 && masterGame == candidate;
            bool fighterHolds = false;
            if (fighterGames != null)
                for (int i = 0; i < fighterGames.Count; i++)
                    if (fighterGames[i] >= 1 && fighterGames[i] == candidate) { fighterHolds = true; break; }
            verdict = (candidate >= 1 && masterHolds ? "master" : candidate >= 1 && fighterHolds ? "fighter" : "no")
                      + " G=" + (gate ? "1" : "0");
            return candidate >= 1 && (masterHolds || fighterHolds);
        }

        // ── N2: the carry ───────────────────────────────────────────────

        /// <summary>The next game's number, decided at this game's edge from
        /// the stored snapshot: F + 1 when F is 1 or more; else the stored
        /// candidate + 1 when the ending master is present and holds room game
        /// exactly none (a missing master is never read as none) and the
        /// candidate is 1 or more; else none. The field at the carry and the
        /// seat's RG at its start reach the log only: the field is never
        /// re-read here.</summary>
        internal static int CarryAfterGameOver(int F, int candidate, int fieldAtCarry, bool masterPresent,
                                               int masterGame, bool heldRGAtStart)
        {
            if (F >= 1) return F + 1;
            if (masterPresent && masterGame == NoGame && candidate >= 1)
                return candidate + 1;
            return NoGame;
        }

        // ── N3 + N7: the room game and the counter at a start edge ──────

        /// <summary>RG at a start: the carry bound to this Room object; else
        /// the previous RG + 1 when this seat's previous start in this Room
        /// object held one and it did not follow a numberless master since;
        /// else 1 on the first start in this Room object with cr_ffa_cyc
        /// absent; else none. The counter becomes RG under the gate when RG is
        /// 1 or more, else counter + 1 (today's). cycleGameAtStart reaches the
        /// log only.</summary>
        internal static void StartNumbers(bool carryHere, int carry, bool prevRGHere, int prevRG,
                                          bool followedPrev, bool firstStartHere, bool cycleAbsent,
                                          int cycleGameAtStart, bool gate, int counter,
                                          out int roomGame, out int nextCounter)
        {
            if (carryHere && carry >= 1)
                roomGame = carry;
            else if (prevRGHere && prevRG >= 1 && !followedPrev)
                roomGame = prevRG + 1;
            else if (firstStartHere && cycleAbsent)
                roomGame = 1;
            else
                roomGame = NoGame;
            nextCounter = gate && roomGame >= 1 ? roomGame : counter + 1;
        }

        /// <summary>The source word for the start log line. Log only: it
        /// decides nothing.</summary>
        internal static string StartSourceLabel(bool carryHere, int carry, bool prevRGHere, int prevRG,
                                                bool followedPrev, bool firstStartHere, bool cycleAbsent,
                                                int roomGame)
        {
            if (roomGame >= 1)
            {
                if (carryHere && carry == roomGame) return "carry";
                if (prevRGHere && prevRG >= 1 && prevRG + 1 == roomGame) return "continuation";
                if (roomGame == 1 && firstStartHere && cycleAbsent) return "first";
                return "other";
            }
            return prevRGHere && prevRG >= 1 && followedPrev ? "followed" : "none";
        }

        // ── N0 / N14: Room-object identity ───────────────────────────────

        /// <summary>The same Room object: reference identity, never the
        /// name. PUN allocates a fresh Room object per entry, so a re-entry
        /// under the same name is a different incarnation.</summary>
        internal static bool SameIncarnation(object a, object b)
        {
            return a != null && ReferenceEquals(a, b);
        }

        /// <summary>A snapshot takes and returns a value only while the Room
        /// object that armed it is current.</summary>
        internal static bool SnapshotArmed(object armedIn, object room)
        {
            return SameIncarnation(armedIn, room);
        }

        /// <summary>The start is in a different Room object from this seat's
        /// last start. The names reach the log only.</summary>
        internal static bool RoomObjectChanged(object lastRoom, object room, string lastName, string name)
        {
            return !SameIncarnation(lastRoom, room);
        }

        // ── N4 / N11 / N5: the witness ──────────────────────────────────

        /// <summary>cr_ffa_gw at a start: RG, or none.</summary>
        internal static int WitnessToPublish(int roomGame)
        {
            return roomGame >= 1 ? roomGame : NoGame;
        }

        /// <summary>cr_ffa_gw staged at a join: none, whatever the seat held
        /// before. A joining seat has started no game in the room it joins.</summary>
        internal static int WitnessAtJoin(int held)
        {
            return NoGame;
        }

        /// <summary>A present seat is a witness of this seat's F when F is 1 or
        /// more and the seat's cr_ffa_gw equals it.</summary>
        internal static bool IsWitness(int witnessed, int frozen)
        {
            return frozen >= 1 && witnessed == frozen;
        }

        // ── N10: the local game sequence ────────────────────────────────

        /// <summary>A leaver's stamp: the local game sequence, never the
        /// counter (which N7 may have re-anchored).</summary>
        internal static int LeaverStampSource(int seq, int counter)
        {
            return seq;
        }

        /// <summary>The leaver left in the game this body reports.</summary>
        internal static bool LeftInGame(int stamp, int seqNow)
        {
            return stamp == seqNow;
        }

        // ── N6 / N8: the gate and the spawn seed ─────────────────────────

        /// <summary>G: every active fighter, this seat included, advertises
        /// cr_ffa_rg == "1:" + the room's key. Missing, foreign or unparseable
        /// is false; there is no pending state.</summary>
        internal static bool DriftGate(string localAdvert, IList<string> peerAdverts, int roomKey)
        {
            string want = AdvertValue(roomKey);
            if (localAdvert != want) return false;
            if (peerAdverts != null)
                for (int i = 0; i < peerAdverts.Count; i++)
                    if (peerAdverts[i] != want) return false;
            return true;
        }

        /// <summary>The spawn seed's game input: under G the host's field
        /// (1 when absent), otherwise the counter (today's).</summary>
        internal static int SpawnSeedGame(bool gate, int fieldGame, int counter)
        {
            return gate ? (fieldGame >= 1 ? fieldGame : 1) : counter;
        }

        // ── N12 / N15: the pick identity ────────────────────────────────

        /// <summary>LIVE(g, c): the field names a game, its result is absent,
        /// and its deadline is absent or at most 15 s (the bail margin) past.</summary>
        internal static bool LiveCycle(int g, bool resultPresent, bool deadlineKnown, float deadline, float now)
        {
            return g >= 1 && !resultPresent && !(deadlineKnown && now > deadline + 15f);
        }

        /// <summary>A numbered, non-master seat follows the host while the
        /// present master holds no room game.</summary>
        internal static bool FollowsHost(bool isMaster, bool masterPresent, int masterWitness, int roomGame)
        {
            return !isMaster && masterPresent && masterWitness == NoGame && roomGame >= 1;
        }

        /// <summary>The game a pick phase keys. G off: the counter (today's).
        /// Under G: RG unless following; else the acquired game; else the
        /// live field; else none (the caller makes no keyed read).</summary>
        internal static int PickIdentitySource(bool gate, int roomGame, bool followHost, int acquiredGame,
                                               int liveGame, int counter)
        {
            if (!gate) return counter;
            if (roomGame >= 1 && !followHost) return roomGame;
            if (acquiredGame >= 1) return acquiredGame;
            return liveGame >= 1 ? liveGame : NoGame;
        }

        /// <summary>N12/N15's regime: under G, a seat with no ACQUIRED identity
        /// in this Room object that holds no RG, or holds one while following
        /// a numberless host. Such a seat takes a LIVE field at the
        /// manifest-wait entry (N12(b)) and on every change of the field
        /// (N12(c)) without the ahead test; every other seat keeps the pin's
        /// ahead-only adoption. One function, called by FfaPickPhase and by
        /// the walk model alike.</summary>
        internal static bool LiveRegime(bool gate, int roomGame, bool followHost, int acquiredGame)
        {
            return gate && acquiredGame < 1 && (roomGame < 1 || followHost);
        }

        /// <summary>N12(b): at the entry, a seat in the regime whose phase
        /// identity is the live field's game takes that field (game, cycle,
        /// counter, manifest) and records it as ACQUIRED.</summary>
        internal static bool TakesLiveAtEntry(bool regime, int identity, int liveGame)
        {
            return regime && liveGame >= 1 && identity == liveGame;
        }

        /// <summary>A numberless master with no live value opens a namespace:
        /// 1:1 at the opening draw; after a point the field's game and cycle +
        /// 1 (1:1 when the field is absent). The caller assigns neither the
        /// counter nor ACQUIRED from it.</summary>
        internal static int MasterOpenerGame(bool openingDraw, int fieldGame, int fieldCycle, out int cycle)
        {
            if (openingDraw) { cycle = 1; return 1; }
            if (fieldGame >= 1) { cycle = fieldCycle + 1; return fieldGame; }
            cycle = 1;
            return 1;
        }

        // ── N13: the numbered consumers ─────────────────────────────────

        /// <summary>The game a live-points send carries: RG, else the
        /// candidate, else none (the send is declined). The gate, HELD and the
        /// counter reach the log only.</summary>
        internal static int LivePointsGame(bool gate, int roomGame, int candidate, bool held, int counter)
        {
            if (roomGame >= 1) return roomGame;
            if (candidate >= 1) return candidate;
            return NoGame;
        }

        /// <summary>The start-edge seed's game: the counter with G off
        /// (today's); under G, RG, else none (the first pick phase publishes
        /// it under the phase identity).</summary>
        internal static int StartSeedGame(bool gate, int roomGame, int counter)
        {
            if (!gate) return counter;
            return roomGame >= 1 ? roomGame : NoGame;
        }

        // ── Log text (decides nothing) ──────────────────────────────────

        internal static string N(int n)
        {
            return n >= 1 ? n.ToString(CultureInfo.InvariantCulture) : "none";
        }

        internal static string FrozeLine(int f, int cand, bool byTicket, string held, bool gate, int carry,
                                         int field, bool rgAtStart, bool followed)
        {
            return "[FFA-NUM] froze F=" + N(f) + " cand=" + N(cand) + " (" + (byTicket ? "ticket" : "readback")
                   + ") held=" + (held ?? "no") + " G=" + (gate ? "1" : "0") + " carry=" + N(carry)
                   + " field=" + field.ToString(CultureInfo.InvariantCulture)
                   + " rgAtStart=" + (rgAtStart ? "1" : "0") + " fol=" + (followed ? "1" : "0");
        }

        internal static string StartLine(int rg, string source, bool gate, int local, int seq)
        {
            return "[FFA-NUM] start RG=" + N(rg) + " (" + source + ") G=" + (gate ? "1" : "0")
                   + " local=" + local.ToString(CultureInfo.InvariantCulture)
                   + " seq=" + seq.ToString(CultureInfo.InvariantCulture);
        }

        // ── self-test (EXECUTED by tools/client-rules-harness, suite "numbering") ──

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>The 91 unit cases, then the SittingModel's 67 walk cases.
        /// Every case prints exactly one line, "PASS id" or "FAIL id ...", so a
        /// FAIL set is a set of case ids.</summary>
        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            RunUnits(r);
            SittingModel.RunAll(r);
            return r;
        }

        private static void Unit(SelfTestResult r, string id, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS " : "FAIL ").Append(id).Append(" | got=").Append(got ?? "(null)").Append('\n');
        }

        private static string B(bool b) { return b ? "true" : "false"; }
        private static string I(int n) { return n.ToString(CultureInfo.InvariantCulture); }

        private static void RunUnits(SelfTestResult r)
        {
            // Candidate
            Unit(r, "U-CAND-1", Candidate(true, 5, 4) == 5, I(Candidate(true, 5, 4)));
            Unit(r, "U-CAND-2", Candidate(false, 5, 4) == 4, I(Candidate(false, 5, 4)));
            Unit(r, "U-CAND-3", Candidate(false, NoGame, -1) == NoGame, I(Candidate(false, NoGame, -1)));
            Unit(r, "U-CAND-4", Candidate(true, 1, 3) == 1, I(Candidate(true, 1, 3)));

            // HeldByRoom
            {
                string v;
                bool h1 = HeldByRoom(4, true, true, 4, new[] { 4, 4 }, out v);
                Unit(r, "U-HELD-1", h1, B(h1) + " " + v);
                bool h2 = HeldByRoom(1, true, true, NoGame, new[] { 1 }, out v);
                Unit(r, "U-HELD-2", h2, B(h2) + " " + v);
                bool h3 = HeldByRoom(3, true, true, 4, new[] { 4 }, out v);
                Unit(r, "U-HELD-3", !h3, B(h3) + " " + v);
                bool h4 = HeldByRoom(NoGame, true, true, NoGame, new[] { NoGame }, out v);
                Unit(r, "U-HELD-4", !h4, B(h4) + " " + v);
                bool h5 = HeldByRoom(1, true, false, NoGame, new[] { 1 }, out v);
                Unit(r, "U-HELD-5", h5, B(h5) + " " + v);
                bool h6 = HeldByRoom(3, false, true, 4, new[] { 4 }, out v);
                Unit(r, "U-HELD-6", !h6, B(h6) + " " + v);
            }

            // CarryAfterGameOver(F, candidate, fieldAtCarry, masterPresent, masterGame, heldRGAtStart)
            {
                int c1 = CarryAfterGameOver(4, 4, 4, true, 4, true);
                Unit(r, "U-CARRY-1", c1 == 5, I(c1));
                int c2 = CarryAfterGameOver(NoGame, 1, 1, true, NoGame, false);
                Unit(r, "U-CARRY-2", c2 == 2, I(c2));
                int c3 = CarryAfterGameOver(NoGame, 1, 1, false, NoGame, false);
                Unit(r, "U-CARRY-3", c3 == NoGame, I(c3));
                int c4 = CarryAfterGameOver(NoGame, 1, 1, true, NoGame, true);
                Unit(r, "U-CARRY-4", c4 == 2, I(c4));
                int c5 = CarryAfterGameOver(NoGame, 1, 3, true, NoGame, false);
                Unit(r, "U-CARRY-5", c5 == 2, I(c5));
                int c6 = CarryAfterGameOver(NoGame, 3, 3, true, 4, false);
                Unit(r, "U-CARRY-6", c6 == NoGame, I(c6));
            }

            // StartNumbers(carryHere, carry, prevRGHere, prevRG, followedPrev, firstStartHere,
            //              cycleAbsent, cycleGameAtStart, gate, counter)
            {
                int rg, next;
                StartNumbers(true, 5, false, NoGame, false, false, false, 4, true, 4, out rg, out next);
                Unit(r, "U-START-1", rg == 5 && next == 5, "RG=" + I(rg) + " counter=" + I(next));
                StartNumbers(false, 5, false, NoGame, false, true, false, 3, true, 0, out rg, out next);
                Unit(r, "U-START-2", rg == NoGame, "RG=" + I(rg));
                StartNumbers(false, NoGame, false, NoGame, false, true, true, NoGame, true, 0, out rg, out next);
                Unit(r, "U-START-3", rg == 1, "RG=" + I(rg));
                StartNumbers(false, NoGame, false, NoGame, false, true, false, 3, true, 0, out rg, out next);
                Unit(r, "U-START-4", rg == NoGame, "RG=" + I(rg));
                StartNumbers(false, NoGame, true, 4, false, false, false, 4, true, 4, out rg, out next);
                Unit(r, "U-START-5", rg == 5, "RG=" + I(rg));
                StartNumbers(false, NoGame, true, NoGame, false, false, false, 3, true, 1, out rg, out next);
                Unit(r, "U-START-6", rg == NoGame, "RG=" + I(rg));
                StartNumbers(true, 5, false, NoGame, false, false, false, 4, false, 2, out rg, out next);
                Unit(r, "U-START-7", rg == 5 && next == 3, "RG=" + I(rg) + " counter=" + I(next));
                StartNumbers(false, NoGame, true, 2, true, false, false, 1, true, 2, out rg, out next);
                Unit(r, "U-START-8", rg == NoGame, "RG=" + I(rg));
            }

            // Room-object identity
            {
                object r1 = new object(), r2 = new object();
                Unit(r, "U-INC-1", SameIncarnation(r1, r1), B(SameIncarnation(r1, r1)));
                Unit(r, "U-INC-2", !SameIncarnation(r1, r2), B(SameIncarnation(r1, r2)));
                Unit(r, "U-INC-3", !SameIncarnation(null, null), B(SameIncarnation(null, null)));
                Unit(r, "U-ARM-1", SnapshotArmed(r1, r1), B(SnapshotArmed(r1, r1)));
                Unit(r, "U-ARM-2", !SnapshotArmed(r1, r2), B(SnapshotArmed(r1, r2)));
                Unit(r, "U-ARM-3", !SnapshotArmed(null, r1), B(SnapshotArmed(null, r1)));
                bool c1 = RoomObjectChanged(r1, r1, "ffa_2", "ffa_2");
                Unit(r, "U-ROOM-1", !c1, B(c1));
                bool c2 = RoomObjectChanged(r1, r2, "ffa_2", "ffa_2");
                Unit(r, "U-ROOM-2", c2, B(c2));
                bool c3 = RoomObjectChanged(r1, r2, "ffa_1", "ffa_2");
                Unit(r, "U-ROOM-3", c3, B(c3));
                bool c4 = RoomObjectChanged(null, r1, "", "ffa_2");
                Unit(r, "U-ROOM-4", c4, B(c4));
            }

            // Witness
            Unit(r, "U-WIT-1", WitnessToPublish(NoGame) == NoGame, I(WitnessToPublish(NoGame)));
            Unit(r, "U-WIT-2", WitnessToPublish(4) == 4, I(WitnessToPublish(4)));
            Unit(r, "U-WIT-3", WitnessAtJoin(4) == NoGame, I(WitnessAtJoin(4)));
            Unit(r, "U-ISW-1", IsWitness(5, 5), B(IsWitness(5, 5)));
            Unit(r, "U-ISW-2", !IsWitness(4, 5), B(IsWitness(4, 5)));
            Unit(r, "U-ISW-3", !IsWitness(6, 5), B(IsWitness(6, 5)));
            Unit(r, "U-ISW-4", !IsWitness(NoGame, NoGame), B(IsWitness(NoGame, NoGame)));

            // Spawn seed
            Unit(r, "U-SPAWN-1", SpawnSeedGame(true, 4, 3) == 4, I(SpawnSeedGame(true, 4, 3)));
            Unit(r, "U-SPAWN-2", SpawnSeedGame(true, NoGame, 3) == 1, I(SpawnSeedGame(true, NoGame, 3)));
            Unit(r, "U-SPAWN-3", SpawnSeedGame(false, 4, 3) == 3, I(SpawnSeedGame(false, 4, 3)));

            // DriftGate
            {
                const int key = 987561;
                string ok = AdvertValue(key), foreign = AdvertValue(654704);
                bool g1 = DriftGate(ok, new[] { ok, ok }, key);
                Unit(r, "U-GATE-1", g1, B(g1));
                bool g2 = DriftGate(null, new[] { ok, ok }, key);
                Unit(r, "U-GATE-2", !g2, B(g2));
                bool g3 = DriftGate(ok, new[] { ok, null }, key);
                Unit(r, "U-GATE-3", !g3, B(g3));
                bool g4 = DriftGate(ok, new[] { ok, foreign }, key);
                Unit(r, "U-GATE-4", !g4, B(g4));
                bool g5 = DriftGate(foreign, new[] { ok, ok }, key);
                Unit(r, "U-GATE-5", !g5, B(g5));
            }

            // Keys and adverts
            Unit(r, "U-KEY-1", RoomKey("") == 136261, I(RoomKey("")));
            Unit(r, "U-KEY-2", RoomKey("ffa_1") == 654704, I(RoomKey("ffa_1")));
            Unit(r, "U-KEY-3", RoomKey("ffa_2") == 987561, I(RoomKey("ffa_2")));
            Unit(r, "U-KEY-4", StagedAdvertKey("ffa_2", "") == 987561, I(StagedAdvertKey("ffa_2", "")));
            {
                string a1 = AdvertAtJoin("ffa_2", 987561, "ffa_2");
                Unit(r, "U-ADV-1", a1 == "1:987561", a1);
                string a2 = AdvertAtJoin("ffa_1", 654704, "ffa_2");
                Unit(r, "U-ADV-2", a2 == null, a2);
                string a3 = AdvertAtJoin(null, NoGame, "ffa_2");
                Unit(r, "U-ADV-3", a3 == null, a3);
                string a4 = AdvertAtJoin("ffa_2", 987561, null);
                Unit(r, "U-ADV-4", a4 == null, a4);
                string s1 = SpectatorAdvertTarget("ffa_2", "ffa_2");
                Unit(r, "U-SPEC-1", s1 == "ffa_2", s1);
                string s2 = SpectatorAdvertTarget("ffa_2", "ffa_3");
                Unit(r, "U-SPEC-2", s2 == null, s2);
            }

            // LiveCycle(g, resultPresent, deadlineKnown, deadline, now)
            Unit(r, "U-LIVE-1", LiveCycle(4, false, false, 0f, 100f), B(LiveCycle(4, false, false, 0f, 100f)));
            Unit(r, "U-LIVE-2", !LiveCycle(4, true, false, 0f, 100f), B(LiveCycle(4, true, false, 0f, 100f)));
            Unit(r, "U-LIVE-3", !LiveCycle(4, false, true, 84f, 100f), B(LiveCycle(4, false, true, 84f, 100f)));
            Unit(r, "U-LIVE-4", LiveCycle(4, false, true, 86f, 100f), B(LiveCycle(4, false, true, 86f, 100f)));
            Unit(r, "U-LIVE-5", !LiveCycle(0, false, false, 0f, 100f), B(LiveCycle(0, false, false, 0f, 100f)));

            // PickIdentitySource(gate, roomGame, followHost, acquired, live, counter), counter 3
            Unit(r, "U-PICK-1", PickIdentitySource(false, 4, false, 5, 6, 3) == 3, I(PickIdentitySource(false, 4, false, 5, 6, 3)));
            Unit(r, "U-PICK-2", PickIdentitySource(true, 4, false, NoGame, NoGame, 3) == 4, I(PickIdentitySource(true, 4, false, NoGame, NoGame, 3)));
            Unit(r, "U-PICK-3", PickIdentitySource(true, NoGame, false, 5, NoGame, 3) == 5, I(PickIdentitySource(true, NoGame, false, 5, NoGame, 3)));
            Unit(r, "U-PICK-4", PickIdentitySource(true, NoGame, false, NoGame, 6, 3) == 6, I(PickIdentitySource(true, NoGame, false, NoGame, 6, 3)));
            Unit(r, "U-PICK-5", PickIdentitySource(true, NoGame, false, NoGame, NoGame, 3) == NoGame, I(PickIdentitySource(true, NoGame, false, NoGame, NoGame, 3)));
            Unit(r, "U-PICK-6", PickIdentitySource(true, 4, true, NoGame, 1, 3) == 1, I(PickIdentitySource(true, 4, true, NoGame, 1, 3)));
            Unit(r, "U-PICK-7", PickIdentitySource(true, 4, true, NoGame, NoGame, 3) == NoGame, I(PickIdentitySource(true, 4, true, NoGame, NoGame, 3)));

            // FollowsHost(isMaster, masterPresent, masterWitness, roomGame)
            Unit(r, "U-FOL-1", FollowsHost(false, true, NoGame, 2), B(FollowsHost(false, true, NoGame, 2)));
            Unit(r, "U-FOL-2", !FollowsHost(false, true, 2, 2), B(FollowsHost(false, true, 2, 2)));
            Unit(r, "U-FOL-3", !FollowsHost(false, false, NoGame, 2), B(FollowsHost(false, false, NoGame, 2)));
            Unit(r, "U-FOL-4", !FollowsHost(true, true, NoGame, 2), B(FollowsHost(true, true, NoGame, 2)));
            Unit(r, "U-FOL-5", !FollowsHost(false, true, NoGame, NoGame), B(FollowsHost(false, true, NoGame, NoGame)));

            // MasterOpenerGame
            {
                int c;
                int g1 = MasterOpenerGame(true, 4, 3, out c);
                Unit(r, "U-OPEN-1", g1 == 1 && c == 1, I(g1) + ":" + I(c));
                int g2 = MasterOpenerGame(false, 4, 3, out c);
                Unit(r, "U-OPEN-2", g2 == 4 && c == 4, I(g2) + ":" + I(c));
                int g3 = MasterOpenerGame(false, NoGame, NoGame, out c);
                Unit(r, "U-OPEN-3", g3 == 1 && c == 1, I(g3) + ":" + I(c));
            }

            // LivePointsGame(gate, roomGame, candidate, held, counter), counter 3
            Unit(r, "U-LP-1", LivePointsGame(true, 4, 1, true, 3) == 4, I(LivePointsGame(true, 4, 1, true, 3)));
            Unit(r, "U-LP-2", LivePointsGame(true, NoGame, 1, true, 3) == 1, I(LivePointsGame(true, NoGame, 1, true, 3)));
            Unit(r, "U-LP-3", LivePointsGame(false, NoGame, 1, false, 3) == 1, I(LivePointsGame(false, NoGame, 1, false, 3)));
            Unit(r, "U-LP-4", LivePointsGame(true, NoGame, 1, false, 3) == 1, I(LivePointsGame(true, NoGame, 1, false, 3)));
            Unit(r, "U-LP-5", LivePointsGame(true, NoGame, NoGame, false, 3) == NoGame, I(LivePointsGame(true, NoGame, NoGame, false, 3)));

            // StartSeedGame(gate, roomGame, counter)
            Unit(r, "U-SEED-1", StartSeedGame(false, 4, 3) == 3, I(StartSeedGame(false, 4, 3)));
            Unit(r, "U-SEED-2", StartSeedGame(true, 4, 3) == 4, I(StartSeedGame(true, 4, 3)));
            Unit(r, "U-SEED-3", StartSeedGame(true, NoGame, 3) == NoGame, I(StartSeedGame(true, NoGame, 3)));

            // Leaver stamp
            Unit(r, "U-LB-1", LeaverStampSource(7, 5) == 7, I(LeaverStampSource(7, 5)));
            Unit(r, "U-LB-2", LeaverStampSource(6, 6) == 6, I(LeaverStampSource(6, 6)));
            Unit(r, "U-LEFT-1", LeftInGame(7, 7), B(LeftInGame(7, 7)));
            Unit(r, "U-LEFT-2", !LeftInGame(5, 7), B(LeftInGame(5, 7)));
        }

        // SITTING-MODEL-BEGIN
        internal static class SittingModel
        {
            internal static void RunAll(SelfTestResult r) { }
        }
        // SITTING-MODEL-END
    }
}
