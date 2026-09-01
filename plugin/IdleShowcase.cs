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
        // Aug 31 (Sid: "show more of / all of the compare tab"): every entry
        // must BYTE-match NativeUI.COMPARE_METRICS (#152 — a mismatch is a
        // silent no-op view). Deliberately excludes the per-player fetch-storm
        // metrics (Achievements/Similar/Nemesis/Records — the 5323-5326
        // design-review note: 12 candidates x N endpoints per view); Gold
        // Sources and Build Types are single-fetch pie boards and safe.
        private static readonly string[] CURATED_METRICS =
        {
            "Elo over games", "Hit / Block %", "Top Cards", "Peak Elo",
            "Top Streaks", "5-0s Given / Taken", "Avg Game Length",
            "Gold Sources", "Build Types",
        };

        // View script, data-driven (Aug 31 rewrite — the old parallel
        // kind-constants + DWELL arrays drifted whenever a view was added).
        // Kinds: 0 Home, 1 Compare (Arg = CURATED_METRICS index; index 0 also
        // does selection setup), 2 leaderboard profile (select + scroll-to-row
        // + detail sweep), 3 2v2 tab, 4 FFA tab.
        private struct View { public int Kind; public int Arg; public float Dwell;
            public View(int k, int a, float d) { Kind = k; Arg = a; Dwell = d; } }
        private static readonly View[] SCRIPT =
        {
            new View(0, 0, 18f),          // Home
            new View(1, 0, 26f),          // Compare: Elo over games (+ setup)
            new View(1, 1, 20f),          // Hit / Block %
            new View(1, 2, 20f),          // Top Cards
            new View(1, 3, 15f),          // Peak Elo
            new View(1, 4, 15f),          // Top Streaks
            new View(1, 5, 15f),          // 5-0s Given / Taken
            new View(1, 6, 15f),          // Avg Game Length
            new View(1, 7, 17f),          // Gold Sources
            new View(1, 8, 17f),          // Build Types
            new View(2, 0, 30f),          // profile A: row-scroll + sweep
            new View(2, 1, 30f),          // profile B
            new View(3, 0, 22f),          // 2v2
            new View(4, 0, 22f),          // FFA
        };

        private static bool opened;             // WE opened the current page
        private static bool suppressed;         // operator interfered this idle epoch
        private static int viewIdx = -1;
        private static float viewStartedAt;
        private static float readyWaitStart = -1f;
        private static readonly List<string> candidates = new List<string>();
        private static int profileRot;
        // Profile sweep state: sweep starts after the hold, runs to the dwell end.
        private const float PROFILE_HOLD_SECONDS = 8f;   // read the header/graph first

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
                float dwell = viewIdx >= 0 && viewIdx < SCRIPT.Length ? SCRIPT[viewIdx].Dwell : 20f;
                TickView(dwell);
                if (Time.realtimeSinceStartup - viewStartedAt < dwell) return;
                StartView(NextView(viewIdx));
            }
            catch { }
        }

        /// <summary>Per-frame behavior INSIDE the current view. Today: the
        /// profile detail sweep — hold PROFILE_HOLD_SECONDS at the top (header,
        /// graph, W/L block), then glide the detail panel top-to-bottom across
        /// the remaining dwell. Re-written every tick from this clock, so async
        /// payloads growing the content mid-sweep just re-map the fraction
        /// (never a jump past the end).</summary>
        private static void TickView(float dwell)
        {
            if (viewIdx < 0 || viewIdx >= SCRIPT.Length || SCRIPT[viewIdx].Kind != 2) return;
            if (!NativeUI.LbProfileLoaded) return;
            float el = Time.realtimeSinceStartup - viewStartedAt;
            if (el <= PROFILE_HOLD_SECONDS) { NativeUI.DevSetLbDetailScroll(0f); return; }
            float span = Mathf.Max(1f, dwell - PROFILE_HOLD_SECONDS - 2f);   // land 2s before the cut
            NativeUI.DevSetLbDetailScroll(Mathf.Clamp01((el - PROFILE_HOLD_SECONDS) / span));
        }

        private static int NextView(int cur)
        {
            int next = cur + 1;
            if (next >= SCRIPT.Length || next < 0) next = 0;
            // Skip whole view CLASSES that lack their data: Compare needs 2+
            // candidates, profiles need 1+ (candidates refresh at view 1's
            // setup; a cold start with nobody known degrades to Home/2v2/FFA).
            int guard = 0;
            while (guard++ < SCRIPT.Length)
            {
                int k = SCRIPT[next].Kind;
                bool skip = (k == 1 && SCRIPT[next].Arg > 0 && candidates.Count < 2)
                         || (k == 2 && candidates.Count < 1);
                if (!skip) break;
                next++; if (next >= SCRIPT.Length) next = 0;
            }
            return next;
        }

        private static bool ViewDataReady(int v)
        {
            try
            {
                if (v < 0 || v >= SCRIPT.Length) return true;
                switch (SCRIPT[v].Kind)
                {
                    case 0: return ApiClient.CachedOnlinePlayers != null;
                    case 1: return SCRIPT[v].Arg > 0 || candidates.Count >= 2;
                    case 2: return ApiClient.CachedLeaderboard != null && NativeUI.LbProfileLoaded;
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
                if (v < 0 || v >= SCRIPT.Length) return;
                switch (SCRIPT[v].Kind)
                {
                    case 0:
                        NativeUI.DevOpenTab(13, -1f);   // Home (SwitchTab fetches presence)
                        break;
                    case 1:
                        if (SCRIPT[v].Arg == 0)
                        {
                            GatherCandidates();
                            if (candidates.Count < 2) { StartView(NextView(v)); return; }
                            NativeUI.DevOpenTab(9, -1f);    // Compare
                            NativeUI.DevSetCompareSelection(candidates);
                        }
                        NativeUI.DevSetCompareMetricByName(CURATED_METRICS[SCRIPT[v].Arg]);
                        break;
                    case 2:
                        if (candidates.Count == 0) { StartView(NextView(v)); return; }
                        NativeUI.DevOpenTab(1, -1f);    // Leaderboard
                        NativeUI.DevSelectLeaderboardPlayer(candidates[profileRot % candidates.Count]);
                        profileRot++;
                        NativeUI.DevScrollLeaderboardToSelected();   // Aug 31: row into view
                        break;
                    case 3:
                        NativeUI.DevOpenTab(8, -1f);    // 2v2
                        break;
                    case 4:
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
