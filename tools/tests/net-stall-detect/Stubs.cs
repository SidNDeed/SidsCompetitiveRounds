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

    internal static partial class GameStateWatcher
    {
        internal static bool PlainOneVOne;
        internal static bool IsPlainOneVOneForHud() { return PlainOneVOne; }

        // Dependencies of the two unchanged production resets. Only the focus
        // state is observed by these controls; unrelated callees are no-ops.
        private static bool tlUnfocused, oppSeqBaselineTaken, oppSeqTransitionSeen, _recvGapOpen;
        private static bool _oppHbGapOpen, _activationSuccessCredited, _loggedFirstFire, _loggedFirstHit;
        private static bool _loggedFirstBlockAct, _loggedFirstBlockOk, _loggedHitBudgetDrop, OppExpandedTelemetrySeen;
        private static bool isTracking, gameOverReported, oneVOneMatchAtStart, macroEvidenceDispatched;
        private static bool sharedGameT0Set, wasGameInProgress, pcolorRoomApplied, playersIdentified;
        private static bool opponentSteamIdResolved, opponentRankChecked, opponentIsRanked, matchIsRanked;
        private static bool opponentCardsViaHarmony, fieldsResolved, opponentWasPresent, opponentDCReported;
        private static bool achTookDamage, achPhoenixUsed, achDied, achWasDown04;
        private static bool lastDeadState, achFiredShot, achMoved, achJumped;
        private static bool achLeftmostViolated, abyssalActivatedThisRound, inPickPhase;
        private static float inputBucketTimer, LocalActiveSecondsThisMatch, LastBlockActivatedTime, LastBlockSuccessfulTime;
        private static float LastBlockAbsorbTime, LastLocalHitTime, LastBlockMissTime, fpsTimeAccum;
        private static float fpsBroadcastTimer, tlAccum, bcAccum, lastOppSeqAdvanceTime;
        private static float localFreezeTotalSec, _bandTotalSec, _bandSummaryAt, LocalDamageTakenThisMatch;
        private static float LocalDamageDealtThisMatch, LocalMaxSingleHit, LocalMaxHealthSeen, OppDamageDealt;
        private static float OppMaxSingleHit, OppMaxHealthSeen;
        private static int LocalShotsThisMatch, LocalBlocksThisMatch, LocalKeysThisMatch, LocalMacroSuspectSeconds;
        private static int LocalMacroPeakKeysPerSecond, LocalMacroPeakClicksPerSecond, LocalMacroPeakEventsPerSecond, inputBucketCount;
        private static int inputBucketKeyCount, inputBucketClickCount, LocalBulletsFiredThisMatch, LocalBulletsHitThisMatch;
        private static int LocalBlocksActivatedThisMatch, LocalBlocksSuccessfulThisMatch, LocalBlockRawAbsorbs, LocalBlockDedupeDrops;
        private static int fpsFrameCount, opponentAvgFps, tlFrames, bcFrames;
        private static int lastBroadcastRecentFps, lastOppGstatsSeq, oppSeqActor, oppRttCurrent;
        private static int localFreezeCount, localFreezeFocusedCount, _freezeLogged, _bandCount;
        private static int _bandMaxMs, _bandLogged, _bandSummaries, _bandSummarisedCount;
        private static int localRecvGapCount, localRecvGapMaxMs, oppHbGapCount, oppFreezeCount;
        private static int oppFreezeFocusedCount, oppRecvGapCount, OppFreezeStatsEpoch, OppFreezeEpoch;
        private static int _hitsRemaining, LocalBestBounceKill, LocalDeaths, LocalDeathsBoundary;
        private static int LocalDeathsOwnBullet, OppDeathsObserved, OppDeathsBoundaryObserved, OppDeathsOwnBulletObserved;
        private static int OppBestBounceKill, matchStartServerTimestamp, sharedGameT0, p1Points;
        private static int p2Points, p1Rounds, p2Rounds, lastP1Points;
        private static int lastP2Points, lastP1Rounds, lastP2Rounds, currentRound;
        private static int localTeamId, lastKnownP1CardCount, lastKnownP2CardCount, pickCountThisMatch;
        private static int lastKnownOpponentBroadcastCount, preMatchPickCount, achMaxOpponentRounds, lastRemainingRespawns;
        private static int abyssalRoundsActivated, OppStatMacroSuspectSeconds, OppStatMacroPeakKeysPerSecond, OppStatMacroPeakClicksPerSecond;
        private static int OppStatMacroPeakEventsPerSecond;
        private static long inputBucketStartedAtMs, _lastTickStopwatchMs;
        private static string LastBlockEventLabel, endStatsLocal, sharedGameToken, previousGameToken;
        private static string OppStatMacroTimeline;
        private static readonly DecimatedList<int> localDamage3sTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> localDamageTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> localFps3sTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> localFpsFocusTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> localFpsTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> oppDamageTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> oppFpsTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> oppPingTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<string> localBlockTimeline = new DecimatedList<string>();
        private static readonly DecimatedList<string> localHitTimeline = new DecimatedList<string>();
        private static readonly DecimatedList<string> oppBlockTimeline = new DecimatedList<string>();
        private static readonly DecimatedList<string> oppHitTimeline = new DecimatedList<string>();
        private static readonly Dictionary<int, PeerTelemetry> peerTele = new Dictionary<int, PeerTelemetry>();
        private static readonly Dictionary<string, string> endStatsBySteam = new Dictionary<string, string>();
        private static readonly List<MatchTracker.CardOfferData> localOffers = new List<MatchTracker.CardOfferData>();
        private static readonly List<MatchTracker.CardPickData> localCards = new List<MatchTracker.CardPickData>();
        private static readonly List<MatchTracker.CardPickData> opponentCards = new List<MatchTracker.CardPickData>();
        private static readonly List<MatchTracker.CardPickData> preMatchCards = new List<MatchTracker.CardPickData>();
        private static readonly List<MatchTracker.CardPickData> preMatchOpponentCards = new List<MatchTracker.CardPickData>();
        private static readonly List<int> pingSamples = new List<int>();
        private static readonly List<int> pointTimes = new List<int>();
        private static readonly List<string> broadcastCardNames = new List<string>();
        private static readonly List<string> inputSuspectWindows = new List<string>();
        private sealed class PeerTelemetry { }
        private const string CARD_PROP_KEY = "cr_cards";
        private static void FlushFreezeBandSummary(bool final) { }

        internal static DecimatedList<int> TestFpsTimeline { get { return localFpsTimeline; } }
        internal static DecimatedList<int> TestFocusTimeline { get { return localFpsFocusTimeline; } }
        internal static int TestFocusFrames { get { return tlFrames; } }
        internal static float TestFocusAccum { get { return tlAccum; } }
        internal static bool TestUnfocused { get { return tlUnfocused; } }

        internal static void TestSeedFocusReset()
        {
            localFpsTimeline.Clear();
            localFpsFocusTimeline.Clear();
            for (int i = 0; i < 300; i++)
            {
                localFpsTimeline.Add(1000 + i);
                localFpsFocusTimeline.Add(i % 2);
            }
            tlFrames = 3; tlAccum = 1.5f; tlUnfocused = true;
        }

        internal static void TestResetFocus(bool perMatch)
        {
            if (perMatch) ResetPerMatchCombatCounters();
            else ResetMatchState();
        }

        // Mirror only TickFrame's five-second sampling block, as the existing
        // FocusTrackedBucket control does, over the real reset-owned fields.
        internal static void TestFocusFrame(bool focused, float dt)
        {
            tlUnfocused = FpsFocusCore.ObserveFrame(tlUnfocused, focused, dt);
            if (dt <= 0f || dt > 1f) return;
            tlFrames++; tlAccum += dt;
            if (tlAccum >= 5f)
            {
                localFpsTimeline.Add((int)Math.Round(tlFrames / (double)tlAccum));
                localFpsFocusTimeline.Add(FpsFocusCore.BucketFlag(tlUnfocused));
                tlUnfocused = false;
                tlFrames = 0; tlAccum = 0f;
            }
        }
    }

    internal static class MatchTracker
    {
        internal sealed class CardOfferData { }
        internal sealed class CardPickData { }
    }
    internal static class AudioSelfCheck { internal static void LogSnapshot(string why) { } }
    internal static class TabStatsOverlay { internal static void ClearCardBaselines() { } }
    internal static class BlockChain { internal static void Reset() { } }
    internal static class CombatTelemetry { internal static void ClearMatchState() { } }

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
        private const string ViewSummaryDiagKey = "net-view";
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

namespace ExitGames.Client.Photon
{
    internal sealed class Hashtable : Dictionary<object, object> { }
}
namespace Photon.Realtime
{
    internal sealed class Player
    {
        internal void SetCustomProperties(ExitGames.Client.Photon.Hashtable props) { }
    }

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
        internal static bool InRoom { get { return CurrentRoom != null; } }
        internal static Photon.Realtime.Player LocalPlayer = new Photon.Realtime.Player();
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
