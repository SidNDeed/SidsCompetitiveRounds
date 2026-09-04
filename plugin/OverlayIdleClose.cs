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
    ///
    /// Scope, by design: a PLAYER seat is only ever idle-closed inside an online
    /// room (a match, a lobby, a spectate) — at the main menu a page left open is
    /// nobody's problem, and the idle showcase manages its own pages there. The
    /// player gets a toast 15 s before the close. The BROADCAST seat has no
    /// reader: in a room it closes after a short quiet spell with no warning, and
    /// at the menu it closes a lever-opened page after a minute (long enough for
    /// the verification screenshots that lever exists for) while leaving showcase-
    /// owned pages to the showcase.</summary>
    internal static class OverlayIdleClose
    {
        private const float PLAYER_WARN_SEC = 60f;
        private const float PLAYER_CLOSE_SEC = 75f;
        private const float BROADCAST_ROOM_CLOSE_SEC = 30f;
        private const float BROADCAST_MENU_CLOSE_SEC = 60f;

        private static bool wasOpen;
        private static bool warned;
        private static float lastPresenceRt;
        private static Vector3 lastMouse;

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

            bool inRoom;
            try { inRoom = GameStateWatcher.IsInOnlineRoom; } catch { inRoom = false; }
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
                try { CompetitiveUI.ShowNotification(I18n.Tr("Menu closes in 15 s - move the mouse to keep it open"), Color.yellow, 6f); } catch { }
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
