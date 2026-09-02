using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Single owner-set controller for Application.runInBackground (music
    /// design v3 §7 / G12). Before this existed, each consumer kept its own
    /// prior-value snapshot — two independent snapshot/restore pairs on one
    /// global engine flag is a lost-update machine (the second releaser
    /// restores a "baseline" the first releaser already changed). Instead:
    /// the FIRST acquire captures the OS baseline, the flag is forced true
    /// while ANY owner holds, and the baseline is restored only after the
    /// LAST release. The baseline is re-captured fresh on each 0→1 owner
    /// transition, matching the old per-room-entry snapshot behavior.
    ///
    /// Owners in this batch: "room" (GameStateWatcher's in-room hold — the
    /// v1.26.8 matchmaking-freeze fix) and "broadcast-music" (MusicEngine,
    /// held for the lifetime of enabled broadcast music so menu/idle
    /// playback ticks while unfocused).
    ///
    /// Main-thread-only BY DESIGN: every call site is the persistent
    /// behaviour's Update/poll chain, and Application.runInBackground is a
    /// main-thread Unity API — a lock could serialize the bookkeeping but
    /// would not make an off-thread Unity write legal, so off-thread calls
    /// are logged and refused instead (module contract).
    ///
    /// External writers: nothing else in the mod or the game writes
    /// runInBackground (grep-verified at introduction); if a future writer
    /// appears mid-hold, the restore still writes the captured baseline —
    /// same accepted limitation the old snapshot code had.
    /// </summary>
    internal static class RunInBackgroundLease
    {
        private static readonly HashSet<string> owners = new HashSet<string>(StringComparer.Ordinal);
        private static bool baselineCaptured = false;
        private static bool baseline = false;
        // Stamped by the first caller (always the main thread in practice —
        // the persistent behaviour's Update chain runs long before any
        // hypothetical off-thread code could reach this class).
        private static int mainThreadId = -1;

        /// <summary>Idempotent per owner name: a second Acquire for a name
        /// already holding is a no-op (no baseline re-capture, no log spam) —
        /// which is what makes a respawned MusicEngine host safe to
        /// re-acquire from without bookkeeping on its side.</summary>
        internal static void Acquire(string owner)
        {
            if (string.IsNullOrEmpty(owner)) return;
            if (!OnMainThread("Acquire", owner)) return;
            if (!owners.Add(owner)) return;
            try
            {
                if (owners.Count == 1)
                {
                    // 0→1 transition: this is the value the last release
                    // restores. Captured BEFORE the force-true write below.
                    baseline = Application.runInBackground;
                    baselineCaptured = true;
                    Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' acquired — forcing true (baseline was {baseline})");
                }
                else
                {
                    Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' acquired ({owners.Count} holders)");
                }
                // Re-asserted for every NEW owner, not just the first — free,
                // and heals a stray external write without a per-tick poll.
                Application.runInBackground = true;
            }
            catch (Exception ex)
            {
                try { Plugin.Log?.LogWarning($"[FOCUS] runInBackground lease Acquire('{owner}') failed: {ex.Message}"); } catch { }
            }
        }

        /// <summary>Idempotent: releasing a name that does not hold is a
        /// no-op. Restores the captured baseline only when the LAST owner
        /// releases; the baseline slot is cleared so the next hold cycle
        /// captures a fresh one (the OS value may legitimately change
        /// between holds).</summary>
        internal static void Release(string owner)
        {
            if (string.IsNullOrEmpty(owner)) return;
            if (!OnMainThread("Release", owner)) return;
            if (!owners.Remove(owner)) return;
            if (owners.Count > 0)
            {
                Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' released ({owners.Count} still holding)");
                return;
            }
            try
            {
                if (baselineCaptured)
                    Application.runInBackground = baseline;
                Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' released (last holder) — restored to {baseline}");
            }
            catch (Exception ex)
            {
                try { Plugin.Log?.LogWarning($"[FOCUS] runInBackground lease Release('{owner}') restore failed: {ex.Message}"); } catch { }
            }
            finally
            {
                baselineCaptured = false;
            }
        }

        private static bool OnMainThread(string op, string owner)
        {
            int tid = Thread.CurrentThread.ManagedThreadId;
            if (mainThreadId == -1) mainThreadId = tid;
            if (tid == mainThreadId) return true;
            try { Plugin.Log?.LogWarning($"[FOCUS] RunInBackgroundLease.{op}('{owner}') called off the main thread (tid {tid}) — refused"); } catch { }
            return false;
        }
    }
}
