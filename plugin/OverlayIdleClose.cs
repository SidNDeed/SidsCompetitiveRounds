using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Closes the F5 overlay when it has been left open with nobody at
    /// the keyboard or mouse (Sid, Sept 4: the broadcast seat sat on the Music
    /// tab over a live spectate for whole games; players park it too).
    ///
    /// Presence is the RAW input surface — any key or mouse button down, a mouse
    /// movement, or a scroll tick — never the overlay's own widgets: a reader who
    /// scrolls a list or nudges the mouse is present even when nothing is
    /// clicked, and this seat's synthetic input cannot reach the widgets anyway
    /// (#420). The timer starts when the page opens (any path: F5, a join
    /// transition, the broadcast lever) and restarts on every sign of presence.
    /// A page modal awaiting a decision (bet amount, LFP ping, first-run language
    /// prompt) counts as in use: the close never fires under one (r1 MEDIUM 2).
    ///
    /// Scope, by design: a PLAYER seat is only ever idle-closed inside a live
    /// online room (a match, a lobby, a spectate) — at the main menu a page left
    /// open is nobody's problem, and the idle showcase manages its own pages
    /// there. Inside a room the page closes after PLAYER_CLOSE_SEC without input;
    /// a courtesy toast is issued once per idle episode at PLAYER_WARN_SEC. The
    /// close does NOT depend on that toast: three review rounds of coupling the
    /// close to the toast's delivery, replacement and per-lifetime retry budget
    /// each found the next hole inside the previous repair, so the coupling was
    /// deleted rather than repaired again (r3 cut). Failure direction: a seat
    /// that produced no input for PLAYER_CLOSE_SEC inside a live room loses one
    /// page and reopens it with F5; a seat that was present produced input and
    /// never reaches the close. With notifications off the toast cannot show and
    /// the close still fires (logged once per session). The BROADCAST seat has
    /// no reader: in a room it closes after a short quiet spell with no warning,
    /// and at the menu it closes a lever-opened page after a minute (long enough
    /// for the verification screenshots that lever exists for) while leaving
    /// showcase-owned pages to the showcase.</summary>
    internal static class OverlayIdleClose
    {
        private const float PLAYER_WARN_SEC = 60f;
        private const float PLAYER_CLOSE_SEC = 75f;          // the toast text promises 15 s more
        private const float BROADCAST_ROOM_CLOSE_SEC = 30f;
        private const float BROADCAST_MENU_CLOSE_SEC = 60f;

        private static bool wasOpen;
        private static bool warned;             // one toast per idle episode
        private static bool notifOffLogged;
        private static float lastPresenceRt;
        private static Vector3 lastMouse;

        /// <summary>Room state read straight from Photon (r1 MEDIUM 1):
        /// `GameStateWatcher.IsInOnlineRoom` is backed by a flag its Poll()
        /// stops maintaining on a spectator seat, so a spectate started from the
        /// menu reads as "no room" there for the whole session. `InRoom` on a
        /// non-offline connection is true for fighters, lobbies and spectators
        /// alike and false for the offline Sandbox room that lingers at the
        /// post-Sandbox menu (#122).</summary>
        internal static bool InLiveOnlineRoom
        {
            get { try { return PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode; } catch { return false; } }
        }

        /// <summary>Called from the persistent tick every frame. Cheap: three
        /// input reads while the page is open, one bool when it is not.</summary>
        internal static void Tick()
        {
            bool open;
            try { open = NativeUI.IsOpen; } catch { return; }
            if (!open) { wasOpen = false; return; }
            float now = Time.realtimeSinceStartup;
            if (!wasOpen)
            {
                wasOpen = true; warned = false; lastPresenceRt = now; lastMouse = Input.mousePosition;
                return;
            }
            Vector3 mouse = Input.mousePosition;
            bool present = Input.anyKeyDown
                || Input.GetMouseButton(0) || Input.GetMouseButton(1)
                || (mouse - lastMouse).sqrMagnitude > 4f
                || Input.mouseScrollDelta.sqrMagnitude > 0f;
            lastMouse = mouse;
            if (present) { lastPresenceRt = now; warned = false; return; }
            bool prompt;
            try { prompt = NativeUI.HasOpenPrompt; } catch { prompt = false; }
            if (prompt) { lastPresenceRt = now; warned = false; return; }

            bool inRoom = InLiveOnlineRoom;
            bool broadcast;
            try { broadcast = BroadcastMode.IsBroadcastIdentity; } catch { broadcast = false; }
            float idle = now - lastPresenceRt;

            if (broadcast)
            {
                if (inRoom) { if (idle >= BROADCAST_ROOM_CLOSE_SEC) CloseIdle("broadcast-room", idle); return; }
                bool showcase;
                try { showcase = NativeUI.ShowcaseOwnsPage; } catch { showcase = false; }
                if (showcase) { lastPresenceRt = now; return; }   // the showcase opens and closes its own pages
                if (idle >= BROADCAST_MENU_CLOSE_SEC) CloseIdle("broadcast-menu", idle);
                return;
            }
            if (!inRoom) { lastPresenceRt = now; warned = false; return; }
            if (!warned && idle >= PLAYER_WARN_SEC)
            {
                warned = true;
                bool delivered = false;
                try { delivered = CompetitiveUI.ShowNotification(I18n.Tr("Menu closes in 15 s - move the mouse to keep it open"), Color.yellow, 6f); }
                catch { }
                if (!delivered && !notifOffLogged)
                {
                    bool notifOff = false;
                    try { notifOff = Plugin.ShowNotifications != null && !Plugin.ShowNotifications.Value; } catch { }
                    if (notifOff)
                    {
                        notifOffLogged = true;
                        Plugin.Log?.LogInfo("[NATIVE] idle-close: notifications are off, so the 15 s warning cannot be shown; an idle page inside a room still closes after " + PLAYER_CLOSE_SEC + " s");
                    }
                }
            }
            if (idle >= PLAYER_CLOSE_SEC) CloseIdle("player-room", idle);
        }

        private static void CloseIdle(string why, float idle)
        {
            Plugin.Log?.LogInfo($"[NATIVE] idle-close ({why}) after {idle:F0}s without input");
            try { NativeUI.Close(); } catch { }
            wasOpen = false; warned = false;
        }
    }
}
