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
        }

        /// <summary>Stage this seat's cr_build once, pre-join, the way the
        /// capability keys are staged (DcReportSync.StageCapability, RoomActors.cs):
        /// never while in a room, only from an idle client state, so it rides
        /// the join of every later room.</summary>
        internal static void StageBuildProp(string source)
        {
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
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { PeerBuildCore.BuildProp, v } });
                _staged = true;
                Plugin.Log.LogInfo("[BUILD-PROP] staged " + PeerBuildCore.BuildProp + "=" + v + " pre-join (" + source + ", state=" + st + ")");
            }
            catch (Exception ex)
            {
                _stageFailed = true;
                try { Plugin.Log.LogWarning("[BUILD-PROP] staging failed: " + ex.Message); } catch { }
            }
        }

        /// <summary>Every remote seat of the current room: print its line when
        /// it is new to this room or its values changed since it was printed.</summary>
        internal static void Tick()
        {
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
        }
    }
}
