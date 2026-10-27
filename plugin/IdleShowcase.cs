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
        // Board row 31 (Sid, 2026-09-28: show every Compare tab category, the
        // other rules unchanged): the rotation is ShowcaseRules.Script over
        // the Compare tab's own metric list - NativeUI.CompareMetricNames, a
        // copy of COMPARE_METRICS in its order - so a metric added to the tab
        // joins the walk with no second list to keep byte-matched (the #152
        // hazard the curated list of 9 carried). One dwell per metric,
        // [Broadcast] ShowcaseMetricSeconds (default 15 s); Home, the two
        // leaderboard profiles and the 2v2 and FFA tabs keep their dwells, and
        // the skip rule is unchanged (ShowcaseRules.Next). The script is
        // rebuilt at every rotation start, so a changed dwell applies from the
        // next rotation. Kinds and args: ShowcaseRules.View.
        //
        // Request cost (why the curated list once left the board metrics out):
        // a board metric's data is fetched per candidate the first time it is
        // shown in a session and then served from ApiClient's caches -
        // FetchCompareBoard skips a key already cached or in flight and holds a
        // failed key for 15 s; the compare achievements are cached per player;
        // the nemesis boards once per selection; Records refetch a board after
        // 5 minutes. So the walk adds at most one request per candidate (12)
        // per board metric on its first showing in a session: the burst Gold
        // Sources and Build Types already made in the curated walk.
        private static string[] metrics = new string[0];
        private static List<ShowcaseRules.View> script =
            ShowcaseRules.Script(metrics, ShowcaseRules.DEFAULT_METRIC_SECONDS);
        private static int metricsShown;        // Compare metrics shown this rotation
        private static bool testRotation;       // [Broadcast] TestShowcase: one rotation, stream-live gate lifted

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

        /// <summary>[Broadcast] TestShowcase lever (board row 31's witness):
        /// play one rotation with ONLY the stream-live gate lifted. The
        /// director must still be idle with nothing to watch, the seat out of
        /// any online room and the F5 page free, and the ownership contract is
        /// unchanged. It ends when the rotation wraps, when the idle epoch
        /// ends, or when the operator takes the page.</summary>
        internal static void DevRunOneRotation()
        {
            testRotation = true;
            suppressed = false;
            Plugin.Log?.LogInfo("[SHOWCASE] test rotation requested: one rotation with the stream-live gate lifted");
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
                    if (testRotation) EndTestRotation("the director left idle");
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
                    if (testRotation) EndTestRotation("the page was taken");
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
                if (!streamLive && !testRotation) { if (opened) Interrupt(); return; }

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
                    BeginRotation();
                    Plugin.Log?.LogInfo("[SHOWCASE] started: " + script.Count + " views, " + metrics.Length
                        + " Compare metrics at " + ShowcaseRules.MetricDwell(MetricSecondsConfigured()).ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)
                        + " s each" + (testRotation ? " (test rotation)" : ""));
                    StartView(0);
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
                float dwell = viewIdx >= 0 && viewIdx < script.Count ? script[viewIdx].Dwell : 20f;
                TickView(dwell);
                if (Time.realtimeSinceStartup - viewStartedAt < dwell) return;
                Advance();
            }
            catch { }
        }

        private static float MetricSecondsConfigured()
        {
            try
            {
                return Plugin.BroadcastShowcaseMetricSeconds != null
                    ? Plugin.BroadcastShowcaseMetricSeconds.Value
                    : ShowcaseRules.DEFAULT_METRIC_SECONDS;
            }
            catch { return ShowcaseRules.DEFAULT_METRIC_SECONDS; }
        }

        /// <summary>A rotation starts: the script is rebuilt from the Compare
        /// tab's metric list and the configured dwell.</summary>
        private static void BeginRotation()
        {
            metrics = NativeUI.CompareMetricNames;
            script = ShowcaseRules.Script(metrics, MetricSecondsConfigured());
            metricsShown = 0;
        }

        /// <summary>A dwell ended: step to the next view. Passing the end of
        /// the rotation logs how many Compare metrics it showed, ends a
        /// lever's test rotation (the page closes; the stream-live gate is
        /// back), or begins the next rotation.</summary>
        private static void Advance()
        {
            bool wrapped;
            int next = ShowcaseRules.Next(script, viewIdx, candidates.Count, out wrapped);
            if (wrapped)
            {
                Plugin.Log?.LogInfo("[SHOWCASE] rotation complete: " + metricsShown + "/" + metrics.Length + " Compare metrics shown");
                if (testRotation)
                {
                    EndTestRotation("the rotation wrapped");
                    Interrupt();
                    return;
                }
                BeginRotation();
                next = 0;   // Home: never skipped
            }
            StartView(next);
        }

        private static void EndTestRotation(string why)
        {
            testRotation = false;
            Plugin.Log?.LogInfo("[SHOWCASE] test rotation finished: " + why);
        }

        /// <summary>Per-frame behavior INSIDE the current view. Today: the
        /// profile detail sweep — hold PROFILE_HOLD_SECONDS at the top (header,
        /// graph, W/L block), then glide the detail panel top-to-bottom across
        /// the remaining dwell. Re-written every tick from this clock, so async
        /// payloads growing the content mid-sweep just re-map the fraction
        /// (never a jump past the end).</summary>
        private static void TickView(float dwell)
        {
            if (viewIdx < 0 || viewIdx >= script.Count || script[viewIdx].Kind != ShowcaseRules.KIND_PROFILE) return;
            if (!NativeUI.LbProfileLoaded) return;
            float el = Time.realtimeSinceStartup - viewStartedAt;
            if (el <= PROFILE_HOLD_SECONDS) { NativeUI.DevSetLbDetailScroll(0f); return; }
            float span = Mathf.Max(1f, dwell - PROFILE_HOLD_SECONDS - 2f);   // land 2s before the cut
            NativeUI.DevSetLbDetailScroll(Mathf.Clamp01((el - PROFILE_HOLD_SECONDS) / span));
        }

        private static int NextView(int cur)
        {
            bool wrapped;
            return ShowcaseRules.Next(script, cur, candidates.Count, out wrapped);
        }

        private static bool ViewDataReady(int v)
        {
            try
            {
                if (v < 0 || v >= script.Count) return true;
                switch (script[v].Kind)
                {
                    case ShowcaseRules.KIND_HOME: return ApiClient.CachedOnlinePlayers != null;
                    case ShowcaseRules.KIND_COMPARE: return script[v].Arg > 0 || candidates.Count >= 2;
                    case ShowcaseRules.KIND_PROFILE: return ApiClient.CachedLeaderboard != null && NativeUI.LbProfileLoaded;
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
                if (v < 0 || v >= script.Count) return;
                var view = script[v];
                switch (view.Kind)
                {
                    case ShowcaseRules.KIND_HOME:
                        NativeUI.DevOpenTab(13, -1f);   // Home (SwitchTab fetches presence)
                        break;
                    case ShowcaseRules.KIND_COMPARE:
                        if (view.Arg == 0)
                        {
                            GatherCandidates();
                            if (candidates.Count < 2) { StartView(NextView(v)); return; }
                            NativeUI.DevOpenTab(9, -1f);    // Compare
                            NativeUI.DevSetCompareSelection(candidates);
                        }
                        if (view.Arg < metrics.Length)
                        {
                            // Board row 31: one log line per metric shown.
                            string name = metrics[view.Arg];
                            bool set = NativeUI.DevSetCompareMetricByName(name);
                            if (set) metricsShown++;
                            Plugin.Log?.LogInfo(ShowcaseRules.MetricLine(view.Arg, metrics.Length, name)
                                + (set ? "" : " (not on the Compare tab)"));
                        }
                        break;
                    case ShowcaseRules.KIND_PROFILE:
                        if (candidates.Count == 0) { StartView(NextView(v)); return; }
                        NativeUI.DevOpenTab(1, -1f);    // Leaderboard
                        NativeUI.DevSelectLeaderboardPlayer(candidates[profileRot % candidates.Count]);
                        profileRot++;
                        NativeUI.DevScrollLeaderboardToSelected();   // Aug 31: row into view
                        break;
                    case ShowcaseRules.KIND_TEAM:
                        NativeUI.DevOpenTab(8, -1f);    // 2v2
                        break;
                    case ShowcaseRules.KIND_FFA:
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
