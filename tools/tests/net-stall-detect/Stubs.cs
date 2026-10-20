// Stand-ins for external dependencies of the real LagNotices evaluator and
// the exact NetworkReplicaDiagnostics methods extracted at each build.
// Controls set the dependency state per case; production decisions stay real.
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
        private T _value;
        internal T Value
        {
            get { return _value; }
            set
            {
                if (EqualityComparer<T>.Default.Equals(_value, value)) return;
                _value = value;
                SettingChanged?.Invoke(this, EventArgs.Empty);
            }
        }
        internal ConfigFile ConfigFile;
        internal event EventHandler SettingChanged;
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

    internal static partial class NetworkReplicaDiagnostics
    {
        private const int ACTOR_SCAN_CAP = 32;
        internal const string JitterDiagKey = "NetworkReplicaDiagnostics-jitter";
        internal const string GameSummaryDiagKey = "NetworkReplicaDiagnostics-game-summary";
        private const string ViewSummaryDiagKey = "NetworkReplicaDiagnostics-view-summary";
        private static readonly Dictionary<int, ActorStats> Actors = new Dictionary<int, ActorStats>();
        private static readonly NetJitterBudgetCore _jitterBudget = new NetJitterBudgetCore();
        private static bool _roomActive, _gameActive, _gameEnded, _gamePartial;
        private static Photon.Realtime.Room _observedRoom;
        private static int _roomStartedAtMs;
        private sealed class ActorStats
        {
            internal readonly TimingWindow Game = new TimingWindow();
            internal int PlayerViewId;
        }
        private sealed class TimingWindow { internal long Views, Batches; }

        // Only dependencies outside the two extracted production methods are
        // stand-ins. The roster selection and same-room branch are real text.
        private static void ResetState()
        {
            _roomActive = _gameActive = _gameEnded = _gamePartial = false;
            _observedRoom = null;
            _jitterBudget.ResetRoom();
            Actors.Clear();
        }
        private static void FlushOpenArrivalGaps(string why) { }
        private static void EmitGameSummary(string why) { }
        private static void EmitRoomSummary(string why) { }
        internal static NetJitterBudgetCore TestJitterBudget { get { return _jitterBudget; } }
        internal static void TestResetReplica(bool spectator)
        {
            ResetState();
            Photon.Pun.PhotonNetwork.OfflineMode = false;
            Photon.Pun.PhotonNetwork.CurrentRoom = new Photon.Realtime.Room();
            SpectatorSession.IsLocalSpectator = spectator;
            VanillaFixSupport.DiagResets.Clear();
        }
        internal static void TestActor(int actor, int playerView, long views, long batches, bool present = true)
        {
            ActorStats a;
            if (!Actors.TryGetValue(actor, out a)) Actors[actor] = a = new ActorStats();
            a.PlayerViewId = playerView;
            a.Game.Views = views;
            a.Game.Batches = batches;
            if (present) Photon.Pun.PhotonNetwork.CurrentRoom.Players[actor] = new object();
            else Photon.Pun.PhotonNetwork.CurrentRoom.Players.Remove(actor);
        }
        internal static void TestPrimeSameRoom()
        {
            _roomActive = true;
            _observedRoom = Photon.Pun.PhotonNetwork.CurrentRoom;
        }

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

namespace Photon.Realtime
{
    internal sealed class Room
    {
        internal readonly Dictionary<int, object> Players = new Dictionary<int, object>();
    }
}
namespace Photon.Pun
{
    internal static class PhotonNetwork
    {
        internal static bool OfflineMode;
        internal static Photon.Realtime.Room CurrentRoom;
    }
}
namespace CompetitiveRounds
{
    internal static class SpectatorSession { internal static bool IsLocalSpectator; }
    internal static class VanillaFixSupport
    {
        internal static readonly List<string> DiagResets = new List<string>();
        internal static void ResetDiag(string key) { DiagResets.Add(key); }
        internal static void LogError(string where, Exception ex) { throw new InvalidOperationException(where, ex); }
    }
    internal static class NetDiag { internal static void RebaseOrphanCounter() { } }
}
