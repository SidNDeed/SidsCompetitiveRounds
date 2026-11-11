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

        /// <summary>The wire format's version (index 0 of every carrier): the
        /// feature's protocol, LimitlessBounds.Protocol, which cr_lim1 carries
        /// in its value. A change to the format bumps the protocol, so the
        /// decision's capability quorum never continues with a seat on another
        /// format.</summary>
        internal const int WireVersion = LimitlessBounds.Protocol;

        /// <summary>4.3: the states go one way, live, then terminating, then ended.</summary>
        internal enum FencePhase { PhaseLive = 0, PhaseTerminating = 1, PhaseEnded = 2 }

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
        /// seat. Room exit ends the current gid, and the ended set lasts the
        /// session, so a rejoin of the same room never revives one.
        /// </summary>
        internal sealed class GidLedger
        {
            private readonly HashSet<string> _ended = new HashSet<string>(StringComparer.Ordinal);

            /// <summary>The seat's current gid, or null while it holds none.</summary>
            internal string CurrentGid { get; private set; }

            internal bool HasEnded(string gid) { return gid != null && _ended.Contains(gid); }

            /// <summary>Live: current, and not ended on this seat.</summary>
            internal bool IsLiveGid(string gid)
            {
                return IsGid(gid) && string.Equals(gid, CurrentGid, StringComparison.Ordinal) && !_ended.Contains(gid);
            }

            /// <summary>Adoption, only from a relayed property value (the
            /// writer's own echo included). An ended or malformed value is not
            /// adopted. A gid it replaces ends: a record of any other gid is dead
            /// (4.3). Answers whether the value is now the live gid.</summary>
            internal bool AdoptRelayed(string relayed)
            {
                if (!IsGid(relayed) || _ended.Contains(relayed)) return false;
                if (CurrentGid != null && !string.Equals(CurrentGid, relayed, StringComparison.Ordinal)) _ended.Add(CurrentGid);
                CurrentGid = relayed;
                return true;
            }

            /// <summary>The terminal path ends the gid; it is never live again.</summary>
            internal void EndGid(string gid)
            {
                if (!IsGid(gid)) return;
                _ended.Add(gid);
                if (string.Equals(gid, CurrentGid, StringComparison.Ordinal)) CurrentGid = null;
            }

            /// <summary>At the seat's own game start: its previous gid ends, then
            /// it adopts the room's value unless it has ended that value.</summary>
            internal bool AtOwnGameStart(string roomValue)
            {
                if (CurrentGid != null) EndGid(CurrentGid);
                return AdoptRelayed(roomValue);
            }

            /// <summary>Room exit is a terminal path (5.3): the current gid ends.</summary>
            internal void ExitRoom()
            {
                if (CurrentGid != null) EndGid(CurrentGid);
                CurrentGid = null;
            }
        }

        /// <summary>
        /// Who mints (4.2, F1): the master, at its own game start or when it
        /// becomes master after that start while it holds no live gid, and only
        /// when the room's value is one this seat has ended. A value it has not
        /// ended is adopted instead: a master that left between two seats'
        /// starts may have minted it. A room created without a gid never runs
        /// the feature, so nothing mints there.
        /// </summary>
        internal static bool ShouldMint(bool isMaster, bool afterOwnStart, string roomValue, GidLedger ledger)
        {
            if (!isMaster || !afterOwnStart || ledger == null) return false;
            if (ledger.IsLiveGid(ledger.CurrentGid)) return false;
            return IsGid(roomValue) && ledger.HasEnded(roomValue);
        }

        /// <summary>
        /// 4.2: who adopts a value when its change arrives. A seat that awaits
        /// one (after its own game start or at its join, holding no live gid)
        /// adopts it, and so does a spectator: it never mints or opts in, and its
        /// game opens at its first call-in after the terminal score. A fighter
        /// that is not awaiting keeps its gid. A value that arrives before its
        /// own next start belongs to that game, and the start reads it from the
        /// room.
        /// </summary>
        internal static bool AdoptOnArrival(bool awaiting, bool spectator, string value, GidLedger ledger)
        {
            if (ledger == null || !IsGid(value) || ledger.HasEnded(value)) return false;
            if (string.Equals(value, ledger.CurrentGid, StringComparison.Ordinal)) return false;
            return awaiting || spectator;
        }

        // ------------------------------------------------------------------ the record and its carriers (4.3, F11)

        /// <summary>4.3's record as every carrier holds it: the decision and
        /// round messages, the mirror `cr_lrec` and the master's snapshot. The
        /// base result is the winner, the winner's rounds, the most rounds of
        /// any other side (GM: the loser's; FFA: the runner-up's) and the base
        /// target.</summary>
        internal struct FenceRecord
        {
            internal string Gid;
            internal int TargetRounds;
            internal bool EndFlag;
            internal int BaseWinner;
            internal int BaseWinnerRounds;
            internal int BaseOtherRounds;
            internal int BaseTarget;
            internal bool Spectatable;
        }

        /// <summary>The number of slots in every carrier.</summary>
        internal const int WireSlots = 12;

        /// <summary>One format for every carrier: [version, gid, target, end,
        /// winner, winner's rounds, other rounds, base target, spectatable,
        /// roster, round arguments, send stamp]. A round message carries the
        /// round's six arguments and its sender's ServerTimestamp at the raise
        /// (the value PUN writes into an RPC as key 2), so every seat applies
        /// the round under one stamp; the decision also carries its roster;
        /// the mirror and the snapshot carry neither (empty arrays, stamp 0).</summary>
        internal static object[] EncodeRecord(FenceRecord r, int[] roster, int[] args, int stamp)
        {
            return new object[]
            {
                WireVersion, r.Gid, r.TargetRounds, r.EndFlag, r.BaseWinner, r.BaseWinnerRounds, r.BaseOtherRounds,
                r.BaseTarget, r.Spectatable, roster ?? new int[0], args ?? new int[0], stamp,
            };
        }

        /// <summary>Every slot is required and typed; a carrier missing any
        /// field of 4.3 is refused whole (F11).</summary>
        internal static bool TryDecodeRecord(object[] o, out FenceRecord r, out int[] roster, out int[] args, out int stamp)
        {
            r = default(FenceRecord);
            roster = null;
            args = null;
            stamp = 0;
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
            if (!(o[11] is int)) return false;
            var seen = new HashSet<int>();
            foreach (var a in ro)
                if (a <= 0 || !seen.Add(a)) return false;
            r = new FenceRecord
            {
                Gid = gid, TargetRounds = (int)o[2], EndFlag = (bool)o[3], BaseWinner = (int)o[4], BaseWinnerRounds = (int)o[5],
                BaseOtherRounds = (int)o[6], BaseTarget = (int)o[7], Spectatable = (bool)o[8],
            };
            roster = ro;
            args = ar;
            stamp = (int)o[11];
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
        internal static FencePhase NextState(FencePhase current, bool endFlag)
        {
            if (current == FencePhase.PhaseEnded) return FencePhase.PhaseEnded;
            if (current == FencePhase.PhaseTerminating || endFlag) return FencePhase.PhaseTerminating;
            return FencePhase.PhaseLive;
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

        /// <summary>4.5 (R, C): a scheduled item runs only while mayContinue
        /// holds, read before every step, nested enumerators included, which run
        /// under the same test. An item that fails it stops: onStop runs, and the
        /// item's finally blocks run (Dispose). Every other yielded value passes
        /// through unchanged.</summary>
        internal static System.Collections.IEnumerator GuardScheduled(System.Collections.IEnumerator item,
                                                                     Func<bool> mayContinue, Action onStop)
        {
            if (item == null) yield break;
            try
            {
                while (true)
                {
                    if (!mayContinue())
                    {
                        if (onStop != null) onStop();
                        yield break;
                    }
                    if (!item.MoveNext()) yield break;
                    var nested = item.Current as System.Collections.IEnumerator;
                    yield return nested != null ? GuardScheduled(nested, mayContinue, onStop) : item.Current;
                }
            }
            finally
            {
                var d = item as IDisposable;
                if (d != null) d.Dispose();
            }
        }

        /// <summary>4.4 at FFA's pick sends (integrator ruling, 01:14Z): a seat
        /// that is master under a handoff count other than its ticket's is in a
        /// new master period. It takes the promotion path again, then captures a
        /// fresh ticket. Keyed on the count, not on a role change, so a lost and
        /// regained mastership counts. Only while the fence applies, when the
        /// ticket names a gid or a record is open; otherwise the pick phase runs
        /// as today (F1).</summary>
        internal static bool HandoffPeriodMoved(bool masterNow, bool fenceApplies, int handoffNow, int handoffCaptured)
        {
            return masterNow && fenceApplies && handoffNow != handoffCaptured;
        }

        /// <summary>4.4, F3: while a seat holds a live or terminating record,
        /// every vanilla round call the fence's handler did not make is refused,
        /// by every sibling that changes state on that call.</summary>
        internal static bool RefuseRawRound(bool hasRecord, FencePhase state, bool fenceCall)
        {
            return hasRecord && state != FencePhase.PhaseEnded && !fenceCall;
        }

        // ------------------------------------------------------------------ the decision (4.7)

        internal enum Decision { Continue, NotMaySend, NoLiveGid, HasRecord, NoFighters, OptIn, Capability, Hold, SeriesNext }

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
            if (d.SeriesFollows) return Decision.SeriesNext;
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

        /// <summary>4.7: the round that ends the game at a target
        /// (GM_ArmsRace:533-585): the winner's point completes its round and
        /// that round reaches the target. The counts are the master's at the
        /// send, the ones its message carries; every seat adds the point when it
        /// applies the round.</summary>
        internal static bool RoundEndsGame(int winnerPoints, int winnerRounds, int pointsToWinRound, int targetRounds)
        {
            return winnerPoints + 1 >= pointsToWinRound && winnerRounds + 1 >= targetRounds;
        }

        /// <summary>4.7: the decision message's record. The target is base + N
        /// and the end flag is clear. The base result is the master's at the
        /// send: the winner, its rounds once this round completes, the other
        /// side's rounds, and the base target. The spectatable flag is latched
        /// here (Table C2, GameStateWatcher.cs:1552).</summary>
        internal static FenceRecord DecisionRecord(string gid, int baseTarget, int winner, int winnerRounds,
                                                   int otherRounds, bool spectatable)
        {
            return new FenceRecord
            {
                Gid = gid, TargetRounds = ContinueTarget(baseTarget), EndFlag = false,
                BaseWinner = winner, BaseWinnerRounds = winnerRounds + 1, BaseOtherRounds = otherRounds,
                BaseTarget = baseTarget, Spectatable = spectatable,
            };
        }

        /// <summary>4.7 and 5.1: the record the master's next round message
        /// carries. Once an end is decided, every later message carries the same
        /// record. A live record that must end carries the end flag and the end
        /// target from the side rounds the message itself carries. Otherwise the
        /// record is unchanged.</summary>
        internal static FenceRecord NextSendRecord(FenceRecord current, bool mustEnd, IList<int> sideRounds)
        {
            if (current.EndFlag || !mustEnd) return current;
            var next = current;
            next.EndFlag = true;
            next.TargetRounds = EndTarget(sideRounds);
            return next;
        }

        /// <summary>D5, read closed (integrator ruling 23:45Z, a deviation from
        /// D5's stated default, which lets a series' deciding game continue):
        /// another rated game of this series follows. No input tells the master
        /// that reliably mid-game (the series counts lag), so a rated game in a
        /// mode that keeps a series (1v1, 2v2, 1v2) is always followed by
        /// another. FFA keeps no series, and an unrated game has none.</summary>
        internal static bool SeriesFollows(bool rated, bool modeKeepsSeries)
        {
            return rated && modeKeepsSeries;
        }

        // ------------------------------------------------------------------ the handler (4.7)

        internal enum HandlerOutcome { RefuseNotMaster, RefuseUncovered, DropTransition, ApplyAsVanilla, CreateRecord, UpdateRecord }

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
        internal static HandlerOutcome HandleFenceMessage(HandlerInputs h)
        {
            if (h == null || !h.SenderIsMasterNow) return HandlerOutcome.RefuseNotMaster;
            if (h.Ledger == null || !h.Ledger.IsLiveGid(h.MessageGid) || h.RecordEnded) return HandlerOutcome.RefuseUncovered;
            if (h.TransitionGuardDrops) return HandlerOutcome.DropTransition;
            if (h.HasRecord) return HandlerOutcome.UpdateRecord;
            if (h.DecisionRoster == null || h.DecisionRoster.Length == 0) return HandlerOutcome.RefuseUncovered;
            return RosterMatches(h.DecisionRoster, h.OwnFighterRoster) ? HandlerOutcome.CreateRecord : HandlerOutcome.ApplyAsVanilla;
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
