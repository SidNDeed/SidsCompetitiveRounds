using System;
using System.Collections.Generic;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Broadcast idle showcase (owner item 7, Aug 30; design-
    /// reviewed by Codex the same day): while the stream is live and the
    /// director is idle with nothing to watch, drive the F5 overlay through
    /// a rotation of mod surfaces — Home, Compare over the ~12 most recent
    /// online/recent players, two of their leaderboard profiles, the 2v2 and
    /// FFA tabs — instead of leaving the capture on a blank between-games
    /// card. The bot switches OBS to the Live scene while the status payload
    /// carries idle_content (director half of the same change).
    ///
    /// Ownership contract (review-mandated): the showcase only ever opens a
    /// page nobody owns (NativeUI.TryOpenForShowcase) and only closes the
    /// page it opened (CloseIfShowcaseOwned; any operator F5/Escape revokes
    /// the token instantly inside Close). A manual close suppresses the
    /// showcase for the remainder of that idle epoch. A report going Active
    /// closes the overlay the SAME tick so the report engine — which pauses
    /// while the overlay is open — starts visible with its clock running;
    /// queue settling and fetching happen while the showcase plays (they
    /// never paused, stale-premise correction from the review).
    ///
    /// Runs from BroadcastMode.Step's persistent tick — never a destroyable
    /// coroutine host (#16/#270c class).</summary>
    internal static class IdleShowcase
    {
        private static readonly string[] CURATED_METRICS =
            { "Elo over games", "Hit / Block %", "Top Cards" };

        // View script: (kind, dwellSeconds). Kinds: 0 Home, 1 Compare-setup,
        // 2/3 Compare metric steps, 4/5 leaderboard profiles, 6 2v2, 7 FFA.
        private static readonly float[] DWELL = { 18f, 26f, 20f, 20f, 22f, 20f, 22f, 22f };

        private static bool opened;             // WE opened the current page
        private static bool suppressed;         // operator interfered this idle epoch
        private static int viewIdx = -1;
        private static float viewStartedAt;
        private static float readyWaitStart = -1f;
        private static readonly List<string> candidates = new List<string>();
        private static int profileRot;

        internal static bool VisiblyActive
        {
            get { try { return opened && NativeUI.ShowcaseOwnsPage; } catch { return false; } }
        }

        /// <summary>Immediate teardown — called at BeginAcquisition (before
        /// the ticket exists) and when the director is disabled. Never
        /// suppresses: the next idle epoch may showcase again.</summary>
        internal static void Interrupt()
        {
            try
            {
                if (opened) NativeUI.CloseIfShowcaseOwned();
            }
            catch { }
            opened = false;
            viewIdx = -1;
        }

        internal static void Tick(bool directorIdleNoTicket)
        {
            try
            {
                if (!BroadcastMode.IsBroadcastIdentity) return;

                if (!directorIdleNoTicket)
                {
                    // Leaving idle ends the epoch: teardown + lift suppression.
                    if (opened) Interrupt();
                    suppressed = false;
                    return;
                }

                // Ownership-loss detection FIRST (r1 finding 15: with the
                // report-active branch ahead of it, an operator close landing
                // the same tick a report went Active read as our own
                // Interrupt and never set the suppression).
                if (opened && !NativeUI.ShowcaseOwnsPage)
                {
                    // We believed we owned the page and no longer do — the
                    // operator closed it (Close revokes the token) or a
                    // teardown ran. Back off for this idle epoch.
                    opened = false;
                    viewIdx = -1;
                    suppressed = true;
                    Plugin.Log?.LogInfo("[SHOWCASE] page taken/closed externally — standing down this idle epoch");
                    return;
                }

                // Yield to a playing report the SAME tick it activates —
                // report ticks run before this (BroadcastMode.Step order),
                // and PHASE_PLAY pauses while the overlay is open.
                bool reportActive = false;
                try { reportActive = PostSessionReport.Active; } catch { }
                if (reportActive)
                {
                    if (opened) Interrupt();
                    return;
                }

                bool streamLive = false;
                try { streamLive = BroadcastMode.StreamInfoLive; } catch { }
                if (!streamLive) { if (opened) Interrupt(); return; }

                // Defensive: idle should mean menu, but never drive the F5
                // page inside a live online room.
                try { if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) { if (opened) Interrupt(); return; } }
                catch { }
                if (suppressed) return;
                if (!opened && NativeUI.IsOpen) return;   // operator is using F5 — never touch

                if (!opened)
                {
                    if (!NativeUI.TryOpenForShowcase()) return;
                    opened = true;
                    profileRot = 0;
                    StartView(0);
                    Plugin.Log?.LogInfo("[SHOWCASE] started");
                    return;
                }

                // Ready-wait: a view whose LOAD-BEARING payload has not
                // arrived holds its dwell clock up to 8s. Readiness is the
                // view's PRIMARY content (candidates for Compare, the
                // selected profile's stats for leaderboard views); secondary
                // panels (achievements, histories) may still stream in
                // during the dwell — accepted (r1 finding 16 scope).
                if (readyWaitStart >= 0f)
                {
                    if (!ViewDataReady(viewIdx) && Time.realtimeSinceStartup - readyWaitStart < 8f) return;
                    readyWaitStart = -1f;
                    viewStartedAt = Time.realtimeSinceStartup;
                }
                float dwell = viewIdx >= 0 && viewIdx < DWELL.Length ? DWELL[viewIdx] : 20f;
                if (Time.realtimeSinceStartup - viewStartedAt < dwell) return;
                StartView(NextView(viewIdx));
            }
            catch { }
        }

        private static int NextView(int cur)
        {
            int next = cur + 1;
            if (next > 7) next = 0;
            // Compare/profile views need at least 2 known players.
            if ((next >= 1 && next <= 3) && candidates.Count < 2 && next != 1) next = 4;
            if ((next == 4 || next == 5) && candidates.Count < 1) next = 6;
            return next;
        }

        private static bool ViewDataReady(int v)
        {
            try
            {
                switch (v)
                {
                    case 0: return ApiClient.CachedOnlinePlayers != null;
                    case 1: return candidates.Count >= 2;
                    case 4:
                    case 5: return ApiClient.CachedLeaderboard != null && NativeUI.LbProfileLoaded;
                    default: return true;
                }
            }
            catch { return true; }
        }

        private static void StartView(int v)
        {
            viewIdx = v;
            viewStartedAt = Time.realtimeSinceStartup;
            readyWaitStart = Time.realtimeSinceStartup;
            try
            {
                switch (v)
                {
                    case 0:
                        NativeUI.DevOpenTab(13, -1f);   // Home (SwitchTab fetches presence)
                        break;
                    case 1:
                        GatherCandidates();
                        if (candidates.Count < 2) { StartView(4); return; }
                        NativeUI.DevOpenTab(9, -1f);    // Compare
                        NativeUI.DevSetCompareSelection(candidates);
                        NativeUI.DevSetCompareMetricByName(CURATED_METRICS[0]);
                        break;
                    case 2:
                        NativeUI.DevSetCompareMetricByName(CURATED_METRICS[1]);
                        break;
                    case 3:
                        NativeUI.DevSetCompareMetricByName(CURATED_METRICS[2]);
                        break;
                    case 4:
                    case 5:
                        if (candidates.Count == 0) { StartView(6); return; }
                        NativeUI.DevOpenTab(1, -1f);    // Leaderboard
                        NativeUI.DevSelectLeaderboardPlayer(candidates[profileRot % candidates.Count]);
                        profileRot++;
                        break;
                    case 6:
                        NativeUI.DevOpenTab(8, -1f);    // 2v2
                        break;
                    case 7:
                        NativeUI.DevOpenTab(12, -1f);   // FFA
                        break;
                }
            }
            catch { }
        }

        /// <summary>Up to 12 most recent players: online first, then recent.
        /// Dedupe by steam id; exclude blanks, "unknown" and this broadcast
        /// seat's own account (design review list).</summary>
        private static void GatherCandidates()
        {
            candidates.Clear();
            try
            {
                string self = MatchTracker.LocalSteamId ?? "";
                void addFrom(List<ApiClient.OnlinePlayerEntry> src)
                {
                    if (src == null) return;
                    foreach (var e in src)
                    {
                        if (candidates.Count >= 12) return;
                        var sid = e?.steamId;
                        if (string.IsNullOrEmpty(sid) || sid == "unknown" || sid == self) continue;
                        if (!candidates.Contains(sid)) candidates.Add(sid);
                    }
                }
                addFrom(ApiClient.CachedOnlinePlayers);
                addFrom(ApiClient.CachedRecentPlayers);
            }
            catch { }
        }
    }
}
