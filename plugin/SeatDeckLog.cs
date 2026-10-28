using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 S0: the seat deck log and the accepted-death ledger of a 2v2 or
    /// 1v2 game. Pure: no Unity, Photon or Harmony type appears here, so the
    /// harness under tools/tests/rj-stage2-client compiles this file as it
    /// ships and executes its rules. The Harmony glue that feeds it lives in
    /// TeamHoldPatches.cs, CombatTelemetry.cs and VanillaFixes.cs.
    ///
    /// The log. Per slot per game: the ordered card names the seat received,
    /// <c>Deals</c> (every deal ends in exactly one applied pick, so deals
    /// equals the committed names) and <c>Deaths</c>. <see cref="Commit"/> is
    /// the ONLY writer. Every online application, the opening pick of
    /// DoStartGame included, runs ApplyCardStats.RPCA_Pick, so the seam is that
    /// RPC: an intent recorded before the original (<see cref="PickIntent"/>),
    /// a commit after it returned (<see cref="PickCommit"/>, only when the
    /// original ran), and a drop on every exit that marks the slots of an
    /// intent no commit completed (<see cref="PickEnd"/>). The
    /// end-pick hook and OFFLINE_Pick are observers that never write: a local
    /// replay (the returner's restore) runs through OFFLINE_Pick and must not
    /// append. The absent-seat grant (S4) is the one logical writer, keyed on
    /// (deal index k, slot) through the same <see cref="Commit"/>.
    ///
    /// The ledger. One key per (slot, scoreboard tuple, life); the tuple is the
    /// same on every client between two RPCA_NextRound events, and life
    /// advances when SafeRespawn completes a Phoenix revive. Three claimers
    /// race for a key and the first wins: RPCA_Die (after the vanilla guard),
    /// RPCA_Die_Phoenix and a departure. A won die or departure claim counts
    /// one death; a Phoenix claim counts none (no Phoenix death is counted
    /// today) and makes a departure during the charge count none; a lost
    /// claim does nothing.
    ///
    /// Failure direction. A faulted application or a drift marks the slot;
    /// the hold classifier refuses a hold for a marked slot, which ends the
    /// game as today.
    /// </summary>
    internal static class SeatDeckLog
    {
        internal sealed class Seat
        {
            internal readonly List<string> Names = new List<string>();
            internal int Deaths;
            internal int Life;
            internal bool Faulted;
            internal bool Drifted;
            internal int Deals { get { return Names.Count; } }
        }

        private sealed class Intent
        {
            internal int ViewId;
            internal string Name;
            internal int[] Slots;
            internal bool Done;
        }

        /// <summary>The outcome of one ledger claim.</summary>
        internal enum Claim { Won, Lost }

        private const char CLAIM_DIE = 'd';
        private const char CLAIM_PHOENIX = 'p';
        private const char CLAIM_DEPART = 'x';

        private static readonly Dictionary<int, Seat> _seats = new Dictionary<int, Seat>();
        private static readonly HashSet<string> _committed = new HashSet<string>(StringComparer.Ordinal);
        private static readonly Dictionary<string, char> _claims = new Dictionary<string, char>(StringComparer.Ordinal);
        private static readonly Stack<Intent> _intents = new Stack<Intent>();
        private static int _game;
        private static int _replays;

        /// <summary>Games started since the room was entered (every client
        /// counts every DoStartGame, rematches included).</summary>
        internal static int Game { get { return _game; } }

        /// <summary>OFFLINE_Pick applications observed this game (the local
        /// replay of a restore). Never a deck write.</summary>
        internal static int Replays { get { return _replays; } }

        // ── lifecycle ───────────────────────────────────────────────────────

        /// <summary>GM_ArmsRace.DoStartGame on every client, every game.</summary>
        internal static void OnGameStart()
        {
            _game++;
            ClearGame();
        }

        /// <summary>The room was left: nothing of this room survives.</summary>
        internal static void OnRoomLeft()
        {
            _game = 0;
            ClearGame();
        }

        private static void ClearGame()
        {
            _seats.Clear();
            _committed.Clear();
            _claims.Clear();
            _intents.Clear();
            _replays = 0;
        }

        internal static Seat SeatOf(int slot)
        {
            Seat s;
            if (!_seats.TryGetValue(slot, out s)) { s = new Seat(); _seats[slot] = s; }
            return s;
        }

        internal static bool TryGetSeat(int slot, out Seat seat) { return _seats.TryGetValue(slot, out seat); }

        internal static IEnumerable<int> Slots() { return _seats.Keys; }

        // ── the writer ──────────────────────────────────────────────────────

        /// <summary>THE writer: one name for one slot, deduplicated on the
        /// application key for the game. <paramref name="key"/> is the card's
        /// PhotonView id for a real application (<see cref="ViewKey"/>) or the
        /// deal index for the absent-seat grant (<see cref="DealKey"/>).
        /// Returns false when the key was already committed.</summary>
        internal static bool Commit(string key, int slot, string name)
        {
            if (slot < 0 || string.IsNullOrEmpty(name) || string.IsNullOrEmpty(key)) return false;
            if (!_committed.Add(key + "|" + slot.ToString(CultureInfo.InvariantCulture))) return false;
            SeatOf(slot).Names.Add(name);
            return true;
        }

        internal static string ViewKey(int viewId) { return "v" + viewId.ToString(CultureInfo.InvariantCulture); }
        internal static string DealKey(int k) { return "k" + k.ToString(CultureInfo.InvariantCulture); }

        /// <summary>The absent-seat grant of S4: deal k of the slot gets the
        /// card unless a real pick for that deal already committed (the slot's
        /// deals already passed k), in which case the grant is superseded and
        /// nothing is written. A grant for a deal beyond the next one marks
        /// the slot (the log would have a hole).</summary>
        internal static bool CommitGrant(int k, int slot, string name, out bool superseded)
        {
            superseded = false;
            var seat = SeatOf(slot);
            if (seat.Deals > k) { superseded = true; return false; }
            if (seat.Deals < k) { seat.Faulted = true; return false; }
            return Commit(DealKey(k), slot, name);
        }

        // ── the RPCA_Pick seam ──────────────────────────────────────────────

        /// <summary>Intent prefix (Priority.First): the card and its target
        /// slots, recorded before the original runs. Writes nothing.</summary>
        internal static void PickIntent(int viewId, string name, int[] slots)
        {
            _intents.Push(new Intent { ViewId = viewId, Name = name, Slots = slots ?? new int[0] });
        }

        /// <summary>Commit postfix: the original returned (Harmony runs no
        /// postfix when it threw). Commits once per target slot when the
        /// original actually ran; a sibling prefix that skipped it commits
        /// nothing. The intent stays on the stack for the finalizer.</summary>
        internal static void PickCommit(bool runOriginal)
        {
            if (_intents.Count == 0) return;
            var it = _intents.Peek();
            if (it.Done) return;
            it.Done = true;
            if (!runOriginal) return;
            for (int i = 0; i < it.Slots.Length; i++)
                Commit(ViewKey(it.ViewId), it.Slots[i], it.Name);
        }

        /// <summary>Finalizer, which runs on every exit: drops the intent. An
        /// intent no postfix completed belongs to an original that threw (a
        /// sibling finalizer may already have swallowed the exception, so the
        /// exception argument is not the test): its target slots are marked
        /// faulted (no hold for them) and nothing is written.</summary>
        internal static void PickEnd()
        {
            if (_intents.Count == 0) return;
            var it = _intents.Pop();
            if (it.Done) return;
            for (int i = 0; i < it.Slots.Length; i++)
                if (it.Slots[i] >= 0) SeatOf(it.Slots[i]).Faulted = true;
        }

        /// <summary>The end-pick hook: an observer only. Every application,
        /// this one included, already committed through RPCA_Pick.</summary>
        internal static void ObserveEndPick(int slot, string name) { }

        /// <summary>OFFLINE_Pick: the local replay of a restore. Counted, never
        /// written to the log.</summary>
        internal static void ObserveOfflinePick(int slot, string name) { _replays++; }

        // ── the accepted-death ledger ───────────────────────────────────────

        /// <summary>The scoreboard tuple p1Rounds:p2Rounds:p1Points:p2Points.</summary>
        internal static string Tuple(int p1Rounds, int p2Rounds, int p1Points, int p2Points)
        {
            return p1Rounds.ToString(CultureInfo.InvariantCulture) + ":" + p2Rounds.ToString(CultureInfo.InvariantCulture)
                   + ":" + p1Points.ToString(CultureInfo.InvariantCulture) + ":" + p2Points.ToString(CultureInfo.InvariantCulture);
        }

        private static string LedgerKey(int slot, string tuple)
        {
            return slot.ToString(CultureInfo.InvariantCulture) + "|" + (tuple ?? "") + "|"
                   + SeatOf(slot).Life.ToString(CultureInfo.InvariantCulture);
        }

        private static Claim TryClaim(int slot, string tuple, char kind)
        {
            if (slot < 0) return Claim.Lost;
            string key = LedgerKey(slot, tuple);
            if (_claims.ContainsKey(key)) return Claim.Lost;
            _claims[key] = kind;
            return Claim.Won;
        }

        /// <summary>RPCA_Die after the vanilla guard. Won: one death counted
        /// here; the caller then records the observed death as today.</summary>
        internal static Claim ClaimDie(int slot, string tuple)
        {
            var c = TryClaim(slot, tuple, CLAIM_DIE);
            if (c == Claim.Won) SeatOf(slot).Deaths++;
            return c;
        }

        /// <summary>RPCA_Die_Phoenix. Counts nothing; holds the key so a
        /// departure during the charge counts nothing either.</summary>
        internal static Claim ClaimPhoenix(int slot, string tuple)
        {
            return TryClaim(slot, tuple, CLAIM_PHOENIX);
        }

        /// <summary>A departure of a fighter (S1 step 8, before the purge).
        /// Won: one death counted; the caller records it as an observed death.</summary>
        internal static Claim ClaimDeparture(int slot, string tuple)
        {
            var c = TryClaim(slot, tuple, CLAIM_DEPART);
            if (c == Claim.Won) SeatOf(slot).Deaths++;
            return c;
        }

        /// <summary>SafeRespawn completed a revive: the next death of this slot
        /// is a new key.</summary>
        internal static void AdvanceLife(int slot)
        {
            if (slot < 0) return;
            SeatOf(slot).Life++;
        }

        // ── the S6 ladder sink ───────────────────────────────────────────────

        /// <summary>Where the [SEATLOG] and [HOLD] ladder lines go. The boot
        /// line binds it to the plugin log; unbound (the harness, before boot)
        /// a line goes nowhere. A throwing sink never reaches the caller.</summary>
        internal static Action<string> Ladder;

        internal static void Emit(string line)
        {
            var f = Ladder;
            if (f == null || line == null) return;
            try { f(line); } catch { }
        }

        // ── the drift probe (log only) ──────────────────────────────────────

        /// <summary>Point start: the body's current card names against the
        /// slot log. A mismatch marks the slot and answers true once per slot
        /// per game, and that first answer emits [SEATLOG] drift. A slot with
        /// no log and no cards is not a mismatch.</summary>
        internal static bool DriftCheck(int slot, IList<string> bodyNames)
        {
            if (slot < 0 || bodyNames == null) return false;
            Seat seat;
            _seats.TryGetValue(slot, out seat);
            int logged = seat != null ? seat.Names.Count : 0;
            bool same = logged == bodyNames.Count;
            for (int i = 0; same && i < logged; i++)
                same = string.Equals(seat.Names[i], bodyNames[i], StringComparison.Ordinal);
            if (same) return false;
            seat = SeatOf(slot);
            bool first = !seat.Drifted;
            seat.Drifted = true;
            if (first)
                Emit("[SEATLOG] drift slot=" + slot.ToString(CultureInfo.InvariantCulture) + " log=" + Describe(slot)
                     + " body=" + bodyNames.Count.ToString(CultureInfo.InvariantCulture));
            return first;
        }

        /// <summary>A faulted application or a drift: S1 refuses a hold for
        /// this slot (toward today).</summary>
        internal static bool Marked(int slot)
        {
            Seat s;
            return _seats.TryGetValue(slot, out s) && (s.Faulted || s.Drifted);
        }

        /// <summary>The slot fields S3 snapshots: names joined by '/', deals,
        /// deaths. Names never contain '/', ':' or ';' (card GameObject names).</summary>
        internal static string Describe(int slot)
        {
            Seat s;
            if (!_seats.TryGetValue(slot, out s)) return "0:0:";
            var sb = new StringBuilder();
            sb.Append(s.Deals.ToString(CultureInfo.InvariantCulture)).Append(':')
              .Append(s.Deaths.ToString(CultureInfo.InvariantCulture)).Append(':');
            for (int i = 0; i < s.Names.Count; i++) { if (i > 0) sb.Append('/'); sb.Append(s.Names[i]); }
            return sb.ToString();
        }

        /// <summary>The restore of S3 step 8: seeds one slot from a verified
        /// snapshot (names, deaths). Replaces the slot; commits no key, so a
        /// later real application of a new card still commits once.</summary>
        internal static void Seed(int slot, IList<string> names, int deaths)
        {
            var s = SeatOf(slot);
            s.Names.Clear();
            if (names != null) s.Names.AddRange(names);
            s.Deaths = deaths;
        }
    }
}
