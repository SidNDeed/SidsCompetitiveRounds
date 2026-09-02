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
    /// the FIRST committed acquire captures the OS baseline, the flag is
    /// forced true while any COMMITTED owner holds, and the baseline is
    /// restored only after the LAST release. The baseline is re-captured
    /// fresh on each committed 0→1 owner transition, matching the old
    /// per-room-entry snapshot behavior.
    ///
    /// TRANSACTIONAL (impl review I2): both verbs return success, and owner
    /// state commits ONLY after the Unity capture/write actually landed. A
    /// failed Acquire inserts no owner — so the caller's retry is a real
    /// acquire, never a duplicate no-op that leaves a baseline-false seat
    /// pausing when unfocused forever. A failed last-owner restore RETAINS
    /// the owner and the captured baseline for retry; nothing is discarded
    /// until the restore write succeeds, so a later hold cycle can never
    /// capture the still-forced-true value as its "baseline".
    ///
    /// Owners in this batch: "room" (GameStateWatcher's in-room hold — the
    /// v1.26.8 matchmaking-freeze fix; consumes the bools and retries on its
    /// next poll tick) and "broadcast-music" (MusicEngine, held for the
    /// lifetime of enabled broadcast music so menu/idle playback ticks while
    /// unfocused).
    ///
    /// Main-thread-only BY DESIGN: every call site is the persistent
    /// behaviour's Update/poll chain, and Application.runInBackground is a
    /// main-thread Unity API — a lock could serialize the bookkeeping but
    /// would not make an off-thread Unity write legal, so off-thread calls
    /// are refused (return false) instead (module contract).
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
        // Failure logs are throttled: the room owner retries at poll cadence,
        // so a persistent Unity fault would otherwise warn ~10x/second.
        // Environment.TickCount, not Time.realtimeSinceStartup — the throttle
        // is reachable from the off-thread refusal path where Unity time APIs
        // themselves throw.
        private static int lastFailLogTick = int.MinValue;

        /// <summary>Idempotent per owner name: a second Acquire for a name
        /// already holding returns true untouched (no baseline re-capture, no
        /// log spam). Returns FALSE — committing nothing — when the Unity
        /// capture/force-true throws or the call is off-thread (I2): the
        /// caller must treat false as "not held" and retry, so a respawned
        /// MusicEngine host or the room poll re-acquires for real instead of
        /// inheriting a phantom hold.</summary>
        internal static bool Acquire(string owner)
        {
            if (string.IsNullOrEmpty(owner)) return false;
            if (!OnMainThread("Acquire", owner)) return false;
            if (owners.Contains(owner)) return true;
            bool capturedThisCall = false;
            try
            {
                if (owners.Count == 0)
                {
                    // 0→1 transition: this is the value the last release
                    // restores. Captured BEFORE the force-true write below.
                    baseline = Application.runInBackground;
                    baselineCaptured = true;
                    capturedThisCall = true;
                }
                // Asserted for every NEW owner, not just the first — free,
                // and heals a stray external write without a per-tick poll.
                Application.runInBackground = true;
                // Committed only now, after the Unity write landed (I2).
                owners.Add(owner);
                if (owners.Count == 1)
                    Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' acquired — forcing true (baseline was {baseline})");
                else
                    Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' acquired ({owners.Count} holders)");
                return true;
            }
            catch (Exception ex)
            {
                // Roll back a capture made this call — nothing committed, so
                // the next attempt's 0→1 capture reads a fresh true baseline.
                if (capturedThisCall) baselineCaptured = false;
                WarnThrottled($"[FOCUS] runInBackground lease Acquire('{owner}') failed (nothing committed, caller should retry): {ex.Message}");
                return false;
            }
        }

        /// <summary>Idempotent: releasing a name that does not hold returns
        /// true (nothing to release). While other owners remain, removal is
        /// pure bookkeeping (no Unity write) and always succeeds. For the
        /// LAST owner the captured baseline is restored FIRST; the owner and
        /// baseline are discarded only when that write lands (I2) — a thrown
        /// restore returns false and RETAINS both so the caller's retry is a
        /// real last-owner release.</summary>
        internal static bool Release(string owner)
        {
            if (string.IsNullOrEmpty(owner)) return true;
            if (!OnMainThread("Release", owner)) return false;
            if (!owners.Contains(owner)) return true;
            if (owners.Count > 1)
            {
                owners.Remove(owner);
                Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' released ({owners.Count} still holding)");
                return true;
            }
            try
            {
                if (baselineCaptured)
                    Application.runInBackground = baseline;
                // Committed only now, after the restore landed (I2). The next
                // hold cycle captures a fresh baseline (the OS value may
                // legitimately change between holds).
                owners.Remove(owner);
                baselineCaptured = false;
                Plugin.Log?.LogInfo($"[FOCUS] runInBackground lease: '{owner}' released (last holder) — restored to {baseline}");
                return true;
            }
            catch (Exception ex)
            {
                WarnThrottled($"[FOCUS] runInBackground lease Release('{owner}') restore failed (owner + baseline retained for retry): {ex.Message}");
                return false;
            }
        }

        private static bool OnMainThread(string op, string owner)
        {
            int tid = Thread.CurrentThread.ManagedThreadId;
            if (mainThreadId == -1) mainThreadId = tid;
            if (tid == mainThreadId) return true;
            WarnThrottled($"[FOCUS] RunInBackgroundLease.{op}('{owner}') called off the main thread (tid {tid}) — refused");
            return false;
        }

        private static void WarnThrottled(string msg)
        {
            int now = Environment.TickCount;
            if (lastFailLogTick != int.MinValue && unchecked(now - lastFailLogTick) < 5000) return;
            lastFailLogTick = now;
            try { Plugin.Log?.LogWarning(msg); } catch { }
        }
    }
}
