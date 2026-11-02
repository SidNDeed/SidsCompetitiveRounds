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
        }

        /// <summary>Every remote seat of the current room: print its line when
        /// it is new to this room or its values changed since it was printed.</summary>
        internal static void Tick()
        {
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
            }
            catch { }
#if SCR_FRAMETIME
            }
            finally { FtSpan.Close(ftSpan); }
#endif
        }
#if SCR_FRAMETIME

        // -- FrameTime A3 (FtA3; SURVIVORS.md S36) ------------------------------------------------

        /// <summary>FtA3.RegisterAll: PB_printed (S36), the printed-peer table and the scan scalars, dependent by
        /// default-deny (ruling FRAME-TIME-ROUND-R2 (1)): Tick writes them, so it is counted at every live reader call
        /// (Tick, StageBuildProp), steady false. No code constant sizes _printed (the room's actors bound it); 1 is
        /// passed and unused.</summary>
        internal static void FtA3Rows()
        {
            FtA3.Set(FtA3.PB_printed, "PB_printed", 1, false, FtCalPrinted, 2000);
        }

        private const int FT_PEERS = 32;
        private static Dictionary<int, string> _ftPrinted;
        private static string _ftValues;
        private static long _ftSink;

        /// <summary>S36 (PB_printed): Tick's per-player probe of _printed and its string compare, on a scratch table.
        /// FULL: FT_PEERS actors printed (above any ROUNDS room), each with a 256-character values string equal to the
        /// probe's but for its last character, so the compare runs nearly whole. EMPTY: the table empty, every probe
        /// misses.</summary>
        internal static long FtCalPrinted(bool full, int n)
        {
            if (_ftPrinted == null)
            {
                _ftPrinted = new Dictionary<int, string>();
                _ftValues = new string('v', 255) + "b";
            }
            _ftPrinted.Clear();
            string held = new string('v', 255) + "a";
            if (full) for (int i = 0; i < FT_PEERS; i++) _ftPrinted[i] = held;
            long s = 0;
            long t0 = System.Diagnostics.Stopwatch.GetTimestamp();
            for (int j = 0; j < n; j++)
            {
                string last;
                if (_ftPrinted.TryGetValue(j % FT_PEERS, out last) && last == _ftValues) continue;
                s++;
            }
            long t = System.Diagnostics.Stopwatch.GetTimestamp() - t0;
            _ftPrinted.Clear();
            _ftSink += s;
            return t;
        }
#endif
    }
}
