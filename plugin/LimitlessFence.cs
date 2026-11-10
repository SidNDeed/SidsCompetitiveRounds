using System;
using System.Security.Cryptography;
using HarmonyLib;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) lane 2, design v4 (md5 4283f353) 4.2 and 4.3: the game's
    /// identity, the seat's epoch and its handoff count, wired to Photon's
    /// edges. The rules are LimitlessFenceRules; this class holds the seat's
    /// state and reads the room.
    /// - The gid is the room property cr_lgid. The creating seat stamps a first
    ///   value into the room's initial properties. Each physical game mints a
    ///   new one by compare-and-set, in the game-start prefix below.
    /// - A seat adopts a value only as the server relays it, with the room's
    ///   properties at its join or in OnRoomPropertiesUpdate. Its own write
    ///   counts only at its echo (lesson 428).
    /// - The epoch rises at each of the seat's own game starts (a spectator's
    ///   is its first call-in after the terminal score) and at room exit. The
    ///   handoff count rises at every master switch, before anything else
    ///   there.
    /// Nothing here is a barrier: no seat waits for a gid (lessons 280, 287).
    /// </summary>
    internal static class LimitlessFence
    {
        internal const string GidKey = "cr_lgid";

        private static readonly LimitlessFenceRules.GidLedger _ledger = new LimitlessFenceRules.GidLedger();
        private static int _epoch;
        private static int _handoff;
        private static bool _awaiting;
        private static bool _startedInRoom;
        private static bool _spectatorBoundaryDue;

        internal static int Epoch { get { return _epoch; } }
        internal static int HandoffCount { get { return _handoff; } }

        /// <summary>The seat's live gid, or null while it holds none.</summary>
        internal static string CurrentLiveGid
        {
            get
            {
                var g = _ledger.CurrentGid;
                return _ledger.IsLiveGid(g) ? g : null;
            }
        }

        internal static string NewGid()
        {
            var b = new byte[LimitlessFenceRules.GidLength / 2];
            using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(b);
            return LimitlessFenceRules.GidOf(b);
        }

        /// <summary>4.2: the creating seat's first value goes into the room's
        /// initial properties, so no write races it.</summary>
        internal static void StampInitialGid(ExitGames.Client.Photon.Hashtable roomProps)
        {
            try
            {
                if (roomProps != null) roomProps[GidKey] = NewGid();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[LIMIT] gid stamp failed, the room runs without the feature: " + ex.Message);
            }
        }

        private static string RoomGid()
        {
            var room = PhotonNetwork.CurrentRoom;
            var props = room != null ? room.CustomProperties : null;
            object v = null;
            if (props != null) props.TryGetValue(GidKey, out v);
            return v as string;
        }

        private static string GidPrefix(string gid)
        {
            return LimitlessFenceRules.IsGid(gid) ? gid.Substring(0, 8) : "none";
        }

        /// <summary>The join: the seat adopts the value it receives with the
        /// room's properties.</summary>
        internal static void NoteJoinedRoom()
        {
            _startedInRoom = false;
            _spectatorBoundaryDue = false;
            _awaiting = true;
            TryAdopt(RoomGid(), "join");
        }

        /// <summary>Room exit is a terminal path (5.3): the current gid ends,
        /// and the epoch rises.</summary>
        internal static void NoteLeftRoom()
        {
            _epoch++;
            _ledger.ExitRoom();
            _awaiting = false;
            _startedInRoom = false;
            _spectatorBoundaryDue = false;
        }

        /// <summary>A master switch. The handoff count rises first, so work
        /// scheduled under the previous master period never acts in this one,
        /// even when this seat is master again (4.3). A seat that becomes master
        /// after its own game start while it holds no live gid mints (4.2).</summary>
        internal static void NoteMasterSwitched(Photon.Realtime.Player newMaster)
        {
            _handoff++;
            if (newMaster != null && newMaster.IsLocal) TryMint("handoff");
        }

        /// <summary>The seat's own physical game start (the prefix below). The
        /// epoch rises; the previous gid ends; the room's value is adopted if
        /// this seat has not ended it, else the seat awaits the next arrival.
        /// Then the master mints over a value it has ended.</summary>
        internal static void NoteOwnGameStart()
        {
            _epoch++;
            _startedInRoom = true;
            _spectatorBoundaryDue = false;
            bool adopted = _ledger.AtOwnGameStart(RoomGid());
            _awaiting = !adopted;
            Plugin.Log.LogInfo("[LIMIT] game start: epoch=" + _epoch + " gid=" + (adopted ? GidPrefix(_ledger.CurrentGid) : "awaiting"));
            TryMint("start");
        }

        /// <summary>A spectator's terminal score (GM: the observer's game over;
        /// FFA: SpectatorCheckGameOver). The observed game is over, so its gid
        /// ends, and the next call-in opens the next game (5.3). Only the first
        /// report of a game counts.</summary>
        internal static void NoteSpectatorGameOver(string mode)
        {
            if (_spectatorBoundaryDue) return;
            _spectatorBoundaryDue = true;
            var g = _ledger.CurrentGid;
            if (g != null) _ledger.EndGid(g);
            Plugin.Log.LogInfo("[LIMIT] spectator game over (" + mode + "): gid " + GidPrefix(g) + " ended");
        }

        /// <summary>A spectator's call-in. The first after the terminal score
        /// opens the next game: the epoch rises, and the room's value is adopted
        /// if this seat has not ended it. In the server's order the master's
        /// mint precedes its call-in, so the value has usually arrived.</summary>
        internal static void NoteSpectatorCallIn()
        {
            if (!_spectatorBoundaryDue) return;
            _spectatorBoundaryDue = false;
            _epoch++;
            TryAdopt(RoomGid(), "spectator boundary");
            Plugin.Log.LogInfo("[LIMIT] spectator next game: epoch=" + _epoch + " gid=" + GidPrefix(CurrentLiveGid));
        }

        /// <summary>A room property change, as the server relays it.</summary>
        internal static void NoteRoomProps(ExitGames.Client.Photon.Hashtable changed)
        {
            if (changed == null || !changed.ContainsKey(GidKey)) return;
            TryAdopt(changed[GidKey] as string, "arrival");
        }

        private static void TryAdopt(string value, string why)
        {
            if (!LimitlessFenceRules.AdoptOnArrival(_awaiting, RoomActors.LocalIsSpectator, value, _ledger)) return;
            if (!_ledger.AdoptRelayed(value)) return;
            _awaiting = false;
            Plugin.Log.LogInfo("[LIMIT] adopted gid " + GidPrefix(value) + " (" + why + ")");
        }

        /// <summary>4.2, F1: the mint is a compare-and-set that expects the
        /// value it replaces. Of two seats that replace the same value, at most
        /// one lands, and every seat adopts the one that did. A spectator hands
        /// the master role on at once and never mints.</summary>
        private static void TryMint(string why)
        {
            try
            {
                if (RoomActors.LocalIsSpectator) return;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null || PhotonNetwork.OfflineMode) return;
                string current = RoomGid();
                if (!LimitlessFenceRules.ShouldMint(PhotonNetwork.IsMasterClient, _startedInRoom, current, _ledger)) return;
                bool sent = room.SetCustomProperties(
                    new ExitGames.Client.Photon.Hashtable { { GidKey, NewGid() } },
                    new ExitGames.Client.Photon.Hashtable { { GidKey, current } });
                Plugin.Log.LogInfo("[LIMIT] mint (" + why + "): sent=" + sent + ", expecting " + GidPrefix(current));
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[LIMIT] mint (" + why + ") failed: " + ex.Message);
            }
        }
    }

    /// <summary>
    /// The fence's game start (v4 4.2, 4.3). Every mode's physical game start
    /// calls DoStartGame: StartGame (GM_ArmsRace:202) and the rematch (:385),
    /// and FFA's prefix swaps in FfaDoStartGame at Normal priority. At
    /// Priority.First this runs before every sibling that changes the game.
    /// HarmonyX runs every prefix even when a sibling skips the original
    /// (#352), so the spectator gate is this prefix's own, the one the
    /// suppressor reads: a spectator's DoStartGame is suppressed
    /// (Spectator_NoDoStartGame_Patch), and its game opens at its call-in.
    /// </summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class LimitlessFence_GameStart_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static void Prefix()
        {
            try
            {
                if (SpectatorPatchSupport.Suppress) return;
                LimitlessFence.NoteOwnGameStart();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[LIMIT] game start: " + ex.Message);
            }
        }
    }
}
