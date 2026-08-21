using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// W7 (A6) — post-session stat screens on the BROADCAST seat.
    ///
    /// Between sittings the director parks at the main menu; this engine plays
    /// after-action report screens + graph pages for the pairs it watched, over
    /// the ROUNDS-blue menu (translucent panels, never a full black screen).
    ///
    /// Contracts (all verified against the live tree, not the briefs — #363):
    ///  - BroadcastMode (A7) calls NotePairActivated at the Watching-activation
    ///    edge, NoteTargetGone at ticket retire/rotation, Tick(idleFlag) every
    ///    Step, Interrupt() on BeginAcquisition / director-disable; it reads
    ///    Active, CurrentScreenKind, CurrentTotalElo, CurrentReportId for the
    ///    lease payload (D1 deltas f14/f15/f19 — no new lease state).
    ///  - ApiClient (A1): FetchBroadcastReportStatus (end authority),
    ///    FetchPlayerStatsForView(id, cb, viewerSteamId), FetchCardStatsForView,
    ///    and the R1 f9 report-private callback variants (results NEVER ride
    ///    the shared F5 caches): FetchMatchHistoryForView(id, (list, ok), limit),
    ///    and the R2 f4/f5 PAGINATED variants
    ///    FetchTeamHistoryForView(id, DateTime? noOlderThanUtc, (list, ok)) and
    ///    FetchFfaHistoryForView(id, DateTime? noOlderThanUtc, (list, ok)) —
    ///    entry types are the F5 tabs' own (TeamSeriesPagedEntry /
    ///    FfaRecentMatch); the cutoff bounds pagination, and ok=false also
    ///    means "pagination could not prove completeness".
    ///  - CompetitiveUI (A5): PaintTeleGraph / PaintPairGraph / PaintScoreGraph
    ///    fixed-rect painters (kind ids mirror the hover regions: 0 fps,
    ///    1 ping, 5 dps).
    ///  - The integrator wires Draw() into CompetitiveUI.DrawUI EARLY.
    ///
    /// Binding rules from ai-collab/streaming-design-d1-deltas.md §W7:
    ///  f6/f7  server report-status is the ONLY end authority (ended_at !=
    ///         null); list absence proves nothing; 25-min unreachable fallback
    ///         plays "(partial)".
    ///  f8     entries exist only for activation-edge identities
    ///         (game_id + incarnation).
    ///  f9     session window = [started_at - 5min, ended_at], both server UTC.
    ///  f10    data fetch begins no earlier than ended_at + 90s.
    ///  f11    1v2/ovt is never enqueued.
    ///  f12    2v2 mirrors the F5 2v2 tab's fidelity; absent data is omitted,
    ///         never fabricated.
    ///  f13    F5 open: hide, PAUSE the page clock, CurrentScreenKind null
    ///         (clears the lease payload fields); resume with remaining time.
    ///
    /// R1 fix deltas applied (ai-collab/streaming-r1-fix-deltas.md — BINDING):
    ///  f6+f8  identity-less entries are LEGAL at enqueue; the report-status
    ///         poll fills roster/names/mode/started_at; playback requires
    ///         identity + terminality + settle; poll batching is round-robin
    ///         with PER-ENTRY outage stamps; cap 16, drops by 2h age only.
    ///  f7     settle + retention run on LOCAL MONOTONIC observation stamps;
    ///         server-UTC math survives ONLY in the match-window comparison.
    ///  f9     every data fetch is a report-private callback variant — the
    ///         shared-cache reference-sniffing paths are DELETED (#310).
    ///  f10    transportOk=false after retries renders "(partial)", never
    ///         "Session: 0 games" / "No games recorded".
    ///  f12    2v2 data from the player-scoped team-history variant; the
    ///         zero-series fallback is a FLAT name list, never fabricated
    ///         team pairings.
    ///  f14    2v2 match rows/graphs filter by each match's OWN ended_at.
    ///  f15    FFA from the player-scoped history variant. Bug 254 replaces
    ///         frozen-roster equality with windowed, thresholded overlap so
    ///         one fluid sitting survives legitimate joins/leaves.
    ///  f16    win_rate wire fractions x100 at every render site; compact
    ///         panels use ranked /cards, else label "Top cards (all modes)".
    ///  f17    every capped list renders "showing N of M" when truncated.
    ///  f21    playback STARTS only while BroadcastMode.StreamInfoLive.
    ///  f22    REJECTED (recorded) — the 2v2 per-game card rows STAY.
    ///
    /// R2 fix deltas applied (ai-collab/streaming-review-r2.log tail report):
    ///  f2     the FetchBox ok flags default FALSE and go true ONLY inside a
    ///         shape-valid successful callback — unresolved-at-deadline,
    ///         retry-in-flight and synchronous-exception paths leave them
    ///         false, so those sections render "(partial)", never a clean
    ///         zero (this includes nonempty lists off a false flag: their
    ///         counts render as labeled floors, not exact totals).
    ///  f4/f5  2v2/FFA session fetches use the paginated ForView variants
    ///         with the session-window start (started_at - 5min) as the
    ///         completeness cutoff; null cutoff = partial-fallback mode.
    ///  f7     the 1v1 favorite-card panels (cap 5) and compact 2v2 card
    ///         lines (cap 3) disclose truncation via "showing N of M".
    ///
    /// Safety: read-only HTTP + IMGUI only — never Photon, never config writes
    /// (#338 family). All server strings are hostile input (#100/#156): names
    /// are sanitized (SanitizeStyled replica) or tag-stripped before render.
    /// All strings are pre-composed once per screen build (#162); the whole
    /// renderer is Repaint-only and allocation-free per event (#364).
    /// </summary>
    internal static class PostSessionReport
    {
        // ── constants (Sid's Aug 19 spec + D1 deltas) ────────────────────

        /// <summary>Sid Aug 19: after-action report screen dwell.</summary>
        private const float REPORT_SECONDS = 60f;
        /// <summary>Sid Aug 19: per graph page (2x2 grid).</summary>
        private const float GRAPH_PAGE_SECONDS = 35f;
        /// <summary>Sid Aug 19: per-game row cap on the report screen.</summary>
        private const int MAX_ROWS = 8;
        /// <summary>Sid Aug 19: entries older than 2h since sitting end are
        /// stale content — dropped, never played. R1 f7: measured on LOCAL
        /// MONOTONIC stamps — 2h from the ended_at OBSERVATION for terminal
        /// entries, 2h from entry creation for never-terminal ones.</summary>
        private const float MAX_REPORT_AGE = 7200f;
        /// <summary>Sid Aug 19: fallback-window slack. Only used in "(partial)"
        /// mode (no server stamps): window opens this far before the first
        /// activation so games already in progress at acquisition count.</summary>
        private const float SESSION_SLACK = 600f;
        /// <summary>Sid Aug 19: fetch deadline — render what arrived rather
        /// than wedge the queue.</summary>
        private const float FETCH_DEADLINE = 30f;
        /// <summary>D1 f10: data fetch begins no earlier than ended_at + 90s —
        /// mirrors ApiClient's existing 90s H2H guard (_oppLifetimeRefetchAfter:
        /// the deciding /matches report can land seconds after game end).
        /// R1 f7: counted from the LOCAL MONOTONIC observation of ended_at,
        /// never from server-vs-VM clock subtraction.</summary>
        private const float SETTLE_SECONDS = 90f;
        /// <summary>D1 f6: report-status poll cadence while entries pend.</summary>
        private const float STATUS_POLL_SECONDS = 30f;
        /// <summary>D1 f7 / R1 f6+f8: PER-ENTRY — an entry whose polls have
        /// gone unanswered this long (from ITS OWN first unanswered poll) may
        /// play labeled "(partial)".</summary>
        private const float STATUS_UNREACHABLE_FALLBACK_SECONDS = 1500f;
        /// <summary>D1 f9: session window opens 5 min before started_at.</summary>
        private const float WINDOW_PRE_START_SECONDS = 300f;
        /// <summary>DEVIATION (see A6 report): the briefs cap nothing, but a
        /// 10-player FFA sitting yields hundreds of graphs — unbounded pages
        /// would monopolize the queue for half an hour (#245: model the budget
        /// before writing the rows). Newest-game-first ordering means the cap
        /// keeps the most relevant content.</summary>
        private const int MAX_GRAPH_PAGES = 6;
        /// <summary>Queue hygiene cap (insertion-ordered; ordering for PLAY is
        /// by sitting-end recency at pick time). R1 f6+f8: raised 12 → 16, and
        /// the ONLY removal is the 2h age rule — a full queue REFUSES a new
        /// entry rather than silently evicting a pending/eligible one.</summary>
        private const int MAX_QUEUE = 16;
        /// <summary>1 issue + 2 retries (brief: "2 retries, then skip").</summary>
        private const int FETCH_ATTEMPTS = 3;
        /// <summary>Backdrop panel alpha — translucent over the menu blue.</summary>
        private const float PANEL_A = 0.82f;
        /// <summary>If the engine clock (Tick) stalls this long while a report
        /// is up, Draw stops painting: the release path must not depend on the
        /// same fragile chain that took the screen (#255 family).</summary>
        private const float TICK_STALL_HIDE_SECONDS = 5f;

        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;

        // Brand watermark. Deliberately NOT routed through I18n: it is the
        // product name (locale-invariant), and a Tr key would invite a
        // translation nothing should ever apply (#295 family).
        private const string WATERMARK = "<color=#66809A>Sid's Competitive Rounds</color>";

        // ── queue model (D1 f8: identity = game_id + incarnation) ───────

        private class Entry
        {
            public string gameId;
            public string incarnation;
            public string mode;              // "1v1" | "2v2" | "ffa" (lowercased)
            public string reportId;          // incarnation + roster hash, <=32 chars (D1 f19)
            // R1 f6+f8: rosterIds may be EMPTY at enqueue (the autonomous seat
            // has no roster at activation) — the report-status poll fills
            // roster/names/mode/started_at server-side. Playback requires
            // identity (non-empty roster) + terminality + settle.
            public string[] rosterIds;       // fighter steam ids (activation roster or the server's validated roster)
            public string[] names;           // roster-aligned display names (hostile input)
            public float[] ratings;          // roster-aligned display ratings; empty = unknown
            public DateTime firstActivatedUtc; // local UTC at first activation — "(partial)" window anchor ONLY
            public float createdRt;            // realtime at creation/re-activation — never-terminal retention anchor (R1 f7)
            public float sittingGoneRt = -1f;  // director stopped watching (NoteTargetGone); -1 = live
            public DateTime? startedAtUtc;   // server UTC (report-status) — match-WINDOW math only (R1 f7)
            public DateTime? endedAtUtc;     // server UTC (report-status) — the ONLY terminal proof (D1 f6); window math only
            public float endedObservedRt = -1f; // realtime when a poll FIRST showed ended_at non-null (R1 f7 settle/retention anchor)
            public float settleReadyRt = -1f;  // realtime when the 90s settle has elapsed (= endedObservedRt + 90)
            public float pollOutageSinceRt = -1f; // realtime of THIS entry's first unanswered poll; -1 = answered/never polled (R1 f6+f8)
            public bool partial;             // playing under the 25-min unreachable fallback
        }

        private static bool HasIdentity(Entry e)
            => e != null && e.rosterIds != null && e.rosterIds.Length > 0;

        private static readonly List<Entry> _queue = new List<Entry>();

        // ── playback state ───────────────────────────────────────────────

        private const int PHASE_NONE = 0, PHASE_FETCH = 1, PHASE_PLAY = 2;
        private static int _phase = PHASE_NONE;
        /// <summary>Ownership token (#367b): bumped on Interrupt/consume so
        /// every in-flight fetch callback from a superseded run no-ops.</summary>
        private static int _gen;
        private static Entry _current;
        private static List<Page> _pages;
        private static int _pageIdx;
        private static float _pageRemaining;
        private static float _lastTickRt = -1f;

        // ── report-status polling state ──────────────────────────────────

        private static float _lastStatusPollRt = -999f;
        private static bool _statusPollInFlight;
        /// <summary>R1 f6+f8: round-robin offset over the UNRESOLVED entries
        /// so a full 8-wide window of live games can never starve entry 9.
        /// The outage clock is PER ENTRY (Entry.pollOutageSinceRt) — a global
        /// stamp let successful replies about OTHER entries disarm it.</summary>
        private static int _pollRotation;

        // ── fetch state ──────────────────────────────────────────────────

        // R1 f9: the cache-reference-sniffing fetch paths (FetchAllSeriesPaged /
        // FetchFfaRecent + snapshot compare) are DELETED — an F5 page request
        // could supersede the report's response and satisfy the "done" test
        // with the wrong page (#310: delete the mechanism, don't patch it).
        private class FetchBox
        {
            public int pending;                                // callback fetches outstanding
            public ApiClient.PlayerStatsData[] stats;          // roster-aligned
            public List<ApiClient.CardStatData>[] cards;       // 1v1 + 2v2 (R1 f16), roster-aligned
            public List<ApiClient.MatchHistoryEntry> history;  // 1v1 (subject = rosterIds[0])
            // R2 f2: the ok flags DEFAULT FALSE — set true ONLY inside a
            // shape-valid successful callback (the single `= ok` site in each
            // fetch slot). Unresolved-at-deadline, retry-in-flight and
            // synchronous-exception paths never touch them, so those sections
            // render "(partial)" instead of a clean zero. R1 f10 semantics
            // widen under R2 f4/f5: false also means "pagination could not
            // prove completeness".
            public bool historyOk;                             // 1v1
            public List<ApiClient.TeamSeriesPagedEntry> teamHistory; // 2v2, report-private (R1 f9/f12)
            public bool teamOk;
            public List<ApiClient.FfaRecentMatch> ffaHistory;  // FFA, report-private (R1 f9/f15)
            public bool ffaOk;
        }

        private static FetchBox _fetch;
        private static float _fetchStartedRt;

        // ── public contract (call sites verified in BroadcastMode.cs) ────

        /// <summary>True while a report playback is in progress — INCLUDING
        /// the F5 pause (A7's lease keeps "watching" through the pause so the
        /// scene does not flap; the payload fields drop via the null
        /// CurrentScreenKind instead, D1 f13).</summary>
        public static bool Active => _phase == PHASE_PLAY;

        /// <summary>"report" | "graphs" while visibly on screen; null when
        /// hidden (F5 open) or not playing. Null clears the lease payload
        /// fields and resets the bot's 3s-stable capture gate (D1 f13).</summary>
        public static string CurrentScreenKind
        {
            get
            {
                if (_phase != PHASE_PLAY || _pages == null || _pages.Count == 0) return null;
                if (NativeUI.IsOpen) return null;
                return _pageIdx <= 0 ? "report" : "graphs";
            }
        }

        /// <summary>Sum of the entry's display ratings, 0 when unknown.</summary>
        public static int CurrentTotalElo
        {
            get
            {
                var e = _current;
                if (_phase != PHASE_PLAY || e == null || e.ratings == null) return 0;
                float s = 0f;
                for (int i = 0; i < e.ratings.Length; i++) s += e.ratings[i];
                return s > 0f ? Mathf.RoundToInt(s) : 0;
            }
        }

        /// <summary>Bounded opaque id: incarnation + sorted-roster hash,
        /// &lt;=32 chars (D1 f19 — the bot dedups thumbnail captures by this,
        /// never by names).</summary>
        public static string CurrentReportId
        {
            get
            {
                var e = _current;
                return _phase == PHASE_PLAY && e != null ? (e.reportId ?? "") : "";
            }
        }

        /// <summary>Roster-aligned display names of the playing entry (null
        /// when idle). NOT consumed by the lease (names[] stays empty during
        /// reports, D1 f16) — exposed for completeness of the A6 contract.</summary>
        public static string[] CurrentNames
        {
            get
            {
                var e = _current;
                return _phase == PHASE_PLAY && e != null ? e.names : null;
            }
        }

        /// <summary>Create-or-refresh an entry at the Watching-activation edge
        /// (D1 f8). Keyed by game_id + incarnation. R1 f6+f8: rosterIds may be
        /// EMPTY (the autonomous seat has none at activation) — enqueue always
        /// succeeds and the report-status poll fills roster/names/mode/
        /// started_at later; an activation-provided roster refreshes on every
        /// call, an EMPTY one never wipes a poll-filled identity. Re-activation
        /// of a pair marked gone clears the gone stamp (it is live again) and
        /// the stale terminal stamps (a re-watched sitting can gain new games —
        /// the poll re-learns its end).</summary>
        public static void NotePairActivated(string gameId, string incarnation, string mode,
                                             string[] rosterIds, string[] names, float[] ratings)
        {
            try
            {
                if (string.IsNullOrEmpty(gameId)) return;
                string m = (mode ?? "").Trim().ToLowerInvariant();
                // D1 f11: 1v2 is excluded — never enqueued.
                if (m == "1v2" || m == "ovt") return;
                if (m != "2v2" && m != "ffa") m = "1v1";   // unknown/"" modes report as 1v1
                string inc = incarnation ?? "";
                float now = Time.realtimeSinceStartup;
                Entry e = null;
                for (int i = 0; i < _queue.Count; i++)
                    if (string.Equals(_queue[i].gameId, gameId, StringComparison.Ordinal)
                        && string.Equals(_queue[i].incarnation, inc, StringComparison.Ordinal))
                    { e = _queue[i]; break; }
                if (e == null)
                {
                    // R1 f6+f8: an entry that is pending-identity or eligible
                    // (or terminal-and-settling) is NEVER evicted except by
                    // the 2h age rule. Cap relief order: age sweep first, then
                    // the oldest UNPROTECTED entry, and only when every entry
                    // is protected is the NEW entry refused (the one residual
                    // where BroadcastMode's ReportNoted latch loses a report —
                    // reachable only with 16 protected entries inside 2h).
                    if (_queue.Count >= MAX_QUEUE)
                    {
                        SweepQueue(now);
                        if (_queue.Count >= MAX_QUEUE) EvictOldestUnprotected(now);
                        if (_queue.Count >= MAX_QUEUE)
                        {
                            try { Plugin.Log?.LogWarning("[REPORT] queue full - refused " + gameId); } catch { }
                            return;
                        }
                    }
                    e = new Entry
                    {
                        gameId = gameId,
                        incarnation = inc,
                        firstActivatedUtc = DateTime.UtcNow,
                        reportId = MakeReportId(inc, rosterIds ?? new string[0]),
                        rosterIds = new string[0],
                        names = new string[0],
                        ratings = new float[0],
                    };
                    _queue.Add(e);
                }
                e.mode = m;
                if (rosterIds != null && rosterIds.Length > 0)
                {
                    // Activation roster present (F5-fed grant path) — refresh.
                    e.rosterIds = (string[])rosterIds.Clone();
                    e.names = NormalizeNames(names, e.rosterIds);
                    e.ratings = ratings != null ? (float[])ratings.Clone() : new float[0];
                    e.reportId = MakeReportId(inc, e.rosterIds);
                }
                e.createdRt = now;          // retention anchor refresh — live again (R1 f7)
                e.sittingGoneRt = -1f;
                e.endedAtUtc = null;
                e.endedObservedRt = -1f;
                e.settleReadyRt = -1f;
                e.pollOutageSinceRt = -1f;
                e.partial = false;
            }
            catch { /* queue note must never throw into the director */ }
        }

        /// <summary>Director-side "stopped watching this pair" stamp. Keyed by
        /// game id (A7 restamps at leave-complete — idempotent per id); no-ops
        /// for a game never noted (a ticket that died before activation).</summary>
        public static void NoteTargetGone(string gameId)
        {
            try
            {
                if (string.IsNullOrEmpty(gameId)) return;
                float now = Time.realtimeSinceStartup;
                for (int i = 0; i < _queue.Count; i++)
                    if (string.Equals(_queue[i].gameId, gameId, StringComparison.Ordinal)
                        && _queue[i].sittingGoneRt < 0f)
                        _queue[i].sittingGoneRt = now;
            }
            catch { }
        }

        /// <summary>Hide immediately (live sittings always outrank a replayed
        /// report). The entry stays queued and replays IN FULL later.</summary>
        public static void Interrupt()
        {
            try
            {
                if (_phase == PHASE_NONE) return;
                _gen++;              // in-flight fetch callbacks no-op (#367b)
                _phase = PHASE_NONE;
                _pages = null;
                _fetch = null;
                _current = null;     // the Entry object itself remains in _queue
            }
            catch { }
        }

        /// <summary>Engine heartbeat, called from BroadcastMode.Step every tick
        /// (idle or not — the flag is the ONLY play condition). Owns the page
        /// clock, the report-status poll, the stale sweep and fetch progress.</summary>
        public static void Tick(bool directorIdleNoTicket)
        {
            try
            {
                float now = Time.realtimeSinceStartup;
                float dt = _lastTickRt > 0f ? Mathf.Clamp(now - _lastTickRt, 0f, 1f) : 0f;
                _lastTickRt = now;

                SweepQueue(now);
                MaybePollStatus(now);

                if (_phase == PHASE_PLAY)
                {
                    // Defensive: A7 calls Interrupt() at BeginAcquisition as
                    // its FIRST statement, so this branch should be dead — but
                    // a playing report beside a non-idle director is never
                    // correct, so the belt matches the suspenders.
                    if (!directorIdleNoTicket) { Interrupt(); return; }
                    // D1 f13: F5 open pauses the clock — same page, remaining
                    // time frozen, resumes when the menu closes.
                    if (NativeUI.IsOpen) return;
                    _pageRemaining -= dt;
                    if (_pageRemaining <= 0f)
                    {
                        _pageIdx++;
                        if (_pages == null || _pageIdx >= _pages.Count) { Consume(); return; }
                        _pageRemaining = GRAPH_PAGE_SECONDS;
                    }
                    return;
                }

                if (_phase == PHASE_FETCH) { TickFetch(now); return; }

                if (!directorIdleNoTicket) return;
                // R1 f21: playback (and its fetch) STARTS only while the
                // stream is actually live — BroadcastMode.StreamInfoLive is
                // the bot's own heartbeat file behind its existing 120s
                // freshness gate (and a 10s read throttle, so this per-tick
                // read is cheap). A dead stream gets no report playback, so a
                // deferred "(partial)" can never cold-start a new bot
                // session/broadcast; entries stay queued under the 2h rule.
                bool streamLive = false;
                try { streamLive = BroadcastMode.StreamInfoLive; } catch { }
                if (!streamLive) return;
                var e = PickEligible(now);
                if (e != null) BeginFetch(e, now);
            }
            catch (Exception ex)
            {
                try { Plugin.Log?.LogWarning("[REPORT] tick: " + ex.Message); } catch { }
            }
        }

        // ── queue lifecycle ──────────────────────────────────────────────

        /// <summary>Cap relief beyond the 2h sweep (R1 f6+f8): only an entry
        /// that is NEITHER pending-identity NOR eligible NOR terminal-and-
        /// settling may be evicted, oldest first (createdRt). Anything with a
        /// terminal stamp plays within its 90s settle — evicting it would be
        /// evicting an eligible report in all but timing, so it is protected
        /// too (strictly MORE protective than the delta's minimum).</summary>
        private static void EvictOldestUnprotected(float now)
        {
            int victim = -1;
            float oldest = float.MaxValue;
            for (int i = 0; i < _queue.Count; i++)
            {
                var e = _queue[i];
                if (e == _current || !HasIdentity(e)) continue;      // playing / pending-identity
                if (e.endedAtUtc.HasValue) continue;                 // terminal: eligible now or within 90s
                bool fallback = e.sittingGoneRt > 0f && e.pollOutageSinceRt > 0f
                                && now - e.pollOutageSinceRt >= STATUS_UNREACHABLE_FALLBACK_SECONDS;
                if (fallback) continue;                              // eligible via the outage fallback
                if (e.createdRt < oldest) { oldest = e.createdRt; victim = i; }
            }
            if (victim >= 0)
            {
                try { Plugin.Log?.LogWarning("[REPORT] cap eviction " + _queue[victim].reportId); } catch { }
                _queue.RemoveAt(victim);
            }
        }

        /// <summary>Drop stale content — R1 f7: 2h on LOCAL MONOTONIC stamps
        /// (a VM wall clock 2h fast deleted a newly terminal entry under the
        /// old server-UTC subtraction): 2h from the ended_at OBSERVATION for
        /// terminal entries, 2h from entry creation/re-activation for
        /// never-terminal ones (this also bounds a stale-open server row,
        /// #348 — the residual is a single 2h+ marathon sitting whose entry
        /// ages out while still being watched). The playing/fetching entry
        /// is exempt: finishing playback consumes it anyway, and a mid-play
        /// removal would strand _current outside the queue.</summary>
        private static void SweepQueue(float now)
        {
            for (int i = _queue.Count - 1; i >= 0; i--)
            {
                var e = _queue[i];
                if (e == _current) continue;
                bool stale = e.endedObservedRt > 0f
                    ? now - e.endedObservedRt > MAX_REPORT_AGE
                    : now - e.createdRt > MAX_REPORT_AGE;
                if (stale) _queue.RemoveAt(i);
            }
        }

        /// <summary>D1 f6: poll GET /broadcast/report-status every 30s while
        /// any entry is UNRESOLVED — lacking its terminal stamp OR lacking
        /// identity (the poll fills roster/names/mode/started_at, R1 f6+f8).
        /// ended_at != null is the ONLY end authority; absence from the
        /// response proves nothing. R1 f8: the CSV window is ROUND-ROBIN over
        /// the unresolved entries (8 live games can no longer starve entry 9),
        /// and outage stamps are PER ENTRY — a failed poll stamps exactly the
        /// entries it asked about, a successful one clears exactly those.</summary>
        private static void MaybePollStatus(float now)
        {
            if (_statusPollInFlight) return;
            if (now - _lastStatusPollRt < STATUS_POLL_SECONDS) return;
            var unresolved = new List<Entry>();
            for (int i = 0; i < _queue.Count; i++)
            {
                var e = _queue[i];
                if (!e.endedAtUtc.HasValue || !HasIdentity(e)) unresolved.Add(e);
            }
            if (unresolved.Count == 0) return;
            var polled = new List<Entry>();
            string csv = null;
            int start = _pollRotation % unresolved.Count;
            for (int k = 0; k < unresolved.Count && polled.Count < 8; k++)   // server cap: game_ids csv <= 8
            {
                var e = unresolved[(start + k) % unresolved.Count];
                csv = csv == null ? e.gameId : csv + "," + e.gameId;
                polled.Add(e);
            }
            _pollRotation = (start + polled.Count) % unresolved.Count;
            _lastStatusPollRt = now;
            _statusPollInFlight = true;
            try
            {
                ApiClient.FetchBroadcastReportStatus(csv, list =>
                {
                    _statusPollInFlight = false;
                    if (list == null)
                    {
                        // Transport failure: only THESE entries went
                        // unanswered — each one's 25-min "(partial)" clock
                        // runs from ITS OWN first unanswered poll (R1 f8).
                        float t = Time.realtimeSinceStartup;
                        for (int i = 0; i < polled.Count; i++)
                            if (polled[i].pollOutageSinceRt < 0f) polled[i].pollOutageSinceRt = t;
                        return;
                    }
                    for (int i = 0; i < polled.Count; i++) polled[i].pollOutageSinceRt = -1f;
                    try { ApplyStatus(list); } catch (Exception ex)
                    { try { Plugin.Log?.LogWarning("[REPORT] status apply: " + ex.Message); } catch { } }
                });
            }
            catch
            {
                // A synchronous throw must not wedge the in-flight latch —
                // that would silence every future poll (#249's lesson shape:
                // never let one lost request own the recovery path).
                _statusPollInFlight = false;
                for (int i = 0; i < polled.Count; i++)
                    if (polled[i].pollOutageSinceRt < 0f) polled[i].pollOutageSinceRt = now;
            }
        }

        private static void ApplyStatus(List<ApiClient.BroadcastReportStatusEntry> list)
        {
            for (int i = 0; i < list.Count; i++)
            {
                var s = list[i];
                if (s == null || string.IsNullOrEmpty(s.game_id)) continue;
                for (int q = _queue.Count - 1; q >= 0; q--)
                {
                    var e = _queue[q];
                    if (!string.Equals(e.gameId, s.game_id, StringComparison.Ordinal)) continue;
                    // R1 f6+f8: the server's mode is authoritative — and the
                    // D1 f11 exclusion re-applies here: a game the server says
                    // is 1v2/ovt must never play, even if it slipped in under
                    // an unknown mode at activation.
                    string sm = (s.mode ?? "").Trim().ToLowerInvariant();
                    if (sm == "1v2" || sm == "ovt")
                    {
                        if (e != _current) _queue.RemoveAt(q);
                        continue;
                    }
                    if (sm == "1v1" || sm == "2v2" || sm == "ffa") e.mode = sm;
                    // R1 f6: identity fill from the server's VALIDATED roster
                    // (the grant response carries none; the activation-side
                    // cache scan reached nothing on the autonomous seat).
                    // roster CSV + names are index-aligned (server contract).
                    ApplyRosterFromStatus(e, s);
                    DateTime started;
                    if (TryParseUtc(s.started_at, out started)) e.startedAtUtc = started;
                    DateTime ended;
                    if (!e.endedAtUtc.HasValue && TryParseUtc(s.ended_at, out ended))
                    {
                        e.endedAtUtc = ended;   // window math ONLY (R1 f7)
                        // R1 f7: settle runs the FULL 90s from the local
                        // monotonic OBSERVATION of ended_at — never from a
                        // server-vs-VM clock subtraction (a fast VM clock
                        // used to skip the settle and fetch N-1 results).
                        e.endedObservedRt = Time.realtimeSinceStartup;
                        e.settleReadyRt = e.endedObservedRt + SETTLE_SECONDS;
                    }
                }
            }
        }

        /// <summary>R1 f6+f8 identity fill. Missing identity adopts the
        /// server roster wholesale; a DIFFERENT existing roster is replaced
        /// (the server's is the validated one — an activation roster can only
        /// have come from a stale UI cache); a set-equal roster just upgrades
        /// placeholder names to the server's display names. Ratings are
        /// roster-ALIGNED display data, so any roster change clears them.</summary>
        private static void ApplyRosterFromStatus(Entry e, ApiClient.BroadcastReportStatusEntry s)
        {
            if (string.IsNullOrEmpty(s.roster)) return;
            var parts = s.roster.Split(',');
            var ids = new List<string>(parts.Length);
            for (int i = 0; i < parts.Length; i++)
            {
                string id = parts[i].Trim();
                if (id.Length > 0) ids.Add(id);
            }
            if (ids.Count == 0) return;
            bool sameSet = false;
            if (HasIdentity(e) && e.rosterIds.Length == ids.Count)
            {
                sameSet = true;
                var have = new HashSet<string>(e.rosterIds, StringComparer.Ordinal);
                for (int i = 0; i < ids.Count; i++)
                    if (!have.Contains(ids[i])) { sameSet = false; break; }
            }
            if (!sameSet)
            {
                e.rosterIds = ids.ToArray();
                e.names = NormalizeNames(s.names != null ? s.names.ToArray() : null, e.rosterIds);
                e.ratings = new float[0];
                e.reportId = MakeReportId(e.incarnation, e.rosterIds);
                return;
            }
            // Same set: adopt server display names aligned to OUR slot order
            // (ratings stay — they are aligned to e.rosterIds).
            if (s.names == null || s.names.Count == 0) return;
            for (int i = 0; i < e.rosterIds.Length; i++)
            {
                for (int j = 0; j < ids.Count && j < s.names.Count; j++)
                {
                    if (!string.Equals(ids[j], e.rosterIds[i], StringComparison.Ordinal)) continue;
                    string nm = s.names[j];
                    if (!string.IsNullOrEmpty(nm) && nm != "?") e.names[i] = nm;
                    break;
                }
            }
        }

        /// <summary>Newest sitting-end first (Sid's pair-3→2→1 ordering).
        /// R1 f6+f8: playback requires IDENTITY (a non-empty roster — from
        /// activation or the poll fill) in every branch. Terminal proof
        /// (server ended_at, settled 90s from its local observation) is the
        /// normal gate; the unreachable fallback needs the director-side gone
        /// stamp AND a 25-min PER-ENTRY poll outage, and marks the play
        /// "(partial)".</summary>
        private static Entry PickEligible(float now)
        {
            Entry best = null;
            DateTime bestEnd = DateTime.MinValue;
            bool bestPartial = false;
            for (int i = 0; i < _queue.Count; i++)
            {
                var e = _queue[i];
                if (!HasIdentity(e)) continue;   // pending-identity: wait for the poll fill (R1 f6+f8)
                bool terminal = e.endedAtUtc.HasValue && e.settleReadyRt >= 0f && now >= e.settleReadyRt;
                bool fallback = !e.endedAtUtc.HasValue && e.sittingGoneRt > 0f
                                && e.pollOutageSinceRt > 0f
                                && now - e.pollOutageSinceRt >= STATUS_UNREACHABLE_FALLBACK_SECONDS;
                if (!terminal && !fallback) continue;
                DateTime end = e.endedAtUtc ?? DateTime.UtcNow.AddSeconds(-(double)(now - e.sittingGoneRt));
                if (best == null || end > bestEnd) { best = e; bestEnd = end; bestPartial = fallback; }
            }
            if (best != null) best.partial = bestPartial;
            return best;
        }

        // ── fetch orchestration (Tick-driven — no coroutine host to die) ──

        private static void BeginFetch(Entry e, float now)
        {
            _gen++;
            int gen = _gen;
            _current = e;
            _phase = PHASE_FETCH;
            _fetchStartedRt = now;
            var f = new FetchBox();
            _fetch = f;
            int n = e.rosterIds.Length;
            f.stats = new ApiClient.PlayerStatsData[n];
            f.cards = new List<ApiClient.CardStatData>[n];
            try
            {
                if (e.mode == "2v2")
                {
                    FetchTeamSlot(gen, e, 0);
                    // Per-player panels use viewer:null (brief) — h2h unused.
                    // R1 f16: compact panels use the ranked /cards fetch like
                    // the 1v1 panels (stats top_cards are ALL-mode).
                    for (int i = 0; i < n; i++)
                    {
                        FetchStatsSlot(gen, e, i, null, 0);
                        FetchCardsSlot(gen, e, i, 0);
                    }
                }
                else if (e.mode == "ffa")
                {
                    FetchFfaSlot(gen, e, 0);
                    for (int i = 0; i < n; i++) FetchStatsSlot(gen, e, i, null, 0);
                }
                else // 1v1
                {
                    string a = e.rosterIds[0];
                    string b = n > 1 ? e.rosterIds[1] : null;
                    // Stats fetched with the OTHER fighter as viewer so h2h_*
                    // counts are fighter-vs-fighter, not vs the broadcast seat.
                    FetchStatsSlot(gen, e, 0, b, 0);
                    if (b != null) FetchStatsSlot(gen, e, 1, a, 0);
                    FetchCardsSlot(gen, e, 0, 0);
                    if (b != null) FetchCardsSlot(gen, e, 1, 0);
                    // DEVIATION from the brief's "history for each fighter":
                    // one viewer-relative history covers both sides of every
                    // shared game (the rows and graphs are A-relative and name
                    // B explicitly); the second 100-row full-detail fetch would
                    // be pure duplication. Subject = rosterIds[0] (sorted CSV,
                    // so the lower id — also the reporter whenever both had
                    // the mod, which keeps the DPS grid resolution local).
                    FetchHistorySlot(gen, e, 0);
                }
            }
            catch (Exception ex)
            {
                try { Plugin.Log?.LogWarning("[REPORT] fetch start failed: " + ex.Message); } catch { }
            }
        }

        private static void FetchStatsSlot(int gen, Entry e, int slot, string viewer, int attempt)
        {
            var f = _fetch;
            if (f == null || gen != _gen) return;
            if (attempt == 0) f.pending++;
            try
            {
                ApiClient.FetchPlayerStatsForView(e.rosterIds[slot], s =>
                {
                    if (gen != _gen || _fetch != f) return;   // superseded run (#367b)
                    if (s == null && attempt + 1 < FETCH_ATTEMPTS)
                    { FetchStatsSlot(gen, e, slot, viewer, attempt + 1); return; }
                    f.stats[slot] = s;
                    f.pending--;
                }, viewer);
            }
            catch { f.pending--; }
        }

        private static void FetchCardsSlot(int gen, Entry e, int slot, int attempt)
        {
            var f = _fetch;
            if (f == null || gen != _gen) return;
            if (attempt == 0) f.pending++;
            try
            {
                ApiClient.FetchCardStatsForView(e.rosterIds[slot], list =>
                {
                    if (gen != _gen || _fetch != f) return;
                    if (list == null && attempt + 1 < FETCH_ATTEMPTS)
                    { FetchCardsSlot(gen, e, slot, attempt + 1); return; }
                    f.cards[slot] = list;
                    f.pending--;
                });
            }
            catch { f.pending--; }
        }

        /// <summary>R3 f7: keep the BEST partial snapshot across retry attempts.
        /// A failed attempt can still have accumulated real rows (a paginated
        /// fetch that died on page 3, a shape failure after two good pages), and
        /// the old code threw them away before retrying — so a poorer retry
        /// could REPLACE a richer result, and the 30s FETCH_DEADLINE firing
        /// while a retry was in flight rendered NO rows at all. Storing the
        /// best-so-far in the slot fixes both: the deadline always finds the
        /// richest snapshot seen.
        /// Explicitly does NOT MERGE two attempts — each attempt is its own
        /// LIMIT/OFFSET window (R3 f4), so concatenating two of them would
        /// splice rows that were never one consistent snapshot. "Best" is
        /// simply the longer list.
        /// The ok FLAG is untouched here: it is written only at settle, so a
        /// retained partial always renders under "(partial)" (R2 f2).</summary>
        private static List<T> BestPartial<T>(List<T> keep, List<T> candidate)
        {
            if (candidate == null) return keep;
            if (keep == null) return candidate;
            return candidate.Count > keep.Count ? candidate : keep;
        }

        private static void FetchHistorySlot(int gen, Entry e, int attempt)
        {
            var f = _fetch;
            if (f == null || gen != _gen) return;
            if (attempt == 0) f.pending++;
            try
            {
                // R1 f10: the (list, ok) overload separates transport failure
                // from a genuinely empty history — retry ONLY on !ok; after
                // the budget the section renders "(partial)", never "0 games".
                ApiClient.FetchMatchHistoryForView(e.rosterIds[0], (list, ok) =>
                {
                    if (gen != _gen || _fetch != f) return;
                    if (!ok && attempt + 1 < FETCH_ATTEMPTS)
                    {
                        // R3 f7: bank this attempt's rows BEFORE retrying.
                        f.history = BestPartial(f.history, list);
                        FetchHistorySlot(gen, e, attempt + 1);
                        return;
                    }
                    f.historyOk = ok;   // R2 f2: true only on success; false re-writes the default
                    // ok=true is an authoritative snapshot and always wins; a
                    // final failure keeps whichever attempt saw more rows.
                    f.history = (ok ? list : BestPartial(f.history, list))
                                ?? new List<ApiClient.MatchHistoryEntry>();
                    f.pending--;
                }, 100);
            }
            catch { f.pending--; }   // R2 f2: historyOk stays false (default)
        }

        /// <summary>2v2 session source (R1 f9/f12): the PLAYER-SCOPED team
        /// history of one watched fighter, report-private — ten unrelated
        /// newer global series can no longer hide the watched one, and an F5
        /// page flip can no longer swap the data mid-fetch.
        /// CONTRACT (R1 delta, verbatim): "SAME entry type the F5 2v2 tab
        /// renders" = TeamSeriesPagedEntry. The thin PlayerTeamHistoryEntry
        /// shape cannot satisfy f12/f14/f22-REJECTED (no slots/steam ids, no
        /// matches, no telemetry, no cards_by_player) — the server response
        /// must carry the rich shape for this roster's series.
        /// R2 f4: PAGINATED variant — one page-0 fetch let 19 newer series
        /// displace all but one game of the watched sitting and print an
        /// unlabeled exact undercount. The cutoff (session-window start =
        /// started_at - 5min, the same WINDOW_PRE_START_SECONDS the window
        /// math uses) lets ApiClient page until the window is provably
        /// covered; null cutoff (no server stamp — the "(partial)" fallback
        /// window) means completeness cannot be bounded, and ok=false then
        /// keeps the section labeled "(partial)".</summary>
        private static void FetchTeamSlot(int gen, Entry e, int attempt)
        {
            var f = _fetch;
            if (f == null || gen != _gen) return;
            if (attempt == 0) f.pending++;
            try
            {
                DateTime? cutoff = e.startedAtUtc.HasValue
                    ? (DateTime?)e.startedAtUtc.Value.AddSeconds(-WINDOW_PRE_START_SECONDS)
                    : null;
                ApiClient.FetchTeamHistoryForView(e.rosterIds[0], cutoff, (list, ok) =>
                {
                    if (gen != _gen || _fetch != f) return;
                    if (!ok && attempt + 1 < FETCH_ATTEMPTS)
                    {
                        // R3 f7: a failed paginated run still carries the pages
                        // that DID arrive — bank them before retrying.
                        f.teamHistory = BestPartial(f.teamHistory, list);
                        FetchTeamSlot(gen, e, attempt + 1);
                        return;
                    }
                    f.teamOk = ok;   // R2 f2: true only on success; false (incl. unproven completeness, R2 f4) re-writes the default
                    f.teamHistory = (ok ? list : BestPartial(f.teamHistory, list))
                                    ?? new List<ApiClient.TeamSeriesPagedEntry>();
                    f.pending--;
                });
            }
            catch { f.pending--; }   // R2 f2: teamOk stays false (default)
        }

        /// <summary>FFA session source (R1 f9/f15): the PLAYER-SCOPED FFA
        /// history of one watched fighter (ranked + casual, as the tab shows),
        /// report-private.
        /// CONTRACT (R1 delta, verbatim): "same entry type as the FFA tab" =
        /// FfaRecentMatch. The thin PlayerFfaHistoryEntry shape cannot satisfy
        /// f15 (participants are display NAMES — steam-id roster overlap is
        /// impossible) nor the placement rows/graphs — the server response
        /// must carry the rich per-player shape.
        /// R2 f5: PAGINATED variant — one page-0/30-row fetch under-reported
        /// a legal 40-game lobby (FFA_MAX_GAMES_PER_LOBBY) and 31 newer
        /// matches could displace the watched window into an unlabeled clean
        /// zero. Cutoff semantics identical to FetchTeamSlot (R2 f4): window
        /// start = started_at - WINDOW_PRE_START_SECONDS, null in the
        /// "(partial)" fallback window; ok=false covers both transport
        /// failure and unproven completeness.
        /// Bug 254 deliberately keeps one anchor fetch: it is the simplest
        /// bounded request shape and normally follows the sitting, but a game
        /// with no persisted player row for rosterIds[0] is not discoverable
        /// from this participant-scoped feed. That coverage residual does NOT change
        /// ffaOk, which remains pagination-completeness only.</summary>
        private static void FetchFfaSlot(int gen, Entry e, int attempt)
        {
            var f = _fetch;
            if (f == null || gen != _gen) return;
            if (attempt == 0) f.pending++;
            try
            {
                DateTime? cutoff = e.startedAtUtc.HasValue
                    ? (DateTime?)e.startedAtUtc.Value.AddSeconds(-WINDOW_PRE_START_SECONDS)
                    : null;
                ApiClient.FetchFfaHistoryForView(e.rosterIds[0], cutoff, (list, ok) =>
                {
                    if (gen != _gen || _fetch != f) return;
                    if (!ok && attempt + 1 < FETCH_ATTEMPTS)
                    {
                        // R3 f7: one leg can fail while the other returned a
                        // full sitting — bank the merged rows before retrying.
                        f.ffaHistory = BestPartial(f.ffaHistory, list);
                        FetchFfaSlot(gen, e, attempt + 1);
                        return;
                    }
                    f.ffaOk = ok;   // R2 f2: true only on success; false (incl. unproven completeness, R2 f5) re-writes the default
                    f.ffaHistory = (ok ? list : BestPartial(f.ffaHistory, list))
                                   ?? new List<ApiClient.FfaRecentMatch>();
                    f.pending--;
                });
            }
            catch { f.pending--; }   // R2 f2: ffaOk stays false (default)
        }

        // R1 f9 tombstone: IssueCacheFetches (FetchAllSeriesPaged/FetchFfaRecent
        // + shared-cache reference sniffing) is DELETED — completion can never
        // again be inferred from a cache an F5 page request also writes (#310).

        private static void TickFetch(float now)
        {
            var f = _fetch;
            var e = _current;
            if (f == null || e == null) { _phase = PHASE_NONE; _current = null; return; }

            bool done = f.pending <= 0;
            if (!done && now - _fetchStartedRt < FETCH_DEADLINE) return;

            // R1 f21: the stream can die during the fetch (<=30s) — never flip
            // to PLAY on a dead stream. Abandon the run; the entry stays
            // queued under the 2h rule and re-picks when the stream is back
            // (the pick gate keeps this from looping).
            bool live = false;
            try { live = BroadcastMode.StreamInfoLive; } catch { }
            if (!live)
            {
                _gen++;
                _fetch = null;
                _current = null;
                _phase = PHASE_NONE;
                try { Plugin.Log?.LogInfo("[REPORT] stream not live - deferring " + e.reportId); } catch { }
                return;
            }

            // Deadline or done: build with whatever arrived (never wedge).
            List<Page> pages = null;
            try { pages = BuildPages(e, f); }
            catch (Exception ex)
            { try { Plugin.Log?.LogWarning("[REPORT] build failed: " + ex.Message); } catch { } }
            _gen++;          // discard any late fetch callbacks
            _fetch = null;
            if (pages == null || pages.Count == 0)
            {
                // A poisoned entry must not replay forever (#276: freed-early
                // beats wedged) — consume it.
                _queue.Remove(e);
                _current = null;
                _phase = PHASE_NONE;
                try { Plugin.Log?.LogWarning("[REPORT] dropped unbuildable entry " + e.reportId); } catch { }
                return;
            }
            _pages = pages;
            _pageIdx = 0;
            _pageRemaining = REPORT_SECONDS;
            _phase = PHASE_PLAY;
            try { Plugin.Log?.LogInfo($"[REPORT] playing {e.mode} report id={e.reportId} pages={pages.Count} partial={e.partial}"); } catch { }
        }

        private static void Consume()
        {
            var e = _current;
            if (e != null) _queue.Remove(e);
            _current = null;
            _pages = null;
            _phase = PHASE_NONE;
            _gen++;
            try { Plugin.Log?.LogInfo("[REPORT] consumed" + (e != null ? " " + e.reportId : "")); } catch { }
        }

        // ── page model (everything pre-composed at build time, #162) ─────

        private const int ST_TITLE = 0, ST_SUB = 1, ST_SECTION = 2, ST_BODY = 3,
                          ST_SMALL = 4, ST_CAPTION = 5, ST_RIGHT = 6;

        private struct Panel { public Rect r; public float a; }
        private struct Label { public Rect r; public string text; public int style; }

        private const int PAINTER_TELE = 0, PAINTER_PAIR = 1, PAINTER_SCORE = 2;

        private class GraphCell
        {
            public Rect box;            // assigned when the cell is placed on a page
            public string caption;
            public int painter;
            public string a, b;         // series (PAINTER_SCORE keeps its timeline in pTimeline)
            public int kind;            // tele: 0 fps / 1 ping / 5 dps (CompetitiveUI region ids)
            public bool isBlock, isOpp, won;
            public float myStep;
            public string pTimes, pTimeline, subject, legA, legB;
            public int dur;
        }

        private class Page
        {
            public List<Panel> panels = new List<Panel>();
            public List<Label> labels = new List<Label>();
            public List<GraphCell> graphs = new List<GraphCell>();
        }

        private static void AddPanel(Page p, float x, float y, float w, float h)
            => p.panels.Add(new Panel { r = new Rect(x, y, w, h), a = PANEL_A });
        private static void AddLabel(Page p, float x, float y, float w, float h, string text, int style)
        {
            if (string.IsNullOrEmpty(text)) return;
            p.labels.Add(new Label { r = new Rect(x, y, w, h), text = text, style = style });
        }

        /// <summary>D1 f9 session window: [started_at - 5min, ended_at], both
        /// server UTC — the ONE place server-UTC math survives (R1 f7: both
        /// sides of the comparison are server-generated). A server stamp is
        /// used whenever OBSERVED, partial or not (an earlier successful poll
        /// may have filled started_at before the outage began); only a stamp
        /// never observed falls back to the local-UTC activation anchor
        /// (first activation - 10min / now) — the "(partial)" degraded
        /// window, the only mode where a Unity-side clock enters this math.</summary>
        private static void GetWindow(Entry e, out DateTime lo, out DateTime hi)
        {
            hi = e.endedAtUtc.HasValue ? e.endedAtUtc.Value : DateTime.UtcNow;
            lo = e.startedAtUtc.HasValue
                ? e.startedAtUtc.Value.AddSeconds(-WINDOW_PRE_START_SECONDS)
                : e.firstActivatedUtc.AddSeconds(-SESSION_SLACK);
        }

        private static List<Page> BuildPages(Entry e, FetchBox f)
        {
            var pages = new List<Page>();
            var report = new Page();
            var cells = new List<GraphCell>();
            string pairTitle;
            if (e.mode == "2v2") pairTitle = Compose2v2(e, f, report, cells);
            else if (e.mode == "ffa") pairTitle = ComposeFfa(e, f, report, cells);
            else pairTitle = Compose1v1(e, f, report, cells);
            AddLabel(report, 1480, 1050, 400, 22, WATERMARK, ST_RIGHT);
            pages.Add(report);
            BuildGraphPages(pages, cells, pairTitle);
            return pages;
        }

        private static Rect GraphSlot(int c)
        {
            float x = (c % 2 == 0) ? 40f : 980f;
            float y = (c < 2) ? 90f : 566f;
            return new Rect(x, y, 900f, 460f);
        }

        private static void BuildGraphPages(List<Page> pages, List<GraphCell> cells, string pairTitle)
        {
            int maxCells = MAX_GRAPH_PAGES * 4;
            int totalCells = cells.Count;   // R1 f17: remember the pre-cap count
            if (cells.Count > maxCells) cells.RemoveRange(maxCells, cells.Count - maxCells);
            int total = (cells.Count + 3) / 4;
            for (int p = 0; p < total; p++)
            {
                var pg = new Page();
                AddPanel(pg, 40, 18, 1840, 56);
                AddLabel(pg, 64, 30, 1380, 34, pairTitle, ST_SECTION);
                string pager = I18n.TrF("Graphs {0}/{1}", p + 1, total);
                if (totalCells > cells.Count)   // R1 f17: capped — say so
                    pager += "  " + I18n.TrF("showing {0} of {1}", cells.Count, totalCells);
                AddLabel(pg, 1456, 36, 400, 24,
                    "<color=#8FA3B8>" + pager + "</color>", ST_RIGHT);
                AddLabel(pg, 1480, 1050, 400, 22, WATERMARK, ST_RIGHT);
                for (int c = 0; c < 4; c++)
                {
                    int idx = p * 4 + c;
                    if (idx >= cells.Count) break;
                    var cell = cells[idx];
                    Rect slot = GraphSlot(c);
                    AddPanel(pg, slot.x, slot.y, slot.width, slot.height);
                    AddLabel(pg, slot.x + 16, slot.y + 8, slot.width - 32, 26, cell.caption, ST_CAPTION);
                    cell.box = new Rect(slot.x + 12, slot.y + 40, slot.width - 24, slot.height - 52);
                    pg.graphs.Add(cell);
                }
                pages.Add(pg);
            }
        }

        // ── 1v1 composition ──────────────────────────────────────────────

        private static string Compose1v1(Entry e, FetchBox f, Page rp, List<GraphCell> cells)
        {
            string idA = e.rosterIds.Length > 0 ? e.rosterIds[0] : "";
            string idB = e.rosterIds.Length > 1 ? e.rosterIds[1] : "";
            var sA = f.stats != null && f.stats.Length > 0 ? f.stats[0] : null;
            var sB = f.stats != null && f.stats.Length > 1 ? f.stats[1] : null;
            string plainA = PlainName(sA, NameAt(e, 0));
            string plainB = PlainName(sB, NameAt(e, 1));

            // Session games: subject A's history vs B inside the window.
            DateTime lo, hi;
            GetWindow(e, out lo, out hi);
            var games = new List<ApiClient.MatchHistoryEntry>();
            if (f.history != null && !string.IsNullOrEmpty(idB))
            {
                // Server order is newest-first; preserved (the graph numbering
                // and the row order both rely on it).
                for (int i = 0; i < f.history.Count; i++)
                {
                    var m = f.history[i];
                    if (m == null || !string.Equals(m.opponent_steam_id, idB, StringComparison.Ordinal)) continue;
                    DateTime end;
                    if (!TryParseUtc(m.ended_at, out end)) continue;
                    if (end < lo || end > hi) continue;
                    games.Add(m);
                }
            }

            // Header.
            AddPanel(rp, 40, 24, 1840, 120);
            string head = StyledHeaderName(sA, NameAt(e, 0), RatingAt(e, 0))
                + "   " + I18n.Tr("<color=#888>vs</color>") + "   "
                + StyledHeaderName(sB, NameAt(e, 1), RatingAt(e, 1))
                + PartialTag(e);
            AddLabel(rp, 60, 32, 1800, 52, head, ST_TITLE);

            // H2H line: session count + session series score | all-time.
            // R1 f10: a transport failure (after retries) must never render
            // as a definitive "Session: 0 games" — the "(partial)" label
            // replaces the claim.
            int sesA = 0, sesB = 0;
            CountSessionSeries(games, ref sesA, ref sesB);
            // R2 f2: a nonempty list can arrive with ok=false (last retry) —
            // render its counts as a labeled floor, never an exact claim.
            string sub = f.historyOk
                ? I18n.TrF("Session: {0} games, series {1}-{2}", games.Count, sesA, sesB)
                : (games.Count > 0
                    ? I18n.TrF("Session: {0} games, series {1}-{2}", games.Count, sesA, sesB) + " " + PartialInline()
                    : PartialInline());
            // h2h_* wins are the VIEWER's (main.py orientation): sB was fetched
            // with viewer=A, so its h2h is A-first; sA (viewer=B) inverts.
            int atW = -1, atL = 0, atSW = 0, atSL = 0;
            if (sB != null)
            { atW = sB.h2h_ranked_wins + sB.h2h_casual_wins; atL = sB.h2h_ranked_losses + sB.h2h_casual_losses; atSW = sB.h2h_series_wins; atSL = sB.h2h_series_losses; }
            else if (sA != null)
            { atW = sA.h2h_ranked_losses + sA.h2h_casual_losses; atL = sA.h2h_ranked_wins + sA.h2h_casual_wins; atSW = sA.h2h_series_losses; atSL = sA.h2h_series_wins; }
            if (atW >= 0)
                sub += "   <color=#888>|</color>   "
                    + I18n.TrF("All-time: {0} games ({1}W-{2}L), series {3}-{4}", atW + atL, atW, atL, atSW, atSL);
            AddLabel(rp, 60, 96, 1800, 32, "<color=#B9C4D0>" + sub + "</color>", ST_SUB);

            // Per-game rows (left panel), series-grouped.
            ComposeGameRows1v1(rp, games, plainA, plainB, f.historyOk);

            // Two per-player panels (right column).
            ComposePlayerPanel1v1(rp, new Rect(1172, 158, 708, 428), sA, NameAt(e, 0), RatingAt(e, 0),
                                  f.cards != null && f.cards.Length > 0 ? f.cards[0] : null);
            ComposePlayerPanel1v1(rp, new Rect(1172, 602, 708, 428), sB, NameAt(e, 1), RatingAt(e, 1),
                                  f.cards != null && f.cards.Length > 1 ? f.cards[1] : null);

            // Graph cells (newest game first; chronological numbering — R3 f5:
            // the numbering is only assertable when the fetch proved complete).
            BuildCells1v1(cells, games, idA, plainA, plainB, f.historyOk);

            // R3 f5: the graph pages render this title on their own, so the
            // 1v1 fetch flag has to travel with it.
            return plainA + "  " + I18n.Tr("<color=#888>vs</color>") + "  " + plainB
                 + PartialTag(e) + FetchPartialSuffix(e, f.historyOk);
        }

        /// <summary>Session series tally over the (newest-first) session games,
        /// grouped by CONSECUTIVE equal non-null series_id — the same grouping
        /// convention as NativeUI.GroupBySeries (source of truth). Only
        /// completed series (either side at 2) count; scores are A-relative
        /// (the history subject's), like series_score itself.</summary>
        private static void CountSessionSeries(List<ApiClient.MatchHistoryEntry> games, ref int sesA, ref int sesB)
        {
            int i = 0;
            while (i < games.Count)
            {
                string sid = games[i].series_id;
                bool has = !string.IsNullOrEmpty(sid) && sid != "null";
                int end = i + 1;
                if (has) while (end < games.Count && games[end].series_id == sid) end++;
                if (has)
                {
                    try
                    {
                        var p = (games[i].series_score ?? "").Split('-');
                        int mw = int.Parse(p[0], INV), tw = int.Parse(p[1], INV);
                        if (mw >= 2 || tw >= 2) { if (mw > tw) sesA++; else sesB++; }
                    }
                    catch { }
                }
                i = end;
            }
        }

        private static void ComposeGameRows1v1(Page rp, List<ApiClient.MatchHistoryEntry> games,
                                               string plainA, string plainB, bool transportOk)
        {
            AddPanel(rp, 40, 158, 1116, 872);
            float y = 210f, bottom = 158f + 872f - 12f;
            if (games.Count == 0)
            {
                // R1 f10: "No games recorded" is a claim only a SUCCESSFUL
                // fetch may make; a failed transport renders "(partial)".
                AddLabel(rp, 64, 170, 1068, 28, transportOk
                    ? I18n.TrF("Session games ({0})", games.Count)
                    : I18n.Tr("Session games") + " " + PartialInline(), ST_SECTION);
                AddLabel(rp, 64, y, 1068, 26,
                    "<color=#8FA3B8>" + (transportOk
                        ? I18n.Tr("No games recorded for this session yet.")
                        : I18n.Tr("match data unavailable")) + "</color>", ST_BODY);
                return;
            }
            int drawn = 0;
            int emitted = 0, gi = 0;
            while (gi < games.Count && emitted < MAX_ROWS)
            {
                // Consecutive-equal-series grouping (NativeUI.GroupBySeries
                // convention); the per-series elo delta renders ONCE, on the
                // group header, exactly like the F5 history's series rows.
                string sid = games[gi].series_id;
                bool has = !string.IsNullOrEmpty(sid) && sid != "null";
                int gEnd = gi + 1;
                if (has) while (gEnd < games.Count && games[gEnd].series_id == sid) gEnd++;
                if (has)
                {
                    if (y + 26f > bottom) break;
                    AddLabel(rp, 64, y, 1068, 24, SeriesHeaderText(games, gi, gEnd), ST_BODY);
                    y += 28f;
                }
                float indent = has ? 96f : 72f;
                for (; gi < gEnd && emitted < MAX_ROWS; gi++)
                {
                    var m = games[gi];
                    string l1 = GameLine1(m);
                    string l2 = GameStatsLine(m, plainA, plainB);
                    string l3 = GameCardsLine(m, plainA, plainB);
                    float rowH = 26f + (l2.Length > 0 ? 20f : 0f) + (l3.Length > 0 ? 20f : 0f) + 8f;
                    if (y + rowH > bottom) { emitted = MAX_ROWS; break; }
                    AddLabel(rp, indent, y, 1132f - indent, 24, l1, ST_BODY);
                    float ly = y + 26f;
                    if (l2.Length > 0) { AddLabel(rp, indent + 12f, ly, 1120f - indent, 18, l2, ST_SMALL); ly += 20f; }
                    if (l3.Length > 0) { AddLabel(rp, indent + 12f, ly, 1120f - indent, 18, l3, ST_SMALL); }
                    y += rowH;
                    emitted++;
                    drawn++;
                }
            }
            // R1 f17: header added AFTER the loop (labels are positioned
            // rects — list order is irrelevant) so a truncated list says so.
            string rowsHead = drawn < games.Count
                ? I18n.Tr("Session games") + " - " + I18n.TrF("showing {0} of {1}", drawn, games.Count)
                : I18n.TrF("Session games ({0})", games.Count);
            // R2 f2: rows off a false flag are a floor, not a total
            // (games.Count > 0 here — the zero case returned above).
            if (!transportOk) rowsHead += " " + PartialInline();
            AddLabel(rp, 64, 170, 1068, 28, rowsHead, ST_SECTION);
        }

        private static string SeriesHeaderText(List<ApiClient.MatchHistoryEntry> games, int gi, int gEnd)
        {
            var first = games[gi];
            string score = first.series_score ?? "?-?";
            bool complete = false, won = false;
            try
            {
                var p = score.Split('-');
                int mw = int.Parse(p[0], INV), tw = int.Parse(p[1], INV);
                complete = mw >= 2 || tw >= 2;
                won = mw > tw;
            }
            catch { }
            int grpGold = 0;
            for (int i = gi; i < gEnd; i++)
                if (games[i].series_gold_gained > grpGold) grpGold = games[i].series_gold_gained;
            string headCol = complete ? (won ? "#00FF00" : "#FF6666") : "#FFD94D";
            string head = complete
                ? I18n.TrF("Series {0} {1}", won ? "W" : "L", score)
                : I18n.TrF("Series {0} (in progress)", score);
            string tail = "";
            if (complete && (first.series_rating_change != 0f || grpGold > 0))
            {
                float rc = first.series_rating_change;
                if (rc != 0f)
                {
                    string rcCol = rc > 0f ? "#00FF00" : "#FF6666";
                    tail += "   <color=" + rcCol + ">"
                         + I18n.TrF("{0} elo", (rc > 0f ? "+" : "") + rc.ToString("F0", INV)) + "</color>";
                }
                if (grpGold > 0) tail += " <color=#FFD94D>+" + grpGold.ToString(INV) + "g</color>";
            }
            return "<color=" + headCol + ">" + head + "</color>" + tail;
        }

        private static string GameLine1(ApiClient.MatchHistoryEntry m)
        {
            string res = m.won ? "<color=#00FF00>W</color>" : "<color=#FF6666>L</color>";
            string score = FmtHalfScore(m.player_rounds_won, m.player_points)
                + "-" + FmtHalfScore(m.opponent_rounds_won, m.opponent_points);
            string tag = m.is_ranked ? "" : "  <color=#888>" + I18n.Tr("casual") + "</color>";
            string dur = m.duration_seconds > 0 ? "  <color=#8FA3B8>" + FmtDur(m.duration_seconds) + "</color>" : "";
            string xp = "";
            if (m.xp_gained > 0)
            {
                xp = "  <color=#88CCFF>+" + m.xp_gained.ToString(INV) + "xp</color>";
                if (m.gold_gained > 0) xp += " <color=#FFD94D>+" + m.gold_gained.ToString(INV) + "g</color>";
            }
            string dt = "";
            try
            {
                if (!string.IsNullOrEmpty(m.ended_at) && m.ended_at.Length >= 10)
                    dt = "  <color=#999>" + DateFmt.Short(DateTime.Parse(m.ended_at)) + "</color>";
            }
            catch { }
            return res + " " + score + tag + dur + xp + dt;
        }

        private static string GameStatsLine(ApiClient.MatchHistoryEntry m, string plainA, string plainB)
        {
            string a = SideStats(plainA, "#99B3E6", m.player_bullets_fired, m.player_bullets_hit,
                m.player_blocks_activated, m.player_blocks_successful, m.player_keys_pressed,
                m.player_active_seconds, m.player_damage_dealt, m.duration_seconds);
            string b = SideStats(plainB, "#E69988", m.opp_bullets_fired, m.opp_bullets_hit,
                m.opp_blocks_activated, m.opp_blocks_successful, m.opp_keys_pressed,
                m.opp_active_seconds, m.opp_damage_dealt, m.duration_seconds);
            if (a.Length == 0 && b.Length == 0) return "";
            if (a.Length == 0) return b;
            if (b.Length == 0) return a;
            return a + "    " + b;
        }

        private static string SideStats(string name, string hex, int fired, int hit, int blkAct, int blkSucc,
                                        int keys, float activeSec, int dmg, int durationSec)
        {
            string parts = "";
            if (fired > 0)
                parts = I18n.TrF("Hit {0}%", (100f * hit / fired).ToString("F0", INV));
            if (blkAct > 0)
                parts += (parts.Length > 0 ? "  " : "") + I18n.TrF("Block {0}%", (100f * blkSucc / blkAct).ToString("F0", INV));
            if (activeSec > 0.5f)
                parts += (parts.Length > 0 ? "  " : "") + I18n.TrF("{0} keys/s", (keys / activeSec).ToString("F1", INV));
            // RECORD_NONE = not recorded (dash suppressed here — the row just
            // omits the cell, #257's "absent, not zero" in row form).
            if (dmg >= 0 && durationSec > 0)
                parts += (parts.Length > 0 ? "  " : "") + I18n.TrF("{0} dps", (dmg / (float)durationSec).ToString("F1", INV));
            if (parts.Length == 0) return "";
            return "<color=" + hex + ">" + name + ":</color> <color=#8FA3B8>" + parts + "</color>";
        }

        private static string GameCardsLine(ApiClient.MatchHistoryEntry m, string plainA, string plainB)
        {
            string ca = FormatCardLine(m.cards_display);
            string cb = FormatCardLine(m.opp_cards_display);
            if (ca.Length == 0 && cb.Length == 0) return "";
            string s = "";
            if (ca.Length > 0) s = "<color=#99B3E6>" + plainA + ":</color> <color=#B9C4D0>" + ca + "</color>";
            if (cb.Length > 0)
                s += (s.Length > 0 ? "    " : "") + "<color=#E69988>" + plainB + ":</color> <color=#B9C4D0>" + cb + "</color>";
            return s;
        }

        private static void ComposePlayerPanel1v1(Page rp, Rect r, ApiClient.PlayerStatsData s,
                                                  string fallbackName, float entryRating,
                                                  List<ApiClient.CardStatData> cards)
        {
            AddPanel(rp, r.x, r.y, r.width, r.height);
            float x = r.x + 24f, w = r.width - 48f, y = r.y + 14f;
            AddLabel(rp, x, y, w, 28, StyledHeaderName(s, fallbackName, entryRating), ST_SECTION);
            y += 34f;
            if (s == null)
            {
                AddLabel(rp, x, y, w, 24, "<color=#8FA3B8>" + I18n.Tr("no data") + "</color>", ST_BODY);
                return;
            }
            // Rank role — same template (and catalogue key) as My Stats.
            if (!string.IsNullOrEmpty(s.rank_name))
            {
                AddLabel(rp, x, y, w, 24,
                    I18n.TrF("Rank: <b><color={0}>{1}</color></b>", SafeHex(s.rank_color), SanitizeStyled(s.rank_name)),
                    ST_BODY);
                y += 26f;
            }
            // Current-mode (1v1) W/L% + totals.
            {
                int sw = s.ranked_series_wins, sl = s.ranked_series_losses;
                string pct = sw + sl > 0 ? (100f * sw / (sw + sl)).ToString("F0", INV) : "0";
                AddLabel(rp, x, y, w, 24,
                    I18n.TrF("1v1 record: series {0}W-{1}L ({2}%)   games {3}W-{4}L", sw, sl, pct, s.wins, s.losses),
                    ST_BODY);
                y += 26f;
            }
            // Per-mode ratings + board standings (TryFormatStanding refuses
            // the "#0 of 0" class by construction).
            AddLabel(rp, x, y, w, 24, ModeLine("#FFD94D", "1v1", s.rating, s.standing, s.standing_population), ST_BODY);
            y += 24f;
            AddLabel(rp, x, y, w, 24, ModeLine("#FFB347", "2v2",
                s.team_completed_series > 0 ? s.team_rating : 0f, s.team_standing, s.team_standing_population), ST_BODY);
            y += 24f;
            AddLabel(rp, x, y, w, 24, ModeLine("#C48CFF", "FFA",
                s.ffa_games > 0 ? s.ffa_rating : 0f, s.ffa_standing, s.ffa_standing_population), ST_BODY);
            y += 24f;
            AddLabel(rp, x, y, w, 24, OvtLine(s), ST_BODY);
            y += 30f;
            // Favorite ranked cards (A1's /cards fetch; stats top_cards as the
            // degrade when the fetch failed or came back empty). R1 f16: the
            // label must match the POPULATION — top_cards has no ranked
            // filter, so the fallback is labeled "Top cards (all modes)".
            bool anyRanked = false;
            if (cards != null)
                for (int i = 0; i < cards.Count; i++)
                    if (cards[i] != null && !string.IsNullOrEmpty(cards[i].card_name)) { anyRanked = true; break; }
            AddLabel(rp, x, y, w, 22, "<color=#66809A>"
                + (anyRanked ? I18n.Tr("Favorite ranked cards") : I18n.Tr("Top cards (all modes)"))
                + "</color>", ST_SMALL);
            y += 24f;
            int shown = 0;
            int sourceRows = 0;   // R2 f7: valid rows in the source that rendered
            if (anyRanked)
            {
                for (int i = 0; i < cards.Count; i++)
                {
                    var c = cards[i];
                    if (c == null || string.IsNullOrEmpty(c.card_name)) continue;
                    sourceRows++;
                    if (shown >= 5) continue;   // keep counting past the cap
                    AddLabel(rp, x, y, w, 20, FavCardLine(c.card_name, c.win_rate, c.times_picked), ST_SMALL);
                    y += 21f;
                    shown++;
                }
            }
            if (shown == 0 && s.top_card_names != null)
            {
                sourceRows = s.top_card_names.Count;   // fallback source supersedes
                for (int i = 0; i < s.top_card_names.Count && shown < 5; i++)
                {
                    float wr = s.top_card_win_rates != null && i < s.top_card_win_rates.Count ? s.top_card_win_rates[i] : 0f;
                    int picks = s.top_card_picks != null && i < s.top_card_picks.Count ? s.top_card_picks[i] : 0;
                    AddLabel(rp, x, y, w, 20, FavCardLine(s.top_card_names[i], wr, picks), ST_SMALL);
                    y += 21f;
                    shown++;
                }
            }
            if (shown == 0)
                AddLabel(rp, x, y, w, 20, "<color=#556270>" + I18n.Tr("no data") + "</color>", ST_SMALL);
            else if (sourceRows > shown)   // R2 f7: capped list says so
                AddLabel(rp, x, y, w, 20,
                    "<color=#8FA3B8>" + I18n.TrF("showing {0} of {1}", shown, sourceRows) + "</color>", ST_SMALL);
        }

        /// <summary>R1 f16: win_rate arrives as a WIRE FRACTION (0.65) from
        /// both sources (/cards win_rate and stats top_card_win_rates) — x100
        /// here, exactly like NativeUI's render sites.</summary>
        private static string FavCardLine(string cardName, float winRate, int picks)
        {
            string disp = cardName ?? "";
            try { disp = CardTextLocalizer.PrettyName(disp, disp); } catch { }
            disp = Trunc(StripTags(disp), 24);
            return I18n.TrF("{0}  {1}%  ({2} picks)", disp, (winRate * 100f).ToString("F0", INV), picks);
        }

        /// <summary>Mode rating + standing line. Mode tokens ("1v1") and
        /// numbers only — nothing translatable, so composed raw; the standing
        /// half comes pre-translated from ApiClient.TryFormatStanding.</summary>
        private static string ModeLine(string hex, string label, float rating, int standing, int population)
        {
            string r = rating > 0f ? rating.ToString("F0", INV) : "-";
            string standingTxt;
            string tail = ApiClient.TryFormatStanding(standing, population, out standingTxt)
                ? "  <color=#888>" + standingTxt + "</color>" : "";
            return "<color=" + hex + ">" + label + ":</color> " + r + tail;
        }

        /// <summary>1v2 W/L line — reuses the exact OvtRecordHead catalogue
        /// keys (NativeUI) so no new translation is minted (#289).</summary>
        private static string OvtLine(ApiClient.PlayerStatsData s)
        {
            int osw = s.ovt_solo_wins, osl = s.ovt_solo_losses, odw = s.ovt_duo_wins, odl = s.ovt_duo_losses;
            if (osw + osl + odw + odl <= 0) return I18n.Tr("<color=#9BE8A0>1v2:</color> -");
            string solo = osw + osl > 0 ? I18n.TrF("Solo {0}W/{1}L", osw, osl) : I18n.Tr("Solo -");
            string duo = odw + odl > 0 ? I18n.TrF("Duo {0}W/{1}L", odw, odl) : I18n.Tr("Duo -");
            return I18n.TrF("<color=#9BE8A0>1v2:</color> {0}  <color=#888>|</color>  {1}", solo, duo);
        }

        /// <summary>Graph cells per session game, newest first: score, DPS,
        /// hit pair A/B, block pair A/B, FPS, ping (Sid's kind order), packed
        /// 4 per page downstream. Empty series are skipped so pages stay
        /// dense.</summary>
        private static void BuildCells1v1(List<GraphCell> cells, List<ApiClient.MatchHistoryEntry> games,
                                          string idA, string plainA, string plainB, bool complete)
        {
            int total = games.Count;
            for (int i = 0; i < games.Count; i++)
            {
                var m = games[i];
                int gameNo = total - i;   // chronological number, newest first in the list
                // R3 f5: `total` is the FETCHED count — with complete=false it
                // is a floor, so the absolute ordinal is not assertable.
                string capBase = I18n.TrF("Game {0}   {1} {2} {3}", GameNoArg(complete, gameNo), plainA,
                    FmtHalfScore(m.player_rounds_won, m.player_points) + "-"
                    + FmtHalfScore(m.opponent_rounds_won, m.opponent_points), plainB);
                // Score.
                if (!string.IsNullOrEmpty(m.point_timeline) && m.point_timeline.IndexOf(':') >= 0)
                    cells.Add(new GraphCell
                    {
                        painter = PAINTER_SCORE, caption = Cap(capBase, I18n.Tr("Score")),
                        pTimeline = m.point_timeline, won = m.won, subject = plainA, dur = m.duration_seconds,
                    });
                // DPS — per-side cadence resolved for the FIGHTER (subject A),
                // never the broadcast viewer (NativeUI.ViewerWasReporter
                // rationale; local replica below because that helper is
                // private and viewer-bound).
                bool rep = SubjectWasReporter(idA, m);
                float stepA = NativeUI.DpsStepFor(m.player_damage_timeline, m.duration_seconds,
                    rep ? NativeUI.DPS_STEP_LOCAL : NativeUI.DPS_STEP_PEER);
                float stepB = NativeUI.DpsStepFor(m.opp_damage_timeline, m.duration_seconds,
                    rep ? NativeUI.DPS_STEP_PEER : NativeUI.DPS_STEP_LOCAL);
                string dpsA = NativeUI.CumulativeToDps(m.player_damage_timeline, stepA);
                string dpsB = NativeUI.CumulativeToDps(m.opp_damage_timeline, stepB);
                if (dpsA.Length > 0 || dpsB.Length > 0)
                    cells.Add(new GraphCell
                    {
                        painter = PAINTER_TELE, kind = 5, caption = Cap(capBase, I18n.Tr("DPS")),
                        a = dpsA.Length > 0 ? dpsA : null, b = dpsB.Length > 0 ? dpsB : null,
                        myStep = stepA, pTimes = m.point_times, pTimeline = m.point_timeline,
                        subject = plainA, legA = plainA, legB = plainB, dur = m.duration_seconds,
                    });
                // Hit pairs (one per fighter — the pair chart is single-subject).
                AddPairCell(cells, m.player_hit_timeline, false, false, plainA, capBase, m);
                AddPairCell(cells, m.opp_hit_timeline, false, true, plainB, capBase, m);
                // Block pairs.
                AddPairCell(cells, m.player_block_timeline, true, false, plainA, capBase, m);
                AddPairCell(cells, m.opp_block_timeline, true, true, plainB, capBase, m);
                // FPS.
                if (!string.IsNullOrEmpty(m.player_fps_timeline) || !string.IsNullOrEmpty(m.opp_fps_timeline))
                    cells.Add(new GraphCell
                    {
                        painter = PAINTER_TELE, kind = 0, caption = Cap(capBase, I18n.Tr("FPS")),
                        a = m.player_fps_timeline, b = m.opp_fps_timeline, myStep = 0f,
                        pTimes = m.point_times, pTimeline = m.point_timeline,
                        subject = plainA, legA = plainA, legB = plainB, dur = m.duration_seconds,
                    });
                // Ping.
                if (!string.IsNullOrEmpty(m.player_ping_timeline) || !string.IsNullOrEmpty(m.opp_ping_timeline))
                    cells.Add(new GraphCell
                    {
                        painter = PAINTER_TELE, kind = 1, caption = Cap(capBase, I18n.Tr("Ping")),
                        a = m.player_ping_timeline, b = m.opp_ping_timeline, myStep = 0f,
                        pTimes = m.point_times, pTimeline = m.point_timeline,
                        subject = plainA, legA = plainA, legB = plainB, dur = m.duration_seconds,
                    });
            }
        }

        private static void AddPairCell(List<GraphCell> cells, string series, bool isBlock, bool isOpp,
                                        string subject, string capBase, ApiClient.MatchHistoryEntry m)
        {
            if (string.IsNullOrEmpty(series)) return;
            cells.Add(new GraphCell
            {
                painter = PAINTER_PAIR, isBlock = isBlock, isOpp = isOpp,
                caption = Cap(capBase, (isBlock ? I18n.TrF("Block rate - {0}", subject) : I18n.TrF("Hit rate - {0}", subject))),
                a = series, pTimes = m.point_times, pTimeline = m.point_timeline,
                subject = subject, dur = m.duration_seconds,
            });
        }

        private static string Cap(string capBase, string metric)
            => capBase + "   <color=#8FA3B8>" + metric + "</color>";

        // ── 2v2 composition (D1 f12: F5 2v2 tab fidelity — team-series
        //    entries + TeamPlayerTele; no score-timeline, no keys/s: those
        //    fields do not exist on the 2v2 wire, so they are omitted, never
        //    fabricated) ─────────────────────────────────────────────────

        private const string TEAM_LEFT_HEX = "#6FB7FF";    // blue side (F5 tab convention)
        private const string TEAM_RIGHT_HEX = "#FFA864";   // orange side

        private static string Compose2v2(Entry e, FetchBox f, Page rp, List<GraphCell> cells)
        {
            // R1 f9 tombstone: the CachedTeamSeriesPaged path is deleted (#310)
            // — session series come from the report-private player-scoped
            // team-history fetch, filtered to roster set-equality + window.
            DateTime lo, hi;
            GetWindow(e, out lo, out hi);
            var rosterSet = new HashSet<string>(e.rosterIds, StringComparer.Ordinal);
            var series = new List<ApiClient.TeamSeriesPagedEntry>();
            var all = f.teamHistory;
            if (all != null)
            {
                for (int i = 0; i < all.Count; i++)
                {
                    var s = all[i];
                    if (s == null || !TeamRosterMatches(s, rosterSet)) continue;
                    if (!TeamSeriesInWindow(s, lo, hi)) continue;
                    series.Add(s);
                }
            }

            // R1 f14: a series QUALIFIES by window, but individual match rows
            // and graphs render only matches whose OWN ended_at is in-window
            // (a resumed BO3's out-of-window game 1 gets no row/graph; the
            // series header metadata below still renders). Key = the match's
            // original index, so "Game N" numbering survives the filter.
            var inWindow = new List<List<KeyValuePair<int, ApiClient.TeamSeriesMatch>>>(series.Count);
            int totalGames = 0;
            for (int i = 0; i < series.Count; i++)
            {
                var msW = TeamMatchesInWindow(series[i], lo, hi);
                inWindow.Add(msW);
                totalGames += msW.Count;
            }

            // Header. Side assignment from the newest matching series. R1 f12:
            // with ZERO series there is NO authoritative slot data — render a
            // FLAT name list + "(partial)", NEVER a fabricated 2+2 pairing
            // (canonical roster order once showed teams {1,4}/{2,3} as 1+2 vs
            // 3+4).
            AddPanel(rp, 40, 24, 1840, 120);
            string pairTitle;
            ApiClient.TeamSeriesSlot la = null, lb = null, ra = null, rb = null;
            if (series.Count > 0)
            {
                la = series[0].t1a; lb = series[0].t1b; ra = series[0].t2a; rb = series[0].t2b;
                string nmLA = SlotPlainName(la, NameAt(e, 0));
                string nmLB = SlotPlainName(lb, NameAt(e, 1));
                string nmRA = SlotPlainName(ra, NameAt(e, 2));
                string nmRB = SlotPlainName(rb, NameAt(e, 3));
                AddLabel(rp, 60, 32, 1800, 52,
                    "<color=" + TEAM_LEFT_HEX + ">" + nmLA + " + " + nmLB + "</color>"
                    + "   " + I18n.Tr("<color=#888>vs</color>") + "   "
                    + "<color=" + TEAM_RIGHT_HEX + ">" + nmRA + " + " + nmRB + "</color>"
                    + PartialTag(e), ST_TITLE);
                // R3 f5: teamOk travels with the title — the graph pages carry
                // no other completeness marker of their own.
                pairTitle = "<color=" + TEAM_LEFT_HEX + ">" + nmLA + " + " + nmLB + "</color>  "
                    + I18n.Tr("<color=#888>vs</color>") + "  "
                    + "<color=" + TEAM_RIGHT_HEX + ">" + nmRA + " + " + nmRB + "</color>"
                    + PartialTag(e) + FetchPartialSuffix(e, f.teamOk);
            }
            else
            {
                AddLabel(rp, 60, 32, 1800, 52, JoinNamesBudget(e, 80) + " " + PartialInline(), ST_TITLE);
                pairTitle = JoinNamesBudget(e, 60) + " " + PartialInline();
            }
            // R1 f10 + R2 f4: a false flag must never assert an exact total —
            // with rows the count renders as a labeled floor; with none, the
            // "(partial)" label alone (never "Session: 0 series").
            AddLabel(rp, 60, 96, 1800, 32,
                "<color=#B9C4D0>" + (f.teamOk
                    ? I18n.TrF("Session: {0} series", series.Count)
                    : (series.Count > 0
                        ? I18n.TrF("Session: {0} series", series.Count) + " " + PartialInline()
                        : PartialInline())) + "</color>", ST_SUB);

            // Series rows.
            AddPanel(rp, 40, 158, 1116, 872);
            float y = 210f, bottom = 158f + 872f - 12f;
            if (series.Count == 0)
                AddLabel(rp, 64, y, 1068, 26,
                    "<color=#8FA3B8>" + (f.teamOk
                        ? I18n.Tr("No games recorded for this session yet.")
                        : I18n.Tr("match data unavailable")) + "</color>", ST_BODY);   // R1 f10
            int gamesEmitted = 0, drawnGames = 0;
            for (int si = 0; si < series.Count && y + 60f <= bottom && gamesEmitted < MAX_ROWS; si++)
            {
                var s = series[si];
                // Neutral winner line (the broadcast seat is never a caller in
                // the series — mirrors the F5 tab's spectator branch; the
                // stamped team-colour tinting is deliberately omitted, see the
                // A6 report).
                bool leftWon = s.winner_team == 1;
                int hiSc = Math.Max(s.t1_series_wins, s.t2_series_wins);
                int loSc = Math.Min(s.t1_series_wins, s.t2_series_wins);
                string side = leftWon
                    ? I18n.TrF("<color={0}>Blue</color>", TEAM_LEFT_HEX)
                    : I18n.TrF("<color={0}>Orange</color>", TEAM_RIGHT_HEX);
                string dt = "";
                try
                {
                    if (!string.IsNullOrEmpty(s.completed_at) && s.completed_at.Length >= 10)
                        dt = "  <color=#999>" + DateFmt.Short(DateTime.Parse(s.completed_at)) + "</color>";
                }
                catch { }
                AddLabel(rp, 64, y, 1068, 24, I18n.TrF("{0} <b>won</b> {1}-{2}", side, hiSc, loSc) + dt, ST_BODY);
                y += 26f;
                // Per-slot elo/gold/xp deltas, one line per team.
                string lDelta = SlotDelta(s.t1a) + SlotDelta(s.t1b);
                string rDelta = SlotDelta(s.t2a) + SlotDelta(s.t2b);
                if (lDelta.Length > 0 && y + 18f <= bottom)
                { AddLabel(rp, 88, y, 1044, 18, "<color=" + TEAM_LEFT_HEX + ">-</color> " + lDelta, ST_SMALL); y += 20f; }
                if (rDelta.Length > 0 && y + 18f <= bottom)
                { AddLabel(rp, 88, y, 1044, 18, "<color=" + TEAM_RIGHT_HEX + ">-</color> " + rDelta, ST_SMALL); y += 20f; }
                // Per-game rows: score + duration, tele line per team (the F5
                // tab's FillTeleCell readout, replicated in TeleCellText),
                // card chips per team. R1 f14: in-window matches only.
                var ms = inWindow[si];
                for (int gi = 0; gi < ms.Count && gamesEmitted < MAX_ROWS; gi++)
                {
                    var m = ms[gi].Value;
                    string durChip = m.duration_seconds > 0
                        ? "  <color=#8FA3B8>" + FmtDur(m.duration_seconds) + "</color>" : "";
                    string g1 = I18n.TrF("Game {0}: {1}-{2}", ms[gi].Key + 1, m.t1_rounds_won, m.t2_rounds_won) + durChip;
                    string telL = JoinCells(TeleCellText(m, s.t1a, TEAM_LEFT_HEX), TeleCellText(m, s.t1b, TEAM_LEFT_HEX));
                    string telR = JoinCells(TeleCellText(m, s.t2a, TEAM_RIGHT_HEX), TeleCellText(m, s.t2b, TEAM_RIGHT_HEX));
                    string cardsL = TeamCardsLine(m, s.t1a, s.t1b, TEAM_LEFT_HEX);
                    string cardsR = TeamCardsLine(m, s.t2a, s.t2b, TEAM_RIGHT_HEX);
                    float rowH = 24f + (telL.Length > 0 ? 18f : 0f) + (telR.Length > 0 ? 18f : 0f)
                               + (cardsL.Length > 0 ? 18f : 0f) + (cardsR.Length > 0 ? 18f : 0f) + 6f;
                    if (y + rowH > bottom) { gamesEmitted = MAX_ROWS; break; }
                    AddLabel(rp, 88, y, 1044, 22, g1, ST_BODY);
                    float ly = y + 24f;
                    if (telL.Length > 0) { AddLabel(rp, 104, ly, 1028, 18, telL, ST_SMALL); ly += 18f; }
                    if (telR.Length > 0) { AddLabel(rp, 104, ly, 1028, 18, telR, ST_SMALL); ly += 18f; }
                    if (cardsL.Length > 0) { AddLabel(rp, 104, ly, 1028, 18, cardsL, ST_SMALL); ly += 18f; }
                    if (cardsR.Length > 0) { AddLabel(rp, 104, ly, 1028, 18, cardsR, ST_SMALL); ly += 18f; }
                    y += rowH;
                    gamesEmitted++;
                    drawnGames++;
                }
                y += 8f;
            }
            // R1 f17: section header added AFTER the loop (labels are
            // positioned rects — list order is irrelevant) so a capped games
            // list says so instead of silently stopping.
            string secHead;
            if (series.Count == 0)
                secHead = f.teamOk ? I18n.TrF("Session series ({0})", series.Count)
                                   : I18n.Tr("Session series") + " " + PartialInline();   // R1 f10
            else if (drawnGames < totalGames)
                secHead = I18n.Tr("Session series") + " - " + I18n.TrF("showing {0} of {1}", drawnGames, totalGames);
            else
                secHead = I18n.TrF("Session series ({0})", series.Count);
            // R2 f4: rows off a false flag are a floor, not a total.
            if (!f.teamOk && series.Count > 0) secHead += " " + PartialInline();
            AddLabel(rp, 64, 170, 1068, 28, secHead, ST_SECTION);

            // Four compressed player panels — slot order when known, roster
            // order otherwise (a vertical stack of INDIVIDUAL panels — no
            // pairing implied, R1 f12).
            var order = new List<KeyValuePair<string, string>>();   // sid → display name
            if (la != null) order.Add(new KeyValuePair<string, string>(la.steam_id ?? "", SlotPlainName(la, NameAt(e, 0))));
            if (lb != null) order.Add(new KeyValuePair<string, string>(lb.steam_id ?? "", SlotPlainName(lb, NameAt(e, 1))));
            if (ra != null) order.Add(new KeyValuePair<string, string>(ra.steam_id ?? "", SlotPlainName(ra, NameAt(e, 2))));
            if (rb != null) order.Add(new KeyValuePair<string, string>(rb.steam_id ?? "", SlotPlainName(rb, NameAt(e, 3))));
            for (int i = 0; order.Count < e.rosterIds.Length && i < e.rosterIds.Length; i++)
            {
                bool present = false;
                for (int o = 0; o < order.Count; o++)
                    if (string.Equals(order[o].Key, e.rosterIds[i], StringComparison.Ordinal)) { present = true; break; }
                if (!present) order.Add(new KeyValuePair<string, string>(e.rosterIds[i], NameAt(e, i)));
            }
            for (int p = 0; p < order.Count && p < 4; p++)
            {
                var stats = StatsForSid(e, f, order[p].Key);
                ComposePlayerPanelCompact(rp, new Rect(1172, 158 + p * 218, 708, 202),
                    stats, order[p].Value, RatingForSid(e, order[p].Key),
                    CardsForSid(e, f, order[p].Key));
            }

            // Graph cells: per game (newest series, newest game first),
            // kind-major over the four slots — hit, block, fps, ping, dps.
            // R1 f14: in-window matches only, original game numbering.
            for (int si = 0; si < series.Count; si++)
            {
                var s = series[si];
                var msW = inWindow[si];
                if (msW.Count == 0) continue;
                var slots = new[] { s.t1a, s.t1b, s.t2a, s.t2b };
                var slotNames = new[] { SlotPlainName(s.t1a, "?"), SlotPlainName(s.t1b, "?"),
                                        SlotPlainName(s.t2a, "?"), SlotPlainName(s.t2b, "?") };
                for (int gi = msW.Count - 1; gi >= 0; gi--)   // newest game first
                {
                    var m = msW[gi].Value;
                    string capBase = I18n.TrF("Game {0}: {1}-{2}", msW[gi].Key + 1, m.t1_rounds_won, m.t2_rounds_won);
                    BuildCells2v2Game(cells, m, slots, slotNames, capBase);
                }
            }

            return pairTitle;
        }

        /// <summary>R1 f14: the matches of one qualifying series whose OWN
        /// ended_at falls inside the session window, keyed by their original
        /// index (so "Game N" labels survive the filter). A match without a
        /// parseable ended_at cannot prove it belongs and is excluded.</summary>
        private static List<KeyValuePair<int, ApiClient.TeamSeriesMatch>> TeamMatchesInWindow(
            ApiClient.TeamSeriesPagedEntry s, DateTime lo, DateTime hi)
        {
            var res = new List<KeyValuePair<int, ApiClient.TeamSeriesMatch>>();
            if (s.matches == null) return res;
            for (int i = 0; i < s.matches.Count; i++)
            {
                var m = s.matches[i];
                if (m == null) continue;
                DateTime t;
                if (!TryParseUtc(m.ended_at, out t) || t < lo || t > hi) continue;
                res.Add(new KeyValuePair<int, ApiClient.TeamSeriesMatch>(i, m));
            }
            return res;
        }

        private static bool TeamRosterMatches(ApiClient.TeamSeriesPagedEntry s, HashSet<string> roster)
        {
            var slots = new[] { s.t1a, s.t1b, s.t2a, s.t2b };
            int hits = 0;
            for (int i = 0; i < slots.Length; i++)
            {
                if (slots[i] == null || string.IsNullOrEmpty(slots[i].steam_id)) return false;
                if (roster.Contains(slots[i].steam_id)) hits++;
            }
            return hits == 4 && roster.Count == 4;
        }

        private static bool TeamSeriesInWindow(ApiClient.TeamSeriesPagedEntry s, DateTime lo, DateTime hi)
        {
            DateTime t;
            if (TryParseUtc(s.completed_at, out t) && t >= lo && t <= hi) return true;
            // A resumed series can complete inside the window while its
            // completed_at-less sibling games happened earlier (#345 family) —
            // any in-window game keeps the series.
            if (s.matches != null)
                for (int i = 0; i < s.matches.Count; i++)
                    if (s.matches[i] != null && TryParseUtc(s.matches[i].ended_at, out t) && t >= lo && t <= hi)
                        return true;
            return false;
        }

        private static string SlotPlainName(ApiClient.TeamSeriesSlot sl, string fallback)
        {
            string nm = sl != null && !string.IsNullOrEmpty(sl.name) ? sl.name : fallback;
            return Trunc(StripTags(nm ?? "?"), 14);
        }

        /// <summary>One slot's elo/gold/xp delta chip (empty when all zero).</summary>
        private static string SlotDelta(ApiClient.TeamSeriesSlot sl)
        {
            if (sl == null) return "";
            string s = "";
            if (Mathf.Abs(sl.rating_change) > 0.01f)
            {
                string col = sl.rating_change > 0f ? "#00FF00" : "#FF6666";
                s += " <color=" + col + ">"
                  + I18n.TrF("{0} elo", (sl.rating_change > 0f ? "+" : "") + sl.rating_change.ToString("F0", INV))
                  + "</color>";
            }
            if (sl.gold_earned > 0) s += " <color=#FFD94D>+" + sl.gold_earned.ToString(INV) + "g</color>";
            if (sl.xp_earned > 0) s += " <color=#88CCFF>+" + sl.xp_earned.ToString(INV) + "xp</color>";
            if (s.Length == 0) return "";
            return "<color=#B9C4D0>" + SlotPlainName(sl, "?") + "</color>" + s + "   ";
        }

        /// <summary>One player's telemetry readout — FillTeleCell's exact
        /// content (NativeUI.cs, source of truth), replicated because that
        /// helper is uGUI-bound and private; integrator may unify. Degrades to
        /// fps-only for old-client peers; empty when no data.</summary>
        private static string TeleCellText(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot sl, string hex)
        {
            if (sl == null) return "";
            string sid = sl.steam_id ?? "";
            ApiClient.TeamPlayerTele tele = null;
            if (m.telemetry_by_player != null) m.telemetry_by_player.TryGetValue(sid, out tele);
            int favg = 0;
            if (m.fps_by_player != null) m.fps_by_player.TryGetValue(sid, out favg);
            string nm = SlotPlainName(sl, "?");
            if (tele != null)
            {
                float hp = tele.bullets_fired > 0 ? 100f * tele.bullets_hit / tele.bullets_fired : 0f;
                float bp = tele.blocks_activated > 0 ? 100f * tele.blocks_successful / tele.blocks_activated : 0f;
                string fpsPart = favg > 0 ? favg.ToString(INV) + "fps " : "";
                string pingPart = tele.ping_avg > 0 ? tele.ping_avg.ToString(INV) + "ms " : "";
                return "<color=" + hex + ">" + nm + "</color> <color=#8FA3B8>" + fpsPart + pingPart
                    + I18n.TrF("Hit {0}% Blk {1}%", hp.ToString("F0", INV), bp.ToString("F0", INV)) + "</color>";
            }
            if (favg > 0)
                return "<color=" + hex + ">" + nm + "</color> <color=#8FA3B8>" + favg.ToString(INV) + "fps</color>";
            return "";
        }

        private static string JoinCells(string a, string b)
        {
            if (string.IsNullOrEmpty(a)) return b ?? "";
            if (string.IsNullOrEmpty(b)) return a;
            return a + "   " + b;
        }

        /// <summary>One team's card chips for a game — cards_by_player exists
        /// on the wire and the F5 tab renders it (BuildTeamCardsColumnChips),
        /// so the report keeps it (D1 f12's verify-against-the-tab clause;
        /// see the A6 report for the judgment call).
        /// R1 f22 REJECTED — these rows STAY (refutation recorded in
        /// ai-collab/streaming-r1-fix-deltas.md; #339).</summary>
        private static string TeamCardsLine(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot a,
                                            ApiClient.TeamSeriesSlot b, string hex)
        {
            if (m.cards_by_player == null || m.cards_by_player.Count == 0) return "";
            string s = "";
            var slots = new[] { a, b };
            for (int i = 0; i < slots.Length; i++)
            {
                var sl = slots[i];
                if (sl == null || string.IsNullOrEmpty(sl.steam_id)) continue;
                List<string> cards;
                if (!m.cards_by_player.TryGetValue(sl.steam_id, out cards) || cards == null || cards.Count == 0) continue;
                string chips = FormatCardLine(string.Join(",", cards.ToArray()));
                if (chips.Length == 0) continue;
                s += (s.Length > 0 ? "   " : "")
                  + "<color=" + hex + ">" + SlotPlainName(sl, "?") + ":</color> <color=#B9C4D0>" + chips + "</color>";
            }
            return s;
        }

        /// <summary>Compressed player panel (2v2's four, FFA reuses nothing of
        /// it): name, rank, three mode lines, top-3 cards on one line.
        /// R1 f16: cards = the ranked /cards fetch; the stats top_cards
        /// fallback is ALL-mode and labeled "Top cards (all modes)".</summary>
        private static void ComposePlayerPanelCompact(Page rp, Rect r, ApiClient.PlayerStatsData s,
                                                      string fallbackName, float entryRating,
                                                      List<ApiClient.CardStatData> cards)
        {
            AddPanel(rp, r.x, r.y, r.width, r.height);
            float x = r.x + 24f, w = r.width - 48f, y = r.y + 12f;
            AddLabel(rp, x, y, w, 26, StyledHeaderName(s, fallbackName, entryRating), ST_SECTION);
            y += 30f;
            if (s == null)
            {
                AddLabel(rp, x, y, w, 22, "<color=#8FA3B8>" + I18n.Tr("no data") + "</color>", ST_SMALL);
                return;
            }
            string rank = !string.IsNullOrEmpty(s.rank_name)
                ? I18n.TrF("Rank: <b><color={0}>{1}</color></b>", SafeHex(s.rank_color), SanitizeStyled(s.rank_name)) + "   "
                : "";
            AddLabel(rp, x, y, w, 22, rank + ModeLine("#FFB347", "2v2",
                s.team_completed_series > 0 ? s.team_rating : 0f, s.team_standing, s.team_standing_population)
                + (s.team_completed_series > 0 ? "  <color=#888>" + I18n.TrF("{0} series played", s.team_completed_series) + "</color>" : ""),
                ST_SMALL);
            y += 24f;
            AddLabel(rp, x, y, w, 22,
                ModeLine("#FFD94D", "1v1", s.rating, s.standing, s.standing_population)
                + "   " + ModeLine("#C48CFF", "FFA", s.ffa_games > 0 ? s.ffa_rating : 0f, s.ffa_standing, s.ffa_standing_population),
                ST_SMALL);
            y += 24f;
            // Top-3 favorite cards, single line (compressed panels drop the
            // 1v2 line and the 5-card list — brief). R1 f16: ranked /cards
            // first; stats top_cards (ALL-mode, labeled so) as the degrade;
            // both sources carry win_rate as a wire FRACTION (x100 in the
            // chip helper).
            string fav = "";
            int shown = 0;
            int sourceRows = 0;   // R2 f7: valid rows in the source that rendered
            bool ranked = false;
            if (cards != null)
            {
                for (int i = 0; i < cards.Count; i++)
                {
                    var c = cards[i];
                    if (c == null || string.IsNullOrEmpty(c.card_name)) continue;
                    sourceRows++;
                    if (shown >= 3) continue;   // keep counting past the cap
                    fav += (shown > 0 ? "<color=#556270>,</color> " : "") + CompactCardChip(c.card_name, c.win_rate);
                    shown++;
                }
                ranked = shown > 0;
            }
            if (shown == 0 && s.top_card_names != null)
            {
                sourceRows = s.top_card_names.Count;   // fallback source supersedes
                for (int i = 0; i < s.top_card_names.Count && shown < 3; i++)
                {
                    float wr = s.top_card_win_rates != null && i < s.top_card_win_rates.Count ? s.top_card_win_rates[i] : 0f;
                    fav += (shown > 0 ? "<color=#556270>,</color> " : "") + CompactCardChip(s.top_card_names[i], wr);
                    shown++;
                }
            }
            if (fav.Length > 0)
            {
                AddLabel(rp, x, y, w, 22,
                    "<color=#66809A>" + (ranked ? I18n.Tr("Favorite ranked cards") : I18n.Tr("Top cards (all modes)"))
                    + "</color>  " + fav, ST_SMALL);
                y += 24f;
                // R2 f7: capped list says so — on its OWN line (appending to
                // the chip line risks the global Truncate default eating the
                // tail, #292; panel is 202 tall, this ends at y+18 <= 132).
                if (sourceRows > shown)
                    AddLabel(rp, x, y, w, 18,
                        "<color=#8FA3B8>" + I18n.TrF("showing {0} of {1}", shown, sourceRows) + "</color>", ST_SMALL);
            }
        }

        /// <summary>Compact card chip: localized truncated name + win rate.
        /// winRateFraction is the 0..1 wire value (R1 f16: x100 here).</summary>
        private static string CompactCardChip(string cardName, float winRateFraction)
        {
            string disp = cardName ?? "";
            try { disp = CardTextLocalizer.PrettyName(disp, disp); } catch { }
            disp = Trunc(StripTags(disp), 16);
            return disp + " <color=#8FA3B8>" + (winRateFraction * 100f).ToString("F0", INV) + "%</color>";
        }

        private static void BuildCells2v2Game(List<GraphCell> cells, ApiClient.TeamSeriesMatch m,
                                              ApiClient.TeamSeriesSlot[] slots, string[] slotNames, string capBase)
        {
            // Kind-major pages: 4 slots x one kind fill exactly one 2x2 page,
            // so each page reads as "Game N - <metric> for everyone".
            for (int kindPass = 0; kindPass < 5; kindPass++)
            {
                for (int sl = 0; sl < slots.Length; sl++)
                {
                    var slot = slots[sl];
                    if (slot == null || string.IsNullOrEmpty(slot.steam_id)) continue;
                    ApiClient.TeamPlayerTele tele = null;
                    if (m.telemetry_by_player != null) m.telemetry_by_player.TryGetValue(slot.steam_id, out tele);
                    if (tele == null) continue;
                    bool right = sl >= 2;
                    string nm = slotNames[sl];
                    switch (kindPass)
                    {
                        case 0:   // hit pair
                            if (!string.IsNullOrEmpty(tele.hit_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_PAIR, isBlock = false, isOpp = right,
                                    caption = Cap(capBase, I18n.TrF("Hit rate - {0}", nm)),
                                    a = tele.hit_timeline, subject = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 1:   // block pair
                            if (!string.IsNullOrEmpty(tele.block_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_PAIR, isBlock = true, isOpp = right,
                                    caption = Cap(capBase, I18n.TrF("Block rate - {0}", nm)),
                                    a = tele.block_timeline, subject = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 2:   // fps — 2v2 telemetry rides the 3s series grid
                            if (!string.IsNullOrEmpty(tele.fps_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_TELE, kind = 0, myStep = 3f,
                                    caption = Cap(capBase, I18n.Tr("FPS") + " - " + nm),
                                    a = tele.fps_timeline, subject = nm, legA = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 3:   // ping
                            if (!string.IsNullOrEmpty(tele.ping_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_TELE, kind = 1, myStep = 3f,
                                    caption = Cap(capBase, I18n.Tr("Ping") + " - " + nm),
                                    a = tele.ping_timeline, subject = nm, legA = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 4:   // dps (cumulative damage -> per-interval)
                            if (!string.IsNullOrEmpty(tele.damage_dealt_timeline))
                            {
                                float step = NativeUI.DpsStepFor(tele.damage_dealt_timeline, m.duration_seconds, 3f);
                                string dps = NativeUI.CumulativeToDps(tele.damage_dealt_timeline, step);
                                if (dps.Length > 0)
                                    cells.Add(new GraphCell
                                    {
                                        painter = PAINTER_TELE, kind = 5, myStep = step,
                                        caption = Cap(capBase, I18n.Tr("DPS") + " - " + nm),
                                        a = dps, subject = nm, legA = nm, dur = m.duration_seconds,
                                    });
                            }
                            break;
                    }
                }
            }
        }

        // ── FFA composition ─────────────────────────────────────────────

        private static string ComposeFfa(Entry e, FetchBox f, Page rp, List<GraphCell> cells)
        {
            DateTime lo, hi;
            GetWindow(e, out lo, out hi);
            var matches = FfaSessionMatches(e, f, lo, hi);
            var roster = new HashSet<string>(e.rosterIds, StringComparer.Ordinal);

            // Header: roster names, budgeted (a 10-name line cannot hold full
            // names at title size — #237: measure, do not hope).
            AddPanel(rp, 40, 24, 1840, 120);
            AddLabel(rp, 60, 32, 1800, 52,
                JoinNamesBudget(e, 80) + PartialTag(e), ST_TITLE);
            // R1 f10 + R2 f5: a false flag must never assert an exact game
            // total — with rows the count renders as a labeled floor; with
            // none, the game count is omitted (no "0 games" claim).
            AddLabel(rp, 60, 96, 1800, 32,
                "<color=#B9C4D0>" + (f.ffaOk
                    ? I18n.TrF("FFA session - {0} players, {1} games", e.rosterIds.Length, matches.Count)
                    : (matches.Count > 0
                        ? I18n.TrF("FFA session - {0} players, {1} games", e.rosterIds.Length, matches.Count) + " " + PartialInline()
                        : I18n.TrF("FFA session - {0} players", e.rosterIds.Length) + " " + PartialInline()))
                + "</color>", ST_SUB);

            // Per-game placement rows.
            AddPanel(rp, 40, 158, 1116, 872);
            float y = 210f, bottom = 158f + 872f - 12f;
            if (matches.Count == 0)
                AddLabel(rp, 64, y, 1068, 26,
                    "<color=#8FA3B8>" + (f.ffaOk
                        ? I18n.Tr("No games recorded for this session yet.")
                        : I18n.Tr("match data unavailable")) + "</color>", ST_BODY);   // R1 f10
            int total = matches.Count;
            int gamesDrawn = 0;
            for (int i = 0; i < matches.Count && i < MAX_ROWS; i++)
            {
                var m = matches[i];
                int gameNo = total - i;
                float need = 24f + 4f + 18f;   // header + at least one player line
                if (y + need > bottom) break;
                string dt = "";
                try
                {
                    if (!string.IsNullOrEmpty(m.ended_at) && m.ended_at.Length >= 10)
                        dt = "  <color=#999>" + DateFmt.Short(DateTime.Parse(m.ended_at)) + "</color>";
                }
                catch { }
                string durChip = m.duration_seconds > 0
                    ? "  <color=#8FA3B8>" + FmtDur(m.duration_seconds) + "</color>" : "";
                string tag = m.is_ranked ? "" : "  <color=#888>" + I18n.Tr("casual") + "</color>";
                // R3 f5: `total` is the FETCHED match count — a newest-30-of-31
                // snapshot would number these 30..1 instead of 31..2, so the
                // ordinal is only asserted when ffaOk proved the fetch whole.
                int otherPlayers;
                var byPlace = FfaRosterPlayers(m, roster, out otherPlayers);
                string otherSuffix = otherPlayers > 0
                    ? "  " + I18n.TrF("<color=#888>+{0} more</color>", otherPlayers)
                    : "";
                AddLabel(rp, 64, y, 1068, 22,
                    I18n.TrF("Game {0}   {1} players", GameNoArg(f.ffaOk, gameNo), byPlace.Count)
                    + otherSuffix + tag + durChip + dt, ST_BODY);
                y += 26f;
                gamesDrawn++;
                int pDrawn = 0;
                for (int p = 0; p < byPlace.Count; p++)
                {
                    var pl = byPlace[p];
                    if (pl == null) continue;
                    if (y + 18f > bottom) break;
                    // R1 f17: when this is the LAST line that fits and players
                    // remain, spend it on the truncation note instead.
                    if (y + 19f + 19f > bottom && p < byPlace.Count - 1)
                    {
                        AddLabel(rp, 96, y, 1036, 18,
                            "<color=#8FA3B8>" + I18n.TrF("showing {0} of {1}", pDrawn, byPlace.Count) + "</color>",
                            ST_SMALL);
                        y += 19f;
                        break;
                    }
                    AddLabel(rp, 96, y, 1036, 18, FfaPlayerLine(pl), ST_SMALL);
                    y += 19f;
                    pDrawn++;
                }
                y += 8f;
            }
            // R1 f17: section header added AFTER the loop so a capped games
            // list says so (label list order does not affect layout).
            string secHead;
            if (matches.Count == 0)
                secHead = f.ffaOk ? I18n.TrF("Session games ({0})", matches.Count)
                                  : I18n.Tr("Session games") + " " + PartialInline();   // R1 f10
            else if (gamesDrawn < matches.Count)
                secHead = I18n.Tr("Session games") + " - " + I18n.TrF("showing {0} of {1}", gamesDrawn, matches.Count);
            else
                secHead = I18n.TrF("Session games ({0})", matches.Count);
            // R2 f5: rows off a false flag are a floor, not a total.
            if (!f.ffaOk && matches.Count > 0) secHead += " " + PartialInline();
            AddLabel(rp, 64, 170, 1068, 28, secHead, ST_SECTION);

            // Per-player FFA mini panels: 2-column grid on the right. These
            // are career figures from PlayerStatsData, not session aggregates;
            // a roster member absent from one included game therefore enters
            // no client-side sum or divisor (bug 254 / #257).
            for (int i = 0; i < e.rosterIds.Length && i < 10; i++)
            {
                float px = (i % 2 == 0) ? 1172f : 1534f;
                float py = 158f + (i / 2) * 176f;
                // -1f: suppress the header elo chip — the FFA line inside the
                // panel carries the mode-correct rating.
                ComposeFfaMiniPanel(rp, new Rect(px, py, 346f, 168f),
                    f.stats != null && i < f.stats.Length ? f.stats[i] : null, NameAt(e, i), -1f);
            }

            // Graph cells: per game newest first, kind-major over ticket-roster
            // player rows carried by that game (hit, block, fps, ping, dps).
            // Outsider rows are summarized on the game line, not given graph
            // panels. See FfaRosterPlayers for the wire's absent-row limit.
            for (int i = 0; i < matches.Count; i++)
            {
                var m = matches[i];
                int gameNo = total - i;
                int ignoredOthers;
                var byPlace = FfaRosterPlayers(m, roster, out ignoredOthers);
                // R3 f5: same unknown-ordinal rule on the graph captions.
                BuildCellsFfaGame(cells, m, byPlace, I18n.TrF("Game {0}", GameNoArg(f.ffaOk, gameNo)));
            }

            // R3 f5: the graph pages are shown independently of this page, so
            // the FFA fetch flag has to ride the title they DO show.
            return JoinNamesBudget(e, 60) + PartialTag(e) + FetchPartialSuffix(e, f.ffaOk);
        }

        private static string FfaPlayerLine(ApiClient.FfaRecentPlayer pl)
        {
            string nm = Trunc(StripTags(pl.display_name ?? "?"), 16);
            string nmCol = pl.placement == 1 ? "#00FF00" : "#B9C4D0";
            string dmg = pl.damage_dealt >= 0 ? pl.damage_dealt.ToString(INV) : "-";
            string line = "<color=#C48CFF>#" + pl.placement.ToString(INV) + "</color> "
                + "<color=" + nmCol + ">" + nm + "</color>  <color=#8FA3B8>"
                + I18n.TrF("{0} kills   {1} dmg", pl.kills, dmg) + "</color>";
            if (pl.gold_gained > 0) line += " <color=#FFD94D>+" + pl.gold_gained.ToString(INV) + "g</color>";
            if (pl.xp_gained > 0) line += " <color=#88CCFF>+" + pl.xp_gained.ToString(INV) + "xp</color>";
            if (pl.has_rating_change && Mathf.Abs(pl.rating_change) > 0.01f)
            {
                string col = pl.rating_change > 0f ? "#00FF00" : "#FF6666";
                line += " <color=" + col + ">"
                     + I18n.TrF("{0} elo", (pl.rating_change > 0f ? "+" : "") + pl.rating_change.ToString("F0", INV))
                     + "</color>";
            }
            return line;
        }

        private static void ComposeFfaMiniPanel(Page rp, Rect r, ApiClient.PlayerStatsData s,
                                                string fallbackName, float entryRating)
        {
            AddPanel(rp, r.x, r.y, r.width, r.height);
            float x = r.x + 18f, w = r.width - 36f, y = r.y + 10f;
            AddLabel(rp, x, y, w, 24, StyledHeaderName(s, fallbackName, 0f), ST_SECTION);
            y += 30f;
            if (s == null)
            {
                AddLabel(rp, x, y, w, 20, "<color=#8FA3B8>" + I18n.Tr("no data") + "</color>", ST_SMALL);
                return;
            }
            string peak = s.ffa_peak_rating > 0f
                ? "  <color=#888>" + I18n.TrF("Peak {0}", s.ffa_peak_rating.ToString("F0", INV)) + "</color>" : "";
            AddLabel(rp, x, y, w, 20,
                ModeLine("#C48CFF", "FFA", s.ffa_games > 0 ? s.ffa_rating : 0f, s.ffa_standing, s.ffa_standing_population) + peak,
                ST_SMALL);
            y += 22f;
            if (s.ffa_games > 0)
            {
                float top3 = 100f * s.ffa_top3 / s.ffa_games;
                AddLabel(rp, x, y, w, 20,
                    "<color=#8FA3B8>" + I18n.TrF("{0} games  {1} wins  Top3 {2}%  Avg place {3}",
                        s.ffa_games, s.ffa_wins, top3.ToString("F0", INV), s.ffa_avg_placement.ToString("F1", INV)) + "</color>",
                    ST_SMALL);
                y += 22f;
            }
            if (!string.IsNullOrEmpty(s.rank_name))
                AddLabel(rp, x, y, w, 20,
                    I18n.TrF("Rank: <b><color={0}>{1}</color></b>", SafeHex(s.rank_color), SanitizeStyled(s.rank_name)),
                    ST_SMALL);
        }

        private static void BuildCellsFfaGame(List<GraphCell> cells, ApiClient.FfaRecentMatch m,
                                              List<ApiClient.FfaRecentPlayer> byPlace, string capBase)
        {
            for (int kindPass = 0; kindPass < 5; kindPass++)
            {
                for (int p = 0; p < byPlace.Count; p++)
                {
                    var pl = byPlace[p];
                    if (pl == null) continue;
                    string nm = Trunc(StripTags(pl.display_name ?? "?"), 14);
                    switch (kindPass)
                    {
                        case 0:
                            if (!string.IsNullOrEmpty(pl.hit_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_PAIR, isBlock = false,
                                    caption = Cap(capBase, I18n.TrF("Hit rate - {0}", nm)),
                                    a = pl.hit_timeline, pTimeline = m.timeline, subject = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 1:
                            if (!string.IsNullOrEmpty(pl.block_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_PAIR, isBlock = true,
                                    caption = Cap(capBase, I18n.TrF("Block rate - {0}", nm)),
                                    a = pl.block_timeline, pTimeline = m.timeline, subject = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 2:
                            if (!string.IsNullOrEmpty(pl.fps_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_TELE, kind = 0, myStep = 0f,
                                    caption = Cap(capBase, I18n.Tr("FPS") + " - " + nm),
                                    a = pl.fps_timeline, pTimeline = m.timeline, subject = nm, legA = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 3:
                            if (!string.IsNullOrEmpty(pl.ping_timeline))
                                cells.Add(new GraphCell
                                {
                                    painter = PAINTER_TELE, kind = 1, myStep = 0f,
                                    caption = Cap(capBase, I18n.Tr("Ping") + " - " + nm),
                                    a = pl.ping_timeline, pTimeline = m.timeline, subject = nm, legA = nm, dur = m.duration_seconds,
                                });
                            break;
                        case 4:
                            if (!string.IsNullOrEmpty(pl.damage_timeline))
                            {
                                // FFA shares one 3s telemetry grid for the whole
                                // match (NativeUI.DPS_STEP_FFA).
                                float step = NativeUI.DpsStepFor(pl.damage_timeline, m.duration_seconds, NativeUI.DPS_STEP_FFA);
                                string dps = NativeUI.CumulativeToDps(pl.damage_timeline, step);
                                if (dps.Length > 0)
                                    cells.Add(new GraphCell
                                    {
                                        painter = PAINTER_TELE, kind = 5, myStep = step,
                                        caption = Cap(capBase, I18n.Tr("DPS") + " - " + nm),
                                        a = dps, pTimeline = m.timeline, subject = nm, legA = nm, dur = m.duration_seconds,
                                    });
                            }
                            break;
                    }
                }
            }
        }

        /// <summary>R1 f9/f15 + bug 254: session games come from the
        /// report-private player-scoped FFA history (ranked + casual, as the
        /// tab shows). A game qualifies when its derived start is inside the
        /// ticket window and it carries at least max(2, floor(roster/2)) unique
        /// ticket-roster player rows. The two-player floor rejects
        /// single-anchor history noise; the half-roster threshold preserves a
        /// fluid sitting across legitimate joins/leaves. Without a shared
        /// lobby/session id, a concurrent lobby meeting that same predicate is
        /// indistinguishable and can still merge into this report.
        /// R1 f9 tombstone: the CachedFfaRecent/CachedFfaRecentCasual
        /// reference-sniffing path is deleted (#310).</summary>
        private static List<ApiClient.FfaRecentMatch> FfaSessionMatches(Entry e, FetchBox f, DateTime lo, DateTime hi)
        {
            var res = new List<ApiClient.FfaRecentMatch>();
            var src = f.ffaHistory;
            if (src == null) return res;
            var roster = new HashSet<string>(e.rosterIds, StringComparer.Ordinal);
            var seen = new HashSet<string>(StringComparer.Ordinal);
            var keyed = new List<KeyValuePair<DateTime, ApiClient.FfaRecentMatch>>();
            for (int i = 0; i < src.Count; i++)
            {
                var m = src[i];
                if (m == null || m.players == null) continue;
                if (string.IsNullOrEmpty(m.match_id) || !seen.Add(m.match_id)) continue;
                DateTime end;
                if (!TryParseUtc(m.ended_at, out end) || end > hi) continue;
                // Bug 254 follow-up: the wire now carries the stored real
                // started_at — prefer it. Older servers omit it; derive
                // ended_at - duration_seconds instead, and fail closed when
                // neither is available: end alone cannot prove condition (a).
                DateTime start;
                if (!TryParseUtc(m.started_at, out start))
                {
                    if (m.duration_seconds <= 0) continue;
                    try
                    {
                        start = end.AddSeconds(-(double)m.duration_seconds);
                    }
                    catch { continue; }
                }
                if (start < lo) continue;
                if (!FfaRosterOverlapEnough(m, roster)) continue;
                keyed.Add(new KeyValuePair<DateTime, ApiClient.FfaRecentMatch>(end, m));
            }
            keyed.Sort((a, b) => b.Key.CompareTo(a.Key));   // newest first
            for (int i = 0; i < keyed.Count; i++) res.Add(keyed[i].Value);
            return res;
        }

        /// <summary>Bug 254's fluid-roster predicate over the rich-history
        /// player rows. Count unique ids so malformed duplicates cannot
        /// manufacture the required overlap. The endpoint currently omits the
        /// persisted `absent` bit, so a carried frozen-roster ghost is not
        /// distinguishable here from a real participant; the server wire must
        /// expose that bit before overlap can mean actual participation.</summary>
        private static bool FfaRosterOverlapEnough(ApiClient.FfaRecentMatch m, HashSet<string> roster)
        {
            if (m == null || m.players == null || roster == null) return false;
            int required = Math.Max(2, roster.Count / 2);
            var shared = new HashSet<string>(StringComparer.Ordinal);
            for (int p = 0; p < m.players.Count; p++)
            {
                var pl = m.players[p];
                if (pl == null || string.IsNullOrEmpty(pl.steam_id)) continue;
                // Bug 254 follow-up: the wire now carries the authoritative
                // frozen-roster-ghost bit — a carried absent row was NOT in
                // this game and must not manufacture overlap (#227). Older
                // servers omit the key; it parses false = today's behavior.
                if (pl.absent) continue;
                if (roster.Contains(pl.steam_id)) shared.Add(pl.steam_id);
            }
            return shared.Count >= required;
        }

        /// <summary>Unique rich-history rows from the ticket roster, sorted by
        /// placement for rows/graphs. Rows outside the ticket remain only as a
        /// counted suffix. The endpoint does not yet expose its authoritative
        /// `absent` flag, so this helper deliberately does NOT guess from
        /// left_early or zero tallies (#227): an absent frozen-roster ghost can
        /// still appear until the wire carries that bit.</summary>
        private static List<ApiClient.FfaRecentPlayer> FfaRosterPlayers(
            ApiClient.FfaRecentMatch m, HashSet<string> roster, out int otherPlayers)
        {
            var res = new List<ApiClient.FfaRecentPlayer>();
            otherPlayers = 0;
            int absentRows = 0;
            if (m == null || m.players == null || roster == null) return res;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (int p = 0; p < m.players.Count; p++)
            {
                var pl = m.players[p];
                if (pl == null) continue;
                // Bug 254 follow-up: absent = frozen-roster ghost, carried
                // for report continuity but NOT in this game (#227). Never a
                // row, never an "other" — and remembered, because
                // player_count INCLUDES ghosts (verified in prod: a 7-row
                // game with 3 ghosts stores player_count=7).
                if (pl.absent) { absentRows++; continue; }
                string sid = pl.steam_id ?? "";
                if (sid.Length == 0)
                {
                    otherPlayers++;
                    continue;
                }
                if (!seen.Add(sid)) continue;
                if (roster.Contains(sid)) res.Add(pl);
                else otherPlayers++;
            }
            // player_count is the server's declared total INCLUDING ghosts.
            // If a malformed or legacy row omitted a player object, keep that
            // participant in the summary rather than pretending the smaller
            // parsed list is whole — but never resurrect the ghosts we just
            // filtered.
            int declaredOthers = m.player_count - absentRows - res.Count;
            if (declaredOthers > otherPlayers) otherPlayers = declaredOthers;
            res.Sort((a, b) => a.placement.CompareTo(b.placement));
            return res;
        }

        private static string JoinNamesBudget(Entry e, int budgetChars)
        {
            string s = "";
            int used = 0;
            for (int i = 0; i < e.names.Length; i++)
            {
                string nm = Trunc(StripTags(e.names[i] ?? "?"), 14);
                if (used + nm.Length + 3 > budgetChars)
                {
                    s += " <color=#888>+" + (e.names.Length - i).ToString(INV) + "</color>";
                    break;
                }
                s += (i > 0 ? " <color=#556270>/</color> " : "") + nm;
                used += nm.Length + 3;
            }
            return s;
        }

        private static ApiClient.PlayerStatsData StatsForSid(Entry e, FetchBox f, string sid)
        {
            if (f.stats == null) return null;
            for (int i = 0; i < e.rosterIds.Length && i < f.stats.Length; i++)
                if (string.Equals(e.rosterIds[i], sid, StringComparison.Ordinal)) return f.stats[i];
            return null;
        }

        private static List<ApiClient.CardStatData> CardsForSid(Entry e, FetchBox f, string sid)
        {
            if (f.cards == null) return null;
            for (int i = 0; i < e.rosterIds.Length && i < f.cards.Length; i++)
                if (string.Equals(e.rosterIds[i], sid, StringComparison.Ordinal)) return f.cards[i];
            return null;
        }

        private static float RatingForSid(Entry e, string sid)
        {
            if (e.ratings == null) return 0f;
            for (int i = 0; i < e.rosterIds.Length && i < e.ratings.Length; i++)
                if (string.Equals(e.rosterIds[i], sid, StringComparison.Ordinal)) return e.ratings[i];
            return 0f;
        }

        // ── renderer ─────────────────────────────────────────────────────

        private static bool _stylesReady;
        private static GUIStyle _stTitle, _stSub, _stSection, _stBody, _stSmall, _stCaption, _stRight;

        /// <summary>Full-screen IMGUI over the main menu. Wired by the
        /// integrator into CompetitiveUI.DrawUI EARLY. The whole body is
        /// Repaint-only (#162 — no interactive controls live here) and draws
        /// nothing when hidden, so the steady-state cost while idle is one
        /// phase check. A throw in here must never starve the overlays drawn
        /// after us in DrawUI (#255), hence the blanket guard.</summary>
        public static void Draw()
        {
            if (_phase != PHASE_PLAY || _pages == null || _pages.Count == 0) return;
            Matrix4x4 savedMatrix = GUI.matrix;
            Color savedColor = GUI.color;
            try
            {
                if (NativeUI.IsOpen) return;                       // D1 f13
                var ev = Event.current;
                if (ev == null || ev.type != EventType.Repaint) return;
                // Engine clock stalled (director Step dead / disabled without
                // an Interrupt): stop painting rather than freeze a stale
                // overlay over the menu forever (#255 family).
                if (Time.realtimeSinceStartup - _lastTickRt > TICK_STALL_HIDE_SECONDS) return;
                EnsureStyles();

                int pi = Mathf.Clamp(_pageIdx, 0, _pages.Count - 1);
                var page = _pages[pi];

                // 1920x1080-referenced scaling: min-axis fit + centering, so a
                // non-16:9 window letterboxes instead of overflowing (#199).
                float k = Mathf.Min(Screen.width / 1920f, Screen.height / 1080f);
                if (k <= 0f) k = 1f;
                float ox = (Screen.width - 1920f * k) * 0.5f;
                float oy = (Screen.height - 1080f * k) * 0.5f;
                GUI.matrix = Matrix4x4.TRS(new Vector3(ox, oy, 0f), Quaternion.identity, new Vector3(k, k, 1f));

                // Translucent dark panels over the ROUNDS-blue menu — never a
                // full-screen black (brief).
                for (int i = 0; i < page.panels.Count; i++)
                {
                    GUI.color = new Color(0f, 0f, 0f, page.panels[i].a);
                    GUI.DrawTexture(page.panels[i].r, Texture2D.whiteTexture);
                }
                GUI.color = Color.white;

                for (int i = 0; i < page.labels.Count; i++)
                {
                    var l = page.labels[i];
                    GUI.Label(l.r, l.text, StyleFor(l.style));
                }

                for (int i = 0; i < page.graphs.Count; i++)
                {
                    var g = page.graphs[i];
                    try
                    {
                        switch (g.painter)
                        {
                            case PAINTER_TELE:
                                CompetitiveUI.PaintTeleGraph(g.box, g.a, g.b, g.kind, g.myStep,
                                    g.pTimes, g.pTimeline, g.subject, g.dur, g.legA, g.legB);
                                break;
                            case PAINTER_PAIR:
                                CompetitiveUI.PaintPairGraph(g.box, g.a, g.isBlock,
                                    g.pTimes, g.pTimeline, g.subject, g.dur, g.isOpp);
                                break;
                            case PAINTER_SCORE:
                                CompetitiveUI.PaintScoreGraph(g.box, g.pTimeline, g.won, g.subject);
                                break;
                        }
                    }
                    catch { /* one bad series must not take the page down */ }
                    GUI.color = Color.white;
                }

                // Page dots (bottom center; watermark label is pre-composed).
                int n = _pages.Count;
                if (n > 1)
                {
                    float x0 = 960f - (n * 22f - 12f) * 0.5f;
                    for (int i = 0; i < n; i++)
                    {
                        GUI.color = i == pi ? new Color(1f, 1f, 1f, 0.95f) : new Color(1f, 1f, 1f, 0.30f);
                        GUI.DrawTexture(new Rect(x0 + i * 22f, 1048f, 10f, 10f), Texture2D.whiteTexture);
                    }
                }
            }
            catch { }
            finally
            {
                GUI.matrix = savedMatrix;
                GUI.color = savedColor;
            }
        }

        private static GUIStyle StyleFor(int id)
        {
            switch (id)
            {
                case ST_TITLE: return _stTitle;
                case ST_SUB: return _stSub;
                case ST_SECTION: return _stSection;
                case ST_SMALL: return _stSmall;
                case ST_CAPTION: return _stCaption;
                case ST_RIGHT: return _stRight;
                default: return _stBody;
            }
        }

        /// <summary>Styles are built lazily INSIDE OnGUI (GUI.skin is only
        /// valid there — the #237 EnsureBugStyles pattern). Overflow clipping:
        /// length is controlled at compose time by character budgets, and a
        /// tight box must bleed into its own padding rather than silently drop
        /// glyphs (#292/#297).</summary>
        private static void EnsureStyles()
        {
            if (_stylesReady) return;
            _stTitle = Mk(34, TextAnchor.MiddleCenter, FontStyle.Bold);
            _stSub = Mk(20, TextAnchor.MiddleCenter, FontStyle.Normal);
            _stSection = Mk(20, TextAnchor.UpperLeft, FontStyle.Bold);
            _stBody = Mk(17, TextAnchor.UpperLeft, FontStyle.Normal);
            _stSmall = Mk(14, TextAnchor.UpperLeft, FontStyle.Normal);
            _stCaption = Mk(16, TextAnchor.UpperLeft, FontStyle.Bold);
            _stRight = Mk(14, TextAnchor.UpperRight, FontStyle.Normal);
            _stylesReady = true;
        }

        private static GUIStyle Mk(int size, TextAnchor anchor, FontStyle fs)
        {
            var st = new GUIStyle(GUI.skin.label)
            {
                fontSize = size,
                alignment = anchor,
                fontStyle = fs,
                richText = true,
                wordWrap = false,
                clipping = TextClipping.Overflow,
            };
            st.normal.textColor = Color.white;
            return st;
        }

        // ── shared small helpers (replicas commented with their sources) ──

        /// <summary>Server-UTC stamp parse — the same style ApiClient uses for
        /// server timestamps (InvariantCulture, AssumeUniversal +
        /// AdjustToUniversal; see ApiClient's ISO parses). D1 f9: all window
        /// math runs on these values, never on Unity clocks.</summary>
        private static bool TryParseUtc(string iso, out DateTime dt)
        {
            dt = default(DateTime);
            if (string.IsNullOrEmpty(iso)) return false;
            return DateTime.TryParse(iso, INV,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out dt);
        }

        /// <summary>incarnation (truncated) + FNV-1a of the sorted roster ids;
        /// always &lt;=32 chars (D1 f19's bounded opaque report id).</summary>
        private static string MakeReportId(string incarnation, string[] roster)
        {
            var ids = new List<string>(roster);
            ids.Sort(StringComparer.Ordinal);
            uint h = 2166136261u;
            for (int i = 0; i < ids.Count; i++)
            {
                string s = ids[i] ?? "";
                for (int j = 0; j < s.Length; j++) { h ^= s[j]; h *= 16777619u; }
                h ^= '|'; h *= 16777619u;
            }
            string inc = incarnation ?? "";
            if (inc.Length > 23) inc = inc.Substring(0, 23);
            return inc + "-" + h.ToString("x8", INV);
        }

        private static string[] NormalizeNames(string[] names, string[] roster)
        {
            var res = new string[roster.Length];
            for (int i = 0; i < roster.Length; i++)
            {
                string nm = names != null && i < names.Length ? names[i] : null;
                if (string.IsNullOrEmpty(nm))
                {
                    string id = roster[i] ?? "";
                    nm = id.Length > 4 ? "#" + id.Substring(id.Length - 4) : id;
                }
                res[i] = nm;
            }
            return res;
        }

        private static string NameAt(Entry e, int i)
            => e.names != null && i < e.names.Length ? e.names[i] : "?";

        private static float RatingAt(Entry e, int i)
            => e.ratings != null && i < e.ratings.Length ? e.ratings[i] : 0f;

        private static string PartialTag(Entry e)
            => e.partial ? "  <color=#FFD94D>" + I18n.Tr("(partial)") + "</color>" : "";

        /// <summary>The same "(partial)" label, inline — R1 f10's marker for a
        /// section whose data fetch failed after retries, and R1 f12's marker
        /// on the flat 2v2 fallback (distinct from Entry.partial, the 25-min
        /// endpoint-outage playback mode; the shared word is deliberate — in
        /// every case it means "this screen is not the whole story").</summary>
        private static string PartialInline()
            => "<color=#FFD94D>" + I18n.Tr("(partial)") + "</color>";

        /// <summary>R3 f5: the completeness suffix for a GRAPH-PAGE title.
        /// The graph pages are displayed independently of the report page, so
        /// they must carry the MODE-SPECIFIC fetch flag (historyOk / teamOk /
        /// ffaOk) and not just Entry.partial — a 31-game FFA sitting that
        /// returned its newest 30 with ok=false reached the graph pages with no
        /// marker OF ITS OWN (only Entry.partial could put one there, and that
        /// is the unrelated 25-min endpoint-outage window). Both conditions can
        /// hold at once, so this yields "" when PartialTag already spoke — the
        /// label is emitted exactly once either way. Call it ONLY where
        /// PartialTag is also appended.</summary>
        private static string FetchPartialSuffix(Entry e, bool modeOk)
            => (modeOk || e.partial) ? "" : "  " + PartialInline();

        /// <summary>R3 f5: the ordinal ARGUMENT for a "Game {0}..." label.
        /// A game number reconstructed from the FETCHED list count is only
        /// true when that fetch PROVED complete — the newest-30-of-31 FFA
        /// snapshot above numbers its games 30..1 when they are really 31..2,
        /// i.e. every caption on the page states a fact the data cannot
        /// support. When the mode flag is false the absolute ordinal is simply
        /// UNKNOWN, so the label renders the SAME existing localized key with
        /// a literal "?" rather than inventing a number. Reusing the key (as
        /// opposed to minting an "unknown game" one) keeps every locale
        /// covered and leaves the catalogue key set untouched (#289/#357).
        /// 2v2 does NOT use this: its ordinal is the match's index inside the
        /// server's own series row, which is complete per series regardless of
        /// how many series the pagination reached.</summary>
        private static object GameNoArg(bool complete, int gameNo)
            => complete ? (object)gameNo : (object)"?";

        private static string PlainName(ApiClient.PlayerStatsData s, string fallback)
        {
            string nm = s != null && !string.IsNullOrEmpty(s.display_name) ? s.display_name : fallback;
            return Trunc(StripTags(nm ?? "?"), 16);
        }

        /// <summary>Styled header name: NametagStyler.Wrap over the active
        /// nametag skus, sanitized for IMGUI (only b/i/color survive — size
        /// tags would blow a fixed-height header), + [Title] span + elo.
        /// Falls back to the plain truncated name when styling collapses or
        /// the plain text is too long to style safely (a truncation cut inside
        /// a rich-text tag is worse than no styling).</summary>
        private static string StyledHeaderName(ApiClient.PlayerStatsData s, string fallbackName, float entryRating)
        {
            string display = s != null && !string.IsNullOrEmpty(s.display_name) ? s.display_name : (fallbackName ?? "?");
            string plain = StripTags(display);
            string styled = "";
            try { styled = SanitizeStyled(NametagStyler.Wrap(display, s != null ? s.active_nametag_skus : null)); }
            catch { }
            if (string.IsNullOrEmpty(styled) || plain.Length > 24)
                styled = Trunc(plain, 24);
            string title = s != null ? TitleSpan(s.active_title, s.active_title_color) : "";
            // entryRating < 0 = SUPPRESS the elo chip (FFA mini panels: the
            // 1v1 rating would be the wrong mode's number beside an FFA line).
            float rating = entryRating > 0f ? entryRating
                : (entryRating < 0f ? 0f : (s != null ? s.rating : 0f));
            string elo = rating > 0f ? " <color=#8FA3B8>" + rating.ToString("F0", INV) + "</color>" : "";
            return styled + title + elo;
        }

        /// <summary>Replica of SpectatorHud.TitleSpan (private there): the one
        /// title shape every surface in the mod uses — bold bracketed span in
        /// the title's own validated colour. Integrator may unify.</summary>
        private static string TitleSpan(string title, string hex)
        {
            if (string.IsNullOrEmpty(title)) return "";
            string safe = SanitizeStyled(title);
            if (safe.Length == 0) return "";
            return " <b><color=" + SafeHex(hex) + ">[" + safe + "]</color></b>";
        }

        // Replica of SpectatorHud.SanitizeStyled (private there; integrator
        // may unify): IMGUI renders <b>/<i>/<color> but NOT <u>/<size> etc, so
        // only those survive — and an UNBALANCED survivor (a crafted color tag
        // with no closer) strips the string to plain, because it would bleed
        // into every element after it in the same label (#100/#156 — names are
        // hostile input).
        private static readonly System.Text.RegularExpressions.Regex _tagStrip =
            new System.Text.RegularExpressions.Regex(
                @"<(?!/?(?:b|i)>)(?!/?color\b)[^>]*>",
                System.Text.RegularExpressions.RegexOptions.Compiled);
        private static readonly System.Text.RegularExpressions.Regex _allTagStrip =
            new System.Text.RegularExpressions.Regex("<[^>]*>",
                System.Text.RegularExpressions.RegexOptions.Compiled);

        private static string SanitizeStyled(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            try
            {
                var kept = _tagStrip.Replace(s, "");
                int opens = 0, closes = 0, bOpens = 0, bCloses = 0, iOpens = 0, iCloses = 0;
                foreach (System.Text.RegularExpressions.Match m in _allTagStrip.Matches(kept))
                {
                    string t = m.Value;
                    if (t.StartsWith("<color", StringComparison.OrdinalIgnoreCase)) opens++;
                    else if (t.StartsWith("</color", StringComparison.OrdinalIgnoreCase)) closes++;
                    else if (t == "<b>") bOpens++;
                    else if (t == "</b>") bCloses++;
                    else if (t == "<i>") iOpens++;
                    else if (t == "</i>") iCloses++;
                }
                if (opens != closes || bOpens != bCloses || iOpens != iCloses)
                    return _allTagStrip.Replace(kept, "");
                return kept;
            }
            catch { return _allTagStrip.Replace(s, ""); }
        }

        private static string StripTags(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            try { return _allTagStrip.Replace(s, "").Trim(); }
            catch { return s; }
        }

        /// <summary>Replica of SpectatorHud.SafeHex (private there): #RGB /
        /// #RRGGBB / #RRGGBBAA only — an unvalidated value inside a color tag
        /// is a rich-text injection into a label that also renders names.</summary>
        private static string SafeHex(string hex)
        {
            const string FALLBACK = "#CCCCCC";
            if (string.IsNullOrEmpty(hex) || hex[0] != '#') return FALLBACK;
            int n = hex.Length - 1;
            if (n != 3 && n != 6 && n != 8) return FALLBACK;
            for (int i = 1; i < hex.Length; i++)
            {
                char c = hex[i];
                bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
                if (!ok) return FALLBACK;
            }
            return hex;
        }

        private static string Trunc(string s, int n)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Length <= n ? s : s.Substring(0, Math.Max(1, n - 2)) + "..";
        }

        /// <summary>Replica of NativeUI.FmtHalfScore (private there — source
        /// of truth): each point is half a round ("2.5-1"), and pts >= 2 is
        /// end-of-game residue that is already counted in rounds.</summary>
        private static string FmtHalfScore(int rounds, int pts)
        {
            if (pts >= 2) pts = 0;
            return pts > 0 ? (rounds + pts * 0.5f).ToString("0.#", INV) : rounds.ToString(INV);
        }

        /// <summary>Replica of NativeUI.FormatCardLine (private there — source
        /// of truth): comma list → 2-letter bracket chips ([MA][EM]...), the
        /// same glyphs vanilla's corner indicator teaches players.</summary>
        private static string FormatCardLine(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return "";
            var sb = new System.Text.StringBuilder();
            foreach (var part in raw.Split(','))
            {
                string name = part.Trim();
                if (string.IsNullOrEmpty(name)) continue;
                int lt = name.IndexOf('>');
                if (lt >= 0 && lt < name.Length - 1) name = name.Substring(lt + 1);
                int gt = name.IndexOf('<');
                if (gt > 0) name = name.Substring(0, gt);
                name = name.Trim();
                if (name.Length == 0) continue;
                string ab = name.Length >= 2 ? name.Substring(0, 2).ToUpperInvariant()
                                             : name.ToUpperInvariant();
                sb.Append('[').Append(ab).Append("] ");
            }
            return sb.ToString().TrimEnd();
        }

        private static string FmtDur(int seconds)
            => seconds > 0 ? (seconds / 60).ToString(INV) + ":" + (seconds % 60).ToString("00", INV) : "";

        /// <summary>Did the SUBJECT fighter's client report this 1v1 match?
        /// Replica of NativeUI.ViewerWasReporter (private and viewer-bound
        /// there) with the subject parameterized, mirroring the
        /// GameStateWatcher election: it only runs when the opponent ALSO had
        /// the mod, and it compares PARSED LONGS — lower id reports, ties to
        /// the subject. Picks the DPS sample grid: reporter = 5s own-seat
        /// stream, peer = ~3s cr_gstats heartbeat.</summary>
        private static bool SubjectWasReporter(string subjectSteamId, ApiClient.MatchHistoryEntry m)
        {
            if (m == null) return true;
            bool oppHadMod = m.opponent_fps_avg > 0 || m.opp_active_seconds > 0f
                             || m.opp_bullets_fired > 0 || m.opp_blocks_activated > 0
                             || m.opp_damage_dealt >= 0
                             || !string.IsNullOrEmpty(m.opp_damage_timeline);
            if (!oppHadMod) return true;
            long mine = 0, theirs = 0;
            long.TryParse(subjectSteamId, out mine);
            long.TryParse(m.opponent_steam_id, out theirs);
            if (mine <= 0 || theirs <= 0) return true;
            return mine <= theirs;
        }
    }
}
