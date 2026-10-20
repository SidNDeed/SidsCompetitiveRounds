"""Night 2026-10-19 calibration lane harness: build the controls over the REAL
plugin files (InboundStallCore.cs, NetJitterBudgetCore.cs, PoisonLedgerCore.cs,
LagNotices.cs, FpsFocusCore.cs, and the DecimatedList class read out of
GameStateWatcher.cs into work/DecimatedList.cs), plus exact ApiClient wire
text and NetworkReplicaDiagnostics snapshot/join methods, run every case, then build
mutated COPIES (work/, the *Source overrides; the tracked files are never
written) and require each mutant's target case to FAIL and its control case to
PASS. Exit 0 only when everything holds.

    python tools/tests/net-stall-detect/run_tests.py [mutant names...]
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "NetStallTests.csproj")
WORK = os.path.join(HERE, "work")
PLUGIN = os.path.join(REPO, "plugin")

SOURCES = {
    "StallSource": "InboundStallCore.cs",
    "JitterSource": "NetJitterBudgetCore.cs",
    "PoisonSource": "PoisonLedgerCore.cs",
    "LagSource": "LagNotices.cs",
    "FocusSource": "FpsFocusCore.cs",
    "TelemetrySource": "NetworkSeatTelemetry.cs",
    "PoisonSyncSource": "PoisonSync.cs",
    "ReplicaSource": "NetworkReplicaDiagnostics.cs",
    "PluginSource": "Plugin.cs",
    "WatcherSource": "GameStateWatcher.cs",
    "ApiSource": "ApiClient.cs",
}
COMPILED_SOURCES = {"StallSource", "JitterSource", "PoisonSource", "LagSource", "FocusSource"}
EXTRACTED_SOURCES = {"ApiSource", "ReplicaSource"}
# DecimatedList lives inside GameStateWatcher.cs (never moved, so the
# keybind-surface manifest keeps its rows); the harness compiles the class
# text itself, cut from the real file at every run.
DECIMATED_FROM = "GameStateWatcher.cs"
DECIMATED_OUT = os.path.join(WORK, "DecimatedList.cs")


def source_text(key, overrides=None):
    path = (overrides or {}).get(key, os.path.join(PLUGIN, SOURCES[key]))
    return open(path, "rb").read().decode("utf-8").replace("\r\n", "\n")


def method_text(raw, marker):
    if raw.count(marker) != 1:
        raise ValueError("method marker count: " + marker)
    start = raw.index(marker)
    depth, i = 0, raw.index("{", start)
    while i < len(raw):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
        i += 1
    raise ValueError("unclosed method: " + marker)


def ordered_once(span, *tokens):
    positions = []
    for token in tokens:
        if span.count(token) != 1:
            return "expected once: " + token
        positions.append(span.index(token))
    return "PASS" if positions == sorted(positions) else "production order changed"


def structural_pins(overrides=None):
    raw = source_text("TelemetrySource", overrides)
    end = method_text(raw, "internal static void OnMatchEnded(string reason)")
    depth = method_text(raw, "internal static void NoteInboundDepth()")
    stall = source_text("StallSource", overrides)
    pins = {
        "h1_game_end": ordered_once(end, "if (!_gameOpen) return;",
            "_stall.Flush(StallNowMs(), _stallStreams, _gameSeq, ReceiverWallGapMsNow())",
            "_gameOpen = false;"),
        "h1_depth_close": ordered_once(depth, "if (_stall.Wants(qi))",
            "_stall.OnDepth(qi, StallNowMs(), _stallStreams, _gameSeq,",
            "_stall.Open && qi <= InboundStallCore.QUEUE_BOUND ? ReceiverWallGapMsNow() : 0"),
        "m1_band_expression": ordered_once(method_text(stall, "internal bool Wants(int depth)"),
            "return unchecked((uint)(depth - _bandFloor)) > _bandWidth;")
            if "if (unchecked((uint)(depth - _bandFloor)) <= _bandWidth) return null;" in
                method_text(stall, "internal string OnDepth(") else "OnDepth range comparison changed",
    }

    poison = source_text("PoisonSyncSource", overrides)
    pins['m3_boundary_capture'] = ordered_once(method_text(poison, 'internal static void NotePointBoundary(GM_ArmsRace gm)'),
        'evidenceBefore = _ledger.PointEpoch;',
        'evidenceActivation = _act.Epoch;',
        'evidenceLive = _act.Live;',
        'if (stamped) _ledger.NotePointBoundary(ts);',
        'string pointBoundaryLine = _v3Log.OnPoint(evidenceBefore, _ledger.PointEpoch, evidenceActivation, evidenceLive);',
        'if (!recorded)')
    pins['m3_activation_capture'] = ordered_once(method_text(poison, 'private static void OnActivate(int sender, object[] a)'),
        'evidenceBefore = _ledger.PointEpoch;',
        'evidenceActivation = _act.Epoch;',
        'evidenceLive = _act.Live;',
        'if (!_act.OnActivate(sender, master, aid, fighters, point, NowMs()))',
        'if (point.Set) _ledger.AdoptPoint(point.Ts);',
        'string activationBoundaryLine = _v3Log.OnPoint(evidenceBefore, _ledger.PointEpoch, evidenceActivation, evidenceLive);',
        'bool ack =')
    pins['m3_upkeep_capture'] = ordered_once(method_text(poison, 'private static void V3Upkeep()'),
        'evidenceBefore = _ledger.PointEpoch;',
        'evidenceActivation = _act.Epoch;',
        'evidenceLive = _act.Live;',
        'bool on = V3On(out why);',
        'string upkeepBoundaryLine = _v3Log.OnPoint(evidenceBefore, _ledger.PointEpoch, evidenceActivation, evidenceLive);',
        'string stateLine = _v3Log.State(state);')
    pins.update(m4_pins(overrides))
    watcher = source_text("WatcherSource", overrides)
    tick = method_text(watcher, "public static void TickFrame()")
    pins["m5_focus_order"] = ordered_once(tick,
        "if (!isTracking) { _lastTickStopwatchMs = -1; return; }",
        "float dt = Time.unscaledDeltaTime;",
        "FpsFocusCore.ObserveFrame(tlUnfocused, Application.isFocused, dt)",
        "if (dt <= 0f || dt > 1f) return;",
        "fpsFrameCount++;",
        "fpsTimeAccum += dt;",
        "tlFrames++; tlAccum += dt;",
        "if (tlAccum >= 5f)",
        "localFpsTimeline.Add((int)Math.Round(tlFrames / (double)tlAccum));",
        "localFpsFocusTimeline.Add(FpsFocusCore.BucketFlag(tlUnfocused));",
        "tlUnfocused = false;")

    # Add these results to structural_pins(overrides), using the same source key
    # M5 uses for GameStateWatcher.cs if it differs from WatcherSource.
    raw = source_text("WatcherSource", overrides)
    for pin_name, marker in (
        ("m7_focus_match_reset", "private static void ResetPerMatchCombatCounters()"),
        ("m7_focus_state_reset", "private static void ResetMatchState()"),
    ):
        span = method_text(raw, marker)
        pins[pin_name] = ordered_once(span,
            "localFpsTimeline.Clear(); tlFrames = 0; tlAccum = 0f;",
            "localFpsFocusTimeline.Clear(); tlUnfocused = false;")

    return pins


# Add these noncompiled SOURCES keys if absent:
# "ReplicaSource": "NetworkReplicaDiagnostics.cs",
# "PluginSource": "Plugin.cs",
# Then: pins.update(m4_pins(overrides)) before structural_pins returns.
# Plugin/Replica files remain read-only; their exact route is pinned.

def m4_pins(overrides=None):
    def all_pass(*checks):
        return next((check for check in checks if check != "PASS"), "PASS")
    telemetry = source_text("TelemetrySource", overrides)
    start = method_text(telemetry, "internal static void OnMatchStarted()")
    end = method_text(telemetry, "internal static void OnMatchEnded(string reason)")
    close = method_text(telemetry, "private static void CloseWindow(bool force)")
    room_change = method_text(telemetry, "internal static void OnRoomChanged()")
    game_end = all_pass(
        ordered_once(start, "_gameOpen = true;", "LagNotices.OnGameStarted();"),
        ordered_once(end, "if (!_gameOpen) return;", "CloseWindow(force: true);",
                     "_gameOpen = false;", "LagNotices.OnGameEnded();"),
        ordered_once(close,
            "if (LagNotices.WindowFeedsEvaluator(force, _gameOpen, _spectatorGame))",
            "LagNotices.OnWindowClosed();"),
    )
    replica = source_text("ReplicaSource", overrides)
    left = method_text(replica, "internal static void OnRoomLeft()")
    reset = method_text(replica, "private static void ResetState()")
    plugin = source_text("PluginSource", overrides)
    disconnected = method_text(plugin, "public void OnDisconnected(Photon.Realtime.DisconnectCause cause)")
    disconnect = all_pass(
        game_end,
        ordered_once(disconnected, "NetworkReplicaDiagnostics.OnRoomLeft();",
                     "if (Diag2v2.PendingSlot() < 0) return;"),
        ordered_once(left, "finally", "ResetState();"),
        ordered_once(reset, "NetworkSeatTelemetry.OnRoomChanged();", "_roomActive = false;", "Actors.Clear();"),
        ordered_once(room_change, 'if (_gameOpen) OnMatchEnded("room-left");',
                     "ResetGame(keepFrozen: true);", "_stall.ResetRoom();"),
    )
    return {"m4_game_end": game_end, "m4_disconnect": disconnect}


def extract_fps_wire(tag, overrides):
    raw = source_text("ApiSource", overrides)
    start_token = "            int[] localFpsKeptIndices;\n"
    end_token = '            sb.Append($"\\"local_freeze_count\\":{localFreezeCount},");'
    if raw.count(start_token) != 1 or raw.count(end_token) != 1:
        raise ValueError("FPS wire block boundary count")
    start, end = raw.index(start_token), raw.index(end_token)
    if end <= start:
        raise ValueError("FPS wire block order")
    wire = raw[start:end]
    methods = [method_text(raw, "private static string ClampTimeline(string t, int max = 512)"),
               method_text(raw, "private static string ClampTimeline(string t, int max, out int[] retainedIndices)"),
               method_text(raw, "private static string Escape(string s)")]
    text = ("using System;\nusing System.Collections.Generic;\nusing System.Text;\n"
            "namespace CompetitiveRounds { internal static class FpsWireProduction {\n"
            "internal static string Wire(string localFpsTimeline, string localFpsFocusTimeline, string oppFpsTimeline = \"\") {\n"
            "var sb = new StringBuilder();\n" + wire + "return sb.ToString();\n}\n"
            "internal static string Clamp(string input, int max, out int[] indices) { return ClampTimeline(input, max, out indices); }\n"
            + "\n".join(methods) + "\n} }\n")
    path = os.path.join(WORK, "FpsWireProduction_" + tag + ".cs")
    open(path, "w", encoding="utf-8", newline="\n").write(text)
    return path


# Add SOURCES["ReplicaSource"] = "NetworkReplicaDiagnostics.cs".
# Add SOURCES["WatcherSource"] = "GameStateWatcher.cs" if M5 has not already.
# Both are noncompiled source keys. Add ReplicaMethodsSource property/Compile
# to the harness project only; pass the extraction output from build().

def extract_replica(tag, overrides=None):
    raw = source_text("ReplicaSource", overrides)
    bodies = [method_text(raw, marker) for marker in (
        "internal static int SnapshotRemoteStreams(int[] actors, long[] batches)",
        "internal static void OnRoomJoined()",
    )]
    text = ("using System;\nusing Photon.Pun;\n"
            "namespace CompetitiveRounds\n{\n"
            "internal static partial class NetworkReplicaDiagnostics\n{\n"
            + "\n\n".join(bodies) + "\n}\n}\n")
    path = os.path.join(WORK, "ReplicaMethods_" + tag + ".cs")
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    return path

# In build(tag, overrides), append:
# cmd.append("-p:ReplicaMethodsSource=" + extract_replica(tag, overrides))
# Project default property: $(MSBuildThisFileDirectory)work\ReplicaMethods_base.cs
# Project Compile item: <Compile Include="$(ReplicaMethodsSource)" />

def m7_scoped_edits(key, marker, old, new):
    # Whole-method replacement gives the mutation runner a unique old anchor,
    # even when the focus reset line has two production sibling sites.
    span = method_text(source_text(key), marker)
    if span.count(old) != 1:
        raise ValueError("M7 scoped edit expected once: " + marker + " / " + old)
    return [(span, span.replace(old, new))]


def extract_decimated():
    raw = open(os.path.join(PLUGIN, DECIMATED_FROM), "rb").read().decode("utf-8").replace("\r\n", "\n")
    start = raw.index("    /// <summary>Bounded telemetry series that COMPRESSES")
    cls = raw.index("    internal sealed class DecimatedList<T>\n", start)
    if raw.count("class DecimatedList<T>") != 1:
        raise SystemExit("DecimatedList: expected exactly one class in " + DECIMATED_FROM)
    depth, i = 0, raw.index("{", cls)
    while True:
        c = raw[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = raw[start:i + 1]
    text = "using System.Collections.Generic;\n\nnamespace CompetitiveRounds\n{\n" + body + "\n}\n"
    open(DECIMATED_OUT, "w", encoding="utf-8", newline="\n").write(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# (name, source key, [(old, new), ...], target case, control case). Each old
# text must occur exactly once in the shipped file.
MUTANTS = [
    ("m7_later_joiner_in_opening_cohort", "StallSource",
     [("                for (int i = 0; i < _openStreams; i++)", "                for (int i = 0; i < n; i++)")],
     "snapshot_roster", "stall_night"),
    ("m7_departed_actor_omitted", "ReplicaSource",
     [("                        if (a == null || a.Game.Views == 0) continue;",
       "                        if (a == null || a.Game.Views == 0 || !PhotonNetwork.CurrentRoom.Players.ContainsKey(en.Current.Key)) continue;")],
     "snapshot_roster", "snapshot_overflow"),
    ("m7_empty_game_view_included", "ReplicaSource",
     [("                        if (a == null || a.Game.Views == 0) continue;", "                        if (a == null) continue;")],
     "snapshot_roster", "snapshot_spectator"),
    ("m7_spectator_player_gate", "ReplicaSource",
     [("                        if (!spectator && a.PlayerViewId == 0) continue;", "                        if (a.PlayerViewId == 0) continue;")],
     "snapshot_spectator", "snapshot_roster"),
    ("m7_snapshot_overflow_slot_lost", "ReplicaSource",
     [("                        if (n >= actors.Length || n >= batches.Length) break;",
       "                        if (n >= actors.Length - 1 || n >= batches.Length) break;")],
     "snapshot_overflow", "snapshot_roster"),
    ("m7_jitter_ties_reversed", "JitterSource",
     [("            while (pos > 0 && _top[pos - 1].ArrivalMs < arrivalMs) pos--;",
       "            while (pos > 0 && _top[pos - 1].ArrivalMs <= arrivalMs) pos--;")],
     "jitter_ties", "jitter_top"),
    ("m7_same_room_slots_not_reset", "ReplicaSource",
     [("                    _jitterBudget.ResetLines();\n", "")],
     "jitter_same_room_reset", "jitter_ties"),
    ("m7_same_room_evidence_erased", "ReplicaSource",
     [("                    _jitterBudget.ResetLines();", "                    _jitterBudget.ResetRoom();")],
     "jitter_same_room_reset", "jitter_ties"),
    ("m7_unkeyed_not_counted", "LagSource",
     [("                if (_recentCount <= 0) { _gUnkeyed++; return; }",
       "                if (_recentCount <= 0) { return; }")],
     "lag_setting_flips", "lag_1v2_gate"),
    ("m7_suppressed_not_counted", "LagSource",
     [("                        case Edge.Suppressed: _gSuppressed++; LogEdge((State)s, \"suppressed\", slot, nowS, null); break;",
       "                        case Edge.Suppressed: LogEdge((State)s, \"suppressed\", slot, nowS, null); break;")],
     "lag_setting_flips", "lag_1v2_gate"),
    ("m7_setting_flip_erases_counts", "LagSource",
     [("            try { if (!SettingOn()) ResetAll(logExits: false, why: null); } catch { }",
       "            try { if (!SettingOn()) { ResetGateCounts(); ResetAll(logExits: false, why: null); } } catch { }")],
     "lag_setting_flips", "lag_1v2_gate"),
    ("m7_setting_flip_keeps_hud", "LagSource",
     [("            try { if (!SettingOn()) ResetAll(logExits: false, why: null); } catch { }", "")],
     "lag_setting_flips", "lag_1v2_gate"),
    ("m7_focus_match_reset_removed", "WatcherSource",
     m7_scoped_edits("WatcherSource", "private static void ResetPerMatchCombatCounters()",
                     "            localFpsFocusTimeline.Clear(); tlUnfocused = false;\n", ""),
     "focus_reset_match", "focus_reset_state"),
    ("m7_focus_state_reset_removed", "WatcherSource",
     m7_scoped_edits("WatcherSource", "private static void ResetMatchState()",
                     "            localFpsFocusTimeline.Clear(); tlUnfocused = false;\n", ""),
     "focus_reset_state", "focus_reset_match"),
    ("m7_same_room_counters_erased", "JitterSource",
     [("        internal void ResetLines() { _routineUsed = 0; _reserveUsed = 0; }",
       "        internal void ResetLines() { _routineUsed = 0; _reserveUsed = 0; _qualifying = 0; _suppressed = 0; }")],
     "jitter_same_room_reset", "jitter_ties"),
    ("m7_same_room_ranking_erased", "JitterSource",
     [("        internal void ResetLines() { _routineUsed = 0; _reserveUsed = 0; }",
       "        internal void ResetLines() { _routineUsed = 0; _reserveUsed = 0; _topN = 0; Array.Clear(_top, 0, _top.Length); }")],
     "jitter_same_room_reset", "jitter_ties"),
    ("m6_focus_clamped_independently", "ApiSource",
     [("Escape(FpsFocusCore.EncodeRetained(localFpsFocusTimeline, localFpsKeptIndices))",
       "Escape(ClampTimeline(localFpsFocusTimeline))")],
     "fps_focus_clamp_wire", "focus_lockstep"),
    ("m6_identity_indices_reversed", "ApiSource",
     [("for (int i = 0; i < count; i++) retainedIndices[i] = i;",
       "for (int i = 0; i < count; i++) retainedIndices[i] = count - 1 - i;")],
     "fps_focus_clamp_short", "focus_lockstep"),
    ("m6_backstop_indices_untrimmed", "ApiSource",
     [("                if (count < retainedIndices.Length) Array.Resize(ref retainedIndices, count);\n", "")],
     "fps_focus_clamp_wire", "focus_lockstep"),
    ("m6_decimation_indices_shifted", "ApiSource",
     [("                    keptIndices.Add(retainedIndices[i]);\n",
       "                    keptIndices.Add(retainedIndices[i - 1]);\n")],
     "fps_focus_clamp_wire", "focus_lockstep"),

    ("m5_outlier_focus_skipped", "FocusSource",
     [("            return anyUnfocusedFrame || !focused;\n",
       "            return anyUnfocusedFrame || (dt > 0f && dt <= 1f && !focused);\n")],
     "focus_outlier_unfocused", "focus_all_focused"),
    ("m5_focus_polarity_inverted", "FocusSource",
     [("            return anyUnfocusedFrame || !focused;\n",
       "            return anyUnfocusedFrame || focused;\n")],
     "focus_all_focused", "focus_outlier_unfocused"),
    ("m5_observation_below_return", "WatcherSource",
     [("            try { tlUnfocused = FpsFocusCore.ObserveFrame(tlUnfocused, Application.isFocused, dt); } catch { }\n", ""),
      ("            tlFrames++; tlAccum += dt;\n",
       "            tlFrames++; tlAccum += dt;\n            try { tlUnfocused = FpsFocusCore.ObserveFrame(tlUnfocused, Application.isFocused, dt); } catch { }\n")],
     "focus_outlier_unfocused", "focus_all_focused"),
    ("m4_zero_window_suppressed", "LagSource",
     [('            return "[LAG-NOTICE-GATE] windows=" + _gWindows.ToString(CultureInfo.InvariantCulture)',
       '            if (_gWindows <= 0) return null;\n            return "[LAG-NOTICE-GATE] windows=" + _gWindows.ToString(CultureInfo.InvariantCulture)')],
     "lag_gate_subsecond_end", "lag_1v1_setting_off"),
    ("m4_repeated_end_guard_removed", "LagSource",
     [("            if (_gateGameStarted)\n", "            if (true)\n")],
     "lag_gate_repeated_end", "lag_gate_subsecond_end"),
    ("m4_disconnect_route_removed", "TelemetrySource",
     [('            if (_gameOpen) OnMatchEnded("room-left");\n', '')],
     "lag_gate_disconnect_before_window", "lag_gate_subsecond_end"),
    ("m3_room_keeps_capture_flag", "PoisonSource",
     [(" _lastEvidencePoint = default(LifeEpoch); _capturedBoundaryKill = false; }",
       " _lastEvidencePoint = default(LifeEpoch); }")],
     "poison_room_reset", "poison_cut_marker"),
    ('m3_capture_delayed',
     'PoisonSource',
     [['            const string killed = "v3 off why=killed:point-boundary";\n'
       '            _lastState = killed;\n'
       '            _capturedBoundaryKill = true;\n'
       '            return Note(killed);\n',
       '            return null; // Evidence left to periodic State after replacement.\n']],
     'poison_replacement_before_upkeep',
     'poison_cut_marker'),
    ('m3_prior_activation_replaced',
     'PoisonSource',
     [['            if (!priorLive || !priorActivation.SameAs(before) || priorActivation.SameAs(after)) return '
       'null;\n',
       '            priorActivation = after;\n'
       '            if (!priorLive || !priorActivation.SameAs(before) || priorActivation.SameAs(after)) return '
       'null;\n']],
     'poison_adoption_before_local_boundary',
     'poison_cut_marker'),
    ('m3_duplicate_replenishes_budget',
     'PoisonSource',
     [['            if (!after.Set || (before.Set && !PoisonLedgerCore.After(after.Ts, before.Ts))) return '
       'null;\n',
       '            OnPoint();\n'
       '            if (!after.Set || (before.Set && !PoisonLedgerCore.After(after.Ts, before.Ts))) return '
       'null;\n']],
     'poison_duplicate_and_older_stamps',
     'poison_cut_marker'),
    ('m3_stamp_wrap_numeric',
     'PoisonSource',
     [['!PoisonLedgerCore.After(after.Ts, before.Ts)', '!(after.Ts > before.Ts)']],
     'poison_stamp_wrap',
     'poison_cut_marker'),
    ('m3_sampled_kill_duplicates',
     'PoisonSource',
     [['            if (_capturedBoundaryKill && state == "v3 off why=killed:point-boundary") return null;\n', '']],
     'poison_ordinary_lines_between',
     'poison_cut_marker'),
    ('m3_only_first_epoch_captured',
     'PoisonSource',
     [['            if (_lastEvidencePoint.Set && !PoisonLedgerCore.After(after.Ts, _lastEvidencePoint.Ts)) '
       'return null;\n',
       '            if (_lastEvidencePoint.Set) return null;\n']],
     'poison_two_games',
     'poison_cut_marker'),
    ('m3_room_keeps_evidence_epoch',
     'PoisonSource',
     [[' _lastEvidencePoint = default(LifeEpoch);', '']],
     'poison_room_reset',
     'poison_cut_marker'),
    ('m3_already_stale_fabricates_kill',
     'PoisonSource',
     [['!priorLive || !priorActivation.SameAs(before) || priorActivation.SameAs(after)',
       '!priorLive || priorActivation.SameAs(after)']],
     'poison_duplicate_and_older_stamps',
     'poison_cut_marker'),
    ('m3_boundary_capture_removed',
     'PoisonSyncSource',
     [['string pointBoundaryLine = _v3Log.OnPoint(evidenceBefore, _ledger.PointEpoch, evidenceActivation, '
       'evidenceLive);',
       'string pointBoundaryLine = null;']],
     'poison_replacement_before_upkeep',
     'poison_cut_marker'),
    ('m3_activation_capture_removed',
     'PoisonSyncSource',
     [['string activationBoundaryLine = _v3Log.OnPoint(evidenceBefore, _ledger.PointEpoch, evidenceActivation, '
       'evidenceLive);',
       'string activationBoundaryLine = null;']],
     'poison_adoption_before_local_boundary',
     'poison_cut_marker'),
    ('m3_upkeep_capture_removed',
     'PoisonSyncSource',
     [['string upkeepBoundaryLine = _v3Log.OnPoint(evidenceBefore, _ledger.PointEpoch, evidenceActivation, '
       'evidenceLive);',
       'string upkeepBoundaryLine = null;']],
     'poison_ordinary_lines_between',
     'poison_cut_marker'),
    ("m2_suppression_room_scoped", "StallSource",
     [("            GameSuppressed = 0;\n", "")],
     "stall_suppressed_per_game", "stall_cap"),
    ("m2_room_budget_not_reset", "StallSource",
     [("            _roomLines = 0;\n", "")],
     "stall_room_reset", "stall_suppressed_per_game"),
    ("m1_rising_gate_always_open", "StallSource",
     [("_bandFloor = LOW_MARK + 1; _bandWidth = QUEUE_BOUND - LOW_MARK - 1;",
       "_bandFloor = -1; _bandWidth = 0;")],
     "stall_steady_bands", "stall_night"),
    ("m1_rise_restarted_at_open", "StallSource",
     [("                    _openMs = nowMs;\n", "                    _openMs = nowMs;\n                    _riseStartMs = nowMs;\n")],
     "stall_band_crossings", "stall_terminal_fast"),
    ("m1_extra_comparison", "StallSource",
     [("return unchecked((uint)(depth - _bandFloor)) > _bandWidth;",
       "return depth >= 0 && unchecked((uint)(depth - _bandFloor)) > _bandWidth;")],
     "stall_steady_bands", "stall_night"),
    ("h1_terminal_ignored_in_core_game_end", "StallSource",
     [("            if (terminalFrameMs > _worstFrameMs) _worstFrameMs = terminalFrameMs;\n", "")],
     "stall_terminal_hitch_game_end", "stall_night"),
    ("h1_terminal_ignored_in_core_depth_close", "StallSource",
     [("            if (terminalFrameMs > _worstFrameMs) _worstFrameMs = terminalFrameMs;\n", "")],
     "stall_terminal_hitch_depth_close", "stall_night"),
    ("h1_terminal_counted_as_frame", "StallSource",
     [("            if (terminalFrameMs > _worstFrameMs) _worstFrameMs = terminalFrameMs;\n",
       "            if (terminalFrameMs > _worstFrameMs) _worstFrameMs = terminalFrameMs;\n            _frames++;\n")],
     "stall_terminal_fast", "stall_frames_hitch"),
    ("h1_game_end_obs_removed", "TelemetrySource",
     [("_stall.Flush(StallNowMs(), _stallStreams, _gameSeq, ReceiverWallGapMsNow())",
       "_stall.Flush(StallNowMs(), _stallStreams, _gameSeq, 0)")],
     "stall_terminal_hitch_game_end", "stall_terminal_hitch_depth_close"),
    ("h1_depth_close_obs_removed", "TelemetrySource",
     [("_stall.Open && qi <= InboundStallCore.QUEUE_BOUND ? ReceiverWallGapMsNow() : 0", "0")],
     "stall_terminal_hitch_depth_close", "stall_terminal_hitch_game_end"),
    # required: the detector threshold removed
    ("stall_threshold_removed", "StallSource",
     [("            if (depth > QUEUE_BOUND)\n", "            if (depth > 0)\n"),
      ("_bandFloor = QUEUE_BOUND + 1; _bandWidth = (uint)(_peak - _bandFloor);",
       "_bandFloor = LOW_MARK + 1; _bandWidth = (uint)(_peak - _bandFloor);")],
     "stall_night", "stall_frames_hitch"),
    ("stall_min_duration_removed", "StallSource",
     [("            if (dur <= MIN_STALL_MS) return null;\n", "")],
     "stall_ordinary_spikes", "stall_night"),
    ("stall_frames_ignored", "StallSource",
     [("            if (_worstFrameMs >= FRAME_OK_MS)\n", "            if (false)\n")],
     "stall_frames_hitch", "stall_night"),
    ("stall_cap_removed", "StallSource",
     [("            if (_roomLines >= MAX_LINES_PER_ROOM) { GameSuppressed++; return null; }\n", "")],
     "stall_cap", "stall_night"),
    ("stall_streams_always_stopped", "StallSource",
     [("                    if (!advanced) stopped++;\n", "                    stopped++;\n")],
     "stall_streams_flowing", "stall_night"),
    # required: the reserve removed
    ("jitter_reserve_removed", "JitterSource",
     [("            if (big && _reserveUsed < RESERVE) { _reserveUsed++; isReserve = true; return true; }\n", "")],
     "jitter_reserve", "stall_night"),
    ("jitter_top_only_logged", "JitterSource",
     [("            _qualifying++;\n            NoteTop(actor, arrivalMs, senderMs, excessMs, game);\n", "            _qualifying++;\n"),
      ("            if (_routineUsed < TOTAL - RESERVE) { _routineUsed++; return true; }\n",
       "            if (_routineUsed < TOTAL - RESERVE) { _routineUsed++; NoteTop(actor, arrivalMs, senderMs, excessMs, game); return true; }\n")],
     "jitter_top", "stall_night"),
    # required: the poison fix reverted (the per-room 24-line cap, no reset at the boundary)
    ("poison_fix_reverted", "PoisonSource",
     [("        internal const int PER_POINT = 12;\n", "        internal const int PER_POINT = 24;\n"),
      ("        internal void OnPoint() { _point = 0; _cutMarked = false; }\n", "        internal void OnPoint() { }\n")],
     "poison_kill_every_epoch", "poison_cut_marker"),
    ("poison_marker_repeats", "PoisonSource",
     [("            if (_cutMarked) return null;\n", "")],
     "poison_cut_marker", "poison_kill_every_epoch"),
    ("lag_gate_not_counted", "LagSource",
     [("                if (!SeatEligible()) { _gNotPlain1v1++; ResetAll(logExits: true, why: \"seat\"); return; }\n",
       "                if (!SeatEligible()) { ResetAll(logExits: true, why: \"seat\"); return; }\n")],
     "lag_1v2_gate", "lag_1v1_fires"),
    ("lag_enters_not_counted", "LagSource",
     [("                        case Edge.Enter: _gEnters++; LogEdge((State)s, \"enter\", slot, nowS, null); changed = true; break;\n",
       "                        case Edge.Enter: LogEdge((State)s, \"enter\", slot, nowS, null); changed = true; break;\n")],
     "lag_1v1_fires", "lag_1v2_gate"),
    ("lag_gate_line_dropped", "LagSource",
     [("                try { string g = GateLine(); if (g != null) Plugin.Log?.LogInfo(g); } catch { }\n", "")],
     "lag_1v1_setting_off", "lag_bar_met_1v2"),
    ("lag_opp_stream_bar_off_by_one", "LagSource",
     [("        internal const int OPP_STREAM_MIN_WINDOWS = 2;", "        internal const int OPP_STREAM_MIN_WINDOWS = 3;")],
     "lag_bar_met_1v2", "lag_1v2_gate"),
    ("focus_flag_inverted", "FocusSource",
     [("        internal static int BucketFlag(bool anyUnfocusedFrame) { return anyUnfocusedFrame ? 0 : 1; }",
       "        internal static int BucketFlag(bool anyUnfocusedFrame) { return anyUnfocusedFrame ? 1 : 0; }")],
     "focus_lockstep", "lag_1v2_gate"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(tag, overrides):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep]
    cmd.append("-p:DecimatedSource=" + DECIMATED_OUT)
    cmd.append("-p:FpsWireSource=" + extract_fps_wire(tag, overrides))
    cmd.append("-p:ReplicaMethodsSource=" + extract_replica(tag, overrides))
    for k, v in overrides.items():
        if k in COMPILED_SOURCES:
            cmd.append("-p:%s=%s" % (k, v))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "NetStallTests.dll")


def run(dll, cases=(), overrides=None):
    env = os.environ.copy()
    for name, result in structural_pins(overrides).items():
        env["NET_STALL_PIN_" + name] = result
    r = subprocess.run(["dotnet", dll] + list(cases), capture_output=True, text=True, env=env)
    return r.returncode, r.stdout.strip()


def main():
    only = sys.argv[1:]
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {k: sha(os.path.join(PLUGIN, f)) for k, f in SOURCES.items()}
    before["Decimated"] = sha(os.path.join(PLUGIN, DECIMATED_FROM))
    print("work/DecimatedList.cs cut from plugin/%s, sha256 %s" % (DECIMATED_FROM, extract_decimated()))
    for k, f in SOURCES.items():
        print("plugin/%s sha256 %s" % (f, before[k]))
    ok = True

    names = [m[0] for m in MUTANTS]
    if len(set(names)) != len(names):
        print("BAD mutant table: a name appears twice")
        ok = False

    dll = build("base", {})
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0
    cases = [l.split()[1] for l in out.splitlines() if l.startswith(("PASS ", "FAIL "))]
    targeted = set(m[3] for m in MUTANTS)
    missing = sorted(set(cases) - targeted)
    if missing:
        print("BAD: cases without a mutant:", ", ".join(missing))
        ok = False
    if not ok:
        print("RESULT FAIL (controls must be green before mutants)")
        return 1

    caught = 0
    run_set = [m for m in MUTANTS if not only or m[0] in only]
    for name, key, edits, target, control in run_set:
        src = os.path.join(PLUGIN, SOURCES[key])
        raw = open(src, "rb").read().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        bad = False
        for old, new in edits:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = raw.count(o)
            if count != 1:
                print("BAD mutant %s: anchor occurs %d times: %r" % (name, count, old[:70]))
                bad = True
                break
            raw = raw.replace(o, n)
        if bad:
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + "_" + SOURCES[key])
        open(path, "wb").write(raw.encode("utf-8"))
        overrides = {key: path}
        mdll = build("mut_" + name, overrides) if key in COMPILED_SOURCES | EXTRACTED_SOURCES else dll
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        trc, tout = run(mdll, [target], overrides)
        crc, cout = run(mdll, [control], overrides)
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
        for l in tout.splitlines():
            if l.startswith("FAIL "):
                print("    " + l[:300])
    print("mutants: %d of %d caught" % (caught, len(run_set)))
    after = {k: sha(os.path.join(PLUGIN, f)) for k, f in SOURCES.items()}
    after["Decimated"] = sha(os.path.join(PLUGIN, DECIMATED_FROM))
    same = after == before
    print("tracked files unchanged:", same)
    ok = ok and same
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
