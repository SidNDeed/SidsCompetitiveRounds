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
    }
}
