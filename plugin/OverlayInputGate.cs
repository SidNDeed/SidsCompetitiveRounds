using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Full gameplay-input gate for the open F5 overlay (Spirit +
    /// Stan, Aug 27; owner-approved; design-reviewed by Codex Aug 30).
    ///
    /// Complaints: clicking overlay buttons fired the gun ("I've almost shot
    /// people trying to put in a bug report"), Space readied players up, and
    /// Escape-to-close-the-menu ABORTED a match-found join (vanilla
    /// EscapeMenuHandler.Update calls NetworkRestart while the loading
    /// screen is up — the ranked 1v1 join path, learning #102).
    ///
    /// Shape: Harmony prefixes/postfixes that each READ
    /// NativeUI.InputCaptureActive live (a visibility-backed predicate, so a
    /// wedged flag can never strand inputs — the #75 discipline). The one
    /// piece of held state is the fire latch below, and it self-releases the
    /// moment the physical button is genuinely neutral. The review
    /// enumerated the raw-input readers that bypass GeneralInput; each gets
    /// its own gate below. The per-mode card-pick guards live with their
    /// existing patches (VanillaFixes.CardPickChatInputGuardPatch, FfaMode's
    /// pick loop), the Gun.Attack / Block.TryBlock belts in Plugin.cs stay
    /// as update-order protection, and EventSystemGuard below owns the
    /// NAVIGATION-Submit channel (the one input path a raycast backdrop and
    /// these prefixes cannot see).</summary>
    internal static class OverlayInputGate
    {
        internal static bool GateActive
        {
            get { try { return NativeUI.InputCaptureActive; } catch { return false; } }
        }

        internal static bool EscapeConsumedThisFrame
        {
            get { try { return NativeUI.EscConsumedFrame == Time.frameCount; } catch { return false; } }
        }
    }

    /// <summary>EventSystem NAVIGATION ownership while the overlay is open
    /// (r2 finding, HIGH): the uGUI backdrop stops pointer raycasts but NOT
    /// navigation Submit — vanilla binds Submit to Space/Action1, ListMenu
    /// keeps a SELECTED button alive behind the overlay, and two Spaces
    /// typed into an overlay field could submit the hidden esc-menu MAIN
    /// MENU button (arm the guard, then disconnect). While capture is
    /// active: sendNavigationEvents is held false and the current selection
    /// is cleared, re-asserted per frame from NativeUI.Tick. Restored by
    /// TeardownOverlaySurfaces — the ONE shared close-path teardown (#369).
    /// Reflection throughout: EventSystem lives in the unreferenced UI
    /// assembly (#15). Stranding note (#255): if the mod stops ticking
    /// entirely, a scene change replaces the EventSystem and the fresh one
    /// defaults sendNavigationEvents=true — self-healing.</summary>
    internal static class EventSystemGuard
    {
        private static Type tEs;
        private static PropertyInfo pCurrent, pSendNav;
        private static MethodInfo mSetSelected;
        private static bool resolveTried, resolveFailed;
        private static bool navSaved, navSavedValue;

        private static bool Resolve()
        {
            if (resolveTried) return !resolveFailed;
            resolveTried = true;
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    tEs = asm.GetType("UnityEngine.EventSystems.EventSystem");
                    if (tEs != null) break;
                }
                if (tEs == null) { resolveFailed = true; }
                else
                {
                    pCurrent = tEs.GetProperty("current", BindingFlags.Public | BindingFlags.Static);
                    pSendNav = tEs.GetProperty("sendNavigationEvents", BindingFlags.Public | BindingFlags.Instance);
                    mSetSelected = tEs.GetMethod("SetSelectedGameObject", new[] { typeof(GameObject) });
                    resolveFailed = pCurrent == null || pSendNav == null || mSetSelected == null;
                }
            }
            catch { resolveFailed = true; }
            if (resolveFailed)
                Plugin.Log?.LogWarning("[OVERLAY-GATE] EventSystem unresolvable — navigation-submit gate NOT active");
            return !resolveFailed;
        }

        internal static void OnCaptureStart()
        {
            try
            {
                if (!Resolve()) return;
                var es = pCurrent.GetValue(null);
                if (es == null) return;
                if (!navSaved)
                {
                    navSavedValue = (bool)pSendNav.GetValue(es);
                    navSaved = true;
                }
                pSendNav.SetValue(es, false);
                mSetSelected.Invoke(es, new object[] { null });
            }
            catch { }
        }

        /// <summary>Per-frame while capture is active: vanilla (ListMenu's
        /// restore pass) can re-select a hidden button mid-overlay, so the
        /// clear is re-asserted, not just applied at open.</summary>
        internal static void AssertWhileActive()
        {
            try
            {
                if (!Resolve()) return;
                var es = pCurrent.GetValue(null);
                if (es == null) return;
                if ((bool)pSendNav.GetValue(es)) pSendNav.SetValue(es, false);
                mSetSelected.Invoke(es, new object[] { null });
            }
            catch { }
        }

        internal static void OnCaptureEnd()
        {
            try
            {
                if (!Resolve()) return;
                var es = pCurrent.GetValue(null);
                if (es == null) { navSaved = false; return; }
                // Restore what was saved; with nothing saved, TRUE is what
                // vanilla ships (restore-to-what-vanilla-wants, #255).
                pSendNav.SetValue(es, navSaved ? navSavedValue : true);
                navSaved = false;
            }
            catch { }
        }
    }

    /// <summary>While the overlay is open (or Escape just closed it this
    /// frame), vanilla gets NO escape handling: not ToggleEsc, not the
    /// loading-screen NetworkRestart abort, and not the controller
    /// Action2/Command loops. Composes by AND with the spectator's own
    /// prefix (SpectatorPatches) — sibling prefixes still run (#352).</summary>
    [HarmonyPatch(typeof(EscapeMenuHandler), "Update")]
    internal static class OverlayGate_EscapeMenu_Patch
    {
        private static bool Prefix()
        {
            return !(OverlayInputGate.GateActive || OverlayInputGate.EscapeConsumedThisFrame);
        }
    }

    /// <summary>GoBack.Update reads Escape independently of
    /// EscapeMenuHandler — without this, the press that closed the overlay
    /// also backed out of character selection / the underlying menu page
    /// (review finding 5).</summary>
    [HarmonyPatch(typeof(GoBack), "Update")]
    internal static class OverlayGate_GoBack_Patch
    {
        private static bool Prefix()
        {
            return !(OverlayInputGate.GateActive || OverlayInputGate.EscapeConsumedThisFrame);
        }
    }

    /// <summary>Lower-impact raw-Escape readers, same one-frame rule
    /// (review "required changes" list).</summary>
    [HarmonyPatch(typeof(MultiOptions), "Update")]
    internal static class OverlayGate_MultiOptions_Patch
    {
        private static bool Prefix()
        {
            return !(OverlayInputGate.GateActive || OverlayInputGate.EscapeConsumedThisFrame);
        }
    }

    [HarmonyPatch(typeof(UIFriendInvite), "Update")]
    internal static class OverlayGate_FriendInvite_Patch
    {
        private static bool Prefix()
        {
            return !(OverlayInputGate.GateActive || OverlayInputGate.EscapeConsumedThisFrame);
        }
    }

    /// <summary>GM_ArmsRace.Update contains ONLY the debug numeric keybinds
    /// (verified against the decompile by the design review): typing 2/4
    /// into an overlay text field would overwrite playersNeededToStart /
    /// PlayerAssigner.maxPlayers mid-assembly (review finding 1).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "Update")]
    internal static class OverlayGate_ArmsRaceDebugKeys_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    /// <summary>Remote Control steering reads the raw mouse every frame on
    /// the OWNER seat (replicas early-return on !view.IsMine, so skipping
    /// Update is replica-safe). While the overlay is open the projectile
    /// coasts on its last velocity instead of tracking the cursor across
    /// menu buttons (review finding 2).</summary>
    [HarmonyPatch(typeof(RemoteControl), "Update")]
    internal static class OverlayGate_RemoteControl_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    /// <summary>The ACTUAL ready-up lives here, not in PlayerAssigner —
    /// Space typed under the overlay toggled ReadyUp and could start the
    /// game behind it (review finding 3).</summary>
    [HarmonyPatch(typeof(CharacterSelectionInstance), "Update")]
    internal static class OverlayGate_CharacterSelect_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    /// <summary>Rematch Yes/No popup reads raw actions — Space under the
    /// overlay confirmed Yes and could NetworkRestart the seat when the
    /// peer never answered (review finding 6). The popup just freezes while
    /// the overlay is open and resumes on close.</summary>
    [HarmonyPatch(typeof(PopUpHandler), "Update")]
    internal static class OverlayGate_PopUp_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    /// <summary>Space ready-up polling + B practice-bot spawn (lobby).
    /// Competitive programmatic spawns call CreatePlayer directly and are
    /// unaffected; polling resumes the frame after close.</summary>
    [HarmonyPatch(typeof(PlayerAssigner), "LateUpdate")]
    internal static class OverlayGate_PlayerAssigner_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    /// <summary>GeneralInput field scrub + fire-until-neutral latch.
    ///
    /// Owner-side clearing covers the networked effects reachable through
    /// these fields (#268: no local edge -> no RPC -> no replica action) —
    /// the raw readers that bypass GeneralInput each carry their own gate in
    /// this file — and a Postfix reading our own predicate strands nothing
    /// (#75). The latch closes the review's finding 4: Fire held across the
    /// overlay-close boundary would otherwise deliver a charged release to
    /// the gun the frame after close.
    ///
    /// R1 finding 1: the latch's arm/neutral tests read the PHYSICAL action
    /// (playerActions.Fire) when available, never only the copied fields —
    /// vanilla's own early returns (GameManager.lockInput, stun, !isPlaying)
    /// clear the copied fields while the button is still physically held, so
    /// a copied-field test either never arms or releases early and the first
    /// unlocked frame fires. The copied fields remain the fallback for a
    /// missing device/actions.
    ///
    /// aimDirection is deliberately untouched (zeroing risks downstream
    /// normalization; shooting is blocked and RemoteControl is gated
    /// separately). Replicas are excluded via controlledElseWhere — their
    /// fields come from the movement sync stream, never local input.</summary>
    [HarmonyPatch(typeof(GeneralInput), "Update")]
    internal static class OverlayGate_GeneralInput_Patch
    {
        // Keyed by instance; an entry lives only while its latch is armed.
        private static readonly Dictionary<GeneralInput, bool> fireLatch = new Dictionary<GeneralInput, bool>();

        private static bool FireHeldPhysically(GeneralInput gi)
        {
            try
            {
                var actions = gi.data != null ? gi.data.playerActions : null;
                var fire = actions != null ? actions.Fire : null;
                if (fire != null)
                    return fire.IsPressed || fire.WasPressed || fire.WasReleased;
            }
            catch { }
            return gi.shootIsPressed || gi.shootWasPressed || gi.shootWasReleased;
        }

        private static void SweepDeadKeys()
        {
            // R2 hardening: bound the dictionary across an arbitrarily long
            // process session (destroyed Unity keys otherwise accrete).
            if (fireLatch.Count <= 8) return;
            var dead = new List<GeneralInput>();
            foreach (var k in fireLatch.Keys) if (k == null) dead.Add(k);
            foreach (var k in dead) fireLatch.Remove(k);
        }

        private static void Postfix(GeneralInput __instance)
        {
            try
            {
                if (__instance == null || __instance.controlledElseWhere) return;
                if (OverlayInputGate.GateActive)
                {
                    if (FireHeldPhysically(__instance)) { SweepDeadKeys(); fireLatch[__instance] = true; }
                    __instance.direction = Vector3.zero;
                    __instance.jumpWasPressed = false;
                    __instance.jumpIsPressed = false;
                    __instance.shootWasPressed = false;
                    __instance.shootIsPressed = false;
                    __instance.shootWasReleased = false;
                    __instance.shieldWasPressed = false;
                    return;
                }
                if (fireLatch.Count == 0 || !fireLatch.ContainsKey(__instance)) return;
                if (!FireHeldPhysically(__instance)) { fireLatch.Remove(__instance); return; }
                __instance.shootWasPressed = false;
                __instance.shootIsPressed = false;
                __instance.shootWasReleased = false;
            }
            catch { }
        }
    }

    /// <summary>Character-editor raw input (review r1 finding 10): clicking
    /// through the overlay could begin and COMMIT a facial-feature drag,
    /// controller navigation could alter selections, and Command could save
    /// the edited face — all behind F5. Freeze the editor while the overlay
    /// owns input; it resumes on close.</summary>
    [HarmonyPatch(typeof(CharacterCreatorDragging), "Update")]
    internal static class OverlayGate_CreatorDragging_Patch
    {
        private static bool Prefix(CharacterCreatorDragging __instance)
        {
            if (!OverlayInputGate.GateActive) return true;
            // r2 finding: freezing Update mid-drag loses the release edge —
            // the resumed frame would apply the whole accumulated cursor
            // delta and keep dragging. Cancel the drag and refresh the
            // baseline while the gate owns input — in WORLD space, the same
            // ScreenToWorldPoint conversion vanilla stores (r3 finding 2:
            // raw Input.mousePosition here mixed pixel coordinates into a
            // world-coordinate field and made the first resumed drag jump).
            try
            {
                if (__instance != null)
                {
                    __instance.draggedObject = null;
                    var cam = MainCam.instance != null ? MainCam.instance.cam : null;
                    if (cam != null)
                        __instance.lastMouse = cam.ScreenToWorldPoint(Input.mousePosition);
                }
            }
            catch { }
            return false;
        }
    }

    [HarmonyPatch(typeof(CharacterCreatorNavigation), "Update")]
    internal static class OverlayGate_CreatorNavigation_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    [HarmonyPatch(typeof(CharacterCreatorPortrait), "Update")]
    internal static class OverlayGate_CreatorPortrait_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    /// <summary>Remaining raw operations (review r1 finding 14): Shift in an
    /// overlay text field cycled the map art, Action3 opened the platform
    /// room-code dialog, and Tab/touchpad toggled the native block-list
    /// pages — all while F5 owned the screen.</summary>
    [HarmonyPatch(typeof(ArtHandler), "Update")]
    internal static class OverlayGate_ArtHandler_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    [HarmonyPatch(typeof(ButtonJoinRoom), "Update")]
    internal static class OverlayGate_ButtonJoinRoom_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    [HarmonyPatch(typeof(UIBlockList), "Update")]
    internal static class OverlayGate_UIBlockList_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    [HarmonyPatch(typeof(UIBlockPlayer), "Update")]
    internal static class OverlayGate_UIBlockPlayer_Patch
    {
        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }

    /// <summary>GeneralInput's Chat action release calls
    /// DevConsole.OpenTextDialog BEFORE any postfix can clear fields
    /// (review finding 7) — a prefix on the dialog itself is the only
    /// complete gate. Resolved via TargetMethods so a vanilla rename fails
    /// LOUD in the startup log (#83) instead of silently not attaching.</summary>
    [HarmonyPatch]
    internal static class OverlayGate_DevConsoleDialog_Patch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            var m = AccessTools.Method(typeof(DevConsole), "OpenTextDialog");
            if (m == null)
            {
                Plugin.Log?.LogError("[OVERLAY-GATE] DevConsole.OpenTextDialog unresolvable — chat-dialog gate NOT attached");
                yield break;
            }
            yield return m;
        }

        private static bool Prefix() { return !OverlayInputGate.GateActive; }
    }
}
