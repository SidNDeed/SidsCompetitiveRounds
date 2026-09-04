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
    /// there. The player gets a toast first and the close follows 15 s after the
    /// toast was actually SHOWN (r1 MEDIUM 4: a toast the notification surface
    /// dropped — notifications off, a critical cue owning the slot — is retried,
    /// and with notifications off the page is simply left open). The BROADCAST
    /// seat has no reader: in a room it closes after a short quiet spell with no
    /// warning, and at the menu it closes a lever-opened page after a minute
    /// (long enough for the verification screenshots that lever exists for)
    /// while leaving showcase-owned pages to the showcase.</summary>
    internal static class OverlayIdleClose
    {
        private const float PLAYER_WARN_SEC = 60f;
        private const float PLAYER_GRACE_SEC = 15f;          // after a DELIVERED warning
        private const float BROADCAST_ROOM_CLOSE_SEC = 30f;
        private const float BROADCAST_MENU_CLOSE_SEC = 60f;

        private static bool wasOpen;
        private static bool warned;
        private static bool undeliverableLogged;
        private static float lastPresenceRt;
        private static float warnedAt;
        private static float nextWarnTryRt;
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
            if (present) { lastPresenceRt = now; ResetWarning(); return; }
            bool prompt;
            try { prompt = NativeUI.HasOpenPrompt; } catch { prompt = false; }
            if (prompt) { lastPresenceRt = now; ResetWarning(); return; }

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
            if (!inRoom) { lastPresenceRt = now; ResetWarning(); return; }
            if (!warned)
            {
                if (idle >= PLAYER_WARN_SEC && now >= nextWarnTryRt)
                {
                    nextWarnTryRt = now + 1f;
                    if (warnAttempts >= WARN_MAX_ATTEMPTS)
                    {
                        // Every warning so far was overwritten before the player
                        // could read it (a busy toast surface). Failure direction:
                        // the page stays open — never close on a warning nobody saw.
                        if (!undeliverableLogged)
                        {
                            undeliverableLogged = true;
                            Plugin.Log?.LogInfo("[NATIVE] idle-close: the warning toast was replaced " + WARN_MAX_ATTEMPTS + " times before it was readable - player page left open");
                        }
                        return;
                    }
                    bool delivered = false;
                    try { delivered = CompetitiveUI.ShowNotification(I18n.Tr("Menu closes in 15 s - move the mouse to keep it open"), Color.yellow, 6f); }
                    catch { }
                    if (delivered)
                    {
                        warned = true; warnedAt = now; warnAttempts++;
                        warnVisibleSec = 0f; lastTickRt = now;
                        try { warnSeq = CompetitiveUI.NotificationSeq; } catch { warnSeq = -1; }
                    }
                    else if (!undeliverableLogged)
                    {
                        bool notifOff = false;
                        try { notifOff = Plugin.ShowNotifications != null && !Plugin.ShowNotifications.Value; } catch { }
                        if (notifOff)
                        {
                            undeliverableLogged = true;
                            Plugin.Log?.LogInfo("[NATIVE] idle-close: notifications are off, so the 15 s warning cannot be shown - player pages are left open");
                        }
                    }
                }
                return;
            }
            // r2 MEDIUM 2: ShowNotification grants no ownership of the slot — an
            // ordinary toast (an FFA auto-pick, say) can overwrite the warning
            // before it was ever rendered. The grace period therefore counts
            // only once the warning has been ON SCREEN for WARN_MIN_VISIBLE_SEC
            // (same sequence number, timer still running, sampled per tick); a
            // warning replaced before that is re-issued, bounded by
            // WARN_MAX_ATTEMPTS, and an unread warning never closes the page.
            bool visible = false;
            try { visible = CompetitiveUI.NotificationVisible(warnSeq); } catch { }
            if (visible) warnVisibleSec += Mathf.Max(0f, now - lastTickRt);
            lastTickRt = now;
            if (warnVisibleSec < WARN_MIN_VISIBLE_SEC)
            {
                if (!visible) { warned = false; nextWarnTryRt = now + 1f; }
                return;
            }
            if (now - warnedAt >= PLAYER_GRACE_SEC) CloseIdle("player-room", idle);
        }

        /// <summary>The warning must be readable before it counts: this many
        /// seconds with the warning toast actually occupying the slot.</summary>
        private const float WARN_MIN_VISIBLE_SEC = 3f;
        /// <summary>Re-issues of a warning that was overwritten early, per idle
        /// episode; past this the page is left open (logged once per session).</summary>
        private const int WARN_MAX_ATTEMPTS = 3;
        private static int warnSeq = -1, warnAttempts;
        private static float warnVisibleSec, lastTickRt;

        private static void ResetWarning()
        {
            warned = false; warnAttempts = 0; warnVisibleSec = 0f; warnSeq = -1;
        }

        private static void CloseIdle(string why, float idle)
        {
            Plugin.Log?.LogInfo($"[NATIVE] idle-close ({why}) after {idle:F0}s without input");
            try { NativeUI.Close(); } catch { }
            wasOpen = false; ResetWarning();
        }
    }
}
