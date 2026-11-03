using Photon.Pun;
using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>EVIDENCE ONLY: one [PEER-BUILD] line per remote seat per room
    /// join, and again whenever the values that line states change (the build
    /// statement or a capability). PeerBuildCore builds the line; this half
    /// reads the room. Nothing here changes a game, a room or a match: the
    /// only write is this seat's own cr_build statement, staged pre-join.
    ///
    /// Runs from Plugin's always-on tick in every room, with no setting, lever
    /// or room-kind check in front of it: evidence a player can dispute ships
    /// in every client build.</summary>
    internal static class PeerBuild
    {
        /// <summary>Remote actor -> the value part last printed for it in the
        /// current room.</summary>
        private static readonly Dictionary<int, string> _printed = new Dictionary<int, string>();
        private static string _room = "";
        private static float _nextScan;
        private static bool _staged, _stageFailed;

        /// <summary>The scan runs at most this often (seconds).</summary>
        private const float SCAN_INTERVAL_S = 1f;

        /// <summary>"version|variant|commit": the mod version, the build
        /// variant and the first 12 characters of the commit the SDK stamps into
        /// the assembly's informational version ("nosha" when there is none).</summary>
        internal static string BuildValue()
        {
#if SCR_FRAMETIME
            // boundary or not-live entry: spanned, never gated (upkeep.py)
            bool ftSpan = FtSpan.Open(FtSpan.PeerBuild, FtSpan.Upkeep);
            try
            {
#endif
            string variant =
#if THUNDERSTORE
                "thunderstore";
#elif SCR_G3
                "g3";
#else
                "standalone";
#endif
            string sha = "nosha";
            try
            {
                var attr = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(
                    typeof(PeerBuild).Assembly, typeof(AssemblyInformationalVersionAttribute));
                string iv = attr != null ? attr.InformationalVersion : null;
                int plus = iv != null ? iv.IndexOf('+') : -1;
                if (plus >= 0 && plus + 1 < iv.Length)
                {
                    string s = iv.Substring(plus + 1);
                    sha = s.Length > 12 ? s.Substring(0, 12) : s;
                }
            }
            catch { }
            return Plugin.ModVersion + "|" + variant + "|" + sha;
#if SCR_FRAMETIME
            }
            finally { FtSpan.Close(ftSpan); }
#endif
        }

        /// <summary>Stage this seat's cr_build once, pre-join, the way the
        /// capability keys are staged (DcReportSync.StageCapability, RoomActors.cs):
        /// never while in a room, only from an idle client state, so it rides
        /// the join of every later room.</summary>
        internal static void StageBuildProp(string source)
        {
#if SCR_FRAMETIME
            int ftScope = FtA3.TEnter(); try {
#endif
#if SCR_FRAMETIME
            FtA3.Read(FtA3.PB_printed);
#endif
#if SCR_FRAMETIME
            if (FtCensus.Skip(FtE.PB_c2)) return;
            bool ftSpan = FtSpan.Open(FtSpan.PeerBuild, FtSpan.Gated);
            try
            {
#endif
            try
            {
                if (_staged || _stageFailed) return;
                if (PhotonNetwork.InRoom) return;
                var st = PhotonNetwork.NetworkClientState;
                if (st != Photon.Realtime.ClientState.Disconnected
                    && st != Photon.Realtime.ClientState.PeerCreated
                    && st != Photon.Realtime.ClientState.ConnectedToMasterServer
                    && st != Photon.Realtime.ClientState.JoinedLobby)
                    return;
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                string v = BuildValue();
                // L7 (seat evidence contract V2): the published cr_build is the
                // complete version|variant|commit inside its limits (16/16/12).
                // A tuple outside them is refused here, never cut.
                if (SeatEvidenceCore.SplitBuild(v) == null)
                {
                    _stageFailed = true;
                    Plugin.Log.LogWarning("[BUILD-PROP] not staged: the build tuple is outside its limits (" + v.Length + " chars)");
                    return;
                }
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { PeerBuildCore.BuildProp, v } });
                _staged = true;
                Plugin.Log.LogInfo("[BUILD-PROP] staged " + PeerBuildCore.BuildProp + "=" + v + " pre-join (" + source + ", state=" + st + ")");
            }
            catch (Exception ex)
            {
                _stageFailed = true;
                try { Plugin.Log.LogWarning("[BUILD-PROP] staging failed: " + ex.Message); } catch { }
            }
#if SCR_FRAMETIME
            }
            finally { FtSpan.Close(ftSpan); }
#endif
#if SCR_FRAMETIME
            } finally { FtA3.TExit(ftScope); }
#endif
        }

        /// <summary>Every remote seat of the current room: print its line when
        /// it is new to this room or its values changed since it was printed.</summary>
        internal static void Tick()
        {
#if SCR_FRAMETIME
            int ftScope = FtA3.TEnter(); try {
#endif
#if SCR_FRAMETIME
            FtA3.Read(FtA3.PB_printed); FtA3.Wrote(FtA3.PB_printed);
#endif
#if SCR_FRAMETIME
            if (FtCensus.Skip(FtE.PB_c3)) return;
            bool ftSpan = FtSpan.Open(FtSpan.PeerBuild, FtSpan.Gated);
            try
            {
#endif
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null)
                {
                    if (_room.Length > 0 || _printed.Count > 0) { _printed.Clear(); _room = ""; }
                    return;
                }
                float now = Time.realtimeSinceStartup;
                if (now < _nextScan) return;
                _nextScan = now + SCAN_INTERVAL_S;
                string room = PhotonNetwork.CurrentRoom.Name ?? "";
                if (room != _room) { _printed.Clear(); _room = room; }
                var others = PhotonNetwork.PlayerListOthers;
                if (others == null) return;
#if SCR_FRAMETIME
                // FrameTime A3 (PB_printed, ruling FRAME-TIME-ROUND-R3-A1): this build runs each seat's scan and line
                // through FtPeerLine (the statements of the branch below, on parameters), so the row's calibration
                // executes the reader this loop runs
                foreach (var p in others)
                {
                    if (p == null) continue;
                    FtPeerLine(_printed, p.ActorNumber, p.CustomProperties, Plugin.Log);
                }
#else
                foreach (var p in others)
                {
                    if (p == null) continue;
                    var props = new Dictionary<string, string>();
                    var cp = p.CustomProperties;
                    if (cp != null)
                        foreach (object k in cp.Keys)
                        {
                            if (k == null) continue;
                            object v = cp[k];
                            props[k.ToString()] = v != null ? v.ToString() : null;
                        }
                    string values = PeerBuildCore.Values(props);
                    string last;
                    if (_printed.TryGetValue(p.ActorNumber, out last) && last == values) continue;
                    _printed[p.ActorNumber] = values;
                    Plugin.Log.LogInfo(PeerBuildCore.Line(p.ActorNumber, props));
                }
#endif
            }
            catch { }
#if SCR_FRAMETIME
            }
            finally { FtSpan.Close(ftSpan); }
#endif
#if SCR_FRAMETIME
            } finally { FtA3.TExit(ftScope); }
#endif
        }
#if SCR_FRAMETIME

        // -- FrameTime A3 (FtA3; SURVIVORS.md S36) ------------------------------------------------

        /// <summary>FtA3.RegisterAll: PB_printed (S36), the printed-peer table and the scan scalars, dependent by
        /// default-deny (ruling FRAME-TIME-ROUND-R2 (1)): Tick writes them, so it is counted at every live reader call
        /// (Tick, StageBuildProp), steady false. No code constant sizes _printed (the room's actors bound it); 1 is
        /// passed and unused. Round 4 (ruling FRAME-TIME-ROUND-R3-A1): the calibration executes FtPeerLine, the scan
        /// and line Tick runs per seat in this build, named by FtA3.Executed.</summary>
        internal static void FtA3Rows()
        {
            FtA3.Set(FtA3.PB_printed, "PB_printed", 1, false, FtCalPrinted, 5);
            FtA3.Executed(FtA3.PB_printed, "PeerBuild.FtPeerLine (Tick's per-seat scan and line in the FrameTime build), PeerBuildCore.Values, PeerBuildCore.Line");
        }

        /// <summary>One remote seat of Tick's scan in the FrameTime build: its custom properties read into a
        /// dictionary, the printed-values probe of `printed` and its string compare, and, when the seat is new or
        /// changed, the store and the [PEER-BUILD] line to `log` (Tick passes _printed and Plugin.Log). The statements
        /// are those of Tick's loop body in the other builds.</summary>
        internal static void FtPeerLine(Dictionary<int, string> printed, int actor, ExitGames.Client.Photon.Hashtable cp, BepInEx.Logging.ManualLogSource log)
        {
            var props = new Dictionary<string, string>();
            if (cp != null)
                foreach (object k in cp.Keys)
                {
                    if (k == null) continue;
                    object v = cp[k];
                    props[k.ToString()] = v != null ? v.ToString() : null;
                }
            string values = PeerBuildCore.Values(props);
            string last;
            if (printed.TryGetValue(actor, out last) && last == values) return;
            printed[actor] = values;
            log.LogInfo(PeerBuildCore.Line(actor, props));
        }

        private const int FT_PEERS = 32, FT_KEYS = 40;
        private const int FT_MATCHING = 0, FT_CHANGED = 1, FT_ABSENT = 2, FT_STATES = 3;
        private static readonly string[] FtStateCheck =
        {
            "matching-hit-compared-skipped-no-line", "changed-hit-compared-stored-logged", "absent-missed-stored-logged",
        };
        private static Dictionary<int, string> _ftPrinted;
        private static ExitGames.Client.Photon.Hashtable[] _ftProps;
        private static string[] _ftValues, _ftHeld;
        private static BepInEx.Logging.ManualLogSource _ftLog;

        /// <summary>S36 (PB_printed): one read = Tick's scan of FT_PEERS seats (above any ROUNDS room), the real
        /// FtPeerLine per seat on a scratch table, logging to FtA3.ScratchLog (a source no live listener holds: its
        /// lines are counted and formatted in memory, never written). StageBuildProp, the other reader, tests two
        /// flags of the row. Each seat publishes every value key with a value past the token cut plus further keys up
        /// to FT_KEYS (continuation lines). The table's content decides which of three states each seat's read meets,
        /// and round 5 (ruling FRAME-TIME-ROUND-R4-A1, H1) measures all three in every call, n reads each, the table
        /// re-staged outside the clock before each read: MATCHING, every seat printed with its current values (the
        /// probe hits, the compare runs the whole string, the seat is skipped: no store, no line); CHANGED, every
        /// seat printed with values differing only in the last character (the probe hits, the whole compare, then the
        /// store and the line); ABSENT, the table empty (the probe misses, then the store and the line). The EMPTY
        /// half (full=false) returns the cheapest state's total and the FULL half the costliest state's, so d is the
        /// costliest state against the cheapest (logging against skipping), never two logging states. One Check per
        /// state, every call, from FtPeerLine's own effect: MATCHING wrote no line and every stored value is still the
        /// instance staged (no store); CHANGED and ABSENT wrote one line per seat and every seat holds a freshly
        /// computed values string equal to its values (a store).</summary>
        internal static long FtCalPrinted(bool full, int n)
        {
            if (_ftProps == null)
            {
                _ftLog = FtA3.ScratchLog("FrameTime-A3");
                _ftPrinted = new Dictionary<int, string>();
                var props = new ExitGames.Client.Photon.Hashtable[FT_PEERS];
                var values = new string[FT_PEERS];
                var held = new string[FT_PEERS];
                var probe = new Dictionary<int, string>();
                for (int i = 0; i < FT_PEERS; i++)
                {
                    var h = new ExitGames.Client.Photon.Hashtable();
                    foreach (var key in PeerBuildCore.ValueKeys) h[key] = key + "|" + new string('v', PeerBuildCore.MAX_TOKEN) + i;
                    for (int k = h.Count; k < FT_KEYS; k++) h["cr_x" + k.ToString(System.Globalization.CultureInfo.InvariantCulture)] = k;
                    props[i] = h;
                    FtPeerLine(probe, i, h, _ftLog);
                    values[i] = probe[i];
                    string v = values[i];
                    held[i] = v.Substring(0, v.Length - 1) + (v[v.Length - 1] == 'a' ? 'b' : 'a');
                }
                _ftProps = props; _ftValues = values; _ftHeld = held;
            }
            long cheapest = long.MaxValue, costliest = long.MinValue;
            for (int st = 0; st < FT_STATES; st++)
            {
                long t = 0;
                bool ok = true;
                for (int j = 0; j < n; j++)
                {
                    _ftPrinted.Clear();
                    if (st == FT_MATCHING) for (int i = 0; i < FT_PEERS; i++) _ftPrinted[i] = _ftValues[i];
                    else if (st == FT_CHANGED) for (int i = 0; i < FT_PEERS; i++) _ftPrinted[i] = _ftHeld[i];
                    long l0 = FtA3.ScratchLines;
                    long s = System.Diagnostics.Stopwatch.GetTimestamp();
                    for (int i = 0; i < FT_PEERS; i++) FtPeerLine(_ftPrinted, i, _ftProps[i], _ftLog);
                    t += System.Diagnostics.Stopwatch.GetTimestamp() - s;
                    ok &= FtA3.ScratchLines - l0 == (st == FT_MATCHING ? 0 : FT_PEERS) && _ftPrinted.Count == FT_PEERS;
                    for (int i = 0; i < FT_PEERS; i++)
                    {
                        string got;
                        bool has = _ftPrinted.TryGetValue(i, out got);
                        bool staged = has && ReferenceEquals(got, _ftValues[i]);
                        ok &= has && got == _ftValues[i] && (st == FT_MATCHING ? staged : !staged);
                    }
                }
                FtA3.Check(FtA3.PB_printed, FtStateCheck[st], ok);
                if (t < cheapest) cheapest = t;
                if (t > costliest) costliest = t;
            }
            _ftPrinted.Clear();
            return full ? costliest : cheapest;
        }
#endif
    }
}
