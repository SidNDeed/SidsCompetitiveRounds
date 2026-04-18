using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>
    /// Shared data classes used by GameStateWatcher, ApiClient, and CompetitiveUI.
    /// </summary>
    public static class MatchTracker
    {
        public class CardPickData
        {
            public string CardName;
            public string CardRarity;
            public int PickOrder;
            public int RoundNumber;
        }

        public class CardOfferData
        {
            public string CardName;
            public int RoundNumber;
            public bool WasPicked;
        }

        public class MatchResult
        {
            public bool Won;
            public int MyRounds;
            public int TheirRounds;
            public string OpponentName;
            public DateTime Timestamp;
        }

        // Delegate to GameStateWatcher for all state
        public static bool IsInMatch => GameStateWatcher.IsInMatch;
        public static bool IsInRoom => GameStateWatcher.IsInRoom;
        public static string LocalSteamId => GameStateWatcher.LocalSteamId;
        public static string LocalDisplayName => GameStateWatcher.LocalDisplayName;
        public static string OpponentDisplayName => GameStateWatcher.OpponentDisplayName;
        public static MatchResult LastResult => GameStateWatcher.LastResult;
        public static bool HasPendingResult => GameStateWatcher.HasPendingResult;
        public static int P1Rounds => GameStateWatcher.P1Rounds;
        public static int P2Rounds => GameStateWatcher.P2Rounds;
        public static int P1Points => GameStateWatcher.P1Points;
        public static int P2Points => GameStateWatcher.P2Points;
        public static int LocalTeamId => GameStateWatcher.LocalTeamId;

        public static void Initialize()
        {
            // Initialization now handled by GameStateWatcher
        }
    }
}
