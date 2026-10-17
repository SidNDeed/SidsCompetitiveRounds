using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 (2v2 and 1v2 mid-game readmission): the pure rules. No Unity,
    /// Photon or Harmony type appears here, so tools/tests/rj-stage2-client
    /// compiles this file as it ships and executes every rule. The glue that
    /// reads the room and acts lives in TeamHoldPatches.cs, TeamHoldWriter.cs,
    /// TeamHoldFence.cs, TeamHoldReturn.cs, TeamHoldPick.cs, TeamHoldExpiry.cs
    /// and Plugin.cs.
    ///
    /// Every rule here fails toward the outcome of today: an unpinned room, an
    /// unreadable key, an exception, a missing answer all answer "run today".
    /// </summary>
    internal static class TeamHoldRules
    {
        internal const string MODE_TEAM = "team";
        internal const string MODE_OVT = "ovt";

        internal const string KEY_TH = "cr_th";
        internal const string KEY_TRD = "cr_trd";
        internal const string KEY_TGID = "cr_tgid";
        internal const string KEY_VLEAVE = "cr_vleave";
        internal const string KEY_SPEC = "cr_spec";

        /// <summary>Team of a slot in a mode: team, slot / 2; ovt, solo slot 0
        /// is team 0 and the duo team 1 (Diag2v2.SlotToTeam, B:plugin/Plugin.cs:4256-4263).</summary>
        internal static int SlotToTeam(string mode, int slot)
        {
            if (slot < 0) return -1;
            if (mode == MODE_TEAM) return slot / 2;
            if (mode == MODE_OVT) return slot == 0 ? 0 : 1;
            return -1;
        }

        internal static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }

        internal static int ParseInt(string s, int dflt)
        {
            int v;
            return int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out v) ? v : dflt;
        }

        // ── The pin store (S1 step 2). Filled ONLY by KX1 from the server's
        //    join, poll, Start and claim answers; at this lane tip nothing
        //    pins, so every room reads unflagged and nothing changes. ───────

        internal sealed class Pin
        {
            internal string Room;
            internal bool Hold;
            internal string Mode;
            internal string SeriesId;
            internal readonly HashSet<string> Roster = new HashSet<string>(StringComparer.Ordinal);
        }

        private static readonly Dictionary<string, Pin> _pins = new Dictionary<string, Pin>(StringComparer.Ordinal);

        /// <summary>The client pins (room, hold, roster) from the server answer
        /// naming the room. A written pin never changes for its room.</summary>
        internal static void PinRoom(string room, bool hold, string mode, string seriesId, IEnumerable<string> roster)
        {
            if (string.IsNullOrEmpty(room) || _pins.ContainsKey(room)) return;
            var p = new Pin { Room = room, Hold = hold, Mode = mode, SeriesId = seriesId };
            if (roster != null) foreach (var r in roster) if (!string.IsNullOrEmpty(r)) p.Roster.Add(r);
            _pins[room] = p;
        }

        internal static Pin PinFor(string room)
        {
            Pin p;
            return room != null && _pins.TryGetValue(room, out p) ? p : null;
        }

        /// <summary>A flagged room: pinned with the hold flag true and a known mode.</summary>
        internal static bool Flagged(string room)
        {
            var p = PinFor(room);
            return p != null && p.Hold && (p.Mode == MODE_TEAM || p.Mode == MODE_OVT);
        }

        internal static void ClearPins() { _pins.Clear(); }

        // ── Room keys ──────────────────────────────────────────────────────

        /// <summary>cr_th = {hold_id}:{slot}:{team}:{G}:{state}:{seq}:{hold_s}:{writer}:{bound_actor}.</summary>
        internal sealed class HoldKey
        {
            internal string HoldId = "";
            internal int Slot = -1;
            internal int Team = -1;
            internal string G = "";
            internal char State;
            internal int Seq;
            internal int HoldS;
            internal int Writer;
            internal int BoundActor;

            internal string Format()
            {
                return (HoldId ?? "") + ":" + I(Slot) + ":" + I(Team) + ":" + (G ?? "") + ":" + State + ":" + I(Seq)
                       + ":" + I(HoldS) + ":" + I(Writer) + ":" + I(BoundActor);
            }

            internal HoldKey With(char state, int seq)
            {
                return new HoldKey { HoldId = HoldId, Slot = Slot, Team = Team, G = G, State = state, Seq = seq,
                                     HoldS = HoldS, Writer = Writer, BoundActor = BoundActor };
            }
        }

        internal static bool TryParseHold(string s, out HoldKey key)
        {
            key = null;
            if (string.IsNullOrEmpty(s)) return false;
            var f = s.Split(':');
            if (f.Length != 9 || f[4].Length != 1 || "pocbex".IndexOf(f[4][0]) < 0) return false;
            key = new HoldKey
            {
                HoldId = f[0], Slot = ParseInt(f[1], -1), Team = ParseInt(f[2], -1), G = f[3], State = f[4][0],
                Seq = ParseInt(f[5], -1), HoldS = ParseInt(f[6], 0), Writer = ParseInt(f[7], 0), BoundActor = ParseInt(f[8], 0),
            };
            return key.Slot >= 0 && key.Seq >= 0 && !string.IsNullOrEmpty(key.G);
        }

        /// <summary>The waiting states: pending, offered, claimed, bound.</summary>
        internal static bool IsLive(char state) { return state == 'p' || state == 'o' || state == 'c' || state == 'b'; }

        internal static bool ThLive(string th)
        {
            HoldKey k;
            return TryParseHold(th, out k) && IsLive(k.State);
        }

        /// <summary>cr_trd: append-only `{G}:{slot}:{kind};...`, kind h or r.</summary>
        internal static bool TrdHas(string trd, string g, int slot)
        {
            if (string.IsNullOrEmpty(trd) || string.IsNullOrEmpty(g)) return false;
            string prefix = g + ":" + I(slot) + ":";
            foreach (var e in trd.Split(';'))
                if (e.StartsWith(prefix, StringComparison.Ordinal)) return true;
            return false;
        }

        internal static string TrdAppend(string trd, string g, int slot, char kind)
        {
            string e = g + ":" + I(slot) + ":" + kind;
            if (!string.IsNullOrEmpty(trd))
                foreach (var x in trd.Split(';')) if (x == e) return trd;
            return string.IsNullOrEmpty(trd) ? e : trd + ";" + e;
        }

        /// <summary>cr_tgid = {G}:s while the game runs, {G}:g after its game-over edge.</summary>
        internal static bool GidStarted(string tgid, out string g)
        {
            g = null;
            if (string.IsNullOrEmpty(tgid)) return false;
            int i = tgid.LastIndexOf(':');
            if (i <= 0 || i != tgid.Length - 2 || tgid[i + 1] != 's') return false;
            g = tgid.Substring(0, i);
            return true;
        }

        internal static string GidValue(string g, bool started) { return g + (started ? ":s" : ":g"); }

        // ── The classifier (S1 step 5) ─────────────────────────────────────

        /// <summary>What the classifier reads about a departure. The first
        /// group comes from replicated keys or the pinned server answer and
        /// is the whole input of the rule. The second group are observations
        /// a client also has but the classifier must NOT read (V3 S1 step 5):
        /// an in-room capability quorum, the local authorization caches, the
        /// room name. They are carried so the harness states that rule as an
        /// executable fact.</summary>
        internal sealed class GateInputs
        {
            internal Pin Pin;
            internal bool IsSpec;
            internal string Uid;
            internal int Slot = -1;
            internal string Tgid;
            internal string Trd;
            internal string Th;
            internal bool VLeave;
            internal bool SlotMarked;
            // never read
            internal bool QuorumCapable;
            internal bool LocalUnauthorized;
            internal bool LocalInMatch;
            internal string RoomName;
        }

        internal static class HoldGate
        {
            private static readonly Dictionary<int, bool> _memo = new Dictionary<int, bool>();

            /// <summary>Suppress only when every condition holds.</summary>
            internal static bool Decide(GateInputs i)
            {
                if (i == null || i.Pin == null || !i.Pin.Hold) return false;
                string mode = i.Pin.Mode;
                if (mode != MODE_TEAM && mode != MODE_OVT) return false;
                if (i.IsSpec) return false;
                if (string.IsNullOrEmpty(i.Uid) || !i.Pin.Roster.Contains(i.Uid)) return false;
                if (i.Slot < 0 || SlotToTeam(mode, i.Slot) < 0) return false;
                string g;
                if (!GidStarted(i.Tgid, out g)) return false;
                if (i.VLeave) return false;
                if (TrdHas(i.Trd, g, i.Slot)) return false;
                if (ThLive(i.Th)) return false;
                if (i.SlotMarked) return false;
                return true;
            }

            /// <summary>Memoised per actor number: computed once by whichever
            /// runs first of the cascade prefix and the mod leave callback;
            /// both read the memo. Any exception answers today.</summary>
            internal static bool DecideOnce(int actor, Func<GateInputs> read)
            {
                bool r;
                if (_memo.TryGetValue(actor, out r)) return r;
                try { r = Decide(read()); }
                catch { r = false; }
                _memo[actor] = r;
                return r;
            }

            internal static bool Known(int actor, out bool suppress) { return _memo.TryGetValue(actor, out suppress); }

            internal static void Clear() { _memo.Clear(); }
        }

        // ── The point in flight (S1 step 8) ────────────────────────────────

        internal enum Resolve { Wait, Nothing, NextRound }

        /// <summary>How the resolver ends a point the leaver lost: the master
        /// arm of vanilla GM_ArmsRace.PlayerDied, statement for statement
        /// (V:GM_ArmsRace.cs:505-511). PlayerDied itself is never called: its
        /// first statement dereferences the departed body (501-504).</summary>
        internal const bool ViaMasterArm = true;

        /// <summary>The purge waits 0.7 s after the leave (learning 222).</summary>
        internal const double PurgeDelay = 0.7;

        /// <summary>Resolution waits for leave plus 0.7 s AND an observed hold
        /// state p, o or x for this drop (RJS-M2); then, over the purged list,
        /// a point still in battle with fewer than two teams alive resolves.</summary>
        internal static Resolve PointAfterLeave(double sinceLeave, char observed, bool battleOngoing, int teamsAlive)
        {
            if (sinceLeave < PurgeDelay) return Resolve.Wait;
            if (observed != 'p' && observed != 'o' && observed != 'x') return Resolve.Wait;
            if (!battleOngoing || teamsAlive >= 2) return Resolve.Nothing;
            return Resolve.NextRound;
        }

        /// <summary>The master arm's arguments: RPCA_NextRound(losing, winning,
        /// ...) with winning = the last team alive and losing = the other of
        /// the two teams (vanilla GetOtherTeam for teams 0 and 1).</summary>
        internal static void MasterArm(int lastTeamAlive, out int losing, out int winning)
        {
            winning = lastTeamAlive;
            losing = lastTeamAlive == 0 ? 1 : 0;
        }

        /// <summary>Convergence (S1 step 6): any further fighter departure
        /// while a hold waits ends it into the expiry on every client.</summary>
        internal static bool SecondDepartureEnds(bool holdWaiting, bool leaverIsFighter)
        {
            return holdWaiting && leaverIsFighter;
        }

        // ── The 2v2 DC election of today, as a pure rule (S1 step 7) ───────

        internal enum DcKind { Nothing, StandDown, Prompt, Fallback, Floor }

        /// <summary>A survivor as the census arm of the leave callback reads
        /// it (B:plugin/Plugin.cs, the leave callback's election).</summary>
        internal struct DcSurvivor
        {
            public long Sid;     // -1 unreadable
            public int Team;     // -1 unreadable
            public bool Local;
            public int Actor;
            public DcSurvivor(long sid, int team, bool local, int actor) { Sid = sid; Team = team; Local = local; Actor = actor; }
        }

        internal sealed class DcResult
        {
            internal DcKind Kind;
            internal bool Unique;
            internal bool TeamsKnown;
            internal bool RoomWide;
            internal int MissingCap = -1;
            internal long LowestNonDc = long.MaxValue;
            internal int ElectedActor = -1;
            internal bool OnFloor;
            internal bool ConsistentView;
        }

        /// <summary>This survivor's own reporter eligibility, exactly the rule
        /// the leave callback runs today: the census arm (prompt reporter,
        /// fallback watcher of the elected seat, or the leaver's team standing
        /// down) when the replicated census proves the rule room-wide, else
        /// the floor of DcReporterElection.ShouldReport. Executes nothing.</summary>
        internal static DcResult DecideDc(long myVal, int myTeam, int dcTeam, long dcId, bool roomWide, int missingCap,
                                          IList<DcSurvivor> survivors, IEnumerable<DcReporterElection.Peer> floorCensus)
        {
            var r = new DcResult { RoomWide = roomWide, MissingCap = missingCap };
            r.TeamsKnown = dcTeam >= 0 && myTeam >= 0;
            int count = survivors != null ? survivors.Count : 0;
            bool unique = r.TeamsKnown && count == 3 && roomWide;
            int nonDcCount = 0, dcTeamCount = 1;
            var seen = new HashSet<long>();
            bool sawSelf = false;
            long lowest = long.MaxValue;
            if (unique)
            {
                if (dcId < 0) unique = false; else seen.Add(dcId);
            }
            if (unique)
            {
                for (int i = 0; i < count; i++)
                {
                    var s = survivors[i];
                    if (s.Sid < 0 || s.Team < 0 || !seen.Add(s.Sid)) { unique = false; break; }
                    if (s.Local) { sawSelf = true; if (s.Sid != myVal) { unique = false; break; } }
                    if (s.Team == dcTeam) dcTeamCount++;
                    else { nonDcCount++; if (s.Sid < lowest) lowest = s.Sid; }
                }
            }
            if (unique && (!sawSelf || dcTeamCount != 2 || nonDcCount != 2)) unique = false;
            r.Unique = unique;
            r.LowestNonDc = lowest;
            if (unique)
            {
                if (myTeam == dcTeam) { r.Kind = DcKind.StandDown; return r; }
                if (myVal == lowest) { r.Kind = DcKind.Prompt; return r; }
                for (int i = 0; i < count; i++)
                    if (survivors[i].Sid == lowest) { r.ElectedActor = survivors[i].Actor; break; }
                r.Kind = DcKind.Fallback;
                return r;
            }
            // Materialised once, here: the floor census is read only when arm
            // (1) is refused, and ShouldReport walks it twice.
            var census = floorCensus != null ? new List<DcReporterElection.Peer>(floorCensus) : new List<DcReporterElection.Peer>();
            bool onFloor, teamsKnown2, consistent;
            bool report = DcReporterElection.ShouldReport(myVal, myTeam, dcTeam, census, out onFloor, out teamsKnown2, out consistent);
            r.OnFloor = onFloor;
            r.ConsistentView = consistent;
            r.Kind = report ? DcKind.Floor : DcKind.Nothing;
            return r;
        }

        // ── The drop cut (S1 step 7) ───────────────────────────────────────

        /// <summary>Every input the outcome of today reads, latched on this
        /// client in the leave frame, before the body goes. Read only by the
        /// expiry (S5).</summary>
        internal sealed class DropCut
        {
            internal string Room;
            internal string Mode;
            internal string G;
            internal string SeriesId;
            internal int Slot = -1;
            internal int Team = -1;
            internal int Actor;
            internal string LeaverUid;
            internal string Name;
            internal int R0, R1, P0, P1;
            internal int W0, W1;
            internal string SlotLog;
            internal int LastP1, LastP2;
            internal double At;
            /// <summary>This survivor's own eligibility (team only).</summary>
            internal DcKind Eligibility = DcKind.Nothing;
            /// <summary>The glue's executable form of the eligibility (the
            /// report fields, the watched seat); opaque here.</summary>
            internal object Plan;
        }

        // ── S2: the hold at the boundary ───────────────────────────────────

        /// <summary>Rank of a state in the hold's order; x is terminal.</summary>
        internal static int Rank(char s)
        {
            switch (s) { case 'p': return 0; case 'o': return 1; case 'c': return 2; case 'b': return 3; case 'e': return 4; case 'x': return 5; default: return -1; }
        }

        internal enum Verdict { Act, Inert, End }

        /// <summary>The transition envelope (RJS-H9). A room state after p is
        /// acted on only when this client's own server read shows that state
        /// (or a later one) of the same hold and game at the same or a later
        /// sequence. <paramref name="server"/> is null while no read issued
        /// after this client observed the room value has answered: the check
        /// is pending and the state is inert (the ceilings bound the wait).
        /// An answered read that does not show the state is the unverified
        /// case: o or c reads as x (end toward today); b or e is inert (keep
        /// waiting); x is inert until the server shows the hold closed or a
        /// ceiling passes. A read that answered nothing parsable is passed as
        /// an empty answer, which shows nothing.</summary>
        internal static Verdict Verify(HoldKey room, TeamHoldNet.StateAnswer server)
        {
            if (room == null) return Verdict.Inert;
            if (room.State == 'p') return Verdict.Act;
            if (server == null) return Verdict.Inert;
            bool same = server.HoldId == room.HoldId && server.G == room.G && server.Seq >= room.Seq;
            bool shows = same && (room.State == 'x' ? server.Closed : Rank(server.State) >= Rank(room.State) && server.State != 'x');
            if (shows) return Verdict.Act;
            if (room.State == 'o' || room.State == 'c') return Verdict.End;
            return Verdict.Inert;
        }

        /// <summary>The local ceilings (RJS-M1), every client: 10 s from the
        /// first p to a verified o; hold_s + 20 s from a verified o; 60 s for
        /// bind and entry from a verified c. Witness timing only shortens.</summary>
        internal sealed class Ceilings
        {
            internal const double PendingS = 10, ClaimedS = 60, Margin = 20;
            internal double FirstP = -1, VerifiedO = -1, VerifiedC = -1;
            internal int HoldS;

            internal void SawP(double now) { if (FirstP < 0) FirstP = now; }
            internal void SawO(double now, int holdS) { if (VerifiedO < 0) { VerifiedO = now; HoldS = holdS; } }
            internal void SawC(double now) { if (VerifiedC < 0) VerifiedC = now; }

            internal bool Passed(double now)
            {
                if (VerifiedC >= 0 && now - VerifiedC >= ClaimedS) return true;
                if (VerifiedO >= 0 && now - VerifiedO >= HoldS + Margin) return true;
                if (FirstP >= 0 && VerifiedO < 0 && now - FirstP >= PendingS) return true;
                return false;
            }
        }

        /// <summary>The fence (RJS-M4): a boundary waits while cr_th names a
        /// waiting state.</summary>
        internal static bool FenceWaits(string th) { return ThLive(th); }

        /// <summary>The vanilla statements of the two two-team transitions, in
        /// order (V:GM_ArmsRace.cs:245-258 and 276-306), with the one inserted
        /// fence immediately before the boundary sync. The mod copies in
        /// TeamHoldFence.cs execute exactly these tables.</summary>
        internal enum Step
        {
            Visualize, WinVisualize, Wait1, Wait05, Wait03, LoadNext, SpeedUp, SlowDown, PickPhase,
            Fence, SyncUp, CallInMove, Revive, BattleOn, TransitionOff, ShowCounter,
        }

        internal static readonly Step[] PointSteps =
        {
            Step.Visualize, Step.Wait1, Step.LoadNext, Step.Wait05, Step.Fence, Step.SyncUp, Step.CallInMove, Step.Revive,
            Step.Wait03, Step.SpeedUp, Step.BattleOn, Step.TransitionOff,
        };

        internal static readonly Step[] RoundSteps =
        {
            Step.WinVisualize, Step.Wait1, Step.LoadNext, Step.Wait03, Step.Wait1, Step.SpeedUp, Step.PickPhase,
            Step.Fence, Step.SyncUp, Step.SlowDown, Step.CallInMove, Step.Revive, Step.Wait03, Step.SpeedUp,
            Step.TransitionOff, Step.BattleOn, Step.ShowCounter,
        };

        /// <summary>The master writer's machine (S2 writer steps 1 to 6). It
        /// decides; the glue performs each action it returns (Photon
        /// compare-and-set writes, HTTP calls) and feeds the answers back.</summary>
        internal sealed class Writer
        {
            internal enum Phase { Idle, Pending, Mirroring, Ending, Done }
            internal enum Op { WriteTh, AppendTrd, PostOpen, GetState, GetByRoom, PostEnd }

            internal sealed class Action
            {
                internal Op Op;
                internal HoldKey Key;
                internal char TrdKind;
                internal string Reason;
                public override string ToString() { return Op + (Key != null ? " " + Key.Format() : "") + (Reason != null ? " " + Reason : ""); }
            }

            internal Phase P = Phase.Idle;
            internal HoldKey Key;
            internal string RequestId;
            internal double PendingAt = -1, LastPoll = -1, EndAt = -1;
            internal const double OpenTimeoutS = 10, PollS = 2, EndWaitS = 3;
            internal string EndReason;

            private readonly List<Action> _out = new List<Action>();
            private List<Action> Flush() { var r = new List<Action>(_out); _out.Clear(); return r; }
            private void Th(HoldKey k) { Key = k; _out.Add(new Action { Op = Op.WriteTh, Key = k }); }

            /// <summary>Step 1: a suppressed drop with no cr_th.</summary>
            internal List<Action> OnDrop(double now, int slot, int team, string g, int writerActor, string requestId)
            {
                if (P != Phase.Idle) return Flush();
                RequestId = requestId;
                PendingAt = now;
                P = Phase.Pending;
                Th(new HoldKey { HoldId = "", Slot = slot, Team = team, G = g, State = 'p', Seq = 0, Writer = writerActor });
                _out.Add(new Action { Op = Op.AppendTrd, Key = Key, TrdKind = 'h' });
                _out.Add(new Action { Op = Op.PostOpen, Key = Key });
                return Flush();
            }

            /// <summary>Step 5: a promoted master finding p reads the hold by
            /// room; finding o, c or b it mirrors.</summary>
            internal List<Action> OnPromoted(double now, HoldKey current, string requestId)
            {
                if (P != Phase.Idle || current == null) return Flush();
                Key = current;
                RequestId = requestId;
                if (current.State == 'p') { P = Phase.Pending; PendingAt = now; _out.Add(new Action { Op = Op.GetByRoom, Key = current }); }
                else if (IsLive(current.State)) { P = Phase.Mirroring; LastPoll = -1; }
                return Flush();
            }

            /// <summary>Step 2: the open answer (status 0 = no transport).</summary>
            internal List<Action> OnOpen(double now, int status, TeamHoldNet.OpenAnswer a)
            {
                if (P != Phase.Pending) return Flush();
                if (a != null && a.Opened)
                {
                    var k = Key.With('o', a.Seq);
                    k.HoldId = a.HoldId; k.HoldS = a.HoldS;
                    Th(k);
                    P = Phase.Mirroring;
                    LastPoll = now;
                    return Flush();
                }
                return End(now, a != null ? "refused:" + a.Reason : "no_answer");
            }

            /// <summary>Step 5: the by-room read. A row resumes; a 404 reposts
            /// the open with the same request key; anything else waits on the
            /// pending ceiling.</summary>
            internal List<Action> OnByRoom(double now, int status, TeamHoldNet.StateAnswer a)
            {
                if (P != Phase.Pending) return Flush();
                if (a != null && !a.Closed)
                {
                    var k = Key.With(a.State, a.Seq);
                    k.HoldId = a.HoldId;
                    if (a.DeadlineS > 0 && k.HoldS == 0) k.HoldS = a.DeadlineS;
                    Th(k);
                    P = Phase.Mirroring;
                    LastPoll = now;
                    return Flush();
                }
                if (a != null && a.Closed) { Th(Key.With('x', a.Seq)); P = Phase.Done; return Flush(); }
                if (status == 404) _out.Add(new Action { Op = Op.PostOpen, Key = Key });
                return Flush();
            }

            /// <summary>Step 3: mirror the server state.</summary>
            internal List<Action> OnState(double now, TeamHoldNet.StateAnswer a)
            {
                if (P != Phase.Mirroring || a == null || a.HoldId != Key.HoldId) return Flush();
                if (a.Closed) { Th(Key.With('x', a.Seq)); P = Phase.Done; return Flush(); }
                if (a.Seq <= Key.Seq && Rank(a.State) <= Rank(Key.State)) return Flush();
                var k = Key.With(a.State, a.Seq);
                if (a.State == 'b') k.BoundActor = a.BoundActor;
                Th(k);
                if (a.State == 'e') { _out.Add(new Action { Op = Op.AppendTrd, Key = k, TrdKind = 'r' }); P = Phase.Done; }
                return Flush();
            }

            /// <summary>Step 6: every local end reason posts the end first,
            /// waits up to 3 s, then writes x.</summary>
            internal List<Action> End(double now, string reason)
            {
                if (P == Phase.Done || P == Phase.Ending) return Flush();
                EndReason = reason;
                if (Key != null && !string.IsNullOrEmpty(Key.HoldId))
                {
                    P = Phase.Ending;
                    EndAt = now;
                    _out.Add(new Action { Op = Op.PostEnd, Key = Key, Reason = reason });
                    return Flush();
                }
                if (Key != null) Th(Key.With('x', Key.Seq + 1));
                P = Phase.Done;
                return Flush();
            }

            internal List<Action> OnEndAnswer(double now)
            {
                if (P != Phase.Ending) return Flush();
                Th(Key.With('x', Key.Seq + 1));
                P = Phase.Done;
                return Flush();
            }

            internal List<Action> Tick(double now)
            {
                if (P == Phase.Pending && now - PendingAt >= OpenTimeoutS) return End(now, "no_answer");
                if (P == Phase.Ending && now - EndAt >= EndWaitS) return OnEndAnswer(now);
                if (P == Phase.Mirroring && (LastPoll < 0 || now - LastPoll >= PollS))
                {
                    LastPoll = now;
                    _out.Add(new Action { Op = Op.GetState, Key = Key });
                }
                return Flush();
            }
        }
    }
}
