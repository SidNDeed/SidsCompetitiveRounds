using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Closes the F5 overlay on the BROADCAST seat when it has been left
    /// open with nobody at the keyboard or mouse (Sid, Sept 4: the seat sat on the
    /// Music tab over a live spectate for whole games).
    ///
    /// Presence is the RAW input surface — any key or mouse button down, a mouse
    /// movement, or a scroll tick — never the overlay's own widgets (this seat's
    /// synthetic input cannot reach the widgets anyway, #420). The timer starts
    /// when the page opens (any path: F5, a join transition, the broadcast lever)
    /// and restarts on every sign of presence. A page modal awaiting a decision
    /// (bet amount, LFP ping, first-run language prompt) counts as in use.
    ///
    /// Scope: broadcast identity ONLY. A player-seat branch (toast at 60 s, close
    /// at 75 s inside a live online room) went through four review rounds and was
    /// cut (r4): a close nobody asked for releases the overlay's input capture,
    /// and a movement input still held at that moment — a controller stick, a
    /// key held past its down edge, neither of which the raw presence read sees —
    /// reaches the live fighter. A player version needs the game's own input
    /// state as the presence signal and must not close during active combat;
    /// that is a design item, not a patch. The broadcast seat is never a fighter.
    /// In a room it closes after a short quiet spell with no warning (there is no
    /// reader), and at the menu it closes a lever-opened page after a minute
    /// (long enough for the verification screenshots that lever exists for)
    /// while leaving showcase-owned pages to the showcase.</summary>
    internal static class OverlayIdleClose
    {
        private const float BROADCAST_ROOM_CLOSE_SEC = 30f;
        private const float BROADCAST_MENU_CLOSE_SEC = 60f;

        private static bool wasOpen;
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

        /// <summary>Called from the persistent tick every frame. One bool on a
        /// player seat; three input reads while the broadcast page is open.</summary>
        internal static void Tick()
        {
            bool broadcast;
            try { broadcast = BroadcastMode.IsBroadcastIdentity; } catch { return; }
            if (!broadcast) return;
            bool open;
            try { open = NativeUI.IsOpen; } catch { return; }
            if (!open) { wasOpen = false; return; }
            float now = Time.realtimeSinceStartup;
            if (!wasOpen)
            {
                wasOpen = true; lastPresenceRt = now; lastMouse = Input.mousePosition;
                return;
            }
            Vector3 mouse = Input.mousePosition;
            bool present = Input.anyKeyDown
                || Input.GetMouseButton(0) || Input.GetMouseButton(1)
                || (mouse - lastMouse).sqrMagnitude > 4f
                || Input.mouseScrollDelta.sqrMagnitude > 0f;
            lastMouse = mouse;
            if (present) { lastPresenceRt = now; return; }
            bool prompt;
            try { prompt = NativeUI.HasOpenPrompt; } catch { prompt = false; }
            if (prompt) { lastPresenceRt = now; return; }

            float idle = now - lastPresenceRt;
            if (InLiveOnlineRoom)
            {
                if (idle >= BROADCAST_ROOM_CLOSE_SEC) CloseIdle("broadcast-room", idle);
                return;
            }
            bool showcase;
            try { showcase = NativeUI.ShowcaseOwnsPage; } catch { showcase = false; }
            if (showcase) { lastPresenceRt = now; return; }   // the showcase opens and closes its own pages
            if (idle >= BROADCAST_MENU_CLOSE_SEC) CloseIdle("broadcast-menu", idle);
        }

        private static void CloseIdle(string why, float idle)
        {
            // Logged AFTER the close, not before it. This said "idle-close
            // after Ns" and then called Close() inside a catch-all — so a close
            // that threw left a log line asserting it had happened, and that
            // line is the only evidence anyone reads afterwards. A swallowed
            // failure that also reports success is worse than a noisy one.
            try
            {
                NativeUI.Close();
            }
            catch (System.Exception ex)
            {
                Plugin.Log?.LogWarning($"[NATIVE] idle-close ({why}) after {idle:F0}s FAILED: {ex.GetType().Name}");
                wasOpen = false;
                return;
            }
            Plugin.Log?.LogInfo($"[NATIVE] idle-close ({why}) after {idle:F0}s without input");
            wasOpen = false;
        }
    }
}
