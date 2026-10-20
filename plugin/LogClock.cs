using System;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// [CLOCK] marker lines (night of 2026-10-19 finding: mod log lines carry
    /// no time, and two seats' clocks differed by 12.9 s, so per-second rates
    /// and cross-seat alignment were not measurable from the logs). One line
    /// a minute from the always-on persistent tick, the first on the first
    /// tick. The line's format is LogBundleCore.FormatClockLine, which the
    /// DSN-free harness executes; this class only reads the three clocks on
    /// the main thread.
    /// </summary>
    internal static class LogClock
    {
        private static double _lastAt = -1;

        internal static void Tick()
        {
            double now = Time.realtimeSinceStartup;
            if (!LogBundleCore.ClockDue(now, _lastAt)) return;
            _lastAt = now;
            bool connected = false;
            int serverMs = 0;
            int localMs = Environment.TickCount;
            try
            {
                connected = PhotonNetwork.IsConnectedAndReady && !PhotonNetwork.OfflineMode;
                if (connected)
                {
                    serverMs = PhotonNetwork.ServerTimestamp;
                    localMs = Environment.TickCount;
                }
            }
            catch { connected = false; }
            Plugin.Log.LogInfo(LogBundleCore.FormatClockLine(DateTime.UtcNow, now, connected, serverMs, localMs));
        }
    }
}
