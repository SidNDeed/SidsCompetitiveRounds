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

        // ── The pin store (S1 step 2). Filled ONLY from the server's answers
        //    naming the room: the team and 1v2 ready_join polls
        //    (TeamHoldNet.PinFromJoin) and the claim answer (TeamHoldReturn).
        //    A room no answer flagged reads unflagged, which is today. ──────

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
            /// both read the memo. Any exception answers today. The one
            /// computation that holds emits [HOLD] cascade suppressed.</summary>
            internal static bool DecideOnce(int actor, Func<GateInputs> read)
            {
                bool r;
                if (_memo.TryGetValue(actor, out r)) return r;
                GateInputs inputs = null;
                try { inputs = read(); r = Decide(inputs); }
                catch { r = false; }
                _memo[actor] = r;
                if (r && inputs != null) SeatDeckLog.Emit("[HOLD] cascade suppressed slot=" + I(inputs.Slot));
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
            /// <summary>The state at the last boundary before the drop (S3
            /// step 7): the scoreboard and the held slot's deck names.</summary>
            internal int BR0, BR1, BP0, BP1;
            internal readonly List<string> BNames = new List<string>();
            internal double At;
            /// <summary>This survivor's own eligibility (team only).</summary>
            internal DcKind Eligibility = DcKind.Nothing;
            /// <summary>The glue's executable form of the eligibility (the
            /// report fields, the watched seat); opaque here.</summary>
            internal object Plan;
            /// <summary>The departing Photon player, retained for the vanilla
            /// leave body at the expiry (S5); opaque here.</summary>
            internal object Leaver;
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

        // ── S3: the snapshot, its digest and the returner's gate ───────────

        internal const string KEY_TSN = "cr_tsn";
        internal const string KEY_TBD = "cr_tbd";
        internal const string KEY_RDT = "cr_rdt";
        internal const string KEY_TOFF = "cr_toff";

        /// <summary>FNV-1a 64 over UTF-16 code units, as hex (16 digits).</summary>
        internal static string Fnv64Hex(string s)
        {
            ulong h = 0xcbf29ce484222325UL;   // the FNV-1a 64 offset basis
            foreach (char c in s ?? "") { h ^= c; h *= 0x100000001b3UL; }   // the FNV-1a 64 prime
            return h.ToString("x16", CultureInfo.InvariantCulture);
        }

        /// <summary>One slot of the snapshot: deals, deaths and the names.</summary>
        internal sealed class SlotState
        {
            internal int Slot;
            internal int Deals;
            internal int Deaths;
            internal List<string> Names = new List<string>();
            internal string Format() { return I(Slot) + "," + I(Deals) + "," + I(Deaths) + "," + string.Join("/", Names.ToArray()); }
        }

        /// <summary>cr_tsn = {hold_id}:{G}:{r0}:{r1}:{p0}:{p1}:{w0}:{w1}:{ledger}:{slots}:{bnd}.
        /// slots = slot,deals,deaths,names separated by ';' (names by '/');
        /// bnd = the state at the last boundary before the drop:
        /// r0,r1,p0,p1,held deals,held names.</summary>
        internal sealed class Snapshot
        {
            internal string HoldId = "", G = "";
            internal int R0, R1, P0, P1, W0, W1;
            internal string Ledger = "";
            internal List<SlotState> Slots = new List<SlotState>();
            internal int BR0, BR1, BP0, BP1, BDeals;
            internal List<string> BNames = new List<string>();

            internal string Boundary()
            {
                return I(BR0) + "," + I(BR1) + "," + I(BP0) + "," + I(BP1) + "," + I(BDeals) + "," + string.Join("/", BNames.ToArray());
            }

            internal string Format()
            {
                var sl = new List<string>();
                foreach (var s in Slots) sl.Add(s.Format());
                return HoldId + ":" + G + ":" + I(R0) + ":" + I(R1) + ":" + I(P0) + ":" + I(P1) + ":" + I(W0) + ":" + I(W1)
                       + ":" + Ledger + ":" + string.Join(";", sl.ToArray()) + ":" + Boundary();
            }

            internal SlotState SlotOf(int slot)
            {
                foreach (var s in Slots) if (s.Slot == slot) return s;
                return null;
            }
        }

        private static List<string> SplitNames(string s)
        {
            var r = new List<string>();
            if (!string.IsNullOrEmpty(s)) r.AddRange(s.Split('/'));
            return r;
        }

        internal static bool TryParseSnapshot(string s, out Snapshot snap)
        {
            snap = null;
            if (string.IsNullOrEmpty(s)) return false;
            var f = s.Split(':');
            if (f.Length != 11) return false;
            var n = new Snapshot { HoldId = f[0], G = f[1], R0 = ParseInt(f[2], -1), R1 = ParseInt(f[3], -1), P0 = ParseInt(f[4], -1),
                                   P1 = ParseInt(f[5], -1), W0 = ParseInt(f[6], -1), W1 = ParseInt(f[7], -1), Ledger = f[8] };
            if (!string.IsNullOrEmpty(f[9]))
                foreach (var e in f[9].Split(';'))
                {
                    var p = e.Split(',');
                    if (p.Length != 4) return false;
                    n.Slots.Add(new SlotState { Slot = ParseInt(p[0], -1), Deals = ParseInt(p[1], -1), Deaths = ParseInt(p[2], -1), Names = SplitNames(p[3]) });
                }
            var b = f[10].Split(',');
            if (b.Length != 6) return false;
            n.BR0 = ParseInt(b[0], -1); n.BR1 = ParseInt(b[1], -1); n.BP0 = ParseInt(b[2], -1); n.BP1 = ParseInt(b[3], -1);
            n.BDeals = ParseInt(b[4], -1); n.BNames = SplitNames(b[5]);
            if (n.R0 < 0 || n.R1 < 0 || n.P0 < 0 || n.P1 < 0 || n.W0 < 0 || n.W1 < 0
                || n.BR0 < 0 || n.BR1 < 0 || n.BP0 < 0 || n.BP1 < 0 || n.BDeals < 0) return false;
            foreach (var x in n.Slots) if (x.Slot < 0 || x.Deals < 0 || x.Deaths < 0 || x.Deals != x.Names.Count) return false;
            snap = n;
            return true;
        }

        /// <summary>The digest every remaining fighter publishes (cr_tbd) and
        /// the returner recomputes from cr_tsn: every field of the snapshot.</summary>
        internal static string SnapshotDigest(Snapshot s) { return Fnv64Hex(s.Format()); }

        /// <summary>The held seat's own boundary checkpoint, which it posts in
        /// every beat and the server stores: the scoreboard and its own deck
        /// at the last boundary.</summary>
        internal static string BoundaryDigest(int r0, int r1, int p0, int p1, IList<string> ownNames)
        {
            return Fnv64Hex(I(r0) + "," + I(r1) + "," + I(p0) + "," + I(p1) + "," + I(ownNames != null ? ownNames.Count : 0)
                            + "," + string.Join("/", ownNames != null ? new List<string>(ownNames).ToArray() : new string[0]));
        }

        /// <summary>The delta from the boundary to the snapshot is legal:
        /// exactly one point to one team, or one round transition (the
        /// winner's rounds +1, both points 0). A game transition changes G,
        /// which the G check refuses (toward today).</summary>
        internal static bool DeltaLegal(Snapshot s, int pointsToWinRound)
        {
            bool point0 = s.R0 == s.BR0 && s.R1 == s.BR1 && s.P0 == s.BP0 + 1 && s.P1 == s.BP1;
            bool point1 = s.R0 == s.BR0 && s.R1 == s.BR1 && s.P1 == s.BP1 + 1 && s.P0 == s.BP0;
            bool round0 = s.R0 == s.BR0 + 1 && s.R1 == s.BR1 && s.P0 == 0 && s.P1 == 0 && s.BP0 + 1 >= pointsToWinRound;
            bool round1 = s.R1 == s.BR1 + 1 && s.R0 == s.BR0 && s.P0 == 0 && s.P1 == 0 && s.BP1 + 1 >= pointsToWinRound;
            return point0 || point1 || round0 || round1;
        }

        /// <summary>The returner's gate (S3 step 7). Null when the snapshot may
        /// be restored, else the refusal reason. <paramref name="peerDigests"/>
        /// holds the cr_tbd digest of every remaining non-master fighter, null
        /// for one that published none; <paramref name="expectedPeers"/> is how
        /// many there must be (2v2: two; 1v2: one).</summary>
        internal static string CheckSnapshot(string tsn, IList<string> peerDigests, int expectedPeers, string claimG,
                                             int serverW0, int serverW1, string serverBoundaryDigest, int heldSlot,
                                             int pointsToWinRound, out Snapshot snap)
        {
            if (!TryParseSnapshot(tsn, out snap)) return "snapshot unreadable";
            string d = SnapshotDigest(snap);
            int present = 0;
            if (peerDigests != null)
                foreach (var pd in peerDigests)
                {
                    if (pd == null) continue;
                    if (pd != d) return "digest mismatch";
                    present++;
                }
            if (expectedPeers < 1 || present < expectedPeers) return "digest missing";
            if (snap.G != claimG) return "game id mismatch";
            if (snap.W0 != serverW0 || snap.W1 != serverW1) return "series tally mismatch";
            var held = snap.SlotOf(heldSlot);
            if (held == null) return "held slot missing";
            if (BoundaryDigest(snap.BR0, snap.BR1, snap.BP0, snap.BP1, snap.BNames) != serverBoundaryDigest) return "boundary checkpoint mismatch";
            if (snap.BDeals != snap.BNames.Count) return "boundary deck malformed";
            if (!DeltaLegal(snap, pointsToWinRound)) return "illegal delta";
            if (held.Names.Count < snap.BNames.Count || held.Names.Count > snap.BNames.Count + 2) return "held deck delta illegal";
            for (int i = 0; i < snap.BNames.Count; i++) if (held.Names[i] != snap.BNames[i]) return "held deck differs from the checkpoint";
            return null;
        }

        /// <summary>The master's hand-over token check (S3 step 4): X carries
        /// cr_rdt = {hold_id}:{T} and SHA-256(T) equals the server verifier.</summary>
        internal static bool TokenOk(string rdt, string holdId, string verifierHex)
        {
            if (string.IsNullOrEmpty(rdt) || string.IsNullOrEmpty(holdId) || string.IsNullOrEmpty(verifierHex)) return false;
            int i = rdt.IndexOf(':');
            if (i <= 0 || rdt.Substring(0, i) != holdId) return false;
            string t = rdt.Substring(i + 1);
            if (t.Length == 0) return false;
            using (var sha = System.Security.Cryptography.SHA256.Create())
            {
                var h = sha.ComputeHash(Encoding.UTF8.GetBytes(t));
                var sb = new StringBuilder();
                foreach (var b in h) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
                return string.Equals(sb.ToString(), verifierHex, StringComparison.OrdinalIgnoreCase);
            }
        }

        /// <summary>The master's token check as the hand-over runs it: a
        /// refusal emits [HOLD] token refused for the bound actor.</summary>
        internal static bool TokenCheck(string rdt, string holdId, string verifierHex, int boundActor)
        {
            bool ok = TokenOk(rdt, holdId, verifierHex);
            if (!ok) SeatDeckLog.Emit("[HOLD] token refused actor=" + I(boundActor));
            return ok;
        }

        /// <summary>A survivor's verified room state moved from prev to next:
        /// the first verified o of a hold emits [HOLD] held (the base of the
        /// S6 ladder). Answers whether it emitted.</summary>
        internal static bool NoteShown(char prev, char next, int slot)
        {
            if (next != 'o' || prev == 'o' || prev == 'c' || prev == 'b' || prev == 'e') return false;
            SeatDeckLog.Emit("[HOLD] held slot=" + I(slot));
            return true;
        }

        /// <summary>The U2 route (S3 step 9), one returner. Each stage must
        /// complete in order; any failure ends the hold toward today and the
        /// boundary stays closed. The boundary is released only after the
        /// server shows entered.</summary>
        internal sealed class ReturnRoute
        {
            internal enum Stage { Claim, Join, Bind, Token, Latch, Snapshot, Register, Activate, Entered, Released, Ended }
            internal Stage S = Stage.Claim;
            internal string EndReason;
            internal double ClaimedAt = -1;
            internal int Slot = -1;
            internal const double EntryBoundS = 60;

            /// <summary>Report one stage's outcome. Out of order is a failure.
            /// The in-order Entered stage emits [HOLD] entered.</summary>
            internal void Done(Stage stage, bool ok, double now, string why = null)
            {
                if (S == Stage.Ended || S == Stage.Released) return;
                if (stage != S || !ok) { S = Stage.Ended; EndReason = why ?? (stage + (ok ? " out of order" : " failed")); return; }
                if (stage == Stage.Claim) ClaimedAt = now;
                if (stage == Stage.Entered) SeatDeckLog.Emit("[HOLD] entered slot=" + I(Slot));
                S = stage + 1;
            }

            internal void Tick(double now)
            {
                if (S == Stage.Ended || S == Stage.Released) return;
                if (ClaimedAt >= 0 && now - ClaimedAt >= EntryBoundS) { S = Stage.Ended; EndReason = "entry bound"; }
            }

            internal bool BoundaryReleased { get { return S == Stage.Released; } }
        }

        /// <summary>T3.9: discovery shows the offer only for a readmissible
        /// answer, and only a shown offer emits [HOLD] offered.</summary>
        internal static bool DiscoveryShows(TeamHoldNet.MineAnswer a)
        {
            bool shows = a != null && a.Readmissible;
            if (shows) SeatDeckLog.Emit("[HOLD] offered mode=" + (a.Mode ?? "") + " slot=" + I(a.Slot));
            return shows;
        }

        // ── S4: one record for every picker; the absent seat; the grant ────

        internal const string KEY_TAP = "cr_tap";

        /// <summary>The picker set of a phase (S4 step 1): the vanilla pickers
        /// (every seat at the game start; the losing team at a round) plus
        /// every held seat of that team, with the deals each makes. The 1v2
        /// solo makes two initial deals when the series has the extra pick.</summary>
        internal static List<KeyValuePair<int, int>> PickerSet(string mode, bool gameStart, int losingTeam,
                                                               IList<int> presentSlots, IList<int> heldSlots, bool ovtSoloExtra)
        {
            var all = new SortedSet<int>();
            if (presentSlots != null) foreach (var s in presentSlots) all.Add(s);
            if (heldSlots != null) foreach (var s in heldSlots) all.Add(s);
            var r = new List<KeyValuePair<int, int>>();
            foreach (var s in all)
            {
                if (!gameStart && SlotToTeam(mode, s) != losingTeam) continue;
                int deals = gameStart && mode == MODE_OVT && s == 0 && ovtSoloExtra ? 2 : 1;
                r.Add(new KeyValuePair<int, int>(s, deals));
            }
            return r;
        }

        /// <summary>S4 step 4: a deal of a slot the room's hold names in a
        /// waiting state is skipped on every client. The test reads cr_th,
        /// never whether a body still resolves (a delayed purge keeps one).</summary>
        internal static bool SkipDeal(int slot, string th, bool bodyResolves)
        {
            HoldKey k;
            return TryParseHold(th, out k) && IsLive(k.State) && k.Slot == slot;
        }

        /// <summary>S4 step 4: the pick phase is waiting on the held slot's own
        /// deal; every client ends it locally (vanilla RPCA_DonePicking, no RPC).</summary>
        internal static bool DonePickingLocally(bool picking, int pickerSlot, string th)
        {
            return picking && SkipDeal(pickerSlot, th, true);
        }

        /// <summary>The record seam (S4 step 2). KX5 binds it to the FFA
        /// offer record and its ledger; unbound it yields NO record, and no
        /// record means no card.</summary>
        internal static Func<string, int, int, string> RecordEntry0;

        internal static string Entry0(string g, int slot, int k)
        {
            var f = RecordEntry0;
            if (f == null) return null;
            try { return f(g, slot, k); } catch { return null; }
        }

        /// <summary>A present owner's screen falls back to today when no
        /// record arrived within 4 s of the phase start.</summary>
        internal const double RecordLateS = 4;
        internal static bool RecordLate(double phaseStart, double now, bool haveRecord)
        {
            return !haveRecord && now - phaseStart >= RecordLateS;
        }

        /// <summary>The owner screen's wait as the deal runs it: the late
        /// answer emits [HOLD] record late for that slot.</summary>
        internal static bool RecordLateFor(int slot, double phaseStart, double now, bool haveRecord)
        {
            bool late = RecordLate(phaseStart, now, haveRecord);
            if (late) SeatDeckLog.Emit("[HOLD] record late slot=" + I(slot));
            return late;
        }

        /// <summary>S4 step 6: one audit answer emits [HOLD] audit; it never
        /// changes what is applied.</summary>
        internal static void AuditLine(int slot, bool match)
        {
            SeatDeckLog.Emit("[HOLD] audit slot=" + I(slot) + " match=" + (match ? "1" : "0"));
        }

        /// <summary>cr_tap = {G}:{slot}:{k}:{card}.</summary>
        internal static string TapFormat(string g, int slot, int k, string card) { return g + ":" + I(slot) + ":" + I(k) + ":" + card; }

        internal static bool TryParseTap(string s, out string g, out int slot, out int k, out string card)
        {
            g = null; slot = -1; k = -1; card = null;
            if (string.IsNullOrEmpty(s)) return false;
            var f = s.Split(new[] { ':' }, 4);
            if (f.Length != 4) return false;
            g = f[0]; slot = ParseInt(f[1], -1); k = ParseInt(f[2], -1); card = f[3];
            return !string.IsNullOrEmpty(g) && slot >= 0 && k >= 0 && !string.IsNullOrEmpty(card);
        }

        internal enum GrantOutcome { Applied, Superseded, Refused }

        /// <summary>S4 step 5 on every client: the grant goes through the one
        /// writer; a real pick for that slot at deal k received first is kept
        /// and the grant ignored.</summary>
        internal static GrantOutcome ApplyGrant(string g, string currentG, int slot, int k, string card)
        {
            if (string.IsNullOrEmpty(card) || g != currentG) return GrantOutcome.Refused;
            bool superseded;
            if (SeatDeckLog.CommitGrant(k, slot, card, out superseded))
            {
                SeatDeckLog.Emit("[HOLD] auto grant slot=" + I(slot) + " card=" + card);
                return GrantOutcome.Applied;
            }
            if (!superseded) return GrantOutcome.Refused;
            SeatDeckLog.Emit("[HOLD] grant superseded slot=" + I(slot) + " k=" + I(k));
            return GrantOutcome.Superseded;
        }

        // ── S5: the expiry from the cut ────────────────────────────────────

        internal enum ExpiryOp { ReportPrompt, ReportFloor, ArmFallback, VanillaLeave }

        /// <summary>At a verified x every client runs the path of today with
        /// the cut as input: a team survivor executes its OWN latched
        /// eligibility (a prompt or floor reporter posts with the cut's
        /// points, a watcher re-arms the fallback watch on its latched target,
        /// the leaver's team stands down), then the vanilla leave body for the
        /// first drop. A 1v2 survivor runs the vanilla body and reports
        /// nothing. <paramref name="presentAtExpiry"/> is the fighters present
        /// at x; the rule must not read it (the set of today is the set at the
        /// drop).</summary>
        internal static List<ExpiryOp> ExpiryActions(DropCut cut, IList<int> presentAtExpiry)
        {
            var r = new List<ExpiryOp>();
            if (cut == null) return r;
            if (cut.Mode == MODE_TEAM)
            {
                switch (cut.Eligibility)
                {
                    case DcKind.Prompt: r.Add(ExpiryOp.ReportPrompt); break;
                    case DcKind.Floor: r.Add(ExpiryOp.ReportFloor); break;
                    case DcKind.Fallback: r.Add(ExpiryOp.ArmFallback); break;
                }
            }
            r.Add(ExpiryOp.VanillaLeave);
            return r;
        }


        // ── KX2: live points (V3 S2, RJS-M5) ───────────────────────────────

        /// <summary>The team live-points gate (V3 S2 live points, RJS-M5).
        /// While this seat observes a waiting hold (cr_th p, o, c or b) in a
        /// room, the team channel creates no post there, and a post created
        /// after the observation never dispatches, neither its first send nor
        /// a retry; a post created before it is sent as today. Two readings
        /// feed the observation: the writer's own cr_th write (its compare-and
        /// -set reaches the room cache only when the server echoes it) and the
        /// room's cr_th as MaybeSendLivePoints reads it. A reading of the same
        /// hold (its game and slot) ended, e or x, lifts the observation (an
        /// older hold's x still in the room does not); it is keyed on
        /// the room, so a seat that left a held room posts in the next one as
        /// today. Posts of other channels carry stamp 0 and always dispatch.</summary>
        internal static class LiveGate
        {
            private static long _created;
            private static long _observedAt = -1;
            private static string _room, _g;
            private static int _slot = -1;

            internal static void Reset() { _created = 0; _observedAt = -1; _room = null; _g = null; _slot = -1; }

            /// <summary>One reading of the room's hold. The first waiting
            /// reading in a room marks the observation; a reading of the
            /// same hold (game and slot) ended lifts it; an unreadable value
            /// (no hold written yet, or a cache the echo has not reached)
            /// changes nothing.</summary>
            internal static void Observe(string room, string th)
            {
                if (string.IsNullOrEmpty(room)) return;
                HoldKey k;
                if (!TryParseHold(th, out k)) return;
                if (IsLive(k.State))
                {
                    if (_observedAt < 0 || _room != room) _observedAt = _created;
                    _room = room; _g = k.G; _slot = k.Slot;
                }
                else if (_room == room && _g == k.G && _slot == k.Slot) { _observedAt = -1; _room = null; _g = null; _slot = -1; }
            }

            internal static bool Held(string room) { return _observedAt >= 0 && room == _room; }

            /// <summary>MaybeSendLivePoints: the creation stamp of a new team
            /// post in <paramref name="room"/>, or 0 (no post) while
            /// <paramref name="th"/>, its own reading of the room's cr_th,
            /// is a waiting hold.</summary>
            internal static long Create(string room, string th)
            {
                Observe(room, th);
                if (ThLive(th)) return 0;
                return ++_created;
            }

            /// <summary>PostTeamLivePoints and SendLivePoints, before every
            /// send: false for a team post created after the observation in
            /// its room.</summary>
            internal static bool Dispatch(long stamp, string room)
            {
                if (stamp <= 0) return true;
                return !(Held(room) && stamp > _observedAt);
            }
        }

        // ── KX3: admission (V3 S3 steps 4 and 5) ───────────────────────────

        /// <summary>The lock-roster feeder of a flagged room (S3 step 5,
        /// lesson g): every roster freeze there, the per-game freeze at each
        /// game start included, reads the pinned series roster and never the
        /// present fighters, so a hold spanning game N to N+1 keeps the held
        /// seat on the roster and a stranger present at the freeze is not on
        /// it. <paramref name="present"/> is the view the freeze would have
        /// read today; the rule never invokes it. Null for a room that is not
        /// flagged or whose pin carries no roster (a pin from the claim answer
        /// alone), which freezes as today.</summary>
        internal static List<string> LockRoster(string room, Func<IEnumerable<string>> present)
        {
            if (!Flagged(room)) return null;
            var pin = PinFor(room);
            if (pin == null || pin.Roster.Count == 0) return null;
            var ids = new List<string>(pin.Roster);
            ids.Sort(StringComparer.Ordinal);
            return ids;
        }

        /// <summary>The held-seat conjunct of RoomActors.IsUnauthorized (S3
        /// step 4): in a flagged room whose cr_th names the held seat's hold
        /// (its slot), an actor whose u_id is the held seat's is a fighter
        /// only if it is X, the hold's
        /// bound actor; before a bind (no X) every such actor is refused, and
        /// so is every one after an x that bound nobody. Null when the rule
        /// does not apply (no flagged room, no readable hold, no held identity
        /// known, or another identity), and the rules of today decide.</summary>
        internal static bool? HeldSeatUnauthorized(string room, string th, int actor, string actorUid, string heldUid, int heldSlot)
        {
            if (!Flagged(room) || string.IsNullOrEmpty(heldUid) || !string.Equals(actorUid, heldUid, StringComparison.Ordinal)) return null;
            HoldKey k;
            if (!TryParseHold(th, out k) || k.Slot != heldSlot) return null;
            return k.BoundActor <= 0 || actor != k.BoundActor;
        }

        /// <summary>S3 step 5: on a verified b every client releases the
        /// latches the roster now covers, once per hold, so an actor refused
        /// before its identity was readable is released at the bind.
        /// <paramref name="lastReleased"/> carries the hold last released.</summary>
        internal static bool ReleaseAtBind(HoldKey verified, ref string lastReleased)
        {
            if (verified == null || verified.State != 'b') return false;
            string id = verified.G + ":" + I(verified.Slot) + ":" + (verified.HoldId ?? "");
            if (lastReleased == id) return false;
            lastReleased = id;
            return true;
        }


        // ── KX4: registration and the returner's seeding (V3 S3 step 8) ───

        /// <summary>The rooms whose RegisterPlayer is the sorted insert (V3
        /// P4.3 step 9): the FFA readmission lobbies and every flagged room.</summary>
        internal static bool SortedRegistration(bool readmitLobby, string room) { return readmitLobby || Flagged(room); }

        /// <summary>The sorted insert, for the RegisterPlayer prefix: the
        /// player list stays sorted by PlayerID with no holes. Dead entries
        /// are dropped, the new PlayerID's sorted index comes from
        /// <paramref name="index"/> (FfaReadmitEntryRules.RegisterIndex), one
        /// placeholder is inserted there for vanilla's assignment and that
        /// index is returned as the forced index, so vanilla never pads with
        /// nulls and never assigns over a live entry. -1 refuses a duplicate
        /// PlayerID and inserts nothing.</summary>
        internal static int PlaceRegistration<T>(List<T> list, Func<T, bool> dead, Func<T, int> idOf, int newId,
                                                 Func<IList<int>, int, int> index) where T : class
        {
            list.RemoveAll(p => p == null || dead(p));
            var ids = new List<int>(list.Count);
            foreach (var p in list) ids.Add(idOf(p));
            int at = index(ids, newId);
            if (at < 0) return -1;
            list.Insert(at, null);
            return at;
        }

        /// <summary>The returner's seeding from the snapshot (S3 step 8),
        /// beyond the vanilla score fields and the seat logs: the watcher's
        /// own score counters, its draw index (the deals its slot made), and
        /// its cr_cards value (its slot's names, pipe-joined, as
        /// GameStateWatcher.BroadcastCardPick writes them).</summary>
        internal sealed class SeedPlan
        {
            internal int R0, R1, P0, P1;
            internal int DrawIndex = -1;
            internal string Cards = "";
            internal List<string> Names = new List<string>();
        }

        internal static SeedPlan PlanSeed(Snapshot s, int slot)
        {
            if (s == null) return null;
            var p = new SeedPlan { R0 = s.R0, R1 = s.R1, P0 = s.P0, P1 = s.P1 };
            foreach (var st in s.Slots)
            {
                if (st.Slot != slot) continue;
                p.DrawIndex = st.Deals;
                p.Names.AddRange(st.Names);
                p.Cards = string.Join("|", st.Names.ToArray());
            }
            return p;
        }


        // ── KX5: the record (V3 S4 step 2 over the FFA P2 record) ──────────

        /// <summary>The pick phases of a game run at its start and after each
        /// round, so the rounds played number them (0 at the game start).</summary>
        internal static int PhaseOf(int r0, int r1) { return r0 + r1; }

        /// <summary>S4 step 2: in a flagged room the master builds the record
        /// of EVERY pick phase, whether or not a seat is held, so every seat
        /// spends from one ledger at record build (the integrity bar, lesson
        /// e: a departure changes no other list or later offer).</summary>
        internal static bool BuildsRecord(bool flagged, bool holdLive) { return flagged; }

        /// <summary>cr_toff = {G}:{phase}:{rule}:{ledger}:{entries}: the FFA P2
        /// offer record's codec (FfaReadmitRules.Encode and Parse) with G in
        /// the epoch field, the phase in the game field and no cycle field.
        /// Null when the record does not encode (a name or G carrying a
        /// reserved separator): no record is written, which is today.</summary>
        internal static string EncodeOff(FfaReadmitRules.FfaOfferRecord r)
        {
            if (r == null) return null;
            string v = FfaReadmitRules.Encode(r);
            if (v == null) return null;
            var f = v.Split(new[] { ':' }, 4);
            return f.Length == 4 ? f[0] + ":" + f[1] + ":" + f[3] : null;
        }

        internal static FfaReadmitRules.FfaOfferRecord ParseOff(string v)
        {
            if (string.IsNullOrEmpty(v)) return null;
            var f = v.Split(new[] { ':' }, 3);
            return f.Length == 3 ? FfaReadmitRules.Parse(f[0] + ":" + f[1] + ":0:" + f[2]) : null;
        }

        /// <summary>The record of (G, phase) in a cr_toff value, or null.</summary>
        internal static FfaReadmitRules.FfaOfferRecord OffFor(string off, string g, int phase)
        {
            var r = ParseOff(off);
            return r != null && r.Epoch == g && r.Game == phase ? r : null;
        }

        /// <summary>The record over the phase's picker set: rule s when the
        /// same-card rule runs (FfaReadmitRules.BuildRuleS: the shared entry
        /// at the deal's index, DeckLegal over the S0 logical deck, the
        /// no-repeat test reading the replicated ledger, each substitute
        /// spent as it is chosen), rule p when it is off (the master's private
        /// roll in the deck form). <paramref name="kOf"/> is the draw index
        /// the slot's deal of this phase consumes. Null when the state it
        /// needs is missing: no record, no card.</summary>
        internal static FfaReadmitRules.FfaOfferRecord BuildOff(string g, int phase, IList<int> pickers, bool sameCards,
                                                                Func<int, int> kOf, Func<int, IList<string>> deckOf,
                                                                FfaReadmitRules.OfferPool pool, FfaReadmitRules.SeqState seq,
                                                                int count, Func<string> roll, FfaReadmitRules.SpendState spend)
        {
            if (string.IsNullOrEmpty(g) || pickers == null || pool == null || spend == null) return null;
            if (sameCards)
                return seq == null ? null : FfaReadmitRules.BuildRuleS(g, phase, 0, pickers, kOf, deckOf, pool, seq, spend);
            return roll == null ? null : FfaReadmitRules.BuildRuleP(g, phase, 0, pickers, deckOf, pool, count, roll, spend);
        }

        /// <summary>The master's record of (G, phase): one already readable
        /// is ADOPTED and never rewritten (a promoted master); otherwise
        /// <paramref name="build"/> runs once.</summary>
        internal static FfaReadmitRules.FfaOfferRecord MasterOff(string held, string g, int phase, Func<FfaReadmitRules.FfaOfferRecord> build)
        {
            var h = OffFor(held, g, phase);
            if (h != null) return h;
            return build != null ? build() : null;
        }

        /// <summary>Every client, as the record arrives (the master as it
        /// publishes): the ledger becomes the record's, and under rule s every
        /// listed slot's draw index becomes the record's k (FfaReadmitRules.
        /// AdoptRecord). The ledger resets at game start with the engine's.</summary>
        internal static void AdoptOff(FfaReadmitRules.FfaOfferRecord rec, FfaReadmitRules.SpendState spend, Action<int, int> setDrawIndex)
        {
            FfaReadmitRules.AdoptRecord(rec, spend, setDrawIndex);
        }

        /// <summary>A grant applied: the ledger was spent at build, so this
        /// changes nothing (FfaReadmitRules.NoteApplied, V3 P2 step 3).</summary>
        internal static void NoteGrantApplied(FfaReadmitRules.SpendState spend, string card) { }

        /// <summary>Entry 0 of the slot's list in the record of (G, phase):
        /// the card a held seat is granted. Null with no record.</summary>
        internal static string Entry0Of(string off, string g, int phase, int slot)
        {
            var r = OffFor(off, g, phase);
            return r != null ? r.FirstOf(slot) : null;
        }

        /// <summary>The owner screen (S4 step 3): a present owner's deal shows
        /// its record list, entry 0 included. Null with no record.</summary>
        internal static List<string> ScreenOf(string off, string g, int phase, int slot)
        {
            var r = OffFor(off, g, phase);
            return r != null ? r.ListOf(slot) : null;
        }
    }
}
