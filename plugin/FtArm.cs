#if SCR_FRAMETIME
using System;
using System.IO;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>FrameTime part b (FORMAT-M-PLAN.md V2 section 3, F03), the arming predicate. The build arms
    /// (gate, plant, self-drive) only while every input holds: the sentinel file is present and parsed clean,
    /// the clock is installed, the shipped CombatEvidencePerf probe is off (it suspends collectors by itself;
    /// its mode binds on CombatEvidence.Tick's first frame, before any room), IdentityClockEvidence's
    /// post-boot fixture file is absent (read at boot and at each game start, never per frame), the seat is in
    /// a room, matchIsRanked is false, the room is named ft_ plus the first eight hex digits of this DLL's own
    /// sha256 (SeatEvidence's own hash), the room's region equals FT_REGION, and exactly two fighters are in
    /// it. Evaluate runs at every frame boundary (FT_Start), so the gate never changes within a frame. Each
    /// change of the first failing input is logged once. A disarm after arming latches for the process: the
    /// gate opens at that boundary, a disarmed line names the input and the point, and the sitting is invalid
    /// (the runner's report).</summary>
    internal static class FtArm
    {
        /// <summary>The one Photon region both seats join (part b: never left to the seats' dropdowns).</summary>
        internal const string FT_REGION = "us";

        internal static bool Armed { get; private set; }

        /// <summary>F7 (ruling R6-A3.9 (1a)): every seat publishes its own DLL sha8 as this player property before
        /// joining, beside the cr_ staging; the arm requires every other fighter to carry the same value, so a seat
        /// with a fighter of unknown provenance in its room never arms and never spawns.</summary>
        internal const string DLL_PROP = "ft_dll";
        private static string _peerSaid = "";

        /// <summary>The own value (the room's sha8), or null before the DLL digest is known.</summary>
        internal static string OwnDll()
        {
            string want = ExpectedRoom();
            return want == null ? null : want.Substring(3);
        }

        /// <summary>Stage (outside a room: delivered with the join, lesson 287) or re-publish (in this build's own
        /// room, if missing) the own DLL_PROP; idempotent, so it writes only when the value differs.</summary>
        internal static void StageOwnDll()
        {
            try
            {
                string v = OwnDll();
                var local = PhotonNetwork.LocalPlayer;
                if (v == null || local == null) return;
                object cur = null;
                if (local.CustomProperties != null && local.CustomProperties.TryGetValue(DLL_PROP, out cur)
                    && string.Equals(cur as string, v, StringComparison.Ordinal)) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { DLL_PROP, v } });
                Plugin.Log.LogInfo("[FRAME-TIME] staged " + DLL_PROP + "=" + v + (PhotonNetwork.InRoom ? " in-room" : " pre-join"));
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] " + DLL_PROP + " staging failed: " + ex.Message); }
        }

        /// <summary>Null when every other fighter carries the own DLL_PROP value, else the first one that does not.</summary>
        private static string UnknownPeer(out string known)
        {
            known = "";
            string own = OwnDll();
            var others = RoomActors.OtherActiveFighters();
            if (own == null || others == null || others.Length == 0) return "none";
            foreach (var p in others)
            {
                object v = null;
                bool ok = p != null && p.CustomProperties != null && p.CustomProperties.TryGetValue(DLL_PROP, out v)
                          && string.Equals(v as string, own, StringComparison.Ordinal);
                if (!ok) return p == null ? "null" : p.ActorNumber.ToString(System.Globalization.CultureInfo.InvariantCulture);
                known += (known.Length > 0 ? "," : "") + p.ActorNumber.ToString(System.Globalization.CultureInfo.InvariantCulture);
            }
            return null;
        }
        internal static bool Latched { get; private set; }
        internal static string Why = "not evaluated";

        private static bool _icFixture;
        private static string _joined = "";

        /// <summary>At boot and at each game start: the fixture file IdentityClockEvidence.PostBoot reads.</summary>
        internal static void ReadFixture()
        {
            try { _icFixture = File.Exists(Path.Combine(BepInEx.Paths.ConfigPath, "scr-ic-postboot.txt")); }
            catch { _icFixture = true; }
        }

        private static string _want;

        /// <summary>Computed once, when SeatEvidence's own-DLL hash is ready (no per-frame allocation).</summary>
        internal static string ExpectedRoom()
        {
            if (_want != null) return _want;
            string sha = SeatEvidence.OwnDllSha;
            if (string.IsNullOrEmpty(sha) || sha.Length < 8) return null;
            _want = "ft_" + sha.Substring(0, 8).ToLowerInvariant();
            return _want;
        }

        /// <summary>The broadcast fence's exemption (part b): exactly this build's own ft_ room, and only while
        /// the sentinel (the arming key) is present. Every other fence site stays as in Release.</summary>
        internal static bool FenceExempt(string roomName)
        {
            if (!FtConfig.Present || string.IsNullOrEmpty(roomName)) return false;
            string want = ExpectedRoom();
            return want != null && string.Equals(roomName, want, StringComparison.Ordinal);
        }

        internal static bool FenceExemptCurrent()
        {
            try { return PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null && FenceExempt(PhotonNetwork.CurrentRoom.Name); }
            catch { return false; }
        }

        /// <summary>The unmasked room line, for the ft_ room only (both seats' lines must agree, F12).</summary>
        internal static void LogJoined()
        {
            Plugin.Log.LogInfo("[FRAME-TIME] room name=" + PhotonNetwork.CurrentRoom.Name + " region=" + Region()
                + " cloud_region=" + (PhotonNetwork.CloudRegion ?? ""));
        }

        /// <summary>Any ft_ room: the opponent ranked check returns without its request (F03).</summary>
        internal static bool InFtRoom()
        {
            try
            {
                return PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null
                    && PhotonNetwork.CurrentRoom.Name.StartsWith("ft_", StringComparison.Ordinal);
            }
            catch { return false; }
        }

        internal static void Evaluate()
        {
            FtConfig.Refresh();
            string why = Latched ? Why : Check();
            if (FenceExemptCurrent())
            {
                // in this build's own room: the joined line once per join, on both seats
                if (_joined.Length == 0) { _joined = PhotonNetwork.CurrentRoom.Name; _peerSaid = ""; LogJoined(); StageOwnDll(); }
            }
            else _joined = "";
            bool armed = why == null;
            if (Armed && !armed && !Latched)
            {
                Latched = true;
                // the completed sitting's own end is not a disarm (it leaves the room after game 16); every other
                // input, escape and a rematch timeout included (round-1 MEDIUM, FtDrive.cs:60), is
                if (why == "complete") Plugin.Log.LogInfo("[FRAME-TIME] ended why=complete pt=" + FtSchedule.Label());
                else Plugin.Log.LogWarning("[FRAME-TIME] disarmed input=" + why + " pt=" + FtSchedule.Label());
            }
            else if (armed && !Armed)
                Plugin.Log.LogInfo("[FRAME-TIME] armed room=" + PhotonNetwork.CurrentRoom.Name + " region=" + Region());
            else if (!armed && !Latched && why != Why)
                Plugin.Log.LogInfo("[FRAME-TIME] not armed input=" + why);
            Armed = armed;
            Why = why;
        }

        private static string Region()
        {
            string r = PhotonNetwork.CloudRegion ?? "";
            int i = r.IndexOf('/');
            return i >= 0 ? r.Substring(0, i) : r;
        }

        /// <summary>The inputs the sitting and the menu self-check share.</summary>
        private static string Common()
        {
            if (!FtConfig.Present) return "sentinel";
            if (FtConfig.Changed) return "sentinel_changed";
            if (FtConfig.Problems.Length > 0) return "sentinel_problems";
            if (!FtClock.Installed) return "clock";
            string probe = CombatEvidencePerf.Mode;
            if (probe == "menu" || probe == "match") return "perf_probe";
            if (_icFixture) return "ic_fixture";
            return null;
        }

        /// <summary>The menu self-check's own arming (build decision 14): the shared inputs, no room and no
        /// game. FtMenu evaluates it at every frame boundary while the sentinel names menu=1.</summary>
        internal static string MenuCheck()
        {
            try
            {
                string c = Common();
                if (c != null) return c;
                if (PhotonNetwork.InRoom) return "in_room";
                if (FtSchedule.Game >= 0) return "game_started";
                return null;
            }
            catch (Exception ex) { return "error_" + ex.GetType().Name; }
        }

        private static string Check()
        {
            try
            {
                if (FtDrive.Complete) return "complete";
                if (FtDrive.Escaped) return "escape";
                if (FtRematch.TimedOut) return "rematch_timeout";
                string c = Common();
                if (c != null) return c;
                if (FtConfig.Menu) return "menu_mode";   // a menu self-check process never arms the sitting
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return "room";
                if (GameStateWatcher.MatchIsRanked) return "matchIsRanked";
                string want = ExpectedRoom();
                if (want == null) return "own_sha";
                if (!string.Equals(PhotonNetwork.CurrentRoom.Name, want, StringComparison.Ordinal)) return "room_name";
                if (!string.Equals(Region(), FT_REGION, StringComparison.OrdinalIgnoreCase)) return "region";
                if (RoomActors.ActiveFighterCount() != 2) return "fighters";
                string known;
                string unknown = UnknownPeer(out known);
                if (unknown != null)
                {
                    string said = "unknown actor=" + unknown;
                    if (said != _peerSaid) { _peerSaid = said; Plugin.Log.LogInfo("[FRAME-TIME] peer " + said + " (no matching " + DLL_PROP + ")"); }
                    return "peer";
                }
                string ok = "known actor=" + known + " " + DLL_PROP + "=" + OwnDll();
                if (ok != _peerSaid) { _peerSaid = ok; Plugin.Log.LogInfo("[FRAME-TIME] peer " + ok); }
                return null;
            }
            catch (Exception ex) { return "error_" + ex.GetType().Name; }
        }
    }
}
#endif
