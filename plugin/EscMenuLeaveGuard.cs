using System;
using System.Reflection;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Confirm-to-leave gate on the ONE vanilla control wired
    /// straight to disconnect (Aug 12, bug 208 session, DC #1).
    ///
    /// The esc menu's "MAIN MENU" button (scene path
    /// Game/UI/UI_Game/Canvas/EscapeMenu/Main/Group/Menu) is the only Button
    /// in the game's entire serialized data whose persistent onClick targets
    /// NetworkConnectionHandler.NetworkRestart — proven by a UnityPy scan of
    /// all 145 data files, twice independently. One stray click there during
    /// a live competitive sitting is an instant, unrecoverable disconnect
    /// (Sid: "i was playing, and then i wasn't" — a mouse press during an
    /// FFA pick transition landed on it).
    ///
    /// Scope discipline (#288, Codex convergence): the gate is BUTTON-scoped,
    /// never a prefix on NetworkRestart itself — NetworkRestart is the
    /// codebase's one honest abort-to-menu recovery lever (#252c) and every
    /// watchdog/leave path must keep it unconditionally callable. Armed only
    /// in mod-issued competitive rooms (constant room identity, #321; the
    /// room-code ranked population, #286, is a KNOWN residual — its
    /// detection is async and a wrong gate there risks recovery paths).
    /// Spectator seats never ARM it (a one-click leave is correct there);
    /// carrying an already-armed guard into a casual or spectated room is
    /// prevented by the unconditional Disarm at the top of OnJoinedRoom,
    /// not by the arm gate alone.
    ///
    /// Identification is by persistent-call METHOD NAME ("NetworkRestart"),
    /// never by label text — menu labels are localized (#47).
    ///
    /// STRANDING INVARIANT — the design rule everything below serves: a click
    /// on that button always has a live route, and the intended degradation
    /// everywhere is vanilla one-click leave, never a dead button.
    ///
    /// THREE review rounds put a blocker in this transaction each time, and
    /// the first two fixes only moved it — because both made OUR HANDLER the
    /// safety rail. The rail is now VANILLA (r3's structural correction), and
    /// that is what makes the design self-healing rather than merely careful:
    ///
    ///  * every Arm STARTS by restoring the candidate button's vanilla call
    ///    to RuntimeOnly. Whatever a previous degraded teardown left behind —
    ///    including "vanilla Off with no handler" — is repaired before
    ///    anything else is touched. This is the one property the earlier
    ///    orderings lacked: they were locally sound but composed a dead state
    ///    when a failed Disarm was followed by a failed Arm.
    ///  * every subsequent step aborts to a state where vanilla is live: the
    ///    defensive detach must SUCCEED (a swallowed throw there could leave
    ///    two handlers and spend the confirm on one click), and a failed
    ///    AddListener leaves vanilla RuntimeOnly.
    ///  * only the FINAL step disables vanilla, and its failure is never
    ///    undone: Off applied => our handler is the route; not applied =>
    ///    both fire and vanilla leaves on the first click.
    ///  * Disarm restores before it detaches, and does NOT guarantee success
    ///    — it catches restore failure. That is survivable because the next
    ///    SUCCESSFUL Arm repairs that button (a later attempt can itself
    ///    fail, and a UI rebuild may hand us a different button; in both
    ///    cases the surviving button still has a live route).
    ///  * the confirmed-leave path reaches NetworkRestart() even if Disarm
    ///    or logging throws.
    ///  * ESCALATION: the guard never depends on the player SEEING the cue. A
    ///    second ignored click leaves regardless of pacing, so "I clicked
    ///    MAIN MENU and nothing happens" cannot outlive two clicks even with
    ///    the toast surface broken. That was the one route to "cannot leave"
    ///    with no exception anywhere — found by self-audit, not by review.
    ///    Precisely: the counter is per ARMED ATTACHMENT (a mid-room button
    ///    rebuild resets it) and a fail-open final flip means one stray can
    ///    still leave immediately — the ceiling bounds the STRAND, not the
    ///    number of strays a sitting tolerates.</summary>
    internal static class EscMenuLeaveGuard
    {
        private const float ConfirmWindowSeconds = 4f;
        private const float RescanCooldownSeconds = 5f;

        private static bool armed;
        private static Component gatedButton;          // the uGUI Button (reflected type)
        private static object gatedOnClick;            // UnityEventBase instance
        private static int gatedPersistentIndex = -1;
        private static MethodInfo gatedRemoveListener;  // resolved at Arm time
        private static float lastClickAt = -999f;
        private static float lastScanAt = -999f;
        private static int ignoredClicks;
        private static string gatedRoom = "";
        private static float lastMatchWarnAt = -999f;
        private static int lastMatchWarnCount = -1;

        /// <summary>ONE handler instance for the process (r2 find 4): every
        /// Arm removes it before adding it, so a partial AddListener failure
        /// can never leave two copies subscribed — two copies would spend the
        /// confirm on a single click (first stamps, second confirms).</summary>
        private static readonly UnityEngine.Events.UnityAction Handler = OnGatedClick;

        /// <summary>Shared scene scan for THE disconnect button (persistent-
        /// call method name "NetworkRestart" — never label text, #47).
        /// Extracted Aug 30 so EscLeaveRow can locate the esc-menu container
        /// and a safe clone template READ-ONLY without duplicating the scan
        /// (#330). Returns the match count; anything but exactly 1 means the
        /// scene invariant broke — every caller fails open.</summary>
        internal static int FindDisconnectButton(out Component btn, out object onClickEvent, out int persistentIdx)
        {
            btn = null; onClickEvent = null; persistentIdx = -1;
            int matches = 0;
            try
            {
                try { UIFactory.InitTypes(); } catch { }
                var btnType = UIFactory.tButton;
                if (btnType == null) return 0;
                foreach (var obj in Resources.FindObjectsOfTypeAll(btnType))
                {
                    var comp = obj as Component;
                    if (comp == null || !comp.gameObject.scene.IsValid()) continue;   // skip assets/prefabs
                    var pOnClick = comp.GetType().GetProperty("onClick");
                    var oc = pOnClick?.GetValue(comp) as UnityEngine.Events.UnityEventBase;
                    if (oc == null) continue;
                    for (int i = 0; i < oc.GetPersistentEventCount(); i++)
                    {
                        if (oc.GetPersistentMethodName(i) != "NetworkRestart") continue;
                        matches++;
                        btn = comp; onClickEvent = oc; persistentIdx = i;
                    }
                }
            }
            catch { }
            return matches;
        }

        /// <summary>Idempotent; safe to call every poll tick, and DOES need a
        /// recurring caller (r2 find 3 — join-edge-only callers cannot retry
        /// a scan that failed or re-arm a button replaced mid-room). Armed
        /// state with a live button returns immediately; only a real rescan
        /// is throttled to one per RescanCooldownSeconds, so a room with no
        /// esc menu cannot turn the poll into a per-tick
        /// FindObjectsOfTypeAll sweep.</summary>
        internal static void Arm()
        {
            try
            {
                if (armed)
                {
                    // r3 find 5: if BOTH room-exit observers missed a fast
                    // transition and the same scene button survived, an
                    // ignored click from the previous room must not count
                    // toward this room's escalation.
                    if (gatedButton != null)
                    {
                        string roomNow = PhotonNetwork.CurrentRoom?.Name ?? "";
                        if (roomNow != gatedRoom)
                        {
                            gatedRoom = roomNow;
                            ignoredClicks = 0;
                            lastClickAt = -999f;
                        }
                        return;                        // still armed on a live button
                    }
                    // Unity fake-null: the button was destroyed => re-arm.
                    // The replacement button carries vanilla wiring, so this
                    // window is lost protection, never a dead leave.
                    armed = false;
                    gatedButton = null; gatedOnClick = null; gatedPersistentIndex = -1;
                    gatedRemoveListener = null;
                    Plugin.Log.LogInfo("[ESC-GUARD] gated button was destroyed — re-arming");
                }
                if (Time.unscaledTime - lastScanAt < RescanCooldownSeconds) return;
                lastScanAt = Time.unscaledTime;

                Component found; object foundOnClick; int foundIdx;
                int matches = FindDisconnectButton(out found, out foundOnClick, out foundIdx);
                // Exactly one is the scene-proven invariant; anything else
                // means the assumption broke (game update, another mod) —
                // fail OPEN to vanilla rather than gate the wrong control.
                if (matches != 1 || found == null)
                {
                    // Throttled: this runs on the rescan cadence, and an
                    // unthrottled warning here would emit ~12 lines/minute
                    // for a whole session and evict real content from the
                    // capped bug-report bundles (#304 territory).
                    if (matches != 1
                        && (matches != lastMatchWarnCount || Time.unscaledTime - lastMatchWarnAt > 60f))
                    {
                        lastMatchWarnCount = matches;
                        lastMatchWarnAt = Time.unscaledTime;
                        Plugin.Log.LogWarning($"[ESC-GUARD] expected exactly 1 NetworkRestart button, found {matches} — guard not armed");
                    }
                    return;
                }
                lastMatchWarnCount = -1;

                // ORDER IS THE SAFETY PROPERTY, and VANILLA is the safety rail
                // (review r3's structural correction — my two earlier
                // orderings made OUR handler the rail, and each left a
                // composed state where a degraded Disarm followed by a failed
                // Arm killed the button).
                //
                //  1. Resolve reflection handles — mutates nothing.
                //  2. RESTORE the candidate's vanilla call to RuntimeOnly
                //     FIRST. This is what makes the whole thing self-healing:
                //     whatever state a previous degraded teardown left, every
                //     Arm begins by making the button work again. Abort
                //     untouched if it throws.
                //  3. Defensive RemoveListener — must SUCCEED (a swallowed
                //     throw here could leave two handlers, which spends the
                //     confirm on one click). Abort if it throws; vanilla is
                //     live from step 2, so aborting is safe.
                //  4. AddListener. If it throws, vanilla is still RuntimeOnly
                //     — button works, protection simply not armed.
                //  5. Commit bookkeeping, so Disarm can clean up step 6.
                //  6. Flip vanilla Off. NEVER undone on throw: Off-applied =>
                //     our handler is the route; not-applied => both fire and
                //     vanilla leaves on the first click (today's behaviour).
                var addListener = foundOnClick.GetType().GetMethod("AddListener",
                    new Type[] { typeof(UnityEngine.Events.UnityAction) });
                var removeListener = foundOnClick.GetType().GetMethod("RemoveListener",
                    new Type[] { typeof(UnityEngine.Events.UnityAction) });
                if (addListener == null || removeListener == null) return;   // nothing mutated yet

                var evt = (UnityEngine.Events.UnityEventBase)foundOnClick;
                try
                {
                    evt.SetPersistentListenerState(foundIdx,
                        UnityEngine.Events.UnityEventCallState.RuntimeOnly);
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[ESC-GUARD] could not restore vanilla call ({ex.Message}) — not arming");
                    return;
                }
                try { removeListener.Invoke(foundOnClick, new object[] { Handler }); }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[ESC-GUARD] defensive detach failed ({ex.Message}) — not arming");
                    return;
                }
                addListener.Invoke(foundOnClick, new object[] { Handler });

                gatedButton = found;
                gatedOnClick = foundOnClick;
                gatedPersistentIndex = foundIdx;
                gatedRemoveListener = removeListener;
                gatedRoom = PhotonNetwork.CurrentRoom?.Name ?? "";
                lastClickAt = -999f;
                ignoredClicks = 0;
                armed = true;

                try
                {
                    evt.SetPersistentListenerState(foundIdx,
                        UnityEngine.Events.UnityEventCallState.Off);
                    Plugin.Log.LogInfo("[ESC-GUARD] leave confirm armed on esc-menu disconnect button");
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning("[ESC-GUARD] vanilla call state unknown after flip "
                        + $"({ex.Message}) — leave still works, confirm may be bypassed");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[ESC-GUARD] arm failed: {ex.Message}");
            }
        }

        /// <summary>Idempotent. Called from the Photon OnLeftRoom callback
        /// (primary) and the watcher's Left-room poll branch (backup — the
        /// 10 Hz poll can miss a fast leave+join edge, review r1 find 4).</summary>
        internal static void Disarm()
        {
            // Resets run even when never armed (r3 find 3): a scan that FAILED
            // in room A stamped the cooldown, and without clearing it here
            // room B stayed unprotected for the rest of that window.
            lastScanAt = -999f;
            ignoredClicks = 0;
            lastClickAt = -999f;
            gatedRoom = "";
            if (!armed) return;
            armed = false;
            try
            {
                var onClick = gatedOnClick as UnityEngine.Events.UnityEventBase;
                if (onClick != null && gatedPersistentIndex >= 0)
                {
                    // RuntimeOnly is the state the scene serializes for this
                    // call (level0: call-state int 2 — review-verified).
                    // Restore FIRST, detach second: if the restore throws, our
                    // handler is still subscribed and the button still leaves
                    // (its !armed branch degrades to an immediate leave), and
                    // the next Arm's step 2 restores vanilla on that same
                    // button — so a degraded teardown self-heals rather than
                    // composing into a dead state (r3 blocker).
                    onClick.SetPersistentListenerState(gatedPersistentIndex,
                        UnityEngine.Events.UnityEventCallState.RuntimeOnly);
                    if (gatedRemoveListener != null)
                        gatedRemoveListener.Invoke(gatedOnClick, new object[] { Handler });
                }
                Plugin.Log.LogInfo("[ESC-GUARD] disarmed — vanilla wiring restored");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[ESC-GUARD] disarm restore failed: {ex.Message}");
            }
            finally
            {
                gatedButton = null; gatedOnClick = null; gatedPersistentIndex = -1;
                gatedRemoveListener = null;
            }
        }

        private static void OnGatedClick()
        {
            // Classify first; ANY failure classifies as leave — the button's
            // contract with the player is "this leaves the match", and the
            // guard must degrade toward honoring it (review r1 blocker 2).
            bool leaveNow;
            try
            {
                if (!armed)
                {
                    leaveNow = true;   // stale listener after a failed restore: vanilla behavior
                }
                else if (Time.unscaledTime - lastClickAt < ConfirmWindowSeconds)
                {
                    leaveNow = true;   // confirmed inside the window
                }
                else
                {
                    // Stamp BEFORE anything that can throw, so a throwing log
                    // listener can never wedge the confirm state.
                    lastClickAt = Time.unscaledTime;
                    ignoredClicks++;
                    // ESCALATION — the guard must never depend on the player
                    // SEEING the cue (self-audit, the one way to reach "I
                    // cannot leave" with no exception anywhere): a player
                    // clicking slower than the window would otherwise
                    // re-stamp forever and never leave. Any SECOND ignored
                    // click leaves, whatever the pacing. Net contract: one
                    // stray click is absorbed — the actual failure that cost
                    // Sid a match — and a player who means it is out in two
                    // clicks. The accepted cost is that two strays in one
                    // sitting, however far apart, still leave; that is
                    // strictly better than today's one.
                    leaveNow = ignoredClicks >= 2;
                }
            }
            catch { leaveNow = true; }

            if (!leaveNow)
            {
                try { Plugin.Log.LogInfo("[ESC-GUARD] leave click intercepted — confirm window open"); } catch { }
                try
                {
                    // Critical surface: renders regardless of the optional
                    // ShowNotifications preference (review r1 find 3 — behind
                    // the pref, the first click read as "nothing happened").
                    // The cue is now a courtesy, not a safety mechanism: the
                    // escalation below leaves on the second ignored click
                    // whether or not this ever renders.
                    CompetitiveUI.ShowNotificationCritical(
                        I18n.Tr("Click MAIN MENU again to leave the match."),
                        new Color(1f, 0.75f, 0.4f), ConfirmWindowSeconds);
                }
                catch { }
                return;
            }

            // Confirmed (or degraded) leave, through the ONE shared exit seam
            // (CompetitiveExit.Request — r1 finding 18: two hand-rolled
            // Disarm+NetworkRestart copies would silently diverge the moment
            // a future settlement step lands in the seam). The seam isolates
            // each step, so NetworkRestart is reached even if Disarm or
            // logging throws.
            try { Plugin.Log.LogInfo("[ESC-GUARD] leave confirmed — disconnecting"); } catch { }
            CompetitiveExit.Request("esc-menu");
        }
    }
}
