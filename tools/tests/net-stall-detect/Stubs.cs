// Stand-ins for the Unity-side classes plugin/LagNotices.cs reads, so the
// REAL evaluator file compiles in a plain net10.0 harness. Each stub holds
// only what the evaluator touches; the controls set them per case.
using System;
using System.Collections.Generic;

namespace BepInEx.Configuration
{
    internal sealed class ConfigFile
    {
        internal ConfigEntry<T> Bind<T>(string section, string key, T defaultValue, string description)
        {
            return new ConfigEntry<T> { Value = defaultValue, ConfigFile = this };
        }
    }

    internal sealed class ConfigEntry<T>
    {
        internal T Value;
        internal ConfigFile ConfigFile;
#pragma warning disable CS0067
        internal event EventHandler SettingChanged;
#pragma warning restore CS0067
    }
}

namespace CompetitiveRounds
{
    internal sealed class LogSink
    {
        internal readonly List<string> Lines = new List<string>();
        internal void LogInfo(object o) { Lines.Add(o == null ? "" : o.ToString()); }
        internal void LogWarning(object o) { Lines.Add("WARN " + (o == null ? "" : o.ToString())); }
    }

    internal static class Plugin
    {
        internal static BepInEx.Configuration.ConfigEntry<bool> LagNoticesEnabled;
        internal static BepInEx.Configuration.ConfigFile ConfigFileForLevers;
        internal static LogSink Log = new LogSink();
    }

    internal static class I18n
    {
        internal static string Tr(string english) { return english; }
        internal static string TrF(string template, params object[] args) { return string.Format(template, args); }
    }

    internal static class BroadcastMode { internal static bool IsBroadcastIdentity; }
    internal static class RoomActors { internal static bool LocalIsSpectator; }

    internal static class GameStateWatcher
    {
        internal static bool PlainOneVOne;
        internal static bool IsPlainOneVOneForHud() { return PlainOneVOne; }
    }

    internal static class TransportExit
    {
        internal static double NowSeconds() { return 0; }
        internal static bool TransportLossActive(double now) { return false; }
        internal static bool SilenceNoticeActive(double now, out int silentMs) { silentMs = 0; return false; }
        internal static int SilenceSeconds(int silentMs) { return silentMs / 1000; }
    }

    internal static class NetworkReplicaDiagnostics
    {
        internal static int DeliveryExcessMs(int arrivalGapMs, int senderGapMs)
        {
            int excess = arrivalGapMs - senderGapMs;
            return excess < 0 ? 0 : excess;
        }
    }

    /// <summary>The closed-window ring LagNotices reads, fed by the control
    /// one window at a time, newest first on read (the production order).</summary>
    internal static class NetworkSeatTelemetry
    {
        internal struct WindowFacts
        {
            public int Seq, WorstMs, OwnPing, PeerRtt, ObsLate300;
            public int OppActor; public string OppId;
        }

        internal static readonly List<WindowFacts> Ring = new List<WindowFacts>();

        internal static int RecentWindows(WindowFacts[] buf)
        {
            int n = 0;
            if (buf == null) return 0;
            for (int i = Ring.Count - 1; i >= 0 && n < buf.Length; i--) buf[n++] = Ring[i];
            return n;
        }
    }
}
