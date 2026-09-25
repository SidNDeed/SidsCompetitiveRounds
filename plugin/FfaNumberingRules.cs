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
        /// host's value; it never supplies one. N1 is ungated: the gate is
        /// not read here, and the froze line prints G itself (V4:L1244,
        /// "held=master|fighter|no G=0|1").</summary>
        internal static bool HeldByRoom(int candidate, bool gate, bool masterPresent, int masterGame,
                                        IList<int> fighterGames, out string verdict)
        {
            bool masterHolds = masterPresent && masterGame >= 1 && masterGame == candidate;
            bool fighterHolds = false;
            if (fighterGames != null)
                for (int i = 0; i < fighterGames.Count; i++)
                    if (fighterGames[i] >= 1 && fighterGames[i] == candidate) { fighterHolds = true; break; }
            verdict = candidate >= 1 && masterHolds ? "master" : candidate >= 1 && fighterHolds ? "fighter" : "no";
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

        // ── N19: phase-epoch provenance (change 26) ─────────────────────
        //
        // A pick phase is named by an epoch its master issues at the phase's
        // cycle write (room cr_ffa_ep = "{E}:{issuer ActorNumber}"). Picks carry
        // it (player cr_ffa_pe = "{nonce}:{E}:{g}:{c}:{card}") and the result
        // carries it in its envelope (room cr_ffa_rep = "{E}:{issuer}:{g}:{c}:
        // {entries}"). A seat collects, counts and applies only under the epoch
        // it holds, and holds only an epoch of the present master that is not
        // closed and not one it terminated, so a pick or result of any other
        // phase is never read (design V10 N19(a)-(i)).

        /// <summary>Two epochs name the same phase: both present and equal.</summary>
        internal static bool SameEpoch(string a, string b)
        {
            return a != null && a == b;
        }

        /// <summary>N19(d)/(i): a peer's pick is adoption evidence only under this
        /// phase's epoch and ahead of the phase's identity; under G only at the
        /// phase's own game and cycle, so under G no peer pick moves the master
        /// (ahead excludes its own identity).</summary>
        internal static bool EpochEvidence(bool gate, bool sameEpoch, int pickGame, int pickCycle,
                                           int phaseGame, int phaseCycle, bool ahead)
        {
            return sameEpoch && ahead && (!gate || (pickGame == phaseGame && pickCycle == phaseCycle));
        }

        /// <summary>N19(d): the manifest's owners other than the local seat, in
        /// their order. An entry that did not resolve is 0, which is never
        /// local.</summary>
        internal static List<int> OthersOf(IList<int> owners, int local)
        {
            var others = new List<int>();
            if (owners == null) return others;
            for (int i = 0; i < owners.Count; i++)
                if (owners[i] != local) others.Add(owners[i]);
            return others;
        }

        /// <summary>N19(d): the detector's quorum: every other owner, capped at
        /// 2 and at least 1. The local seat is never its own evidence.</summary>
        internal static int EvidenceQuorum(IList<int> owners, int local)
        {
            int n = OthersOf(owners, local).Count;
            return Math.Min(2, Math.Max(1, n));
        }

        /// <summary>Split a cr_ffa_ep value "{E}:{A}" at its last ':' into the
        /// epoch and the issuing ActorNumber (null when absent or not an
        /// integer). A null value gives a null epoch.</summary>
        internal static void SplitEpochField(string raw, out string epoch, out int? issuer)
        {
            epoch = null;
            issuer = null;
            if (raw == null) return;
            int i = raw.LastIndexOf(':');
            if (i < 0) { epoch = raw; return; }
            epoch = raw.Substring(0, i);
            int a;
            if (TryInt(raw.Substring(i + 1), out a)) issuer = a;
        }

        /// <summary>N19(b)/(i): the epoch a seat may hold from the room's
        /// cr_ffa_ep, or null when it is missing, was not issued by the present
        /// master (issuer), is already closed by the cached envelope (closed; rep
        /// is that envelope's epoch field) or was terminated by this process
        /// (finalized).</summary>
        internal static string LiveEpoch(string rawEp, int masterActor, string rep, ICollection<string> finalized)
        {
            string e;
            int? issuer;
            SplitEpochField(rawEp, out e, out issuer);
            if (string.IsNullOrEmpty(e)) return null;
            if (!issuer.HasValue || issuer.Value != masterActor) return null;
            if (e == rep) return null;
            if (finalized != null && finalized.Contains(e)) return null;
            return e;
        }

        /// <summary>N19(i): the epoch held after an evaluation is the live value,
        /// so a refused or departed epoch clears the hold.</summary>
        internal static string HeldEpoch(string pe, string live)
        {
            return live;
        }

        /// <summary>N19(i), the use-site check: the held epoch is usable only
        /// while its issuer is the present master (-1: none).</summary>
        internal static string EpochAtUse(string pe, int issuer, int masterActor)
        {
            return issuer == masterActor ? pe : null;
        }

        /// <summary>N19(i): the result a seat may apply, read from the envelope
        /// "{E}:{A}:{g}:{c}:{entries}" only: E must be this seat's epoch, A the
        /// present master and g:c this phase's identity; else null. An empty
        /// entry list is an empty result. cr_ffa_res is never read.</summary>
        internal static Dictionary<int, string> ResultFromEnvelope(string rawRep, string pe, int masterActor,
                                                                  int game, int cycle)
        {
            if (rawRep == null) return null;
            var parts = rawRep.Split(new[] { ':' }, 5);
            if (parts.Length != 5) return null;
            string e = parts[0];
            if (string.IsNullOrEmpty(e) || IsIntegerText(e)) return null;
            if (!SameEpoch(e, pe)) return null;
            int issuer, g, c;
            if (!TryInt(parts[1], out issuer) || !TryInt(parts[2], out g) || !TryInt(parts[3], out c)) return null;
            if (issuer != masterActor) return null;
            if (g != game || c != cycle) return null;
            var result = new Dictionary<int, string>();
            if (parts[4].Length > 0)
            {
                foreach (var pair in parts[4].Split('|'))
                {
                    int eq = pair.IndexOf('=');
                    if (eq <= 0) continue;
                    int pid;
                    if (TryInt(pair.Substring(0, eq), out pid)) result[pid] = pair.Substring(eq + 1);
                }
            }
            return result;
        }

        /// <summary>N19(i), the promotion reissue's refusal test: the envelope
        /// names game:cycle, whatever its epoch and issuer.</summary>
        internal static bool EnvelopeNames(string rawRep, int game, int cycle)
        {
            if (rawRep == null) return false;
            var parts = rawRep.Split(new[] { ':' }, 5);
            if (parts.Length != 5) return false;
            int g, c;
            return TryInt(parts[2], out g) && TryInt(parts[3], out c) && g == game && c == cycle;
        }

        /// <summary>N19(g): a phase that held an epoch records it as terminated at
        /// every exit, an empty result and a bail included.</summary>
        internal static bool FinalizesAtTermination(string pe, int applied)
        {
            return pe != null;
        }

        /// <summary>N19(c): the value this build writes to the legacy pick key.
        /// It is always empty, so a current-build master never counts or
        /// collects a pick of this build.</summary>
        internal static string LegacyPickValue(string nonce, int game, int cycle, string card)
        {
            return "";
        }

        /// <summary>N19(c): the epoch-carrying pick, cr_ffa_pe.</summary>
        internal static string PickValue(string nonce, string epoch, int game, int cycle, string card)
        {
            return nonce + ":" + epoch + ":" + game.ToString(CultureInfo.InvariantCulture) + ":"
                   + cycle.ToString(CultureInfo.InvariantCulture) + ":" + card;
        }

        /// <summary>A parsed cr_ffa_pe value.</summary>
        internal sealed class ParsedPick
        {
            internal string Epoch;
            internal int Game, Cycle;
            internal string Card;
        }

        /// <summary>N19(c): a cr_ffa_pe value of this room, or null: another
        /// room, empty, the legacy shape (no epoch) or malformed.</summary>
        internal static ParsedPick ParsePick(string value, string nonce)
        {
            if (value == null || nonce == null) return null;
            string prefix = nonce + ":";
            if (!value.StartsWith(prefix, StringComparison.Ordinal)) return null;
            var parts = value.Substring(prefix.Length).Split(new[] { ':' }, 4);
            if (parts.Length != 4) return null;
            if (parts[0].Length == 0 || IsIntegerText(parts[0])) return null;
            int g, c;
            if (!TryInt(parts[1], out g) || !TryInt(parts[2], out c)) return null;
            if (parts[3].Length == 0) return null;
            return new ParsedPick { Epoch = parts[0], Game = g, Cycle = c, Card = parts[3] };
        }

        /// <summary>N19(a): a fresh phase epoch. No two phases share one.</summary>
        internal static string NewEpoch()
        {
            return Guid.NewGuid().ToString("N");
        }

        private static bool TryInt(string s, out int v)
        {
            return int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out v);
        }

        private static bool IsIntegerText(string s)
        {
            int v;
            return TryInt(s, out v);
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

        /// <summary>Why LiveEpoch refused a cr_ffa_ep value, for the log only:
        /// missing, issuer, closed or finalized; null when it did not refuse.</summary>
        internal static string EpochRefusal(string rawEp, int masterActor, string rep, ICollection<string> finalized)
        {
            string e;
            int? issuer;
            SplitEpochField(rawEp, out e, out issuer);
            if (string.IsNullOrEmpty(e)) return "missing";
            if (!issuer.HasValue || issuer.Value != masterActor) return "issuer";
            if (e == rep) return "closed";
            if (finalized != null && finalized.Contains(e)) return "finalized";
            return null;
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
        /// <summary>RJ-DRIFT V4 section 5: the walk model. Pure C#. It calls the
        /// production rule functions above, and FfaReportRules' GameKeySnapshot
        /// and ElectReporter, at the sites where FfaMode and GameStateWatcher
        /// call them, and re-implements none of them (#391). Photon is modelled
        /// as one FIFO queue per sender and receiver, each with its own stall
        /// switch (#428): a seat sees its own room and player property writes
        /// only when they echo back, and a pre-join stage merges locally. PUN's
        /// fresh Room object per entry is a fresh token per entry, compared by
        /// reference. Every walk states its expected values before it runs; each
        /// walk case prints its per-seat start and freeze lines as TRACE lines,
        /// then one verdict line, "PASS walk-Dx Wy | ..." or "FAIL walk-Dx Wy |
        /// ...". A walk that differs from V4's prose says so where it is scripted.</summary>
        internal static class SittingModel
        {
            private const string KCyc = "cr_ffa_cyc", KRes = "cr_ffa_res", KDl = "cr_ffa_dl", KSeq = "cr_ffa_seq";
            private const string KGw = "cr_ffa_gw", KRg = "cr_ffa_rg", KPick = "cr_ffa_pk";
            private const double TickS = 0.5, LatencyS = 0.2, RoundS = 20.0, BetweenGamesS = 10.0;

            internal static void RunAll(SelfTestResult r)
            {
                Walks.Run(r);
            }

            private sealed class Cyc
            {
                internal int G, C;
                internal List<int> Ids;
            }

            private static int ParseInt(string s, out bool ok)
            {
                int v;
                ok = int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out v);
                return v;
            }

            private static Cyc ParseCyc(string raw)
            {
                if (raw == null) return null;
                var parts = raw.Split(new[] { ':' }, 3);
                if (parts.Length != 3) return null;
                bool ok1, ok2;
                int g = ParseInt(parts[0], out ok1), c = ParseInt(parts[1], out ok2);
                if (!ok1 || !ok2) return null;
                var ids = new List<int>();
                foreach (var s in parts[2].Split(','))
                {
                    bool ok;
                    int v = ParseInt(s, out ok);
                    if (ok) ids.Add(v);
                }
                return new Cyc { G = g, C = c, Ids = ids };
            }

            private sealed class Leaver
            {
                internal string Name;
                internal int Stamp;
                internal int PointsAtLeave;
                internal int TruthPoints;
                internal int TruthGame;
            }

            private sealed class Stub
            {
                internal int GamesPlayed;
                internal readonly HashSet<int> Locked = new HashSet<int>();
            }

            private sealed class Room
            {
                internal readonly string Name;
                internal readonly bool Checked;
                internal readonly Dictionary<string, string> Props = new Dictionary<string, string>();
                internal readonly List<Seat> Present = new List<Seat>();
                internal readonly Stub Stub = new Stub();
                internal int NextActor = 1;
                internal Seat Master;
                internal bool InGame;
                internal int FieldPoints;
                internal int PhysGame;
                internal Room(string name, bool isChecked) { Name = name; Checked = isChecked; }
            }

            private sealed class Phase
            {
                internal int Stage;           // 0 manifest wait, 1 latch, 2 result, 3 done
                internal int Game, Cycle;
                internal double Start, LatchWait, Deadline, AdoptedAt, LastPublishedDl;
                internal List<int> Pickers, Manifest;
                internal string RawAtEntry, RawAtResultEntry, Nonce;
                internal bool Gate, WasMaster, IPick;
                internal int RgNow, LastGot;
            }

            private sealed class Msg
            {
                internal Seat From, To, Owner;
                internal object ToObj;
                internal double Due;
                internal bool RoomProp;
                internal string Key;
                internal object Val;
            }

            private sealed class Seat
            {
                internal readonly string Name;
                internal string Steam;
                internal bool Current, NoMod, Spectator;
                internal Room R;
                internal object Obj;
                internal int Actor;
                internal Dictionary<string, object> Local = new Dictionary<string, object>();
                internal Dictionary<string, object> Auth = new Dictionary<string, object>();
                internal Dictionary<string, string> RoomView = new Dictionary<string, string>();
                internal readonly Dictionary<Seat, Dictionary<string, object>> View =
                    new Dictionary<Seat, Dictionary<string, object>>();
                // FfaMode's statics (the pin's, for a current-build seat)
                internal int GameNumber, LocalGameSeq, CycleNumber;
                internal int RoomGame = NoGame, Carry = NoGame, TicketGame = NoGame, AcquiredGame = NoGame;
                internal object RoomGameRoom, CarryRoom, StartedInRoom, LastGameRoom, TicketRoom, AcquiredRoom,
                                FollowedRoom, GateLatchRoom;
                internal string LastGameRoomName = "";
                internal bool HeldRGAtStart, TicketAfterStart, Followed, GateLatch;
                internal string AdvertTarget;
                internal int AdvertKey = NoGame;
                internal FfaReportRules.GameKeySnapshot Snap = new FfaReportRules.GameKeySnapshot();
                internal bool FreezeByTicket, HeldAtFreeze;
                internal string HeldVerdict = "no";
                internal readonly Dictionary<string, Leaver> Leavers = new Dictionary<string, Leaver>();
                // FfaCardSequence
                internal int LatchedGame = -1;
                internal double LatchPendingSince = -1;
                internal bool LatchActive;
                // the pin's snapshot (current build)
                internal int PinFrozen = -1;
                internal Phase Ph;
                internal string PendingPick;
                // observation and script truth
                internal int FirstLatchGame = -1, FirstLatchPhys = -1;
                internal object FirstLatchObj;
                internal object LastStartObj;
                internal int LastStartPhys = -1;
                internal List<string> EdgeE;
                internal string TruthTarget;
                internal string ExpAdvert;
                internal Seat(string name, string steam) { Name = name; Steam = steam; }
            }

            /// <summary>A game's options: entry orders ('1', '2', '3' for V4's i, ii,
            /// iii), the number of points, hooks, the seats that skip the edge
            /// (P6), and a report lost in flight.</summary>
            private sealed class Opts
            {
                internal readonly Dictionary<Seat, char> Order = new Dictionary<Seat, char>();
                internal readonly HashSet<Seat> SkipEdge = new HashSet<Seat>();
                internal int Points = 4;
                internal Func<int, bool> Entries;
                internal Action<int> AfterEntries, AfterCycle, AfterPoint;
                internal Seat LostReport;
            }

            private sealed class GameRec
            {
                internal int N;
                internal int Key;
                internal readonly Dictionary<string, string> Global = new Dictionary<string, string>();
                internal readonly Dictionary<string, Dictionary<string, string>> PerSeat =
                    new Dictionary<string, Dictionary<string, string>>();
                internal readonly List<Seat> Starters = new List<Seat>();
                internal readonly Dictionary<Seat, int> StartRG = new Dictionary<Seat, int>();
                internal readonly Dictionary<Seat, bool> StartG = new Dictionary<Seat, bool>();
                internal readonly Dictionary<Seat, bool> FirstInEntry = new Dictionary<Seat, bool>();
                internal bool G1;
                internal bool StartChecked;
            }

            private sealed partial class Model
            {
                private readonly SelfTestResult _r;
                private readonly string _id;
                internal double T;
                private readonly List<Msg> _queue = new List<Msg>();
                private readonly HashSet<string> _stalled = new HashSet<string>();
                private readonly List<Seat> _seats = new List<Seat>();
                private readonly List<string> _fails = new List<string>();
                private readonly List<string> _trace = new List<string>();
                private readonly List<string> _counts = new List<string>();
                private int _nextSteam = 1001;
                private GameRec _game;

                internal Model(SelfTestResult r, string id) { _r = r; _id = id; }

                internal void Run(Action<Model> script)
                {
                    try { script(this); }
                    catch (Exception ex) { Fail("THREW " + ex.GetType().Name + ": " + ex.Message); }
                    foreach (var t in _trace) _r.Report.Append("TRACE ").Append(_id).Append(' ').Append(t).Append('\n');
                    bool ok = _fails.Count == 0;
                    if (ok) _r.Passed++; else _r.Failed++;
                    _r.Report.Append(ok ? "PASS " : "FAIL ").Append(_id).Append(" | ")
                        .Append(ok ? "LIVE-F " + string.Join(" ", _counts.ToArray()) : string.Join("; ", _fails.ToArray()))
                        .Append('\n');
                }

                private void Fail(string msg)
                {
                    if (!_fails.Contains(msg)) _fails.Add(msg);
                }

                internal Seat NewSeat(string name)
                {
                    var s = new Seat(name, _nextSteam.ToString(CultureInfo.InvariantCulture));
                    _nextSteam++;
                    _seats.Add(s);
                    return s;
                }

                internal Seat NewSeat(string name, string steam)
                {
                    var s = new Seat(name, steam);
                    _seats.Add(s);
                    return s;
                }

                internal Room NewRoom(string name) { return new Room(name, true); }
                internal Room NewHistoryRoom(string name) { return new Room(name, false); }

                // ── transport ─────────────────────────────────────────────

                private static bool IsMaster(Seat s) { return s.R != null && s.R.Master == s; }

                private void Send(Seat from, bool roomProp, string key, object val)
                {
                    foreach (var to in from.R.Present)
                        _queue.Add(new Msg { From = from, To = to, Owner = from, ToObj = to.Obj, Due = T + LatencyS,
                                             RoomProp = roomProp, Key = key, Val = val });
                }

                private bool WriteRoom(Seat s, string key, string val)
                {
                    if (s.R == null) return false;
                    if (val == null) s.R.Props.Remove(key); else s.R.Props[key] = val;
                    Send(s, true, key, val);
                    return true;
                }

                private void WriteOwn(Seat s, string key, object val)
                {
                    if (s.R == null) { Merge(s.Local, key, val); return; }
                    Merge(s.Auth, key, val);
                    Send(s, false, key, val);
                }

                private static void Merge(Dictionary<string, object> d, string key, object val)
                {
                    if (val == null) d.Remove(key); else d[key] = val;
                }

                private void Deliver()
                {
                    var blocked = new HashSet<string>();
                    int i = 0;
                    while (i < _queue.Count)
                    {
                        var m = _queue[i];
                        string link = m.From.Name + ">" + m.To.Name;
                        if (m.Due > T + 1e-9 || _stalled.Contains(link) || blocked.Contains(link))
                        {
                            blocked.Add(link);
                            i++;
                            continue;
                        }
                        _queue.RemoveAt(i);
                        if (m.To.Obj == null || !ReferenceEquals(m.To.Obj, m.ToObj)) continue;
                        if (m.RoomProp)
                        {
                            if (m.Val == null) m.To.RoomView.Remove(m.Key); else m.To.RoomView[m.Key] = (string)m.Val;
                        }
                        else if (m.Owner == m.To) Merge(m.To.Local, m.Key, m.Val);
                        else
                        {
                            Dictionary<string, object> v;
                            if (m.To.View.TryGetValue(m.Owner, out v)) Merge(v, m.Key, m.Val);
                        }
                    }
                }

                internal void Stall(Seat from, Seat to) { _stalled.Add(from.Name + ">" + to.Name); }
                internal void Unstall(Seat from, Seat to) { _stalled.Remove(from.Name + ">" + to.Name); }
                internal void StallInbound(Seat to) { foreach (var p in _seats) _stalled.Add(p.Name + ">" + to.Name); }
                internal void UnstallInbound(Seat to) { foreach (var p in _seats) _stalled.Remove(p.Name + ">" + to.Name); }

                internal void Advance(double seconds)
                {
                    int n = (int)Math.Round(seconds / TickS);
                    for (int i = 0; i < n; i++) TickOnce();
                }

                private void TickOnce()
                {
                    T += TickS;
                    Deliver();
                    for (int i = 0; i < _seats.Count; i++)
                    {
                        var s = _seats[i];
                        if (s.R != null && s.Ph != null && s.Ph.Stage != 3) StepPhase(s);
                    }
                }

                private void RunPhases()
                {
                    for (int i = 0; i < 1200; i++)
                    {
                        bool any = false;
                        foreach (var s in _seats) if (s.R != null && s.Ph != null && s.Ph.Stage != 3) any = true;
                        if (!any) return;
                        TickOnce();
                    }
                    throw new InvalidOperationException("a pick phase did not end");
                }

                // ── property reads ────────────────────────────────────────

                private static Dictionary<string, object> PropsOf(Seat s, Seat p)
                {
                    if (p == s) return s.Local;
                    Dictionary<string, object> v;
                    return s.View.TryGetValue(p, out v) ? v : null;
                }

                private static int WitnessOf(Seat s, Seat p)
                {
                    var props = PropsOf(s, p);
                    object o;
                    return props != null && props.TryGetValue(KGw, out o) && o is int ? (int)o : -1;
                }

                private static string StrProp(Seat s, Seat p, string key)
                {
                    var props = PropsOf(s, p);
                    object o;
                    return props != null && props.TryGetValue(key, out o) ? o as string : null;
                }

                private static string Raw(Seat s, string key)
                {
                    string v;
                    return s.RoomView.TryGetValue(key, out v) ? v : null;
                }

                private static int PublishedGameNumber(Seat s)
                {
                    var c = ParseCyc(Raw(s, KCyc));
                    return c != null ? c.G : -1;
                }

                private static List<Seat> Fighters(Room room)
                {
                    var l = new List<Seat>();
                    foreach (var p in room.Present) if (!p.Spectator && !p.NoMod) l.Add(p);
                    l.Sort((a, b) => a.Actor.CompareTo(b.Actor));
                    return l;
                }

                /// <summary>RoomActors.ActiveFighters: every present non-spectator,
                /// a seat without the mod included.</summary>
                private static List<Seat> ActiveFighters(Seat s)
                {
                    var l = new List<Seat>();
                    foreach (var p in s.R.Present) if (!p.Spectator) l.Add(p);
                    return l;
                }

                private static Seat ByActor(Room room, int actor)
                {
                    foreach (var p in room.Present) if (p.Actor == actor) return p;
                    return null;
                }

                // ── membership ────────────────────────────────────────────

                /// <summary>A join through one of the plugin's paths: "ready" records
                /// its target (change 11), "spectator" records
                /// SpectatorAdvertTarget(pending, join) (change 20), "pending" (a
                /// rejoin through the pending room) records nothing. The pre-join
                /// fence then stages the witness void and the advert (change 16)
                /// unless the walk scripts it refused (P15). A current-build seat
                /// stages nothing.</summary>
                internal void Join(Seat s, Room room, string path, bool refuseStage)
                {
                    if (s.R != null) throw new InvalidOperationException(s.Name + " joins while in a room");
                    if (!s.Current && !s.NoMod)
                    {
                        if (path == "ready") { RecordAdvertTarget(s, room.Name); s.TruthTarget = room.Name; }
                        else if (path == "spectator")
                        {
                            RecordAdvertTarget(s, SpectatorAdvertTarget(room.Name, room.Name));
                            s.TruthTarget = room.Name;
                        }
                        if (!refuseStage)
                        {
                            StageJoinNumbering(s, room.Name);
                            s.ExpAdvert = s.TruthTarget == room.Name ? AdvertValue(RoomKey(room.Name)) : null;
                        }
                    }
                    s.R = room;
                    s.Obj = new object();
                    s.Actor = room.NextActor++;
                    s.Auth = new Dictionary<string, object>(s.Local);
                    s.RoomView = new Dictionary<string, string>(room.Props);
                    s.View.Clear();
                    foreach (var p in room.Present)
                    {
                        s.View[p] = new Dictionary<string, object>(p.Auth);
                        p.View[s] = new Dictionary<string, object>(s.Auth);
                    }
                    room.Present.Add(s);
                    if (room.Master == null) room.Master = s;
                }

                internal void Join(Seat s, Room room, string path) { Join(s, room, path, false); }

                internal void JoinAll(Room room, params Seat[] seats)
                {
                    foreach (var s in seats) Join(s, room, "ready", false);
                    Advance(1.0);
                }

                private void RemoveFromRoom(Seat s)
                {
                    var room = s.R;
                    room.Present.Remove(s);
                    foreach (var p in room.Present) p.View.Remove(s);
                    s.R = null;
                    s.Obj = null;
                    s.Ph = null;
                    s.View.Clear();
                    s.RoomView = new Dictionary<string, string>();
                    if (room.InGame && !s.Spectator && !s.NoMod)
                        foreach (var p in room.Present)
                            if (!p.Spectator && !p.NoMod) RecordLeaver(p, s, room);
                    if (room.Master == s) SwitchMaster(room);
                }

                /// <summary>Photon passes the role to the lowest actor; a spectator
                /// that receives it hands it to the lowest fighter (Plugin.cs:4248).
                /// Every seat's OnMasterClientSwitched clears its ticket (change 3).</summary>
                private void SwitchMaster(Room room)
                {
                    Seat low = null;
                    foreach (var p in room.Present) if (low == null || p.Actor < low.Actor) low = p;
                    room.Master = low;
                    NotifySwitch(room);
                    if (low != null && low.Spectator)
                    {
                        Seat f = null;
                        foreach (var p in room.Present)
                            if (!p.Spectator && !p.NoMod && (f == null || p.Actor < f.Actor)) f = p;
                        if (f != null) { room.Master = f; NotifySwitch(room); }
                    }
                }

                private static void NotifySwitch(Room room)
                {
                    foreach (var p in room.Present) if (!p.Current && !p.NoMod) ClearTicket(p);
                }

                /// <summary>An ordinary leave or a drop: the seat leaves, then its
                /// poll runs OnRoomLeft.</summary>
                internal void Leave(Seat s) { RemoveFromRoom(s); OnRoomLeft(s); }

                /// <summary>A fast same-name re-entry's leave: OnRoomLeft never runs (M5).</summary>
                internal void FastLeave(Seat s) { RemoveFromRoom(s); }

                /// <summary>A relaunch: the process ends; a fresh one holds nothing.</summary>
                internal void Relaunch(Seat s)
                {
                    if (s.R != null) RemoveFromRoom(s);
                    s.Local = new Dictionary<string, object>();
                    s.Auth = new Dictionary<string, object>();
                    s.GameNumber = 0; s.LocalGameSeq = 0; s.CycleNumber = 0;
                    s.RoomGame = NoGame; s.Carry = NoGame; s.TicketGame = NoGame; s.AcquiredGame = NoGame;
                    s.RoomGameRoom = null; s.CarryRoom = null; s.StartedInRoom = null; s.LastGameRoom = null;
                    s.TicketRoom = null; s.AcquiredRoom = null; s.FollowedRoom = null; s.GateLatchRoom = null;
                    s.LastGameRoomName = "";
                    s.HeldRGAtStart = false; s.TicketAfterStart = false; s.Followed = false; s.GateLatch = false;
                    s.AdvertTarget = null; s.AdvertKey = NoGame;
                    s.Snap = new FfaReportRules.GameKeySnapshot();
                    s.Leavers.Clear();
                    s.LatchedGame = -1; s.LatchPendingSince = -1; s.LatchActive = false;
                    s.PinFrozen = -1; s.PendingPick = null;
                    s.TruthTarget = null; s.ExpAdvert = null;
                }

                internal void Promote(Seat s) { s.Spectator = false; }

                // ── FfaMode's numbering state (design V4 §4) ──────────────

                private static int RoomGameOf(Seat s)
                {
                    return SameIncarnation(s.RoomGameRoom, s.Obj) ? s.RoomGame : NoGame;
                }

                private static int AcquiredHere(Seat s)
                {
                    return SameIncarnation(s.AcquiredRoom, s.Obj) ? s.AcquiredGame : NoGame;
                }

                private static void SetAcquired(Seat s, int g) { s.AcquiredGame = g; s.AcquiredRoom = s.Obj; }

                private static void ClearTicket(Seat s)
                {
                    s.TicketGame = NoGame;
                    s.TicketRoom = null;
                    s.TicketAfterStart = false;
                }

                private static void ArmTicket(Seat s, int g)
                {
                    s.TicketGame = g;
                    s.TicketRoom = s.Obj;
                    s.TicketAfterStart = true;
                }

                private static int CandidateNow(Seat s, out bool byTicket)
                {
                    bool valid = s.TicketGame >= 1 && s.TicketAfterStart && SameIncarnation(s.TicketRoom, s.Obj);
                    int cand = Candidate(valid, s.TicketGame, PublishedGameNumber(s));
                    byTicket = valid && cand == s.TicketGame;
                    return cand;
                }

                private static int MasterGameNow(Seat s, out bool present)
                {
                    if (IsMaster(s)) { present = true; return RoomGameOf(s); }
                    var m = s.R.Master;
                    present = m != null;
                    return present ? WitnessOf(s, m) : NoGame;
                }

                private static bool HeldNow(Seat s, int candidate, out string verdict)
                {
                    bool mp;
                    int mg = MasterGameNow(s, out mp);
                    var fg = new List<int>();
                    string want = AdvertValue(RoomKey(s.R.Name));
                    foreach (var p in ActiveFighters(s))
                    {
                        if (StrProp(s, p, KRg) != want) continue;
                        fg.Add(p == s ? RoomGameOf(s) : WitnessOf(s, p));
                    }
                    return HeldByRoom(candidate, GateNow(s), mp, mg, fg, out verdict);
                }

                private static bool DriftGateNow(Seat s)
                {
                    var peers = new List<string>();
                    foreach (var p in ActiveFighters(s)) if (p != s) peers.Add(StrProp(s, p, KRg));
                    return DriftGate(StrProp(s, s, KRg), peers, RoomKey(s.R.Name));
                }

                private static bool GateNow(Seat s)
                {
                    return SameIncarnation(s.GateLatchRoom, s.Obj) ? s.GateLatch : DriftGateNow(s);
                }

                private static string TakeCarry(Seat s)
                {
                    int f = s.Snap.Frozen(s.Obj);
                    int cand = s.Snap.Candidate(s.Obj);
                    int field = PublishedGameNumber(s);
                    bool mp;
                    int mg = MasterGameNow(s, out mp);
                    int c = CarryAfterGameOver(f, cand, field, mp, mg, s.HeldRGAtStart);
                    s.Carry = c;
                    s.CarryRoom = c >= 1 ? s.Obj : null;
                    bool fol = s.Followed && SameIncarnation(s.FollowedRoom, s.Obj);
                    s.Followed = false;
                    s.FollowedRoom = null;
                    return FrozeLine(f, cand, s.FreezeByTicket, s.HeldVerdict, GateNow(s), c, field, s.HeldRGAtStart, fol);
                }

                private static void RecordAdvertTarget(Seat s, string target)
                {
                    if (target == null) return;
                    s.AdvertTarget = target;
                    s.AdvertKey = StagedAdvertKey(target, s.R != null ? s.R.Name : null);
                }

                /// <summary>The fence's stage, run outside any room, so it merges into
                /// the local properties at once and rides the join.</summary>
                private static void StageJoinNumbering(Seat s, string joinTarget)
                {
                    string advert = AdvertAtJoin(s.AdvertTarget, s.AdvertKey, joinTarget);
                    Merge(s.Local, KGw, WitnessAtJoin(WitnessOf(s, s)));
                    Merge(s.Local, KRg, advert);
                }

                private bool EvaluateFollow(Seat s, bool gate, int rgNow)
                {
                    if (!gate) return false;
                    bool mp;
                    int mw = MasterGameNow(s, out mp);
                    bool f = FollowsHost(IsMaster(s), mp, mw, rgNow);
                    if (f) { s.Followed = true; s.FollowedRoom = s.Obj; }
                    return f;
                }

                private bool LiveNow(Seat s, int g, int c)
                {
                    if (g < 1) return false;
                    bool resultPresent = ReadCycleResult(s, g, c);
                    double dl;
                    bool known = TryReadDeadline(s, g, c, out dl);
                    return LiveCycle(g, resultPresent, known, (float)dl, (float)T);
                }

                private static void CardSeqReset(Seat s)
                {
                    s.LatchedGame = -1;
                    s.LatchPendingSince = -1;
                    s.LatchActive = false;
                }

                private void OnRoomLeft(Seat s)
                {
                    Merge(s.Local, KPick, "");
                    s.GameNumber = 0;
                    if (!s.Current)
                    {
                        s.LocalGameSeq = 0;
                        s.Carry = NoGame; s.CarryRoom = null;
                        ClearTicket(s);
                        s.RoomGame = NoGame; s.RoomGameRoom = null;
                        s.Followed = false; s.FollowedRoom = null;
                        s.StartedInRoom = null;
                    }
                    s.Leavers.Clear();
                    CardSeqReset(s);
                    s.Ph = null;
                    s.PendingPick = null;
                }

                private void RecordLeaver(Seat p, Seat leaver, Room room)
                {
                    int stamp = p.Current ? p.GameNumber : LeaverStampSource(p.LocalGameSeq, p.GameNumber);
                    p.Leavers[leaver.Steam] = new Leaver
                    {
                        Name = leaver.Name, Stamp = stamp, PointsAtLeave = room.FieldPoints,
                        TruthPoints = room.FieldPoints, TruthGame = room.PhysGame,
                    };
                }

                private void MasterPublishSeed(Seat s, int game)
                {
                    if (!IsMaster(s)) return;
                    WriteRoom(s, KSeq, game.ToString(CultureInfo.InvariantCulture));
                }

                /// <summary>FfaCardSequence.LatchForGame: latch the shared sequence
                /// when the seed names this game; wait up to 8 s; then fall back
                /// (latched, but not to the shared sequence).</summary>
                private void LatchForGame(Seat s, int game)
                {
                    if (s.LatchedGame == game) return;
                    s.LatchActive = false;
                    bool ok = false;
                    string raw = Raw(s, KSeq);
                    int pg = raw != null ? ParseInt(raw, out ok) : -1;
                    if (raw != null && ok && pg == game) { s.LatchPendingSince = -1; SetLatch(s, game, true); return; }
                    if (s.LatchPendingSince < 0) s.LatchPendingSince = T;
                    if (T - s.LatchPendingSince < 8.0) return;
                    s.LatchPendingSince = -1;
                    SetLatch(s, game, false);
                }

                private void SetLatch(Seat s, int game, bool active)
                {
                    s.LatchedGame = game;
                    s.LatchActive = active;
                    int phys = s.R != null ? s.R.PhysGame : -1;
                    if (s.FirstLatchPhys != phys || !ReferenceEquals(s.FirstLatchObj, s.Obj))
                    {
                        s.FirstLatchPhys = phys;
                        s.FirstLatchObj = s.Obj;
                        s.FirstLatchGame = game;
                    }
                }

                // ── the start edge ────────────────────────────────────────

                /// <summary>FfaMode.OnGameStart (the new build) or the pin's (a
                /// current-build seat), then GameStateWatcher.OnFfaMatchStarted.</summary>
                internal void StartSeat(Seat s)
                {
                    var room = s.R;
                    object prevStartObj = s.LastStartObj;
                    int rg = NoGame;
                    bool gate = false;
                    if (s.Current) StartCurrent(s);
                    else
                    {
                        StartNew(s);
                        rg = RoomGameOf(s);
                        gate = s.GateLatch;
                    }
                    s.LastStartObj = s.Obj;
                    s.LastStartPhys = room.PhysGame;
                    if (room.Checked && _game != null)
                    {
                        _game.Starters.Add(s);
                        _game.StartRG[s] = rg;
                        _game.StartG[s] = gate;
                        _game.FirstInEntry[s] = !ReferenceEquals(prevStartObj, s.Obj);
                        if (!s.Current && _game.FirstInEntry[s] && (s.GameNumber != 1 || s.LocalGameSeq != 1))
                            Fail("RESET g" + I(room.PhysGame) + " " + s.Name + " counter " + I(s.GameNumber)
                                 + " sequence " + I(s.LocalGameSeq));
                    }
                }

                private void StartNew(Seat s)
                {
                    var room = s.R;
                    object roomObj = s.Obj;
                    ClearTicket(s);
                    if (RoomObjectChanged(s.LastGameRoom, roomObj, s.LastGameRoomName, room.Name))
                    {
                        s.GameNumber = 0;
                        s.LocalGameSeq = 0;
                        s.Leavers.Clear();
                        s.AcquiredGame = NoGame;
                        s.AcquiredRoom = null;
                        s.LastGameRoom = roomObj;
                        s.LastGameRoomName = room.Name;
                    }
                    s.AcquiredGame = NoGame;
                    s.AcquiredRoom = null;
                    s.GateLatch = DriftGateNow(s);
                    s.GateLatchRoom = roomObj;
                    bool carryHere = SameIncarnation(s.CarryRoom, roomObj);
                    bool prevHere = SameIncarnation(s.StartedInRoom, roomObj);
                    int prevRG = prevHere ? s.RoomGame : NoGame;
                    bool followedPrev = s.Followed && SameIncarnation(s.FollowedRoom, roomObj);
                    bool cycleAbsent = Raw(s, KCyc) == null;
                    int cycleGameAtStart = PublishedGameNumber(s);
                    int rg, next;
                    StartNumbers(carryHere, s.Carry, prevHere, prevRG, followedPrev, !prevHere, cycleAbsent,
                                 cycleGameAtStart, s.GateLatch, s.GameNumber, out rg, out next);
                    string src = StartSourceLabel(carryHere, s.Carry, prevHere, prevRG, followedPrev, !prevHere,
                                                  cycleAbsent, rg);
                    s.Carry = NoGame;
                    s.CarryRoom = null;
                    s.RoomGame = rg;
                    s.RoomGameRoom = roomObj;
                    s.HeldRGAtStart = rg >= 1;
                    s.StartedInRoom = roomObj;
                    s.Followed = false;
                    s.FollowedRoom = null;
                    s.GameNumber = next;
                    s.LocalGameSeq++;
                    if (room.Checked)
                        _trace.Add("g" + I(room.PhysGame) + " " + s.Name + " "
                                   + StartLine(rg, src, s.GateLatch, s.GameNumber, s.LocalGameSeq)
                                   + " field=" + cycleGameAtStart.ToString(CultureInfo.InvariantCulture));
                    s.CycleNumber = 0;
                    foreach (var kv in s.Leavers) kv.Value.PointsAtLeave = -1;
                    CardSeqReset(s);
                    int seedGame = StartSeedGame(GateNow(s), RoomGameOf(s), s.GameNumber);
                    if (seedGame >= 1) MasterPublishSeed(s, seedGame);
                    // GameStateWatcher.OnFfaMatchStarted: arm the snapshot, publish the witness.
                    s.Snap.Clear(roomObj);
                    WriteOwn(s, KGw, WitnessToPublish(RoomGameOf(s)));
                }

                /// <summary>The pin: the name test, L + 1, the counter seed, W = L.</summary>
                private void StartCurrent(Seat s)
                {
                    var room = s.R;
                    if (room.Name != s.LastGameRoomName)
                    {
                        s.GameNumber = 0;
                        s.Leavers.Clear();
                        s.LastGameRoomName = room.Name;
                    }
                    s.GameNumber++;
                    s.CycleNumber = 0;
                    foreach (var kv in s.Leavers) kv.Value.PointsAtLeave = -1;
                    CardSeqReset(s);
                    MasterPublishSeed(s, s.GameNumber);
                    s.PinFrozen = -1;
                    WriteOwn(s, KGw, s.GameNumber);
                    if (room.Checked)
                        _trace.Add("g" + I(room.PhysGame) + " " + s.Name + " [pin] start local="
                                   + I(s.GameNumber) + " W=" + I(s.GameNumber));
                }
            }

            private sealed partial class Model
            {
                private int _winnerNow = -1;

                // ── the pick phase (FfaMode.FfaPickPhase) ─────────────────

                private static string CycValue(int g, int c, List<int> ids)
                {
                    var sb = new StringBuilder();
                    sb.Append(I(g)).Append(':').Append(I(c)).Append(':');
                    for (int i = 0; i < ids.Count; i++) { if (i > 0) sb.Append(','); sb.Append(I(ids[i])); }
                    return sb.ToString();
                }

                private static string ResValue(int g, int c, Dictionary<int, string> got)
                {
                    var keys = new List<int>(got.Keys);
                    keys.Sort();
                    var sb = new StringBuilder();
                    sb.Append(I(g)).Append(':').Append(I(c)).Append(':');
                    for (int i = 0; i < keys.Count; i++)
                    {
                        if (i > 0) sb.Append('|');
                        sb.Append(I(keys[i])).Append('=').Append(got[keys[i]]);
                    }
                    return sb.ToString();
                }

                private static List<int> ReadCycleManifest(Seat s, int g, int c)
                {
                    var cy = ParseCyc(Raw(s, KCyc));
                    return cy != null && cy.G == g && cy.C == c ? new List<int>(cy.Ids) : null;
                }

                private static bool ReadCycleResult(Seat s, int g, int c)
                {
                    string raw = Raw(s, KRes);
                    if (raw == null) return false;
                    var parts = raw.Split(new[] { ':' }, 3);
                    if (parts.Length != 3) return false;
                    bool ok1, ok2;
                    int rg = ParseInt(parts[0], out ok1), rc = ParseInt(parts[1], out ok2);
                    return ok1 && ok2 && rg == g && rc == c;
                }

                private static bool TryReadDeadline(Seat s, int g, int c, out double dl)
                {
                    dl = 0;
                    string raw = Raw(s, KDl);
                    if (raw == null) return false;
                    var parts = raw.Split(new[] { ':' }, 3);
                    if (parts.Length != 3) return false;
                    bool ok1, ok2;
                    int rg = ParseInt(parts[0], out ok1), rc = ParseInt(parts[1], out ok2);
                    if (!ok1 || !ok2 || rg != g || rc != c) return false;
                    return double.TryParse(parts[2], NumberStyles.Float, CultureInfo.InvariantCulture, out dl);
                }

                private void PublishDeadline(Seat s, Phase ph)
                {
                    if (Math.Abs(ph.Deadline - ph.LastPublishedDl) < 0.5) return;
                    ph.LastPublishedDl = ph.Deadline;
                    WriteRoom(s, KDl, I(ph.Game) + ":" + I(ph.Cycle) + ":"
                                      + ph.Deadline.ToString("F2", CultureInfo.InvariantCulture));
                }

                internal void Enter(Seat s) { EnterPhase(s, _winnerNow); }

                private void EnterPhase(Seat s, int winnerActor)
                {
                    var room = s.R;
                    var ph = new Phase();
                    s.Ph = ph;
                    s.CycleNumber++;
                    ph.Cycle = s.CycleNumber;
                    ph.Game = s.GameNumber;
                    ph.Start = T;
                    ph.AdoptedAt = -999;
                    ph.LastPublishedDl = -1;
                    ph.Nonce = room.Name;
                    s.PendingPick = null;
                    ph.Pickers = new List<int>();
                    foreach (var p in room.Present) if (!p.Spectator && p.Actor != winnerActor) ph.Pickers.Add(p.Actor);
                    ph.Pickers.Sort();
                    ph.RawAtEntry = Raw(s, KCyc);
                    if (s.Current)
                    {
                        ph.Gate = false;
                        ph.RgNow = NoGame;
                    }
                    else
                    {
                        ph.Gate = GateNow(s);
                        ph.RgNow = RoomGameOf(s);
                        bool follow = EvaluateFollow(s, ph.Gate, ph.RgNow);
                        int acq = AcquiredHere(s);
                        var ef = ParseCyc(ph.RawAtEntry);
                        int liveGame = ef != null && LiveNow(s, ef.G, ef.C) ? ef.G : NoGame;
                        ph.Game = PickIdentitySource(ph.Gate, ph.RgNow, follow, acq, liveGame, s.GameNumber);
                        bool regime = LiveRegime(ph.Gate, ph.RgNow, follow, acq);
                        if (TakesLiveAtEntry(regime, ph.Game, liveGame))
                        {
                            ph.Cycle = ef.C;
                            s.GameNumber = ph.Game;
                            s.CycleNumber = ph.Cycle;
                            ph.Manifest = new List<int>(ef.Ids);
                            SetAcquired(s, ph.Game);
                        }
                        else if (ph.Game < 1 && IsMaster(s))
                        {
                            bool openingDraw = winnerActor < 0 && s.CycleNumber == 1;
                            int oc;
                            ph.Game = MasterOpenerGame(openingDraw, ef != null ? ef.G : NoGame, ef != null ? ef.C : 0, out oc);
                            ph.Cycle = oc;
                        }
                    }
                    if (IsMaster(s) && ph.Game >= 1
                        && WriteRoom(s, KCyc, CycValue(ph.Game, ph.Cycle, ph.Pickers)) && !s.Current)
                        ArmTicket(s, ph.Game);
                    StepPhase(s);
                }

                /// <summary>One frame of the phase coroutine: runs until it yields.</summary>
                private void StepPhase(Seat s)
                {
                    var ph = s.Ph;
                    for (int guard = 0; guard < 8 && ph != null && ph.Stage != 3; guard++)
                    {
                        if (ph.Stage == 0)
                        {
                            if (ph.Manifest == null && T - ph.Start < 8.0)
                            {
                                WaitBody(s, ph);
                                if (ph.Manifest == null) return;
                            }
                            if (ph.Manifest == null && ph.Game >= 1) ph.Manifest = new List<int>(ph.Pickers);
                            if (ph.Game >= 1)
                            {
                                MasterPublishSeed(s, ph.Game);
                                ph.LatchWait = T;
                                ph.Stage = 1;
                            }
                            else BeginResult(s, ph);
                            continue;
                        }
                        if (ph.Stage == 1)
                        {
                            LatchForGame(s, ph.Game);
                            if (s.LatchedGame == ph.Game || T - ph.LatchWait > 12.0) { BeginResult(s, ph); continue; }
                            return;
                        }
                        ResultBody(s, ph);
                        return;
                    }
                }

                private static bool Ahead(Cyc c, Phase ph)
                {
                    return c != null && ph.Game >= 1 && (c.G > ph.Game || (c.G == ph.Game && c.C > ph.Cycle));
                }

                private static void TakeField(Seat s, Phase ph, Cyc ad)
                {
                    ph.Game = ad.G;
                    ph.Cycle = ad.C;
                    s.GameNumber = ad.G;
                    s.CycleNumber = ad.C;
                    ph.Manifest = new List<int>(ad.Ids);
                }

                private void WaitBody(Seat s, Phase ph)
                {
                    if (ph.Game >= 1)
                    {
                        ph.Manifest = ReadCycleManifest(s, ph.Game, ph.Cycle);
                        if (ph.Manifest != null) return;
                    }
                    string rawNow = Raw(s, KCyc);
                    if (rawNow != null && rawNow != ph.RawAtEntry)
                    {
                        var ad = ParseCyc(rawNow);
                        if (s.Current)
                        {
                            if (Ahead(ad, ph)) { TakeField(s, ph, ad); WriteOwn(s, KGw, s.GameNumber); return; }
                        }
                        else
                        {
                            bool followNow = EvaluateFollow(s, ph.Gate, ph.RgNow);
                            bool regimeNow = LiveRegime(ph.Gate, ph.RgNow, followNow, AcquiredHere(s));
                            if (ad != null && regimeNow && LiveNow(s, ad.G, ad.C))
                            {
                                TakeField(s, ph, ad);
                                SetAcquired(s, ad.G);
                                return;
                            }
                            if (!regimeNow && Ahead(ad, ph)) { TakeField(s, ph, ad); return; }
                        }
                    }
                    if (IsMaster(s) && ph.Game >= 1 && T - ph.Start > 2.0
                        && WriteRoom(s, KCyc, CycValue(ph.Game, ph.Cycle, ph.Pickers)) && !s.Current)
                        ArmTicket(s, ph.Game);
                }

                private void BeginResult(Seat s, Phase ph)
                {
                    ph.IPick = ph.Game >= 1 && ph.Manifest != null && ph.Manifest.Contains(s.Actor);
                    if (ph.IPick)
                    {
                        s.PendingPick = "c" + s.Name + I(ph.Cycle);
                        WriteOwn(s, KPick, ph.Nonce + ":" + I(ph.Game) + ":" + I(ph.Cycle) + ":" + s.PendingPick);
                    }
                    ph.Deadline = ph.Start + 45.0;
                    ph.AdoptedAt = -999;
                    ph.LastGot = 0;
                    ph.WasMaster = IsMaster(s);
                    if (ph.WasMaster) PublishDeadline(s, ph);
                    ph.RawAtResultEntry = Raw(s, KCyc);
                    ph.Stage = 2;
                    if (IsMaster(s))
                    {
                        var pre = DetectAhead(s, ph);
                        if (pre != null) Adopt(s, ph, pre.G, pre.C, null, true, null);
                    }
                }

                private void ResultBody(Seat s, Phase ph)
                {
                    if (ph.Game >= 1 && ReadCycleResult(s, ph.Game, ph.Cycle)) { ph.Stage = 3; return; }
                    double now = T;
                    if (IsMaster(s))
                    {
                        var ahead = DetectAhead(s, ph);
                        if (ahead != null) Adopt(s, ph, ahead.G, ahead.C, null, true, null);
                    }
                    else
                    {
                        string rawNow = Raw(s, KCyc);
                        var np = rawNow != ph.RawAtResultEntry ? ParseCyc(rawNow) : null;
                        if (s.Current)
                        {
                            if (Ahead(np, ph)) Adopt(s, ph, np.G, np.C, np.Ids, false, rawNow);
                        }
                        else
                        {
                            bool followNow = np != null && EvaluateFollow(s, ph.Gate, ph.RgNow);
                            bool regimeNow = np != null && LiveRegime(ph.Gate, ph.RgNow, followNow, AcquiredHere(s));
                            if (regimeNow && LiveNow(s, np.G, np.C))
                            {
                                SetAcquired(s, np.G);
                                Adopt(s, ph, np.G, np.C, np.Ids, false, rawNow);
                            }
                            else if (np != null && !regimeNow && Ahead(np, ph)) Adopt(s, ph, np.G, np.C, np.Ids, false, rawNow);
                        }
                    }
                    var got = ph.Game >= 1 && ph.Manifest != null ? CollectPicks(s, ph) : new Dictionary<int, string>();
                    if (got.Count > ph.LastGot)
                    {
                        ph.LastGot = got.Count;
                        ph.Deadline = Math.Max(ph.Deadline, Math.Min(ph.Start + 90.0, now + 20.0));
                    }
                    if (IsMaster(s) && !ph.WasMaster)
                    {
                        ph.WasMaster = true;
                        ph.Deadline = Math.Max(ph.Deadline, now + 20.0);
                    }
                    if (IsMaster(s)) PublishDeadline(s, ph);
                    else
                    {
                        double sh;
                        if (ph.Game >= 1 && TryReadDeadline(s, ph.Game, ph.Cycle, out sh) && sh > 0) ph.Deadline = sh;
                    }
                    if (IsMaster(s))
                    {
                        bool allIn = got.Count >= CountStillPresent(s, ph.Manifest);
                        bool settling = !allIn && (now - ph.AdoptedAt) < 20.0;
                        if (settling)
                        {
                            ph.Deadline = Math.Max(ph.Deadline, ph.AdoptedAt + 20.0);
                            PublishDeadline(s, ph);
                        }
                        if (allIn || (now > ph.Deadline && !settling))
                        {
                            WriteRoom(s, KRes, ResValue(ph.Game, ph.Cycle, got));
                            OnResultWritten(s, ph);
                            ph.Stage = 3;
                            return;
                        }
                    }
                    if (now > ph.Deadline + 15.0 && now - ph.Start > 20.0) ph.Stage = 3;
                }

                private void Adopt(Seat s, Phase ph, int g, int c, List<int> manifest, bool asMaster, string observedRaw)
                {
                    ph.Game = g;
                    ph.Cycle = c;
                    s.GameNumber = g;
                    s.CycleNumber = c;
                    if (manifest != null) ph.Manifest = new List<int>(manifest);
                    if (asMaster)
                    {
                        ph.Manifest = new List<int>(ph.Pickers);
                        if (WriteRoom(s, KCyc, CycValue(g, c, ph.Pickers)) && !s.Current) ArmTicket(s, g);
                    }
                    if (s.PendingPick != null)
                        WriteOwn(s, KPick, ph.Nonce + ":" + I(g) + ":" + I(c) + ":" + s.PendingPick);
                    ph.AdoptedAt = T;
                    ph.LastGot = 0;
                    ph.LastPublishedDl = -1;
                    if (observedRaw != null) ph.RawAtResultEntry = observedRaw;
                    if (s.Current) WriteOwn(s, KGw, s.GameNumber);   // the pin's witness re-stamp
                    if (s.R != null && s.R.Checked)
                        _trace.Add("g" + I(s.R.PhysGame) + " " + s.Name + " adopt " + I(g) + ":" + I(c)
                                   + (asMaster ? " as master (pick evidence)" : " (field change)"));
                }

                private static int PickGameOf(Seat s, Seat p, string prefix, out int cycle)
                {
                    cycle = 0;
                    string v = StrProp(s, p, KPick);
                    if (v == null || !v.StartsWith(prefix, StringComparison.Ordinal)) return -1;
                    var parts = v.Substring(prefix.Length).Split(new[] { ':' }, 3);
                    if (parts.Length != 3) return -1;
                    bool ok1, ok2;
                    int g = ParseInt(parts[0], out ok1);
                    cycle = ParseInt(parts[1], out ok2);
                    return ok1 && ok2 ? g : -1;
                }

                private static Cyc DetectAhead(Seat s, Phase ph)
                {
                    if (ph.Manifest == null) return null;
                    var counts = new Dictionary<string, int>();
                    var order = new List<string>();
                    foreach (var pid in ph.Manifest)
                    {
                        var p = ByActor(s.R, pid);
                        if (p == null) continue;
                        int c;
                        int g = PickGameOf(s, p, ph.Nonce + ":", out c);
                        if (g < 0) continue;
                        if (g > ph.Game || (g == ph.Game && c > ph.Cycle))
                        {
                            string key = I(g) + ":" + I(c);
                            int n;
                            counts[key] = (counts.TryGetValue(key, out n) ? n : 0) + 1;
                            if (!order.Contains(key)) order.Add(key);
                        }
                    }
                    int quorum = Math.Min(2, Math.Max(1, ph.Manifest.Count - 1));
                    foreach (var key in order)
                        if (counts[key] >= quorum) return ParseCyc(key + ":");
                    return null;
                }

                private static Dictionary<int, string> CollectPicks(Seat s, Phase ph)
                {
                    var got = new Dictionary<int, string>();
                    string prefix = ph.Nonce + ":" + I(ph.Game) + ":" + I(ph.Cycle) + ":";
                    foreach (var pid in ph.Manifest)
                    {
                        var p = ByActor(s.R, pid);
                        if (p == null) continue;
                        string v = StrProp(s, p, KPick);
                        if (v != null && v.StartsWith(prefix, StringComparison.Ordinal) && v.Length > prefix.Length)
                            got[pid] = v.Substring(prefix.Length);
                    }
                    return got;
                }

                private static int CountStillPresent(Seat s, List<int> manifest)
                {
                    int n = 0;
                    if (manifest != null) foreach (var pid in manifest) if (ByActor(s.R, pid) != null) n++;
                    return n;
                }

                // ── the game: starts, cycles, points, edge ────────────────

                private static char Ord(Opts o, Seat s)
                {
                    char ch;
                    return o != null && o.Order.TryGetValue(s, out ch) ? ch : '3';
                }

                private static Seat WinnerOf(Room room)
                {
                    var m = room.Master;
                    if (m != null && !m.Spectator && !m.NoMod) return m;
                    var f = Fighters(room);
                    return f.Count > 0 ? f[0] : null;
                }

                private void BeginGame(Room room, string spec)
                {
                    room.PhysGame++;
                    room.InGame = true;
                    room.FieldPoints = 0;
                    if (room.Checked) _game = ParseSpec(room.PhysGame, spec);
                }

                /// <summary>One game: the start edges, the cycles and their points
                /// (a pick phase, then a round won by the master), and the edge.</summary>
                internal void Play(Room room, string spec, Opts o)
                {
                    BeginGame(room, spec);
                    foreach (var s in Fighters(room)) if (Ord(o, s) != '1') StartSeat(s);
                    int points = o != null ? o.Points : 4;
                    int winner = -1;
                    for (int c = 1; c <= points; c++)
                    {
                        Cycle(room, c, winner, o);
                        if (o != null && o.AfterCycle != null) o.AfterCycle(c);
                        var w = WinnerOf(room);
                        winner = w != null ? w.Actor : -1;
                        PointAt(room);
                        if (o != null && o.AfterPoint != null) o.AfterPoint(c);
                    }
                    Edge(room, o);
                    Advance(BetweenGamesS);
                }

                internal void Play(Room room, string spec) { Play(room, spec, null); }

                /// <summary>V4's S0: games played with every expectation at its
                /// default (key = the game, everything agrees, G 1 unless stated).</summary>
                internal void Games(Room room, int count, string spec)
                {
                    for (int i = 0; i < count; i++) Play(room, spec, null);
                }

                /// <summary>A walk's last game when V4 states only its start: the
                /// start edges and their checks, no play.</summary>
                internal void StartOnly(Room room, string spec)
                {
                    BeginGame(room, spec);
                    foreach (var s in Fighters(room)) StartSeat(s);
                    StartChecks(room);
                    room.InGame = false;
                }

                private void Cycle(Room room, int c, int winnerActor, Opts o)
                {
                    _winnerNow = winnerActor;
                    bool handled = o != null && o.Entries != null && o.Entries(c);
                    if (!handled)
                    {
                        var entered = new HashSet<Seat>();
                        if (c == 1)
                            foreach (var s in Fighters(room))
                                if (Ord(o, s) == '2') { EnterPhase(s, winnerActor); entered.Add(s); }
                        var master = room.Master;
                        if (master != null && !master.Spectator && !master.NoMod && !entered.Contains(master))
                        {
                            EnterPhase(master, winnerActor);
                            entered.Add(master);
                        }
                        TickOnce();
                        if (c == 1)
                            foreach (var s in Fighters(room))
                                if (Ord(o, s) == '1') StartSeat(s);
                        foreach (var s in Fighters(room))
                            if (!entered.Contains(s)) { EnterPhase(s, winnerActor); entered.Add(s); }
                    }
                    if (c == 1) StartChecks(room);
                    if (o != null && o.AfterEntries != null) o.AfterEntries(c);
                    RunPhases();
                }

                private void PointAt(Room room)
                {
                    Advance(RoundS);
                    room.FieldPoints++;
                    var m = room.Master;
                    if (m == null || m.Spectator || m.NoMod) return;
                    int lp = m.Current ? m.GameNumber : LivePointsGameNow(m);
                    if (room.Checked && !m.Current) CheckLivePoints(room, m, lp);
                    if (lp >= 1 && room.FieldPoints >= 2) room.Stub.Locked.Add(room.Stub.GamesPlayed + 1);
                }

                private static int LivePointsGameNow(Seat m)
                {
                    int rg = RoomGameOf(m);
                    bool byTicket;
                    int cand = CandidateNow(m, out byTicket);
                    string verdict;
                    bool held = HeldNow(m, cand, out verdict);
                    return LivePointsGame(GateNow(m), rg, cand, held, m.GameNumber);
                }

                private void Edge(Room room, Opts o)
                {
                    var ran = new List<Seat>();
                    foreach (var s in Fighters(room))
                    {
                        if (o != null && o.SkipEdge.Contains(s)) continue;
                        if (s.Current) EdgeCurrent(room, s, o); else EdgeNew(room, s, o);
                        ran.Add(s);
                    }
                    room.InGame = false;
                    if (room.Checked) EdgeChecks(room, ran);
                }

                /// <summary>GameStateWatcher's FFA edge: freeze (N1), carry (N2), the
                /// electorate (N5) and the election, the report, and the body's
                /// leaver entries (N10).</summary>
                private void EdgeNew(Room room, Seat s, Opts o)
                {
                    bool byTicket;
                    int cand = CandidateNow(s, out byTicket);
                    s.FreezeByTicket = byTicket;
                    string verdict;
                    bool held = HeldNow(s, cand, out verdict);
                    s.HeldVerdict = verdict;
                    s.HeldAtFreeze = held;
                    s.Snap.Freeze(held ? cand : NoGame, cand, s.Obj);
                    string line = TakeCarry(s);
                    if (room.Checked) _trace.Add("g" + I(room.PhysGame) + " " + s.Name + " " + line);
                    int f = s.Snap.Frozen(s.Obj);
                    var present = new List<string>();
                    var witnesses = new List<string>();
                    s.EdgeE = new List<string>();
                    foreach (var p in Fighters(room))
                    {
                        present.Add(p.Steam);
                        if (IsWitness(WitnessOf(s, p), f)) { witnesses.Add(p.Steam); s.EdgeE.Add(p.Name); }
                    }
                    bool fallback;
                    string rep = FfaReportRules.ElectReporter(present, witnesses, out fallback);
                    string key = s.Snap.Key(room.Name, s.Obj);
                    if (rep == s.Steam && key != null && f >= 1 && (o == null || o.LostReport != s)) Report(room, f);
                    if (room.Checked && f >= 1) CheckLeavers(room, s);
                }

                /// <summary>The pin's edge: the readback frozen, the electorate
                /// {W >= L}, the report.</summary>
                private void EdgeCurrent(Room room, Seat s, Opts o)
                {
                    if (s.PinFrozen < 0) s.PinFrozen = PublishedGameNumber(s);
                    int f = s.PinFrozen >= 1 ? s.PinFrozen : NoGame;
                    var present = new List<string>();
                    var witnesses = new List<string>();
                    foreach (var p in Fighters(room))
                    {
                        present.Add(p.Steam);
                        if (WitnessOf(s, p) >= s.GameNumber) witnesses.Add(p.Steam);
                    }
                    bool fallback;
                    string rep = FfaReportRules.ElectReporter(present, witnesses, out fallback);
                    if (rep == s.Steam && f >= 1 && (o == null || o.LostReport != s)) Report(room, f);
                    if (room.Checked) _trace.Add("g" + I(room.PhysGame) + " " + s.Name + " [pin] froze F=" + N(f));
                }

                /// <summary>The server stub: _rk is accepted when k = games_played + 1.</summary>
                private void Report(Room room, int k)
                {
                    var st = room.Stub;
                    if (k != st.GamesPlayed + 1) return;
                    if (room.Checked && !st.Locked.Contains(k))
                        Fail("SETTLE-LOCK g" + I(room.PhysGame) + " _r" + I(k) + " accepted, game " + I(k) + " never locked");
                    st.GamesPlayed = k;
                }
            }

            private sealed partial class Model
            {
                // ── walk helpers ──────────────────────────────────────────

                internal Seat[] Abcd()
                {
                    return new[] { NewSeat("A"), NewSeat("B"), NewSeat("C"), NewSeat("D") };
                }

                internal void Tick() { TickOnce(); }

                /// <summary>V4's S0: the seats join through the ready path, then three games.</summary>
                internal void S0(Room room, string spec, params Seat[] seats)
                {
                    JoinAll(room, seats);
                    Games(room, 3, spec);
                }

                /// <summary>Games fought before this sitting in another room (solo, in
                /// an unchecked room with its own stub), left by an ordinary leave or
                /// by a teardown that missed OnRoomLeft.</summary>
                internal void FoughtElsewhere(Seat s, string roomName, int games, bool missedTeardown)
                {
                    var h = NewHistoryRoom(roomName);
                    Join(s, h, "ready", false);
                    Advance(1.0);
                    for (int i = 0; i < games; i++) Play(h, null, null);
                    if (missedTeardown) FastLeave(s); else Leave(s);
                    Advance(1.0);
                }

                // ── expectations ──────────────────────────────────────────

                /// <summary>"RG A4 B4 C- D4; F 4; CAND 4; CS A4 S1; G 0; N 2": a token
                /// that starts with a capital names one seat; any other token is
                /// the value for every fighter; N sets the game's key (default: the
                /// physical game).</summary>
                private static GameRec ParseSpec(int n, string spec)
                {
                    var g = new GameRec { N = n, Key = n };
                    if (string.IsNullOrEmpty(spec)) return g;
                    foreach (var seg in spec.Split(';'))
                    {
                        var toks = seg.Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                        if (toks.Length < 2) continue;
                        string field = toks[0];
                        if (field == "N")
                        {
                            bool ok;
                            int k = ParseInt(toks[1], out ok);
                            if (ok) g.Key = k;
                            continue;
                        }
                        for (int i = 1; i < toks.Length; i++)
                        {
                            string t = toks[i];
                            if (char.IsUpper(t[0]))
                            {
                                Dictionary<string, string> d;
                                if (!g.PerSeat.TryGetValue(field, out d))
                                {
                                    d = new Dictionary<string, string>();
                                    g.PerSeat[field] = d;
                                }
                                d[t.Substring(0, 1)] = t.Substring(1);
                            }
                            else g.Global[field] = t;
                        }
                    }
                    return g;
                }

                private static bool IsFighter(Seat s) { return !s.Spectator && !s.NoMod; }

                private string Exp(Seat s, string field, string dflt)
                {
                    Dictionary<string, string> d;
                    string v;
                    if (_game.PerSeat.TryGetValue(field, out d) && d.TryGetValue(s.Name, out v)) return v;
                    if (IsFighter(s) && _game.Global.TryGetValue(field, out v)) return v;
                    return dflt;
                }

                private static string Num(int v) { return v >= 1 ? I(v) : "-"; }

                private static List<Seat> ByName(IEnumerable<Seat> seats)
                {
                    var l = new List<Seat>(seats);
                    l.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));
                    return l;
                }

                private sealed class Miss
                {
                    internal string Seat, Obs, Exp;
                }

                private void Expected(string field, List<Miss> misses)
                {
                    var exps = new List<string>();
                    foreach (var m in misses) if (!exps.Contains(m.Exp)) exps.Add(m.Exp);
                    foreach (var e in exps)
                    {
                        var names = new List<string>();
                        var pairs = new List<string>();
                        bool allNone = true;
                        foreach (var m in misses)
                        {
                            if (m.Exp != e) continue;
                            names.Add(m.Seat);
                            pairs.Add(m.Seat + m.Obs);
                            if (m.Obs != "-") allNone = false;
                        }
                        string expText = e == "-" ? "none" : e;
                        Fail(allNone
                            ? "EXPECTED g" + I(_game.N) + " " + field + " none, expected " + expText + " on "
                              + string.Join(",", names.ToArray())
                            : "EXPECTED g" + I(_game.N) + " " + field + "{" + string.Join(",", pairs.ToArray())
                              + "} expected " + expText);
                    }
                }

                private void ExpectedAdvert(List<Miss> misses)
                {
                    var keys = new List<string>();
                    foreach (var m in misses)
                    {
                        string k = m.Obs + "|" + m.Exp;
                        if (!keys.Contains(k)) keys.Add(k);
                    }
                    foreach (var k in keys)
                    {
                        var names = new List<string>();
                        string obs = null, exp = null;
                        foreach (var m in misses)
                        {
                            if (m.Obs + "|" + m.Exp != k) continue;
                            names.Add(m.Seat);
                            obs = m.Obs;
                            exp = m.Exp;
                        }
                        Fail("EXPECTED g" + I(_game.N) + " advert{" + string.Join(",", names.ToArray()) + "} "
                             + obs + " expected " + exp);
                    }
                }

                // ── script truth (independent of the rule functions) ──────

                private static int TruthRG(Seat s)
                {
                    return s.Obj != null && ReferenceEquals(s.RoomGameRoom, s.Obj) ? s.RoomGame : NoGame;
                }

                private static int TruthCand(Seat s)
                {
                    if (s.TicketGame >= 1 && s.TicketAfterStart && s.Obj != null && ReferenceEquals(s.TicketRoom, s.Obj))
                        return s.TicketGame;
                    int rb = PublishedGameNumber(s);
                    return rb >= 1 ? rb : NoGame;
                }

                private static bool StartedHere(Seat s, Room room)
                {
                    return s.Obj != null && ReferenceEquals(s.LastStartObj, s.Obj) && s.LastStartPhys == room.PhysGame;
                }

                private static int ObsCS(Seat s, Room room)
                {
                    return s.FirstLatchPhys == room.PhysGame && s.Obj != null && ReferenceEquals(s.FirstLatchObj, s.Obj)
                        ? s.FirstLatchGame : NoGame;
                }

                // ── assertions ────────────────────────────────────────────

                /// <summary>At each start: EXPECTED RG, AGREE-RG and AGREE-G over the
                /// new-build starters; a game is G-1 when every one of them latched 1.</summary>
                private void StartChecks(Room room)
                {
                    var g = _game;
                    if (!room.Checked || g == null || g.StartChecked) return;
                    g.StartChecked = true;
                    string key = I(g.Key);
                    var misses = new List<Miss>();
                    var rgs = new List<string>();
                    var gs = new List<string>();
                    var vals = new HashSet<int>();
                    var gates = new HashSet<bool>();
                    int starters = 0;
                    bool allG1 = true;
                    foreach (var s in ByName(g.Starters))
                    {
                        if (s.Current || s.NoMod) continue;
                        int rg = g.StartRG[s];
                        bool gate = g.StartG[s];
                        starters++;
                        if (!gate) allG1 = false;
                        string exp = Exp(s, "RG", key);
                        if (Num(rg) != exp) misses.Add(new Miss { Seat = s.Name, Obs = Num(rg), Exp = exp });
                        rgs.Add(s.Name + Num(rg));
                        gs.Add(s.Name + (gate ? "1" : "0"));
                        if (rg >= 1) vals.Add(rg);
                        gates.Add(gate);
                    }
                    Expected("RG", misses);
                    if (vals.Count > 1) Fail("two numbers g" + I(g.N) + " RG{" + string.Join(",", rgs.ToArray()) + "}");
                    if (gates.Count > 1) Fail("AGREE-G g" + I(g.N) + " G{" + string.Join(",", gs.ToArray()) + "}");
                    g.G1 = starters > 0 && allG1;
                }

                /// <summary>At each game-over edge: EXPECTED (F, cand, CS, G, advert),
                /// LIVE-F with its count, AGREE-F, AGREE-E, PROVENANCE and AGREE-CS.</summary>
                private void EdgeChecks(Room room, List<Seat> ran)
                {
                    var g = _game;
                    if (g == null) return;
                    string n = I(g.N), key = I(g.Key);
                    var present = ByName(room.Present);
                    var ranSet = new HashSet<Seat>(ran);
                    var fM = new List<Miss>();
                    var cM = new List<Miss>();
                    var csM = new List<Miss>();
                    var gM = new List<Miss>();
                    var aM = new List<Miss>();
                    var obsF = new Dictionary<Seat, int>();
                    var liveMiss = new List<string>();
                    int count = 0;
                    bool expectF = false;
                    foreach (var s in present)
                    {
                        bool fighter = IsFighter(s);
                        bool edge = ranSet.Contains(s);
                        int pin = s.PinFrozen >= 1 ? s.PinFrozen : NoGame;
                        int f = !edge ? NoGame : s.Current ? pin : s.Snap.Frozen(s.Obj);
                        int cand = !edge ? NoGame : s.Current ? pin : s.Snap.Candidate(s.Obj);
                        int cs = ObsCS(s, room);
                        string gate = !fighter ? "-" : s.Current ? "0" : (GateNow(s) ? "1" : "0");
                        string adv = StrProp(s, s, KRg) ?? "none";
                        bool keyed = fighter && edge && StartedHere(s, room);
                        string ef = Exp(s, "F", keyed ? key : "-");
                        string ec = Exp(s, "CAND", keyed ? key : "-");
                        string ecs = Exp(s, "CS", fighter ? key : "-");
                        string eg = Exp(s, "G", fighter ? "1" : "-");
                        string ea = s.ExpAdvert ?? "none";
                        if (Num(f) != ef) fM.Add(new Miss { Seat = s.Name, Obs = Num(f), Exp = ef });
                        if (Num(cand) != ec) cM.Add(new Miss { Seat = s.Name, Obs = Num(cand), Exp = ec });
                        if (Num(cs) != ecs) csM.Add(new Miss { Seat = s.Name, Obs = Num(cs), Exp = ecs });
                        if (gate != eg) gM.Add(new Miss { Seat = s.Name, Obs = gate, Exp = eg });
                        if (adv != ea) aM.Add(new Miss { Seat = s.Name, Obs = adv, Exp = ea });
                        if (!edge) continue;
                        obsF[s] = f;
                        if (f >= 1) count++;
                        if (ef != "-") expectF = true;
                        if (!s.Current && StartedHere(s, room) && s.HeldAtFreeze && f < 1) liveMiss.Add(s.Name);
                    }
                    Expected("F", fM);
                    Expected("cand", cM);
                    Expected("CS", csM);
                    Expected("G", gM);
                    ExpectedAdvert(aM);

                    // LIVE-F: the positive arm, with its count.
                    if (liveMiss.Count > 0) Fail("LIVE-F g" + n + " F none on " + string.Join(",", liveMiss.ToArray()));
                    _counts.Add("g" + n + ":" + I(count));
                    if (expectF && count == 0) Fail("LIVE-F g" + n + " count 0");

                    // AGREE-F over every seat that ran the edge.
                    var fVals = new HashSet<int>();
                    var fList = new List<string>();
                    foreach (var s in present)
                    {
                        if (!obsF.ContainsKey(s)) continue;
                        fList.Add(s.Name + Num(obsF[s]));
                        if (obsF[s] >= 1) fVals.Add(obsF[s]);
                    }
                    if (fVals.Count > 1) Fail("two numbers g" + n + " F{" + string.Join(",", fList.ToArray()) + "}");

                    // AGREE-E over the new-build F holders.
                    var order = new List<string>();
                    var holdersOf = new Dictionary<string, List<string>>();
                    var fOf = new Dictionary<string, int>();
                    foreach (var s in present)
                    {
                        if (!obsF.ContainsKey(s) || s.Current || obsF[s] < 1 || s.EdgeE == null) continue;
                        var e = new List<string>(s.EdgeE);
                        e.Sort(string.CompareOrdinal);
                        string k = string.Join(",", e.ToArray());
                        if (!holdersOf.ContainsKey(k))
                        {
                            holdersOf[k] = new List<string>();
                            order.Add(k);
                            fOf[k] = obsF[s];
                        }
                        holdersOf[k].Add(s.Name);
                    }
                    if (order.Count > 1)
                    {
                        var parts = new List<string>();
                        foreach (var k in order) parts.Add("E{" + k + "} on " + string.Join(",", holdersOf[k].ToArray()));
                        Fail("AGREE-E g" + n + " " + string.Join("; ", parts.ToArray()));
                    }
                    foreach (var k in order)
                    {
                        var bad = new List<string>();
                        foreach (var name in k.Split(','))
                        {
                            if (name.Length == 0) continue;
                            Seat mSeat = null;
                            foreach (var p in room.Present) if (p.Name == name) mSeat = p;
                            int truth = mSeat == null ? NoGame : mSeat.Current ? WitnessOf(mSeat, mSeat) : TruthRG(mSeat);
                            if (truth != fOf[k]) bad.Add(name + " holds " + N(truth));
                        }
                        if (bad.Count > 0)
                            Fail("AGREE-E g" + n + " E{" + k + "} on " + string.Join(",", holdersOf[k].ToArray()) + ": "
                                 + string.Join(", ", bad.ToArray()));
                    }

                    // PROVENANCE: every new-build F is held as RG by the ending master
                    // or by a present fighter that advertises this room.
                    var holders = new HashSet<int>();
                    var master = room.Master;
                    if (master != null && IsFighter(master))
                        holders.Add(master.Current ? WitnessOf(master, master) : TruthRG(master));
                    string want = AdvertValue(RoomKey(room.Name));
                    foreach (var p in present)
                        if (IsFighter(p) && !p.Current && StrProp(p, p, KRg) == want) holders.Add(TruthRG(p));
                    var provList = new List<string>();
                    bool provBad = false;
                    foreach (var s in present)
                    {
                        if (!obsF.ContainsKey(s) || s.Current || obsF[s] < 1) continue;
                        provList.Add(s.Name + I(obsF[s]));
                        if (!holders.Contains(obsF[s])) provBad = true;
                    }
                    if (provBad) Fail("provenance g" + n + " F{" + string.Join(",", provList.ToArray()) + "}");

                    // AGREE-CS, G-1 games: every latch is the host's seed game.
                    if (g.G1)
                    {
                        int host = master != null && IsFighter(master) ? ObsCS(master, room) : NoGame;
                        string sv;
                        if (host < 1 && room.Props.TryGetValue(KSeq, out sv))
                        {
                            bool ok;
                            int v = ParseInt(sv, out ok);
                            if (ok) host = v;
                        }
                        bool bad = false;
                        var list = new List<string>();
                        foreach (var s in present)
                        {
                            if (!IsFighter(s)) continue;
                            int cs = ObsCS(s, room);
                            list.Add(s.Name + Num(cs));
                            if (cs >= 1 && cs != host) bad = true;
                        }
                        if (bad) Fail("AGREE-CS g" + n + " CS{" + string.Join(",", list.ToArray()) + "}");
                    }
                }

                /// <summary>AGREE-P, G-1 games: at the master's result write, every seat
                /// holding a pick identity holds the host's game and cycle.</summary>
                private void OnResultWritten(Seat s, Phase ph)
                {
                    var room = s.R;
                    if (room == null || !room.Checked || _game == null || !_game.G1) return;
                    bool bad = false;
                    var list = new List<string>();
                    foreach (var p in ByName(room.Present))
                    {
                        if (p.Ph == null || p.Ph.Stage == 3 || p.Ph.Game < 1) continue;
                        list.Add(p.Name + I(p.Ph.Game) + ":" + I(p.Ph.Cycle));
                        if (p.Ph.Game != ph.Game || p.Ph.Cycle != ph.Cycle) bad = true;
                    }
                    if (bad) Fail("AGREE-P g" + I(_game.N) + " P{" + string.Join(",", list.ToArray()) + "}");
                }

                /// <summary>LIVE-POINTS: a new-build master sends RG, else the
                /// candidate, and declines only with neither.</summary>
                private void CheckLivePoints(Room room, Seat m, int lp)
                {
                    string pre = "LIVE-POINTS g" + I(room.PhysGame) + " " + m.Name + " ";
                    int rg = TruthRG(m), cand = TruthCand(m);
                    if (rg >= 1)
                    {
                        if (lp != rg) Fail(pre + (lp >= 1 ? "sent " + I(lp) : "declined") + ", expected RG " + I(rg));
                    }
                    else if (cand >= 1)
                    {
                        if (lp != cand)
                            Fail(lp >= 1 ? pre + "sent " + I(lp) + ", expected the candidate " + I(cand)
                                         : pre + "declined with candidate " + I(cand));
                    }
                    else if (lp >= 1) Fail(pre + "sent " + I(lp) + ", expected a decline");
                }

                /// <summary>LEAVER: a leaver recorded in game k is listed as left in
                /// game k's body, with its points, and as absent in every later body.</summary>
                private void CheckLeavers(Room room, Seat s)
                {
                    foreach (var kv in s.Leavers)
                    {
                        var e = kv.Value;
                        bool back = false;
                        foreach (var p in room.Present) if (p.Steam == kv.Key) back = true;
                        if (back) continue;
                        bool listed = s.Current ? e.Stamp == s.GameNumber : LeftInGame(e.Stamp, s.LocalGameSeq);
                        bool truth = e.TruthGame == room.PhysGame;
                        string pre = "LEAVER g" + I(room.PhysGame) + " body lists " + e.Name + " ";
                        if (truth && !listed) Fail(pre + "absent (left in g" + I(e.TruthGame) + ")");
                        else if (!truth && listed) Fail(pre + "left in game (left in g" + I(e.TruthGame) + ")");
                        else if (truth && e.PointsAtLeave != e.TruthPoints)
                            Fail(pre + "with " + I(e.PointsAtLeave) + " points (left at " + I(e.TruthPoints) + ")");
                    }
                }
            }

            /// <summary>The 67 walk cases of V4 section 5, scripted from section 3.
            /// Orders: '1' = (i), '2' = (ii), '3' = (iii); an order label applies
            /// to the seat's next start. Rooms: ffa_2 (key 987561) is the sitting,
            /// ffa_1 (key 654704) the earlier room.</summary>
            private static class Walks
            {
                private static readonly string[] OrderNames = { "i", "ii", "iii" };

                private static void Case(SelfTestResult r, string id, Action<Model> script)
                {
                    new Model(r, id).Run(script);
                }

                private static void Ordered(SelfTestResult r, string id, Action<Model, char> script)
                {
                    for (int i = 0; i < 3; i++)
                    {
                        char ord = (char)('1' + i);
                        Case(r, id + "(" + OrderNames[i] + ")", m => script(m, ord));
                    }
                }

                private static Opts With(Seat s, char ord)
                {
                    var o = new Opts();
                    o.Order[s] = ord;
                    return o;
                }

                internal static void Run(SelfTestResult r)
                {
                    Ordered(r, "walk-D3 W3.1", W31);
                    Ordered(r, "walk-D3 W3.2", W32);
                    Case(r, "walk-D3 W3.2m", W32m);
                    Ordered(r, "walk-D3 W3.3", W33);
                    Ordered(r, "walk-D3 W3.4", W34);

                    Ordered(r, "walk-D4 W4.1", W41);
                    Ordered(r, "walk-D4 W4.2", W42);
                    Case(r, "walk-D4 W4.3", W43);
                    Ordered(r, "walk-D4 W4.4", W41);   // the contract pair is read by nothing: W4.1's script

                    Case(r, "walk-D5 W5.1", W51);
                    Ordered(r, "walk-D5 W5.2", W52);
                    Case(r, "walk-D5 W5.2m", W52m);
                    Case(r, "walk-D5 W5.2x", m => W52xf(m, false));
                    Case(r, "walk-D5 W5.2f", m => W52xf(m, true));
                    Ordered(r, "walk-D5 W5.3", W53);
                    Ordered(r, "walk-D5 W5.4", W54);

                    Ordered(r, "walk-D6 W6.1", W61);
                    Case(r, "walk-D6 W6.2", W62);
                    Case(r, "walk-D6 W6.3q", m => W63(m, false));
                    Case(r, "walk-D6 W6.3n", m => W63(m, true));
                    Case(r, "walk-D6 W6.4", W64);
                    Ordered(r, "walk-D6 W6.5", W65);
                    Ordered(r, "walk-D6 W6.6", (m, o) => W66(m, o, 0));
                    Case(r, "walk-D6 W6.6s", m => W66(m, '3', 1));
                    Ordered(r, "walk-D6 W6.7", W67);
                    Case(r, "walk-D6 W6.7a", m => W66(m, '3', 2));
                    Case(r, "walk-D6 W6.8", m => W68(m, false));
                    Case(r, "walk-D6 W6.8d", m => W68(m, true));
                    Ordered(r, "walk-D6 W6.9", (m, o) => W69(m, o, false));
                    Case(r, "walk-D6 W6.9p", m => W69(m, '1', true));

                    Case(r, "walk-D12 W7.1", W71);
                    Case(r, "walk-D12 W7.2", W72);
                    Case(r, "walk-D12 W7.3", W73);
                    Case(r, "walk-D12 W7.4", W74);
                    Case(r, "walk-D12 W7.5", W75);
                    Case(r, "walk-D12 W7.6", W76);
                    Case(r, "walk-D12 W7.7", W77);
                }

                // ── D3 ────────────────────────────────────────────────────

                private static void W31(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    m.S0(room, null, s);
                    m.Relaunch(s[2]);
                    m.Join(s[2], room, "ready");
                    m.Play(room, "RG A4 B4 C- D4", With(s[2], ord));
                    m.StartOnly(room, null);
                }

                private static void W32(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var C = s[2];
                    m.S0(room, null, s);
                    var o4 = new Opts();
                    o4.AfterEntries = c => { if (c == 2) m.Relaunch(C); };
                    m.Play(room, null, o4);
                    m.Join(C, room, "ready");
                    m.Play(room, "RG A5 B5 C- D5", With(C, ord));
                    m.StartOnly(room, null);
                }

                private static void W32m(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var C = s[2];
                    m.S0(room, null, s);
                    var o4 = new Opts();
                    o4.AfterEntries = c => { if (c == 2) m.Relaunch(C); };
                    o4.AfterCycle = c => { if (c == 2) m.Join(C, room, "ready"); };
                    m.Play(room, "F A4 B4 C- D4", o4);
                    m.Play(room, "RG A5 B5 C- D5", With(C, '1'));
                    m.StartOnly(room, null);
                }

                private static void W33(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var A = m.NewSeat("A");
                    var B = m.NewSeat("B");
                    var C = m.NewSeat("C", "1000");   // the lowest steam id: C is elected
                    var D = m.NewSeat("D");
                    m.S0(room, null, A, B, C, D);
                    var o4 = new Opts();
                    o4.LostReport = C;
                    m.Play(room, null, o4);
                    m.Relaunch(C);
                    m.Join(C, room, "ready");
                    m.Play(room, "RG A5 B5 C- D5", With(C, ord));
                    m.StartOnly(room, null);
                }

                /// <summary>W3.4 differs from V4's prose in one moment. V4 arms B's
                /// ticket at the new master's 2 s republish of 4:c (FfaMode's master-
                /// migration WriteCycleProp); this model does not run that timer, so
                /// B's ticket arms at its next cycle's entry write, still in game 4.
                /// The numbers are V4's.</summary>
                private static void W34(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var A = s[0];
                    m.S0(room, null, s);
                    var o4 = new Opts();
                    o4.AfterCycle = c => { if (c == 2) m.Relaunch(A); };
                    m.Play(room, "F B4 C4 D4", o4);
                    m.Join(A, room, "ready");
                    m.Play(room, "RG A- B5 C5 D5", With(A, ord));
                    m.StartOnly(room, null);
                }

                // ── D4 ────────────────────────────────────────────────────

                private static void W41(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var C = s[2];
                    m.S0(room, null, s);
                    m.Leave(C);
                    m.Join(C, room, "ready");
                    m.Play(room, "RG A4 B4 C- D4", With(C, ord));
                    m.StartOnly(room, null);
                }

                private static void W42(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var C = s[2];
                    m.S0(room, null, s);
                    m.Leave(C);
                    var o4 = new Opts();
                    o4.AfterCycle = c => { if (c == 1) m.Join(C, room, "ready"); };
                    m.Play(room, "F A4 B4 C- D4", o4);
                    m.Play(room, "RG A5 B5 C- D5", With(C, ord));
                    m.StartOnly(room, null);
                }

                private static void W43(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    m.JoinAll(room, s);
                    m.Play(room, "RG A1 B- C1 D1", With(s[1], '1'));
                    m.StartOnly(room, null);
                }

                // ── D5 ────────────────────────────────────────────────────

                /// <summary>Games 1-3 with S joining as a spectator in game 2.</summary>
                private static void WithKeeper(Model m, Room room, Seat[] seats, Seat S, bool refuse, string spec)
                {
                    m.JoinAll(room, seats);
                    m.Play(room, spec, null);
                    var o2 = new Opts();
                    o2.AfterCycle = c => { if (c == 1) m.Join(S, room, "spectator", refuse); };
                    m.Play(room, spec, o2);
                    m.Play(room, spec, null);
                }

                private static void W51(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var S = m.NewSeat("S");
                    S.Spectator = true;
                    WithKeeper(m, room, s, S, false, null);
                }

                private static void W52(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var S = m.NewSeat("S");
                    S.Spectator = true;
                    WithKeeper(m, room, s, S, false, null);
                    m.Promote(S);
                    m.Play(room, "RG A4 B4 C4 D4 S-", With(S, ord));
                    m.StartOnly(room, null);
                }

                private static void W52m(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var S = m.NewSeat("S");
                    m.FoughtElsewhere(S, "ffa_1", 6, false);
                    S.Spectator = true;
                    WithKeeper(m, room, s, S, false, null);
                    var o4 = new Opts();
                    o4.AfterCycle = c => { if (c == 1) m.Promote(S); };
                    m.Play(room, "F A4 B4 C4 D4 S-", o4);
                    m.Play(room, "RG A5 B5 C5 D5 S-", With(S, '1'));
                    m.StartOnly(room, null);
                }

                private static void W52xf(Model m, bool foreign)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var S = m.NewSeat("S");
                    if (foreign) m.FoughtElsewhere(S, "ffa_1", 2, false);
                    S.Spectator = true;
                    WithKeeper(m, room, s, S, true, null);
                    m.Promote(S);
                    m.Play(room, "G 0; RG A4 B4 C4 D4 S-; CS A4 B4 C4 D4 S1", With(S, '1'));
                    m.StartOnly(room, null);
                }

                /// <summary>W5.3 and W5.4: V4's sequence says X enters room Y (A-D);
                /// V4's numbers list A, B, D and X only, and these scripts follow the
                /// numbers (no seat C).</summary>
                private static void W53(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var A = m.NewSeat("A");
                    var B = m.NewSeat("B");
                    var D = m.NewSeat("D");
                    var X = m.NewSeat("X");
                    m.FoughtElsewhere(X, "ffa_1", 6, true);
                    m.S0(room, null, A, B, D);
                    m.Join(X, room, "ready");
                    m.Play(room, "RG A4 B4 D4 X-", With(X, ord));
                    m.StartOnly(room, null);
                }

                private static void W54(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var A = m.NewSeat("A");
                    var B = m.NewSeat("B");
                    var D = m.NewSeat("D");
                    var X = m.NewSeat("X");
                    m.FoughtElsewhere(X, "ffa_1", 6, true);
                    m.S0(room, null, A, B, D);
                    var o4 = new Opts();
                    o4.AfterCycle = c => { if (c == 1) m.Join(X, room, "ready"); };
                    m.Play(room, "F A4 B4 D4 X-", o4);
                    m.Play(room, "RG A5 B5 D5 X-", With(X, ord));
                    m.StartOnly(room, null);
                }

                // ── D6 ────────────────────────────────────────────────────

                private static void W61(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var C = s[2];
                    m.S0(room, null, s);
                    var o4 = new Opts();
                    o4.AfterCycle = c =>
                    {
                        if (c == 2) m.Leave(C);
                        else if (c == 3) m.Join(C, room, "pending");
                    };
                    m.Play(room, "F A4 B4 C- D4", o4);
                    m.Play(room, "RG A5 B5 C- D5", With(C, ord));
                    m.StartOnly(room, null);
                }

                private static void W62(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    m.S0(room, null, s);
                    var o4 = new Opts();
                    o4.Entries = c =>
                    {
                        if (c != 4) return false;
                        m.Enter(s[1]);
                        m.Enter(s[2]);
                        m.Enter(s[3]);
                        m.Leave(s[0]);   // A drops before its cycle-4 write
                        return true;
                    };
                    m.Play(room, "F B4 C4 D4", o4);
                    m.StartOnly(room, null);
                }

                /// <summary>G 0 for the whole sitting: D's stage was refused at its
                /// first join (a fresh process, as W7.6).</summary>
                private static void RefusedD(Model m, Room room, Seat[] s)
                {
                    m.Join(s[0], room, "ready");
                    m.Join(s[1], room, "ready");
                    m.Join(s[2], room, "ready");
                    m.Join(s[3], room, "ready", true);
                    m.Advance(1.0);
                    m.Games(room, 3, "G 0");
                }

                /// <summary>W6.3n differs from V4's prose. With D the point winner,
                /// C's pick alone meets the production quorum
                /// Math.Min(2, Math.Max(1, manifest - 1)) = 1 and B adopts. And the
                /// detector (DetectAheadPickIdentity) also counts every manifest
                /// peer's RETAINED pick, B's own included: after cycle 3, B's, C's
                /// and D's picks all read 4:3, which is ahead of B's 3:4, so B adopts
                /// 4:3 at its first result pre-pass (W6.3q reaches F 4 that way, not
                /// through 4:4). The no-quorum state is therefore scripted by delay:
                /// C's traffic to B is held from point 1 and D's from point 2, so B
                /// sees B 4:3, C 4:1 and D 4:2 (three identities, no quorum) and
                /// never receives a 4:4 pick; both are released after cycle 4.</summary>
                private static void W63(Model m, bool noQuorum)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    Seat A = s[0], B = s[1], D = s[3];
                    RefusedD(m, room, s);
                    var o4 = new Opts();
                    Seat C = s[2];
                    o4.AfterPoint = c =>
                    {
                        if (noQuorum && c == 1) m.Stall(C, B);
                        if (noQuorum && c == 2) m.Stall(D, B);
                        if (c != 3) return;
                        m.Leave(A);
                        B.GameNumber = 3;   // a counter behind under G 0, after the leaver entry is stamped
                    };
                    if (noQuorum)
                        o4.AfterCycle = c =>
                        {
                            if (c != 4) return;
                            m.Unstall(C, B);
                            m.Unstall(D, B);
                        };
                    m.Play(room, noQuorum ? "G 0; F -; CAND 3" : "G 0; F B4 C4 D4", o4);
                    m.StartOnly(room, null);
                }

                private static void W64(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    Seat A = s[0], B = s[1], C = s[2], D = s[3];
                    RefusedD(m, room, s);
                    var o4 = new Opts();
                    o4.AfterPoint = c =>
                    {
                        if (c != 3) return;
                        m.Leave(A);
                        B.GameNumber = 5;   // a counter ahead under G 0
                        m.StallInbound(B);  // B's own 5:4 never echoes back to it
                    };
                    o4.Entries = c =>
                    {
                        if (c != 4) return false;
                        m.Enter(C);
                        m.Enter(B);
                        m.Tick();
                        m.Enter(D);
                        return true;
                    };
                    m.Play(room, "G 0; F -; CAND 5", o4);
                    m.UnstallInbound(B);
                    m.Advance(1.0);
                    m.StartOnly(room, null);
                }

                private static void W65(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var C = s[2];
                    m.S0(room, null, s);
                    m.Leave(C);   // during the game-over transition, after game 3's edge
                    var o4 = new Opts();
                    o4.AfterCycle = c => { if (c == 3) m.Join(C, room, "pending"); };
                    m.Play(room, "F A4 B4 C- D4", o4);
                    m.Play(room, "RG A5 B5 C- D5", With(C, ord));
                    m.StartOnly(room, null);
                }

                /// <summary>W6.6 (variant 0, ordinary leaves), W6.6s (1: A's inbound
                /// stalls right after its 1:1 write) and W6.7a (2: fast same-name
                /// re-entries). S keeps the room; A, B, C and D re-enter in turn, so
                /// S receives the role when D leaves and hands it to A. W6.6s plays
                /// game 4 as the opening draw and one point: in a longer game A's
                /// stale cache would reopen at 3:k+1 at its next entry.</summary>
                private static void W66(Model m, char ord, int variant)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var S = m.NewSeat("S");
                    S.Spectator = true;
                    Seat A = s[0], B = s[1], C = s[2], D = s[3];
                    WithKeeper(m, room, s, S, false, null);
                    foreach (var x in s)
                    {
                        if (variant == 2) { m.FastLeave(x); m.Join(x, room, "pending"); }
                        else { m.Leave(x); m.Join(x, room, "ready"); }
                    }
                    m.Advance(1.0);
                    var o4 = new Opts();
                    if (variant == 0)
                    {
                        o4.Order[B] = ord;
                        o4.Order[C] = ord;
                        o4.Order[D] = ord;
                    }
                    if (variant == 1)
                    {
                        o4.Points = 1;
                        o4.Entries = c =>
                        {
                            if (c != 1) return false;
                            m.Enter(A);
                            m.StallInbound(A);
                            m.Tick();
                            m.Enter(B);
                            m.Enter(C);
                            m.Enter(D);
                            return true;
                        };
                    }
                    m.Play(room, "RG -; CAND 1; F -; CS 1", o4);
                    if (variant == 1)
                    {
                        m.UnstallInbound(A);
                        m.Advance(1.0);
                    }
                    m.Play(room, "N 2", null);
                }

                private static void W67(Model m, char ord)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var C = s[2];
                    m.S0(room, null, s);
                    m.FastLeave(C);
                    m.Join(C, room, "pending");
                    m.Play(room, "RG A4 B4 C- D4", With(C, ord));
                    m.StartOnly(room, null);
                }

                /// <summary>W6.8 and W6.8d (delayed). In W6.8d V4 arms B's ticket at
                /// the new master's 2 s republish of 1:1; this model does not run that
                /// timer, so B's ticket arms at its next cycle's entry write, still in
                /// game 1. The numbers are V4's.</summary>
                private static void W68(Model m, bool delayed)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    Seat A = s[0], B = s[1], C = s[2], D = s[3];
                    m.JoinAll(room, s);
                    var o = With(B, '1');
                    if (delayed)
                    {
                        m.Stall(C, B);
                        m.Stall(D, B);
                        o.AfterEntries = c => { if (c == 1) m.Leave(A); };
                        m.Play(room, "RG B-; F B- C1 D1", o);
                        m.Unstall(C, B);
                        m.Unstall(D, B);
                        m.Advance(1.0);
                    }
                    else
                    {
                        o.AfterCycle = c => { if (c == 2) m.Leave(A); };
                        m.Play(room, "RG A1 B- C1 D1; F B1 C1 D1", o);
                    }
                    m.StartOnly(room, null);
                }

                private static void W69(Model m, char ord, bool skipB)
                {
                    var room = m.NewRoom("ffa_2");
                    var Z = m.NewSeat("Z");
                    var A = m.NewSeat("A");
                    var B = m.NewSeat("B");
                    var C = m.NewSeat("C");
                    m.JoinAll(room, Z, A, B, C);
                    var o1 = With(A, '1');
                    o1.SkipEdge.Add(A);
                    m.Play(room, "RG Z1 A- B1 C1; F A-; CAND A-", o1);
                    m.Leave(Z);
                    m.Leave(C);
                    m.Join(C, room, "ready");
                    m.Advance(1.0);
                    var o2 = new Opts();
                    o2.Order[B] = ord;
                    o2.Order[C] = ord;
                    if (skipB) o2.SkipEdge.Add(B);
                    m.Play(room, skipB ? "RG A- B2 C-; CAND A1 B- C1; F -; CS 1" : "RG A- B2 C-; CAND 1; F -; CS 1", o2);
                    if (!skipB)
                    {
                        m.Play(room, "N 2", null);
                        return;
                    }
                    m.Play(room, "N 2; RG A2 B- C2", null);
                    m.StartOnly(room, "N 3");
                }

                // ── D12 ───────────────────────────────────────────────────

                private static void W71(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    s[1].Current = true;
                    m.S0(room, "G 0", s);
                }

                private static void W72(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    s[1].Current = true;
                    s[2].Current = true;
                    m.S0(room, "G 0", s);
                    s[1].GameNumber = 4;   // a double start (R9): L 5 and W 5 at game 4
                    s[2].GameNumber = 4;
                    m.Play(room, "G 0; F A- B5 C5 D-; CAND 5; CS A4 B5 C5 D4", null);
                    m.StartOnly(room, null);
                }

                private static void W73(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    var N = m.NewSeat("N");
                    N.NoMod = true;
                    m.S0(room, "G 0", s[0], s[1], s[2], s[3], N);
                }

                /// <summary>W7.4: V4 leaves the drift's origin outside the walk. Here
                /// Z's counter is set to 1 after game 3 (two behind the lobby at game
                /// 4), and P's and Q's counter and sequence to 1, so that fresh picks
                /// from the new seats do not out-vote Z; X keeps counter and sequence
                /// 3, which gives V4's stamp inputs (sequence 7, counter 5) when P
                /// leaves game 7. The expectations are V4's. They hold only if the
                /// pick-evidence detector ignores retained picks of a finalized cycle:
                /// as built, X's, P's and Q's game-3 picks still read 3:4, ahead of
                /// Z's 2:1, and meet the quorum at Z's first result pre-pass
                /// (DetectAheadPickIdentity, unchanged since the pin), so Z adopts 3:4
                /// and this walk is red for that reason.</summary>
                private static void W74(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var Z = m.NewSeat("Z", "1000");
                    var X = m.NewSeat("X");
                    var P = m.NewSeat("P");
                    var Q = m.NewSeat("Q");
                    Z.Current = true;
                    m.S0(room, "G 0", Z, X, P, Q);
                    Z.GameNumber = 1;
                    P.GameNumber = 1;
                    P.LocalGameSeq = 1;
                    Q.GameNumber = 1;
                    Q.LocalGameSeq = 1;
                    m.Play(room, "G 0; RG 4; F 2; CAND 2; CS Z2 X4 P2 Q2", null);
                    m.Play(room, "G 0; RG 3; F 3; CAND 3; CS Z3 X5 P3 Q3", null);
                    m.Play(room, "G 0; RG 4; F 4; CAND 4; CS Z4 X6 P4 Q4", null);
                    m.Leave(Z);
                    var o7 = new Opts();
                    o7.AfterCycle = c => { if (c == 2) m.Leave(P); };
                    m.Play(room, "N 5", o7);
                    m.Play(room, "N 6", null);
                }

                private static void W75(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var A = m.NewSeat("A");
                    var B = m.NewSeat("B");
                    var C = m.NewSeat("C");
                    var Z = m.NewSeat("Z");
                    var S = m.NewSeat("S");
                    Z.Current = true;
                    S.Spectator = true;
                    var seats = new[] { A, B, C, Z };
                    WithKeeper(m, room, seats, S, false, "G 0");
                    foreach (var x in seats)
                    {
                        m.Leave(x);
                        m.Join(x, room, "ready");
                    }
                    m.Advance(1.0);
                    m.Play(room, "G 0; RG A- B- C-; F A- B- C- Z1; CAND 1; CS 1", null);
                    m.Play(room, "G 0; N 2", null);
                }

                private static void W76(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    m.Join(s[0], room, "ready");
                    m.Join(s[1], room, "ready", true);   // a fresh process; the stage refused
                    m.Join(s[2], room, "ready");
                    m.Join(s[3], room, "ready");
                    m.Advance(1.0);
                    m.Games(room, 3, "G 0");
                }

                private static void W77(Model m)
                {
                    var room = m.NewRoom("ffa_2");
                    var s = m.Abcd();
                    m.FoughtElsewhere(s[3], "ffa_1", 2, false);   // D keeps "1:654704"
                    m.Join(s[0], room, "ready");
                    m.Join(s[1], room, "ready");
                    m.Join(s[2], room, "ready");
                    m.Join(s[3], room, "ready", true);
                    m.Advance(1.0);
                    m.Games(room, 3, "G 0");
                }
            }
        }
        // SITTING-MODEL-END
    }
}
