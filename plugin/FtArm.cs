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

        /// <summary>The unmasked joined line, for the ft_ room only (both seats' lines must agree, F12).</summary>
        internal static void LogJoined()
        {
            Plugin.Log.LogInfo("[FRAME-TIME] joined room=" + PhotonNetwork.CurrentRoom.Name + " region=" + Region()
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
            string why = Latched ? Why : Check();
            if (FenceExemptCurrent())
            {
                // in this build's own room: the joined line once per join, on both seats
                if (_joined.Length == 0) { _joined = PhotonNetwork.CurrentRoom.Name; LogJoined(); }
            }
            else _joined = "";
            bool armed = why == null;
            if (Armed && !armed && !Latched)
            {
                Latched = true;
                Plugin.Log.LogWarning("[FRAME-TIME] disarmed input=" + why + " pt=" + FtSchedule.Label());
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

        private static string Check()
        {
            try
            {
                if (!FtConfig.Present) return "sentinel";
                if (FtConfig.Problems.Length > 0) return "sentinel_problems";
                if (!FtClock.Installed) return "clock";
                string probe = CombatEvidencePerf.Mode;
                if (probe == "menu" || probe == "match") return "perf_probe";
                if (_icFixture) return "ic_fixture";
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return "room";
                if (GameStateWatcher.MatchIsRanked) return "matchIsRanked";
                string want = ExpectedRoom();
                if (want == null) return "own_sha";
                if (!string.Equals(PhotonNetwork.CurrentRoom.Name, want, StringComparison.Ordinal)) return "room_name";
                if (!string.Equals(Region(), FT_REGION, StringComparison.OrdinalIgnoreCase)) return "region";
                if (RoomActors.ActiveFighterCount() != 2) return "fighters";
                return null;
            }
            catch (Exception ex) { return "error_" + ex.GetType().Name; }
        }
    }
}
#endif
