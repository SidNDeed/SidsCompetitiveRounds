using System;
using System.Collections.Generic;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Key-based quick-chat (localization-design §2.6): ~14 canned phrases
    /// carried as a Photon RaiseEvent payload {byte proto, int actor,
    /// byte phraseId} on event code 48 (PoisonSync owns 47). The KEY is sent,
    /// never the text — each recipient renders the phrase from its OWN locale
    /// catalogue via I18n.Tr, so a matched Russian and English player each
    /// read the phrase in their own language. This is the one chat surface
    /// that must not be language-partitioned.
    ///
    /// ReceiverGroup.All so the sender renders down the same receive path as
    /// everyone else (one code path, one ordering — the PoisonSync rule).
    /// </summary>
    internal static class QuickChat
    {
        private const byte EventCode = 48;
        private const byte Protocol = 1;

        // English canonical phrases — these strings are catalogue KEYS
        // (I18nCatalogues carries es/ru targets). Order is the wire id:
        // NEVER reorder or remove entries, only append (a mixed-version room
        // must agree on what id N says). Unknown ids render as nothing.
        internal static readonly string[] Phrases =
        {
            "Good luck, have fun!",     // 0
            "Good game!",               // 1
            "Well played!",             // 2
            "Nice shot!",               // 3
            "So close!",                // 4
            "Thanks!",                  // 5
            "Sorry!",                   // 6
            "Be right back",            // 7
            "I'm ready",                // 8
            "Hold on!",                 // 9
            "Rematch?",                 // 10
            "Last game for me",         // 11
            "Hello!",                   // 12
            "Bye!",                     // 13
        };

        private static bool _hooked;
        private static float _lastSendAt = -999f;
        // Per-sender receive throttle so a spammer can't flood everyone's
        // notification queue. Actor numbers are ROOM-LOCAL (wave-2 find 24):
        // the map is cleared whenever the room name changes, so a new room's
        // actor 2 never inherits the old room's throttle window.
        private static readonly Dictionary<int, float> _lastRecvByActor = new Dictionary<int, float>();
        private static string _throttleRoom;

        internal static void Hook()
        {
            if (_hooked) return;
            try
            {
                PhotonNetwork.NetworkingClient.EventReceived += OnEvent;
                _hooked = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[QUICKCHAT] hook failed: {ex.Message}"); }
        }

        /// <summary>Send phrase by id. No-op outside an online room, on an
        /// out-of-range id, or inside the 2s local send throttle.</summary>
        internal static bool Send(int phraseId)
        {
            if (phraseId < 0 || phraseId >= Phrases.Length) return false;
            if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
            if (Time.unscaledTime - _lastSendAt < 2f) return false;
            _lastSendAt = Time.unscaledTime;
            try
            {
                bool ok = PhotonNetwork.RaiseEvent(
                    EventCode,
                    new object[] { Protocol, PhotonNetwork.LocalPlayer.ActorNumber, (byte)phraseId },
                    new RaiseEventOptions { Receivers = ReceiverGroup.All },
                    SendOptions.SendReliable);
                // RaiseEvent can return false WITHOUT throwing (#280c). A
                // quick-chat line is fire-and-forget — log it, never retry.
                if (!ok) Plugin.Log.LogWarning("[QUICKCHAT] RaiseEvent returned false");
                return ok;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[QUICKCHAT] send threw: {ex.Message}");
                return false;
            }
        }

        private static void OnEvent(EventData e)
        {
            if (e.Code != EventCode) return;
            try
            {
                var a = e.CustomData as object[];
                if (a == null || a.Length < 3) return;
                if (!(a[0] is byte) || (byte)a[0] != Protocol) return;
                int claimedActor = a[1] is int ? (int)a[1] : -1;
                // Anti-spoof: the payload's actor must match Photon's own
                // sender stamp — e.Sender is the transport truth.
                if (claimedActor != e.Sender) return;
                int phraseId = a[2] is byte ? (byte)a[2] : -1;
                if (phraseId < 0 || phraseId >= Phrases.Length) return;

                string roomNow = null;
                try { roomNow = PhotonNetwork.CurrentRoom?.Name; } catch { }
                if (roomNow != _throttleRoom) { _lastRecvByActor.Clear(); _throttleRoom = roomNow; }
                float last;
                if (_lastRecvByActor.TryGetValue(e.Sender, out last)
                    && Time.unscaledTime - last < 1.5f)
                    return;
                _lastRecvByActor[e.Sender] = Time.unscaledTime;

                string name = "?";
                try
                {
                    var room = PhotonNetwork.CurrentRoom;
                    Photon.Realtime.Player p = room != null ? room.GetPlayer(e.Sender) : null;
                    if (p != null && !string.IsNullOrEmpty(p.NickName)) name = p.NickName;
                }
                catch { }
                // NickName can carry nametag rich text — neutralise brackets.
                // ASCII parens, NOT fullwidth twins (wave-2 find 23): this
                // renders through IMGUI (GUI.Label), outside the TMP fallback
                // atlas, where U+FF1C/FF1E are tofu on the default font.
                name = name.Replace("<", "(").Replace(">", ")");
                if (name.Length > 24) name = name.Substring(0, 24);

                // Rendered in the RECEIVER's locale — this is the point.
                string phrase = I18n.Tr(Phrases[phraseId]);
                CompetitiveUI.ShowNotification($"{name}: {phrase}", new Color(0.72f, 0.86f, 1f), 4f);
                NativeUI.AddQuickChatLine(name, phrase);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[QUICKCHAT] recv error: {ex.Message}"); }
        }
    }
}
