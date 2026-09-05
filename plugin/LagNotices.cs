using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using BepInEx.Configuration;

namespace CompetitiveRounds
{
    /// <summary>
    /// Release B §4 (bug 332): opt-in in-game lag notices, config
    /// [Network] LagNotices, default OFF.
    ///
    /// Four states, each decided ONLY from CLOSED 1 s windows of
    /// NetworkSeatTelemetry: OnWindowClosed runs from CloseWindow (1 Hz while
    /// a fighter game is open) and reads the last five closed windows, never
    /// the partial one and never the forced game-end window
    /// (WindowFeedsEvaluator). Every input is a measurement taken on THIS
    /// seat — its own frame wall gaps, its own Photon ping, the DELIVERY
    /// EXCESS of the opponent's Player-stream batches as received here
    /// (arrival gap minus the sender-stamped gap; design-review r3 M6) —
    /// except PeerRtt, the opponent's self-reported ping (cr_gstats field
    /// 12, bounded 1..3000, fresh within 10 s), which is labelled "reports"
    /// wherever it is shown.
    ///
    /// The evaluator (Step / EnterPredicate / WindowClean / EntryValue) is
    /// PURE: it reads no statics, only the window array, the slot and the
    /// clock it is handed — so the [Network] LagNoticesSelfTest run at
    /// startup exercises the production predicates over canned sequences
    /// (r3 L6). The production wrapper (OnWindowClosed) is the only reader of
    /// NetworkSeatTelemetry; it builds the HUD lines, and ResetAll (game
    /// start/end, seat ineligible, setting turned off) clears them.
    ///
    /// Render/log only: nothing is persisted, sent, or read by any match,
    /// report or rating path. Plain-1v1 fighter seats only; spectator seats
    /// and the broadcast identity never evaluate or draw (§9 Q3).
    ///
    /// A "[LAG-NOTICE] state=" line is written in exactly two places: for a
    /// non-None Edge from Step (returned only by a branch that assigned a new
    /// phase) and by ResetAll for a state that was Shown (its exit) — the
    /// line cannot appear without a transition (#342). The self-test's lines
    /// carry "selftest" in place of "state=", so a grep for state edges never
    /// counts them.
    /// </summary>
    internal static class LagNotices
    {
        internal const int MAX_LINES = 4;
        internal const int LOOKBACK = 5;

        // §4.2 enter thresholds and hysteresis.
        internal const int LOCAL_WORST_MS = 250;          // LOCAL_FRAMES: WorstMs >= 250 in >= 2 of the last 5
        internal const int LOCAL_MIN_WINDOWS = 2;
        internal const int OWN_PING_MS = 150;             // OWN_PING: OwnPing >= 150 in 3 consecutive
        internal const int LATE_EXCESS_MS = 300;          // a late-delivery sample: delivery excess >= 300 ms (r3 M6)
        internal const int OPP_STREAM_MIN_WINDOWS = 2;    // OPP_STREAM: ObsLate300 > 0 AND WorstMs < 100 in >= 2 of the last 5
        internal const int OPP_STREAM_LOCAL_WORST_MAX = 100;
        internal const int PEER_RTT_MS = 150;             // OPP_PING_REPORTED: PeerRtt >= 150 in 3 consecutive (0 = not fresh)
        internal const int CONSECUTIVE = 3;
        internal const int EXIT_CLEAN_WINDOWS = 3;
        internal const double MIN_SHOWN_S = 5.0;
        internal const double REANNOUNCE_COOLDOWN_S = 30.0;

        internal enum State { LOCAL_FRAMES = 0, OWN_PING = 1, OPP_STREAM = 2, OPP_PING_REPORTED = 3 }
        internal const int STATE_COUNT = 4;
        internal static readonly string[] StateNames = { "LOCAL_FRAMES", "OWN_PING", "OPP_STREAM", "OPP_PING_REPORTED" };
        internal enum Phase { Off, Shown, Suppressed }
        internal enum Edge { None, Enter, Suppressed, Exit }

        /// <summary>One state's machine. Times are seconds on whatever
        /// monotonic clock the caller passes to Step (Stopwatch in
        /// production, the step index in the self-test).</summary>
        internal sealed class Slot
        {
            public Phase Phase;
            public double EnterS, ExitS;
            public bool HasExited;
            public int Clean;
            // r3 M7(c): the DISPLAYED number. Set at entry to the value that
            // met the threshold, raised to the newest window's value while
            // shown, never lowered — so a shown line never reads below its
            // own threshold. 0 for OPP_STREAM (no number).
            public int Value;
        }

        internal static Slot[] NewSlots()
        {
            var a = new Slot[STATE_COUNT];
            for (int i = 0; i < a.Length; i++) a[i] = new Slot();
            return a;
        }

        // ── pure evaluator (no statics read) ─────────────────────────────

        /// <summary>The CloseWindow gate (r3 M7(a)): a forced close — the
        /// durationless window OnMatchEnded flushes on game end, room leave
        /// and disconnect — never ticks the evaluator; neither does a closed
        /// game or a spectator seat.</summary>
        internal static bool WindowFeedsEvaluator(bool force, bool gameOpen, bool spectator)
        {
            return !force && gameOpen && !spectator;
        }

        /// <summary>r7 M3/L1: the window-keying PRODUCER's decision, here so
        /// the self-test runs the same code NetworkSeatTelemetry.CloseWindow
        /// does. A closed window carries a key only when it was one eligible
        /// opponent's window for its WHOLE span, not merely at its ends:
        /// • openActor/openId — the eligible key sampled when the window
        ///   opened; openActor 0 means the seat was not an eligible 1v1 then.
        /// • closeActor/closeId — the same, sampled when it closed.
        /// • keyBroken — latched by the telemetry the moment any frame INSIDE
        ///   the window sampled a different key (eligibility lost, the
        ///   opponent replaced, a third fighter present), so an opponent who
        ///   arrives and leaves between two boundaries can no longer leave the
        ///   window keyed.
        /// • lateForeign — a late batch arrived from an actor other than the
        ///   one the window opened under.
        /// False => the window is stored with no key, and AdmitWindows never
        /// lets the evaluator read it.</summary>
        internal static bool WindowKeyed(int openActor, string openId, int closeActor, string closeId,
                                         bool lateForeign, bool keyBroken)
        {
            if (openActor == 0 || keyBroken || lateForeign) return false;
            return closeActor == openActor && string.Equals(openId ?? "", closeId ?? "", StringComparison.Ordinal);
        }

        /// <summary>r3 M6 / r6 M2: the per-sample OPP_STREAM input. Only the
        /// delivery excess counts — never the raw arrival gap. The excess is a
        /// RECEIVER observation: the interval between two batch arrivals,
        /// measured on this seat's clock, minus the interval the peer's
        /// embedded timestamps advanced between the same two batches. The
        /// peer's timestamps are an input this seat cannot verify, so the
        /// excess means "arrival interval beyond what the peer's stamps
        /// account for" and says nothing about WHERE the time went.</summary>
        internal static bool IsLateDelivery(int deliveryExcessMs)
        {
            return deliveryExcessMs >= LATE_EXCESS_MS;
        }

        /// <summary>One state's transition for the window that just closed.
        /// <paramref name="recent"/> is newest first with <paramref name="count"/>
        /// valid entries; <paramref name="nowS"/> is the caller's monotonic
        /// clock in seconds. Mutates only <paramref name="slot"/>.</summary>
        internal static Edge Step(State s, Slot slot, NetworkSeatTelemetry.WindowFacts[] recent, int count, double nowS)
        {
            int n = Math.Min(count, LOOKBACK);
            if (n <= 0) return Edge.None;
            bool enter = EnterPredicate(s, recent, n);
            bool clean = WindowClean(s, recent[0]);
            switch (slot.Phase)
            {
                case Phase.Off:
                    if (!enter) return Edge.None;
                    if (slot.HasExited && nowS - slot.ExitS < REANNOUNCE_COOLDOWN_S)
                    {
                        // Re-entry inside the per-state cooldown: logged, not shown.
                        slot.Phase = Phase.Suppressed;
                        slot.Clean = 0;
                        return Edge.Suppressed;
                    }
                    Show(s, slot, recent, n, nowS);
                    return Edge.Enter;

                case Phase.Shown:
                    // Latch: the number may only rise while shown (r3 M7(c)).
                    slot.Value = Math.Max(slot.Value, WindowValue(s, recent[0]));
                    slot.Clean = clean ? slot.Clean + 1 : 0;
                    if (slot.Clean >= EXIT_CLEAN_WINDOWS && nowS - slot.EnterS >= MIN_SHOWN_S)
                    {
                        slot.Phase = Phase.Off;
                        slot.ExitS = nowS;
                        slot.HasExited = true;
                        return Edge.Exit;
                    }
                    return Edge.None;

                case Phase.Suppressed:
                    slot.Clean = clean ? slot.Clean + 1 : 0;
                    if (slot.Clean >= EXIT_CLEAN_WINDOWS)
                    {
                        // Nothing was shown, so nothing is an exit.
                        slot.Phase = Phase.Off;
                        slot.Clean = 0;
                        return Edge.None;
                    }
                    if (enter && nowS - slot.ExitS >= REANNOUNCE_COOLDOWN_S)
                    {
                        Show(s, slot, recent, n, nowS);
                        return Edge.Enter;
                    }
                    return Edge.None;
            }
            return Edge.None;
        }

        private static void Show(State s, Slot slot, NetworkSeatTelemetry.WindowFacts[] recent, int n, double nowS)
        {
            slot.Phase = Phase.Shown;
            slot.EnterS = nowS;
            slot.Clean = 0;
            slot.Value = EntryValue(s, recent, n);
        }

        /// <summary>§4.2 enter conditions over the closed windows, newest
        /// first. An OwnPing/PeerRtt of 0 means "unavailable / not fresh" and
        /// never satisfies a threshold.</summary>
        internal static bool EnterPredicate(State s, NetworkSeatTelemetry.WindowFacts[] recent, int n)
        {
            switch (s)
            {
                case State.LOCAL_FRAMES:
                {
                    int hits = 0;
                    for (int i = 0; i < n; i++) if (recent[i].WorstMs >= LOCAL_WORST_MS) hits++;
                    return hits >= LOCAL_MIN_WINDOWS;
                }
                case State.OWN_PING:
                    if (n < CONSECUTIVE) return false;
                    for (int i = 0; i < CONSECUTIVE; i++) if (recent[i].OwnPing < OWN_PING_MS) return false;
                    return true;
                case State.OPP_STREAM:
                {
                    // ObsLate300 counts samples whose DELIVERY EXCESS reached
                    // 300 ms (r3 M6; NetworkReplicaDiagnostics computes the
                    // excess). Conservative local-frame exclusion: a window
                    // whose own worst frame reached 100 ms cannot count — a
                    // receiver stall inflates the same excess (NRD's
                    // receiverFrame class).
                    int hits = 0;
                    for (int i = 0; i < n; i++)
                        if (recent[i].ObsLate300 > 0 && recent[i].WorstMs < OPP_STREAM_LOCAL_WORST_MAX) hits++;
                    return hits >= OPP_STREAM_MIN_WINDOWS;
                }
                case State.OPP_PING_REPORTED:
                    if (n < CONSECUTIVE) return false;
                    for (int i = 0; i < CONSECUTIVE; i++) if (recent[i].PeerRtt < PEER_RTT_MS) return false;
                    return true;
            }
            return false;
        }

        /// <summary>A window with none of the state's signal. For OPP_STREAM
        /// that is "no late sample at all" — a late sample in a window with a
        /// local stall is ambiguous and keeps the notice up rather than
        /// clearing it.</summary>
        internal static bool WindowClean(State s, NetworkSeatTelemetry.WindowFacts w)
        {
            switch (s)
            {
                case State.LOCAL_FRAMES: return w.WorstMs < LOCAL_WORST_MS;
                case State.OWN_PING: return w.OwnPing < OWN_PING_MS;
                case State.OPP_STREAM: return w.ObsLate300 == 0;
                case State.OPP_PING_REPORTED: return w.PeerRtt < PEER_RTT_MS;
            }
            return true;
        }

        /// <summary>The number one window contributes to a state's line.</summary>
        internal static int WindowValue(State s, NetworkSeatTelemetry.WindowFacts w)
        {
            switch (s)
            {
                case State.LOCAL_FRAMES: return w.WorstMs;
                case State.OWN_PING: return w.OwnPing;
                case State.OPP_PING_REPORTED: return w.PeerRtt;
            }
            return 0;
        }

        /// <summary>The value that met the threshold at entry (r3 M7(c)):
        /// the lookback's worst frame for LOCAL_FRAMES (>= 250 whenever the
        /// predicate held), the newest window's ping / reported RTT for the
        /// ping states (>= 150 whenever the predicate held).</summary>
        internal static int EntryValue(State s, NetworkSeatTelemetry.WindowFacts[] recent, int n)
        {
            if (s == State.LOCAL_FRAMES)
            {
                int worst = 0;
                for (int i = 0; i < n; i++) if (recent[i].WorstMs > worst) worst = recent[i].WorstMs;
                return worst;
            }
            return n > 0 ? WindowValue(s, recent[0]) : 0;
        }

        /// <summary>r6 M3: a window carries a key (OppActor != 0) only when
        /// the telemetry captured the whole window under one eligible
        /// opponent; the key is the actor number plus the advertised id
        /// ("" when the id property was absent — an id that arrives later
        /// makes a different key, the conservative direction).</summary>
        internal static bool KeyEquals(NetworkSeatTelemetry.WindowFacts w, int actor, string id)
        {
            return w.OppActor != 0 && w.OppActor == actor
                && string.Equals(w.OppId ?? "", id ?? "", StringComparison.Ordinal);
        }

        /// <summary>r6 M3 history admission — the one decision both the
        /// production tick and the self-test apply before any Step. Of the
        /// closed windows (newest first, <paramref name="count"/> valid),
        /// Step may read only the newest-first CONTIGUOUS run keyed exactly
        /// like the newest window; a window without a key (not an eligible
        /// 1v1 against one opponent at both its open and its close, or a late
        /// batch from another actor inside it) or keyed to another opponent
        /// ends the run and is never consumed. Returns 0 when the newest
        /// window has no key. <paramref name="resetWhy"/> is non-null when the caller must
        /// reset every slot before stepping: the slots were built under a key
        /// (<paramref name="builtActor"/> != 0) that the newest window no
        /// longer carries ("key-lost") or differs from ("opponent"). Pure —
        /// mutates nothing; the caller resets, then adopts the newest
        /// window's key. Through the production sampler two adjacent keyed
        /// windows always share a key (a change spans a window that opens
        /// under one key and closes under another, which is unkeyed), so
        /// "opponent" states the invariant for any producer and is reached
        /// by the self-test, which feeds windows directly.</summary>
        internal static int AdmitWindows(NetworkSeatTelemetry.WindowFacts[] recent, int count, int builtActor, string builtId, out string resetWhy)
        {
            resetWhy = null;
            int n = Math.Min(count, LOOKBACK);
            if (n <= 0) return 0;
            if (recent[0].OppActor == 0)
            {
                if (builtActor != 0) resetWhy = "key-lost";
                return 0;
            }
            if (builtActor != 0 && !KeyEquals(recent[0], builtActor, builtId)) resetWhy = "opponent";
            int run = 1;
            while (run < n && KeyEquals(recent[run], recent[0].OppActor, recent[0].OppId)) run++;
            return run;
        }

        /// <summary>The line for a shown state and its latched value.</summary>
        internal static string LineFor(State s, int value)
        {
            switch (s)
            {
                case State.LOCAL_FRAMES:
                    return I18n.TrF("Your game is dropping frames (worst {0} ms)", value);
                case State.OWN_PING:
                    return I18n.TrF("Your ping to the relay is high ({0} ms)", value);
                case State.OPP_STREAM:
                    // Cause-neutral by design (r6 M2): the enter condition is
                    // a receiver observation — batch arrival intervals on this
                    // seat's clock, less the interval the peer's own embedded
                    // timestamps advanced — and the peer's timestamps are an
                    // input this seat cannot verify. So the line states only
                    // what this seat observed (the updates arrived late) and
                    // names neither a leg nor a party: a one-sided receiver
                    // cannot tell the opponent's uplink from the relay from
                    // its own downlink (#446), and this seat's own stall
                    // windows are excluded from the enter condition rather
                    // than attributed.
                    return I18n.Tr("Opponent's updates are arriving late");
                case State.OPP_PING_REPORTED:
                    // Peer-reported value: "reports" is the label, never a bare attribution.
                    return I18n.TrF("Opponent reports {0} ms ping", value);
            }
            return null;
        }

        // ── production wrapper ───────────────────────────────────────────

        private static readonly Slot[] _slots = NewSlots();
        private static readonly NetworkSeatTelemetry.WindowFacts[] _recent = new NetworkSeatTelemetry.WindowFacts[LOOKBACK];
        private static int _recentCount;
        // r6 M3: the eligible-opponent key the slots' state was built under
        // (0/null = none). Every closed window carries the key it was captured
        // under (NetworkSeatTelemetry: actor number + advertised id of the
        // only other fighter, present only when the seat was an eligible
        // plain 1v1 against that opponent at the window's open and close and
        // every late sample in it came from that actor); AdmitWindows lets
        // Step read only the newest windows keyed exactly like this and asks
        // for a reset when the key is lost or differs.
        private static int _keyActor;
        private static string _keyId;

        private static readonly string[] NoLines = new string[0];
        private static string[] _lines = NoLines;

        /// <summary>The HUD stack, fixed state order, at most MAX_LINES.
        /// Rebuilt at window close only, so the Repaint path allocates
        /// nothing and reads one array reference.</summary>
        internal static string[] ActiveLines => _lines;

        private static bool SettingOn()
        {
            try { return Plugin.LagNoticesEnabled != null && Plugin.LagNoticesEnabled.Value; } catch { return false; }
        }

        /// <summary>Plain-1v1 fighter seat, not a spectator, not the broadcast
        /// identity (hidden there regardless of the setting, §9 Q3). Also the
        /// predicate NetworkSeatTelemetry.SampleEligibleKey keys windows by
        /// (r6 M3), so a keyed window and an eligible tick cannot disagree.</summary>
        /// <summary>Whether a closed window's key can be consumed at all
        /// (review r8 LOW 4). OnWindowClosed returns at its first statement
        /// when the setting is off, so with notices off nothing anywhere reads
        /// OppActor/OppId — and the per-frame sampling that maintains them is
        /// pure cost on every eligible 1v1 frame. Flipping the setting on is
        /// picked up by the next window, one second later.</summary>
        internal static bool WindowKeyingWanted()
        {
            return SettingOn();
        }

        internal static bool SeatEligible()
        {
            try
            {
                if (BroadcastMode.IsBroadcastIdentity) return false;
                if (RoomActors.LocalIsSpectator) return false;
                return GameStateWatcher.IsPlainOneVOneForHud();
            }
            catch { return false; }
        }

        internal static void OnGameStarted()
        {
            EnsureStartup();
            // A new game starts every state at Off with no cooldown carried
            // over; nothing from the previous game is announced or suppressed.
            ResetAll(logExits: false, why: null);
        }

        /// <summary>Reached from every end edge of NetworkSeatTelemetry.OnMatchEnded:
        /// game over, room leave (OnRoomChanged) and disconnect (the
        /// OnDisconnected handler's NetworkReplicaDiagnostics.OnRoomLeft →
        /// ResetState → OnRoomChanged) — r3 M7(b).</summary>
        internal static void OnGameEnded()
        {
            // Shown states end here; the exit line is written only when the
            // setting is still on (setting off => zero lines, §4.4).
            ResetAll(logExits: SettingOn(), why: "game-end");
        }

        /// <summary>The only tick: called by NetworkSeatTelemetry.CloseWindow
        /// after the window is in the ring and only when WindowFeedsEvaluator
        /// allowed it, so every value read below belongs to a CLOSED,
        /// unforced window. r6 M3: Step reads only the newest contiguous run
        /// of windows captured under the current eligible opponent
        /// (AdmitWindows) — the ring keeps every window for the bundle, so
        /// eligibility gained mid-game must not import windows captured
        /// before it.</summary>
        internal static void OnWindowClosed()
        {
            try
            {
                if (!SettingOn()) { ResetAll(logExits: false, why: null); return; }
                if (!SeatEligible()) { ResetAll(logExits: true, why: "seat"); return; }
                _recentCount = NetworkSeatTelemetry.RecentWindows(_recent);
                string resetWhy;
                int admitted = AdmitWindows(_recent, _recentCount, _keyActor, _keyId, out resetWhy);
                // A reset's exit lines print the whole fill (the opp= series
                // shows the key change that decided it); ResetAll clears the
                // built key, so the newest window's key is adopted after it.
                if (resetWhy != null) ResetAll(logExits: true, why: resetWhy);
                _recentCount = admitted;
                if (_recentCount <= 0) return;
                _keyActor = _recent[0].OppActor;
                _keyId = _recent[0].OppId;
                double nowS = NowS();
                bool changed = false;
                for (int s = 0; s < STATE_COUNT; s++)
                {
                    var slot = _slots[s];
                    switch (Step((State)s, slot, _recent, _recentCount, nowS))
                    {
                        case Edge.Enter: LogEdge((State)s, "enter", slot, nowS, null); changed = true; break;
                        case Edge.Exit: LogEdge((State)s, "exit", slot, nowS, null); changed = true; break;
                        case Edge.Suppressed: LogEdge((State)s, "suppressed", slot, nowS, null); break;
                    }
                }
                // A shown line's latched number can rise on any window, so the
                // stack is rebuilt every window while anything is shown.
                if (changed || _lines.Length > 0) RebuildLines();
            }
            // Different tag on purpose: "[LAG-NOTICE]" is reserved for transition
            // and self-test lines, so a grep for it never counts a failure as a state edge.
            catch (Exception ex) { Plugin.Log?.LogWarning("[NET-SEAT] lag-notice evaluate failed: " + ex.Message); }
        }

        private static void RebuildLines()
        {
            var list = new List<string>(MAX_LINES);
            for (int s = 0; s < STATE_COUNT && list.Count < MAX_LINES; s++)
            {
                if (_slots[s].Phase != Phase.Shown) continue;
                string line = LineFor((State)s, _slots[s].Value);
                if (!string.IsNullOrEmpty(line)) list.Add(line);
            }
            _lines = list.Count == 0 ? NoLines : list.ToArray();
        }

        private static void ResetAll(bool logExits, string why)
        {
            double nowS = NowS();
            for (int s = 0; s < STATE_COUNT; s++)
            {
                var slot = _slots[s];
                if (logExits && slot.Phase == Phase.Shown) LogEdge((State)s, "exit", slot, nowS, why);
                slot.Phase = Phase.Off;
                slot.Clean = 0;
                slot.HasExited = false;
                slot.EnterS = 0;
                slot.ExitS = 0;
                slot.Value = 0;
            }
            _lines = NoLines;
            _recentCount = 0;
            _keyActor = 0;
            _keyId = null;
        }

        private static double NowS()
        {
            return System.Diagnostics.Stopwatch.GetTimestamp() / (double)System.Diagnostics.Stopwatch.Frequency;
        }

        /// <summary>The acceptance signal (§4.4): one line per transition,
        /// carrying the latched value and the closed-window values (newest
        /// first) the transition was decided on. Called ONLY for a non-None
        /// Edge from Step, or from ResetAll for a shown state.</summary>
        private static void LogEdge(State s, string edge, Slot slot, double nowS, string why)
        {
            try
            {
                var sb = new StringBuilder(256);
                sb.Append("[LAG-NOTICE] state=").Append(StateNames[(int)s]).Append(" edge=").Append(edge);
                if (!string.IsNullOrEmpty(why)) sb.Append(" why=").Append(why);
                sb.Append(" value=").Append(slot.Value.ToString(CultureInfo.InvariantCulture));
                sb.Append(" seq=").Append(_recentCount > 0 ? _recent[0].Seq : 0);
                if (edge == "exit")
                    sb.Append(" shownS=").Append((nowS - slot.EnterS).ToString("F1", CultureInfo.InvariantCulture));
                else if (edge == "suppressed")
                    sb.Append(" sinceExitS=").Append((nowS - slot.ExitS).ToString("F1", CultureInfo.InvariantCulture));
                AppendSeries(sb, " worstMs=", 0);
                AppendSeries(sb, " ownPing=", 1);
                AppendSeries(sb, " late300=", 2);
                AppendSeries(sb, " peerRtt=", 3);
                AppendSeries(sb, " opp=", 4);   // r6 M3: the key (actor number) each window was captured under; 0 = unkeyed
                Plugin.Log?.LogInfo(sb.ToString());
            }
            catch { }
        }

        private static void AppendSeries(StringBuilder sb, string key, int which)
        {
            sb.Append(key);
            if (_recentCount <= 0) { sb.Append('-'); return; }
            for (int i = 0; i < _recentCount; i++)
            {
                if (i > 0) sb.Append('/');
                int v;
                switch (which)
                {
                    case 0: v = _recent[i].WorstMs; break;
                    case 1: v = _recent[i].OwnPing; break;
                    case 2: v = _recent[i].ObsLate300; break;
                    case 3: v = _recent[i].PeerRtt; break;
                    case 4: v = _recent[i].OppActor; break;
                    default: v = 0; break;
                }
                sb.Append(v.ToString(CultureInfo.InvariantCulture));
            }
        }

        // ── startup: setting-off edge + self-test ────────────────────────

        private static bool _startupDone;
        private static ConfigEntry<bool> _selfTest;

        /// <summary>Once per process, from the first HUD Repaint
        /// (CompetitiveUI.DrawLagNotices) or the first game start, whichever
        /// comes first: subscribes the setting-off edge (r3 M7(b)) and binds
        /// [Network] LagNoticesSelfTest through the plugin's own ConfigFile
        /// (the same Config.Bind API Plugin.cs uses; bound here because this
        /// file owns the evaluator), running the self-test when it is true.</summary>
        internal static void EnsureStartup()
        {
            if (_startupDone) return;
            _startupDone = true;
            try { if (Plugin.LagNoticesEnabled != null) Plugin.LagNoticesEnabled.SettingChanged += OnSettingChanged; } catch { }
            try
            {
                ConfigFile cf = Plugin.ConfigFileForLevers;
                if (cf == null && Plugin.LagNoticesEnabled != null) cf = Plugin.LagNoticesEnabled.ConfigFile;
                if (cf != null)
                    _selfTest = cf.Bind(
                        "Network", "LagNoticesSelfTest",
                        false,
                        "Development only: once at startup, run the lag-notice evaluator over canned window sequences and log one [LAG-NOTICE] selftest line per case plus a summary line. Nothing is shown, sent or persisted.");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[NET-SEAT] lag-notice self-test bind failed: " + ex.Message); }
            bool run = false;
            try { run = _selfTest != null && _selfTest.Value; } catch { }
            if (run) RunSelfTest();
        }

        /// <summary>r3 M7(b): turning the setting off clears every state and
        /// the HUD lines at once, not at the next window close. Off means
        /// zero lines, so no exit line is written.</summary>
        private static void OnSettingChanged(object sender, EventArgs e)
        {
            try { if (!SettingOn()) ResetAll(logExits: false, why: null); } catch { }
        }

        // ── self-test (r3 L6) ────────────────────────────────────────────
        //
        // Table-driven: each case is a window sequence fed one window at a
        // time through the PRODUCTION gate and evaluator with the step index
        // as the clock (one window per second), and the expected shown set
        // after every step, authored by hand. One line per case:
        //   [LAG-NOTICE] selftest case=<name> expected=<states> got=<states> <PASS|FAIL>
        // <states> = one entry per window, ',' separated: '-' none, 'x' the
        // window was dropped by the forced-close gate, 'k' the window carried
        // no opponent key so nothing was stepped (r6 M3), else the shown
        // states in fixed order joined by '+', each NAME@value (no @ for
        // OPP_STREAM).
        // Summary:
        //   [LAG-NOTICE] selftest summary run=<n> expected=<CASE_COUNT> pass=<p> fail=<f> <PASS|FAIL>
        // PASS requires run == CASE_COUNT (a literal — a deleted or throwing
        // case cannot pass silently) and fail == 0.
        // r6 M3: every canned window carries the opponent key the telemetry
        // would have stamped (default actor 2 / id "A"; actor 0 = captured
        // while the seat was not an eligible 1v1), and each step applies the
        // production admission (AdmitWindows) before Step, resetting the
        // slots exactly where OnWindowClosed does.
        // r7 L1: the "producer_" cases are the other half — the sequence cases
        // take a window's key as given, and these run the code that DECIDES it
        // (WindowKeyed, the same call NetworkSeatTelemetry.CloseWindow makes)
        // over one window's boundary facts. Their <states> field is that
        // verdict, "keyed" or "unkeyed", not a window sequence.

        private const int CASE_COUNT = 32;

        private struct Canned
        {
            public NetworkSeatTelemetry.WindowFacts W;
            public bool Forced;
        }

        private sealed class Case
        {
            public string Name;
            public Canned[] Seq;
            public string Expected;
            public bool IgnoreForcedGate;   // negative control only: proves the forced case discriminates (#391)
            public bool IgnoreKeyGate;      // negative control only: proves the r6 M3 admission discriminates (#391)
            // r7 L1: a PRODUCER case — it runs the window-keying producer
            // (WindowKeyed) on one window's boundary facts instead of feeding
            // the evaluator a window sequence, and its result is the string.
            public Func<string> Producer;
        }

        /// <summary>r7 L1: the producer's verdict for one window, rendered.</summary>
        private static string Keyed(int openActor, string openId, int closeActor, string closeId,
                                    bool lateForeign, bool keyBroken)
        {
            return WindowKeyed(openActor, openId, closeActor, closeId, lateForeign, keyBroken) ? "keyed" : "unkeyed";
        }

        private const int KEY_A = 2;   // the default canned opponent: actor 2, id "A"
        private const int KEY_B = 3;

        private static Canned W(int worst, int ping = 40, int peer = 40, int late = 0, bool forced = false, int actor = KEY_A, string id = "A")
        {
            return new Canned
            {
                W = new NetworkSeatTelemetry.WindowFacts { WorstMs = worst, OwnPing = ping, PeerRtt = peer, ObsLate300 = late, OppActor = actor, OppId = id },
                Forced = forced,
            };
        }

        /// <summary>An opponent-stream window built the way the sampler
        /// builds it: one accepted batch with the given arrival gap and
        /// peer-stamped gap, classified by the production excess formula
        /// and threshold, captured under the given key (actor 0 = the seat
        /// was not an eligible 1v1 for that window).</summary>
        private static Canned Opp(int worst, int arrivalGapMs, int senderGapMs, int actor = KEY_A, string id = "A")
        {
            int excess = NetworkReplicaDiagnostics.DeliveryExcessMs(arrivalGapMs, senderGapMs);
            return W(worst, late: IsLateDelivery(excess) ? 1 : 0, actor: actor, id: id);
        }

        private static Canned[] Seq(params Canned[] w) { return w; }

        private static Canned[] Cat(params Canned[][] parts)
        {
            var l = new List<Canned>();
            foreach (var p in parts) l.AddRange(p);
            return l.ToArray();
        }

        private static Canned[] Rep(Canned w, int n)
        {
            var a = new Canned[n];
            for (int i = 0; i < n; i++) a[i] = w;
            return a;
        }

        private static string Exp(params string[] steps) { return string.Join(",", steps); }

        private static string[] RepS(string s, int n)
        {
            var a = new string[n];
            for (int i = 0; i < n; i++) a[i] = s;
            return a;
        }

        private static string[] CatS(params string[][] parts)
        {
            var l = new List<string>();
            foreach (var p in parts) l.AddRange(p);
            return l.ToArray();
        }

        private static Case[] BuildCases()
        {
            const string LF300 = "LOCAL_FRAMES@300";
            var hot = W(300);
            var c = W(40);
            return new[]
            {
                new Case { Name = "local_frames_enter", Seq = Seq(hot, c, hot), Expected = Exp("-", "-", LF300) },
                new Case { Name = "local_frames_under_threshold", Seq = Rep(W(249), 5), Expected = Exp(RepS("-", 5)) },
                new Case { Name = "own_ping_enter_3_consecutive", Seq = Rep(W(40, ping: 150), 3), Expected = Exp("-", "-", "OWN_PING@150") },
                new Case
                {
                    Name = "own_ping_non_enter",
                    Seq = Seq(W(40, ping: 149), W(40, ping: 149), W(40, ping: 149), W(40, ping: 150), W(40, ping: 150), W(40, ping: 40), W(40, ping: 150), W(40, ping: 150)),
                    Expected = Exp(RepS("-", 8)),
                },
                new Case { Name = "two_of_five_enter", Seq = Seq(hot, c, c, c, hot), Expected = Exp("-", "-", "-", "-", LF300) },
                new Case { Name = "one_of_five_no_enter", Seq = Seq(hot, c, c, c, c, hot), Expected = Exp(RepS("-", 6)) },
                // enter t=2; 3 clean at t=5 but shown 3 s; exit at t=7 (shown 5 s).
                new Case { Name = "exit_hysteresis", Seq = Cat(Seq(hot, hot), Rep(c, 5)), Expected = Exp(CatS(new[] { "-" }, RepS(LF300, 5), new[] { "-" })) },
                // a hot window at t=5 resets the clean run; exit at t=8, not t=7.
                new Case { Name = "exit_needs_3_consecutive_clean", Seq = Seq(hot, hot, c, c, hot, c, c, c), Expected = Exp(CatS(new[] { "-" }, RepS(LF300, 6), new[] { "-" })) },
                // enter t=2, exit t=7; re-enter at t=9 (2 s after exit) is suppressed
                // (Off branch), clears to Off by t=12; at t=36 (29 s) suppressed
                // again; at t=37 (30 s) the cooldown has elapsed while the
                // condition persists → shown from the SUPPRESSED branch.
                new Case
                {
                    Name = "cooldown_reannounce_from_suppressed",
                    Seq = Cat(Seq(hot, hot), Rep(c, 5), Seq(hot, hot), Rep(c, 25), Seq(hot, hot, c)),
                    Expected = Exp(CatS(new[] { "-" }, RepS(LF300, 5), RepS("-", 30), new[] { LF300 })),
                },
                // Same exit at t=7; the next enter attempt lands at t=37 from the
                // OFF branch with exactly 30 s since exit → shown, not suppressed.
                new Case
                {
                    Name = "cooldown_boundary_from_off",
                    Seq = Cat(Seq(hot, hot), Rep(c, 5), Seq(hot, hot), Rep(c, 26), Seq(hot, hot)),
                    Expected = Exp(CatS(new[] { "-" }, RepS(LF300, 5), RepS("-", 30), new[] { LF300 })),
                },
                new Case { Name = "forced_window_excluded", Seq = Seq(hot, W(300, forced: true)), Expected = Exp("-", "x") },
                new Case { Name = "forced_window_gate_control", Seq = Seq(hot, W(300, forced: true)), Expected = Exp("-", LF300), IgnoreForcedGate = true },
                new Case
                {
                    Name = "two_states_at_once",
                    Seq = Seq(W(300, ping: 200), W(300, ping: 200), W(40, ping: 200)),
                    Expected = Exp("-", LF300, LF300 + "+OWN_PING@200"),
                },
                // arrival 2700 ms, sender stamps advanced 300 ms → excess 2400 → late.
                new Case { Name = "opp_stream_enter_on_excess", Seq = Rep(Opp(40, 2700, 300), 2), Expected = Exp("-", "OPP_STREAM") },
                // UnreliableOnChange silence: the sender stamps advanced with the
                // arrival gap → excess 0 → never a late sample.
                new Case { Name = "opp_stream_stationary_negative", Seq = Rep(Opp(40, 2700, 2700), 3), Expected = Exp("-", "-", "-") },
                new Case { Name = "opp_stream_local_stall_excluded", Seq = Rep(Opp(120, 2700, 300), 3), Expected = Exp("-", "-", "-") },
                new Case { Name = "opp_ping_reported_enter", Seq = Rep(W(40, peer: 150), 3), Expected = Exp("-", "-", "OPP_PING_REPORTED@150") },
                new Case
                {
                    Name = "opp_ping_reported_non_enter",
                    Seq = Seq(W(40, peer: 149), W(40, peer: 149), W(40, peer: 149), W(40, peer: 0), W(40, peer: 150), W(40, peer: 150)),
                    Expected = Exp(RepS("-", 6)),
                },
                new Case { Name = "latch_local_value_never_falls", Seq = Seq(W(250), W(250), W(400), c, c), Expected = Exp("-", "LOCAL_FRAMES@250", "LOCAL_FRAMES@400", "LOCAL_FRAMES@400", "LOCAL_FRAMES@400") },
                new Case
                {
                    Name = "latch_ping_value_never_falls",
                    Seq = Seq(W(40, ping: 150), W(40, ping: 150), W(40, ping: 150), W(40, ping: 200), W(40, ping: 160)),
                    Expected = Exp("-", "-", "OWN_PING@150", "OWN_PING@200", "OWN_PING@200"),
                },
                // r6 M3 lifecycle: two late windows captured while the seat was
                // NOT an eligible 1v1 (a third fighter's stream in a casual
                // room — no key), then the room becomes a 1v1 against A. The
                // unkeyed windows are never consumed: A needs two of its own.
                new Case
                {
                    Name = "opp_stream_unkeyed_windows_never_consumed",
                    Seq = Seq(Opp(40, 2700, 300, actor: 0, id: null), Opp(40, 2700, 300, actor: 0, id: null), Opp(40, 2700, 300), Opp(40, 2700, 300)),
                    Expected = Exp("k", "k", "-", "OPP_STREAM"),
                },
                // Negative control: the same sequence with the admission
                // bypassed reproduces the defect — OPP_STREAM at step 2 from
                // the unkeyed windows alone.
                new Case
                {
                    Name = "opp_stream_unkeyed_gate_control",
                    Seq = Seq(Opp(40, 2700, 300, actor: 0, id: null), Opp(40, 2700, 300, actor: 0, id: null), Opp(40, 2700, 300), Opp(40, 2700, 300)),
                    Expected = Exp("-", "OPP_STREAM", "OPP_STREAM", "OPP_STREAM"),
                    IgnoreKeyGate = true,
                },
                // A window under another opponent's key resets the machine;
                // B needs two late windows of its own (A's are not contiguous).
                new Case
                {
                    Name = "opp_stream_key_change_resets",
                    Seq = Seq(Opp(40, 2700, 300), Opp(40, 2700, 300), Opp(40, 2700, 300, actor: KEY_B, id: "B"), Opp(40, 2700, 300, actor: KEY_B, id: "B")),
                    Expected = Exp("-", "OPP_STREAM", "-", "OPP_STREAM"),
                },
                // Same actor number, different advertised id = a different key.
                new Case
                {
                    Name = "opp_stream_same_actor_new_id_resets",
                    Seq = Seq(Opp(40, 2700, 300), Opp(40, 2700, 300), Opp(40, 2700, 300, id: "C"), Opp(40, 2700, 300, id: "C")),
                    Expected = Exp("-", "OPP_STREAM", "-", "OPP_STREAM"),
                },
                // Eligibility lost for one window (no key) resets the machine
                // AND breaks contiguity: A's earlier windows sit behind the gap
                // and are not consumed once A is eligible again.
                new Case
                {
                    Name = "opp_stream_key_lost_breaks_contiguity",
                    Seq = Seq(Opp(40, 2700, 300), Opp(40, 2700, 300), Opp(40, 2700, 300, actor: 0, id: null), Opp(40, 2700, 300), Opp(40, 2700, 300)),
                    Expected = Exp("-", "OPP_STREAM", "k", "-", "OPP_STREAM"),
                },

                // r7 L1: the PRODUCER that decides whether a window carries a
                // key at all — the cases above take that decision as given.
                // Arguments: open key, close key, lateForeign, keyBroken.
                new Case { Name = "producer_one_opponent_whole_window", Producer = () => Keyed(KEY_A, "A", KEY_A, "A", false, false), Expected = "keyed" },
                // r7 M3: eligibility lost (or a third fighter present) INSIDE
                // the window, back to the same key by the boundary — the two
                // boundary samples agree and only the latch sees it.
                new Case { Name = "producer_key_broken_inside_window", Producer = () => Keyed(KEY_A, "A", KEY_A, "A", false, true), Expected = "unkeyed" },
                // Negative control for the case above: the same window with the
                // latch term dropped is keyed, so that case discriminates the
                // latch and nothing else (#391).
                new Case { Name = "producer_key_broken_latch_control", Producer = () => Keyed(KEY_A, "A", KEY_A, "A", false, false), Expected = "keyed" },
                new Case { Name = "producer_opponent_replaced_at_close", Producer = () => Keyed(KEY_A, "A", KEY_B, "B", false, false), Expected = "unkeyed" },
                new Case { Name = "producer_same_actor_new_id_at_close", Producer = () => Keyed(KEY_A, "A", KEY_A, "C", false, false), Expected = "unkeyed" },
                new Case { Name = "producer_ineligible_at_open", Producer = () => Keyed(0, null, KEY_A, "A", false, false), Expected = "unkeyed" },
                new Case { Name = "producer_late_batch_from_other_actor", Producer = () => Keyed(KEY_A, "A", KEY_A, "A", true, false), Expected = "unkeyed" },
            };
        }

        private static string RunCase(Case c)
        {
            if (c.Producer != null) return c.Producer();
            var slots = NewSlots();
            var ring = new List<NetworkSeatTelemetry.WindowFacts>(LOOKBACK + 1);
            var recent = new NetworkSeatTelemetry.WindowFacts[LOOKBACK];
            var got = new List<string>(c.Seq.Length);
            int keyActor = 0; string keyId = null;
            for (int i = 0; i < c.Seq.Length; i++)
            {
                double nowS = i + 1;
                // The production gate: a forced (game-end) window never reaches
                // the evaluator — and never reaches the next game's ring either
                // (ResetGame clears it), so it is dropped here outright.
                if (!c.IgnoreForcedGate && !WindowFeedsEvaluator(c.Seq[i].Forced, gameOpen: true, spectator: false))
                {
                    got.Add("x");
                    continue;
                }
                var w = c.Seq[i].W;
                w.Seq = i + 1;
                ring.Insert(0, w);
                if (ring.Count > LOOKBACK) ring.RemoveAt(LOOKBACK);
                int filled = ring.Count;
                for (int k = 0; k < filled; k++) recent[k] = ring[k];
                // The production admission (r6 M3), mirrored from
                // OnWindowClosed: reset on a lost/changed key, step only the
                // admitted contiguous run, adopt the newest window's key.
                int n = filled;
                if (!c.IgnoreKeyGate)
                {
                    string resetWhy;
                    n = AdmitWindows(recent, filled, keyActor, keyId, out resetWhy);
                    if (resetWhy != null) { slots = NewSlots(); keyActor = 0; keyId = null; }
                    if (n <= 0) { got.Add("k"); continue; }
                    keyActor = recent[0].OppActor; keyId = recent[0].OppId;
                }
                for (int s = 0; s < STATE_COUNT; s++) Step((State)s, slots[s], recent, n, nowS);
                got.Add(Render(slots));
            }
            return string.Join(",", got.ToArray());
        }

        private static string Render(Slot[] slots)
        {
            var sb = new StringBuilder();
            for (int s = 0; s < STATE_COUNT; s++)
            {
                if (slots[s].Phase != Phase.Shown) continue;
                if (sb.Length > 0) sb.Append('+');
                sb.Append(StateNames[s]);
                if (slots[s].Value > 0) sb.Append('@').Append(slots[s].Value.ToString(CultureInfo.InvariantCulture));
            }
            return sb.Length == 0 ? "-" : sb.ToString();
        }

        internal static void RunSelfTest()
        {
            int run = 0, pass = 0, fail = 0;
            try
            {
                var cases = BuildCases();
                foreach (var c in cases)
                {
                    run++;
                    string got;
                    try { got = RunCase(c); }
                    catch (Exception ex) { got = "EXCEPTION:" + ex.GetType().Name; }
                    bool ok = got == c.Expected;
                    if (ok) pass++; else fail++;
                    Plugin.Log?.LogInfo("[LAG-NOTICE] selftest case=" + c.Name + " expected=" + c.Expected + " got=" + got + (ok ? " PASS" : " FAIL"));
                }
            }
            catch (Exception ex)
            {
                fail++;
                Plugin.Log?.LogWarning("[LAG-NOTICE] selftest harness failed: " + ex.Message);
            }
            bool all = run == CASE_COUNT && fail == 0;
            string summary = "[LAG-NOTICE] selftest summary run=" + run + " expected=" + CASE_COUNT + " pass=" + pass + " fail=" + fail + (all ? " PASS" : " FAIL");
            if (all) Plugin.Log?.LogInfo(summary); else Plugin.Log?.LogWarning(summary);
        }
    }
}
