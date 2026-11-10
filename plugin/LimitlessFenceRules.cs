using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) lane 2 (design v4 at md5 4283f353, sections 4.2 to 4.7 and 5.1):
    /// the continuation fence's pure rules. No Unity or Photon type appears
    /// here, so the client-rules harness runs every rule (suite `fencerules`)
    /// with a mutant per rule. The wiring reads its inputs from the room and
    /// calls these; nothing here reads local state.
    /// </summary>
    internal static class LimitlessFenceRules
    {
        /// <summary>D1 (Sid's, default 50): a continuation ends when a side
        /// reaches the base target plus this many rounds.</summary>
        internal const int ExtraRounds = 50;

        /// <summary>4.2: a gid is 16 lowercase hexadecimal characters (8 bytes
        /// from RandomNumberGenerator).</summary>
        internal const int GidLength = 16;

        /// <summary>The wire format's own version (index 0 of every carrier).</summary>
        internal const int WireVersion = 1;

        /// <summary>4.3: the states go one way, live, then terminating, then ended.</summary>
        internal enum State { Live = 0, Terminating = 1, Ended = 2 }

        // ------------------------------------------------------------------ identity (4.2)

        internal static bool IsGid(string s)
        {
            if (s == null || s.Length != GidLength) return false;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
            }
            return true;
        }

        /// <summary>The gid for eight random bytes; the wiring supplies them
        /// from RandomNumberGenerator, never from local numbering.</summary>
        internal static string GidOf(byte[] eight)
        {
            if (eight == null || eight.Length != GidLength / 2) return null;
            var chars = new char[GidLength];
            const string hex = "0123456789abcdef";
            for (int i = 0; i < eight.Length; i++)
            {
                chars[2 * i] = hex[eight[i] >> 4];
                chars[2 * i + 1] = hex[eight[i] & 15];
            }
            return new string(chars);
        }

        /// <summary>
        /// One seat's gids (4.2): a gid is live from its adoption until the seat
        /// runs a terminal path for it; an ended gid is never live again on this
        /// seat. Cleared at room exit, where every gid of the room is gone.
        /// </summary>
        internal sealed class GidLedger
        {
            private readonly HashSet<string> _ended = new HashSet<string>(StringComparer.Ordinal);

            /// <summary>The seat's current gid, or null while it holds none.</summary>
            internal string Current { get; private set; }

            internal bool HasEnded(string gid) { return gid != null && _ended.Contains(gid); }

            /// <summary>Live: current, and not ended on this seat.</summary>
            internal bool IsLiveGid(string gid)
            {
                return IsGid(gid) && string.Equals(gid, Current, StringComparison.Ordinal) && !_ended.Contains(gid);
            }

            /// <summary>Adoption, only from a relayed property value (the
            /// writer's own echo included). An ended or malformed value is not
            /// adopted. Answers whether the value is now the live gid.</summary>
            internal bool AdoptRelayed(string relayed)
            {
                if (!IsGid(relayed) || _ended.Contains(relayed)) return false;
                Current = relayed;
                return true;
            }

            /// <summary>The terminal path ends the gid; it is never live again.</summary>
            internal void EndGid(string gid)
            {
                if (!IsGid(gid)) return;
                _ended.Add(gid);
                if (string.Equals(gid, Current, StringComparison.Ordinal)) Current = null;
            }

            /// <summary>At the seat's own game start: its previous gid ends, then
            /// it adopts the room's value unless it has ended that value.</summary>
            internal bool AtOwnGameStart(string roomValue)
            {
                if (Current != null) EndGid(Current);
                return AdoptRelayed(roomValue);
            }

            internal void ExitRoom()
            {
                _ended.Clear();
                Current = null;
            }
        }

        /// <summary>
        /// Who mints (4.2, F1): the master, at its own game start or when it
        /// becomes master after that start while it holds no live gid, and only
        /// when the room's value is one this seat has ended (or none). A value
        /// it has not ended is adopted instead: a master that left between two
        /// seats' starts may have minted it.
        /// </summary>
        internal static bool ShouldMint(bool isMaster, bool afterOwnStart, string roomValue, GidLedger ledger)
        {
            if (!isMaster || !afterOwnStart || ledger == null) return false;
            if (ledger.IsLiveGid(ledger.Current)) return false;
            return !IsGid(roomValue) || ledger.HasEnded(roomValue);
        }

        // ------------------------------------------------------------------ the record and its carriers (4.3, F11)

        /// <summary>4.3's record as every carrier holds it: the decision and
        /// round messages, the mirror `cr_lrec` and the master's snapshot. The
        /// base result is the winner, the winner's rounds, the most rounds of
        /// any other side (GM: the loser's; FFA: the runner-up's) and the base
        /// target.</summary>
        internal struct Record
        {
            internal string Gid;
            internal int Target;
            internal bool End;
            internal int BaseWinner;
            internal int BaseWinnerRounds;
            internal int BaseOtherRounds;
            internal int BaseTarget;
            internal bool Spectatable;
        }

        /// <summary>The number of slots in every carrier.</summary>
        internal const int WireSlots = 11;

        /// <summary>One format for every carrier: [version, gid, target, end,
        /// winner, winner's rounds, other rounds, base target, spectatable,
        /// roster, round arguments]. A round message carries the round's six
        /// arguments; the decision also carries its roster; the mirror and the
        /// snapshot carry neither (empty arrays).</summary>
        internal static object[] EncodeRecord(Record r, int[] roster, int[] args)
        {
            return new object[]
            {
                WireVersion, r.Gid, r.Target, r.End, r.BaseWinner, r.BaseWinnerRounds, r.BaseOtherRounds,
                r.BaseTarget, r.Spectatable, roster ?? new int[0], args ?? new int[0],
            };
        }

        /// <summary>Every slot is required and typed; a carrier missing any
        /// field of 4.3 is refused whole (F11).</summary>
        internal static bool TryDecodeRecord(object[] o, out Record r, out int[] roster, out int[] args)
        {
            r = default(Record);
            roster = null;
            args = null;
            if (o == null || o.Length != WireSlots) return false;
            if (!(o[0] is int) || (int)o[0] != WireVersion) return false;
            var gid = o[1] as string;
            if (!IsGid(gid)) return false;
            if (!(o[2] is int) || (int)o[2] < 1) return false;
            if (!(o[3] is bool)) return false;
            if (!(o[4] is int) || (int)o[4] < 0) return false;
            if (!(o[5] is int) || (int)o[5] < 0) return false;
            if (!(o[6] is int) || (int)o[6] < 0) return false;
            if (!(o[7] is int) || (int)o[7] < 1) return false;
            if (!(o[8] is bool)) return false;
            var ro = o[9] as int[];
            var ar = o[10] as int[];
            if (ro == null || ar == null) return false;
            if (ar.Length != 0 && ar.Length != 6) return false;
            var seen = new HashSet<int>();
            foreach (var a in ro)
                if (a <= 0 || !seen.Add(a)) return false;
            r = new Record
            {
                Gid = gid, Target = (int)o[2], End = (bool)o[3], BaseWinner = (int)o[4], BaseWinnerRounds = (int)o[5],
                BaseOtherRounds = (int)o[6], BaseTarget = (int)o[7], Spectatable = (bool)o[8],
            };
            roster = ro;
            args = ar;
            return true;
        }

        /// <summary>D1: the target while a record is live.</summary>
        internal static int ContinueTarget(int baseTarget)
        {
            return baseTarget + ExtraRounds;
        }

        /// <summary>5.1: an explicit end's target is the smallest round count of
        /// any side, as the master holds it at the send, plus 1, and at least 1
        /// (the GM spectator reads 0 or less as 5). The side that completes the
        /// next round then holds at least this many, whichever side it is.</summary>
        internal static int EndTarget(IList<int> sideRounds)
        {
            if (sideRounds == null || sideRounds.Count == 0) return 1;
            int min = int.MaxValue;
            foreach (var n in sideRounds)
                if (n < min) min = n;
            return Math.Max(1, min + 1);
        }

        /// <summary>4.3: live, then terminating, then ended; never back.</summary>
        internal static State NextState(State current, bool endFlag)
        {
            if (current == State.Ended) return State.Ended;
            if (current == State.Terminating || endFlag) return State.Terminating;
            return State.Live;
        }

        // ------------------------------------------------------------------ authority (4.4, 4.5)

        /// <summary>4.4: immediately before every send, after any yield or wait.</summary>
        internal static bool MaySend(bool isMasterNow, bool gidCurrentAndLive, bool recordEnded,
                                     int epochNow, int epochCaptured, int handoffNow, int handoffCaptured)
        {
            return isMasterNow && gidCurrentAndLive && !recordEnded
                   && epochNow == epochCaptured && handoffNow == handoffCaptured;
        }

        /// <summary>4.5 (R): at each resume point. The epoch is unchanged and,
        /// for an item that captured a gid, that gid is still the seat's live gid
        /// and its record is not ended. An item that captured no gid never waits
        /// for one.</summary>
        internal static bool MayResume(int epochNow, int epochCaptured, string capturedGid, GidLedger ledger,
                                       bool recordEnded)
        {
            if (epochNow != epochCaptured) return false;
            if (capturedGid == null) return true;
            return ledger != null && ledger.IsLiveGid(capturedGid) && !recordEnded;
        }

        /// <summary>4.5 (C, F12): cleanup the game owns reads the epoch only.</summary>
        internal static bool MayClean(int epochNow, int epochCaptured)
        {
            return epochNow == epochCaptured;
        }

        /// <summary>4.4, F3: while a seat holds a live or terminating record,
        /// every vanilla round call the fence's handler did not make is refused,
        /// by every sibling that changes state on that call.</summary>
        internal static bool RefuseRawRound(bool hasRecord, State state, bool fenceCall)
        {
            return hasRecord && state != State.Ended && !fenceCall;
        }

        // ------------------------------------------------------------------ the decision (4.7)

        internal enum Decision { Continue, NotMaySend, NoLiveGid, HasRecord, NoFighters, OptIn, Capability, Hold, Series }

        /// <summary>The master's inputs at the round that would end the game at
        /// the base. Every list is read from replicated room state.</summary>
        internal sealed class DecisionInputs
        {
            internal bool MaySend;
            internal string LiveGid;
            internal bool HasRecord;
            internal IList<string> FighterOptIns;
            internal IList<string> ActorCapabilities;
            internal string MasterVersion;
            internal bool HoldHasHeldSeat;
            internal bool HoldHasPendingCut;
            internal bool SeriesFollows;
        }

        /// <summary>4.7: all five must hold. The first that fails names the answer.</summary>
        internal static Decision DecideContinuation(DecisionInputs d)
        {
            if (d == null || !d.MaySend) return Decision.NotMaySend;
            if (!IsGid(d.LiveGid)) return Decision.NoLiveGid;
            if (d.HasRecord) return Decision.HasRecord;
            var why = ContinuationQuorum(d.FighterOptIns, d.LiveGid, d.ActorCapabilities, d.MasterVersion);
            if (why != Decision.Continue) return why;
            if (d.HoldHasHeldSeat || d.HoldHasPendingCut) return Decision.Hold;
            if (d.SeriesFollows) return Decision.Series;
            return Decision.Continue;
        }

        /// <summary>Every fighter's opt-in names the gid, and every actor in the
        /// room, spectators included, advertises the master's own version. An
        /// empty list fails closed.</summary>
        internal static Decision ContinuationQuorum(IList<string> fighterOptIns, string gid, IList<string> actorCapabilities,
                                        string masterVersion)
        {
            if (fighterOptIns == null || fighterOptIns.Count == 0) return Decision.NoFighters;
            foreach (var o in fighterOptIns)
                if (!string.Equals(o, gid, StringComparison.Ordinal)) return Decision.OptIn;
            if (actorCapabilities == null || actorCapabilities.Count == 0 || string.IsNullOrEmpty(masterVersion))
                return Decision.Capability;
            foreach (var c in actorCapabilities)
                if (!string.Equals(c, masterVersion, StringComparison.Ordinal)) return Decision.Capability;
            return Decision.Continue;
        }

        /// <summary>4.7: at every round message past the decision the master
        /// re-reads the opt-ins, the capabilities and its handoff count. A change
        /// in any of them is an end (lesson 273).</summary>
        internal static bool MustEnd(IList<string> fighterOptIns, string gid, IList<string> actorCapabilities,
                                     string masterVersion, int handoffNow, int handoffAtDecision)
        {
            if (handoffNow != handoffAtDecision) return true;
            return ContinuationQuorum(fighterOptIns, gid, actorCapabilities, masterVersion) != Decision.Continue;
        }

        // ------------------------------------------------------------------ the handler (4.7)

        internal enum Outcome { RefuseNotMaster, RefuseUncovered, DropTransition, ApplyAsVanilla, Create, Update }

        internal sealed class HandlerInputs
        {
            internal bool SenderIsMasterNow;
            internal string MessageGid;
            internal GidLedger Ledger;
            internal bool HasRecord;
            internal bool RecordEnded;
            internal bool TransitionGuardDrops;
            internal int[] DecisionRoster;
            internal IList<int> OwnFighterRoster;
        }

        /// <summary>
        /// 4.7's order on every seat: (1) the sender is the master now, else
        /// nothing applies; (2) the gid is live here and its record is not ended,
        /// else the fence does not cover it and the seat takes its terminal path;
        /// (3) vanilla's transition guard, before the record changes; (4) a seat
        /// with no record compares the decision roster with its own replicated
        /// roster: equal creates the record, unequal applies vanilla's round at
        /// the base. A seat with no record and no roster is not covered.
        /// </summary>
        internal static Outcome HandleFenceMessage(HandlerInputs h)
        {
            if (h == null || !h.SenderIsMasterNow) return Outcome.RefuseNotMaster;
            if (h.Ledger == null || !h.Ledger.IsLiveGid(h.MessageGid) || h.RecordEnded) return Outcome.RefuseUncovered;
            if (h.TransitionGuardDrops) return Outcome.DropTransition;
            if (h.HasRecord) return Outcome.Update;
            if (h.DecisionRoster == null || h.DecisionRoster.Length == 0) return Outcome.RefuseUncovered;
            return RosterMatches(h.DecisionRoster, h.OwnFighterRoster) ? Outcome.Create : Outcome.ApplyAsVanilla;
        }

        /// <summary>F4: the decision roster against the seat's own replicated
        /// fighter roster, as sets. Both read server-ordered inputs only, so every
        /// seat, the sender's echo included, gets the same answer.</summary>
        internal static bool RosterMatches(int[] decisionRoster, IList<int> ownFighters)
        {
            if (decisionRoster == null || ownFighters == null || decisionRoster.Length == 0) return false;
            var mine = new HashSet<int>(ownFighters);
            var theirs = new HashSet<int>(decisionRoster);
            if (mine.Count != ownFighters.Count || theirs.Count != decisionRoster.Length) return false;
            return theirs.SetEquals(mine);
        }
    }
}
