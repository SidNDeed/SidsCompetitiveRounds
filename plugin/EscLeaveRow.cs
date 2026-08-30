using System;
using System.Reflection;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>The ONE sanctioned deliberate-exit route, shared by the
    /// LEAVE MATCH row below. Structured as a helper so a future option-B
    /// (real per-mode concession endpoints with settlement) can replace the
    /// body without rebuilding any UI (design review, Aug 30).</summary>
    internal static class CompetitiveExit
    {
        internal static void Request(string context)
        {
            try { Plugin.Log?.LogInfo("[LEAVE-ROW] confirmed leave (" + context + ")"); } catch { }
            // Same transaction as the guarded MAIN MENU click: restore the
            // vanilla esc wiring, then the codebase's one honest
            // abort-to-menu lever. Each step isolated so the leave is
            // reached even if the disarm throws.
            try { EscMenuLeaveGuard.Disarm(); } catch { }
            try { NetworkConnectionHandler.instance.NetworkRestart(); } catch { }
        }
    }

    /// <summary>An OBVIOUS way to leave a competitive match (owner item 5,
    /// Aug 30). Design review verdict: a surface named FORFEIT/CONCEDE is a
    /// false promise today — sanctioned leave semantics do NOT consistently
    /// impose a game/series loss (1v1 at 0-0 can cancel, 2v2 settles only
    /// when the other team leads, 1v2 has no auto-forfeit, FFA follows
    /// early-leave rules) — so this row says LEAVE MATCH and its copy says
    /// exactly which rules apply. Real concession settlement is future
    /// server work (option B), for which CompetitiveExit is the seam.
    ///
    /// Construction rules (all review-mandated):
    /// - NEVER clone the MAIN MENU button: its serialized persistent onClick
    ///   call (NetworkRestart) survives RemoveAllListeners, and a second
    ///   persistent NetworkRestart call would also make EscMenuLeaveGuard's
    ///   exactly-one scan refuse to arm. The template is any OTHER esc-menu
    ///   ListMenuButton, with EVERY persistent call flipped Off and
    ///   QuitButton/GoBack stripped.
    /// - Confirm state binds to (room generation, room name, mode, context
    ///   id, button instance) and is revalidated on BOTH clicks; the room
    ///   generation increments on every join, so a same-name rejoin can
    ///   never satisfy a stale confirm (#312/#430 family).
    /// - Visible only for a non-spectator seat in an ONLINE competitive
    ///   context, explicitly excluding tournament rooms (sct-* /
    ///   IsTournamentMatch) — those have their own authoritative Forfeit
    ///   flow in the Tournaments tab and two controls with different
    ///   semantics may not share a menu.</summary>
    internal static class EscLeaveRow
    {
        private const float ConfirmWindowSeconds = 4f;
        private const float ConfirmMinSeconds = 0.35f;   // #158-class double-fire guard
        private const float RescanCooldownSeconds = 5f;

        private static GameObject rowGO;
        private static Component rowTmp;                 // TMP_Text (reflected)
        private static PropertyInfo tmpTextProp;
        private static int roomGen;
        private static float lastScanAt = -999f;

        private static string pendingContext;
        private static float pendingAt = -999f;
        private static GameObject pendingButton;
        // All-seat match generation (r2 finding: series-id fences only move
        // on the elected REPORTER's seat — a non-reporter's stale id could
        // satisfy a confirm armed in the previous sitting). Bumped on every
        // observed match-START edge, which every seat sees, and baked into
        // the confirm context below.
        private static int matchGen;
        private static bool lastInMatch;

        /// <summary>Room generation token: bumped on EVERY join, including a
        /// same-name rejoin (name is not incarnation — #428/#430).</summary>
        internal static void OnRoomJoined()
        {
            roomGen++;
            ResetConfirm();
            lastScanAt = -999f;   // fresh room = fresh scan allowance
            SetRowVisible(false);
            try { GameStateWatcher.ClearTournamentContextResolved(); } catch { }
        }

        internal static void OnRoomLeft()
        {
            ResetConfirm();
            SetRowVisible(false);
            try { GameStateWatcher.ClearTournamentContextResolved(); } catch { }
        }

        private static void ResetConfirm()
        {
            pendingContext = null;
            pendingAt = -999f;
            pendingButton = null;
            SetLabel(false);
        }

        /// <summary>Recurring reconcile (same cadence/host as
        /// EscMenuLeaveGuard.Arm — the room-state poll). Injects the row when
        /// a valid context exists, hides it otherwise, re-asserts the label
        /// (vanilla ListMenuButton re-inits can reset TMP text), and expires
        /// a lapsed confirm.</summary>
        internal static void Reconcile()
        {
            try
            {
                bool im = false;
                try { im = GameStateWatcher.IsInMatch; } catch { }
                if (im && !lastInMatch) matchGen++;
                lastInMatch = im;
                string ctx = ComputeContext();
                if (ctx == null)
                {
                    ResetConfirm();
                    SetRowVisible(false);
                    return;
                }
                if (rowGO == null && !TryInject()) return;
                SetRowVisible(true);
                if (pendingContext != null
                    && Time.unscaledTime - pendingAt > ConfirmWindowSeconds)
                    ResetConfirm();
                if (pendingContext == null) SetLabel(false);
            }
            catch { }
        }

        /// <summary>The full eligibility predicate. Null = no row. Encodes
        /// the design review's q3 checklist: online room only, never
        /// OfflineMode (#122), never a spectator, never a tournament, and a
        /// mode-specific liveness term per population. The returned string
        /// doubles as the confirm-binding context id.</summary>
        private static string ComputeContext()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return null;
                if (RoomActors.LocalIsSpectator) return null;
                if (GameStateWatcher.IsTournamentMatch) return null;
                var room = PhotonNetwork.CurrentRoom;
                string name = room?.Name ?? "";
                if (name.StartsWith("sct-", StringComparison.Ordinal)) return null;
                bool crFf = false;
                try { crFf = room != null && room.CustomProperties != null && room.CustomProperties.ContainsKey("cr_ff"); }
                catch { }
                string mode = null, ctxId = "";
                if (crFf || name.StartsWith("team_", StringComparison.Ordinal))
                {
                    mode = "2v2";
                    try { ctxId = ApiClient.ActiveTeamSeriesId ?? ""; } catch { }
                }
                else if (name.StartsWith("ovt_", StringComparison.Ordinal))
                {
                    mode = "1v2";
                    // r1 finding 11 / r2 refinement: the series id only moves
                    // on the elected reporter's seat, so it is a best-effort
                    // term — the ALL-SEAT invalidator for a new sitting
                    // between the two clicks is the matchGen baked into every
                    // context (bumped on each match-start edge).
                    try { ctxId = ApiClient.ActiveOvt1v2SeriesId ?? ""; } catch { }
                }
                else if (name.StartsWith("ffa_", StringComparison.Ordinal))
                {
                    bool engine = false;
                    try { engine = FfaMode.EngineActive(); } catch { }
                    if (!engine) return null;
                    mode = "ffa";
                    try { ctxId = ApiClient.ActiveFfaLobbyId ?? ""; } catch { }
                }
                else if (name.StartsWith("ranked_", StringComparison.Ordinal))
                {
                    mode = "1v1";
                    try { ctxId = ApiClient.ActiveRankedSeriesId ?? ""; } catch { }
                }
                else
                {
                    // Room-code population (#286): only while the current
                    // room's game is RANKED and actually tracking.
                    bool ranked = false, inMatch = false;
                    try { ranked = GameStateWatcher.MatchIsRanked; inMatch = GameStateWatcher.IsInMatch; } catch { }
                    if (!ranked || !inMatch) return null;
                    mode = "1v1";
                    try { ctxId = ApiClient.ActiveRankedSeriesId ?? ""; } catch { }
                    // r1 finding 2 (HIGH) + r3 finding 1: a room-code
                    // TOURNAMENT match must never flash this row past its
                    // authoritative Forfeit surface. The series id alone is
                    // NOT proof this room's preflight resolved — a
                    // queue-staged id can survive a failed join into a later
                    // room — so the gate requires BOTH: a non-empty id AND
                    // the room-scoped provenance latch, which only the
                    // fenced current-room preflight response sets (and it
                    // stamps tournament context strictly before publishing
                    // the id — ordering made load-bearing in ApiClient,
                    // Aug 30 r2). Missing either fails HIDE-only.
                    if (string.IsNullOrEmpty(ctxId)) return null;
                    bool resolved = false;
                    try { resolved = GameStateWatcher.TournamentContextResolvedThisRoom; } catch { }
                    if (!resolved) return null;
                }
                if (mode == null) return null;
                return mode + "|" + name + "|g" + roomGen + "|m" + matchGen + "|" + ctxId;
            }
            catch { return null; }
        }

        private static bool TryInject()
        {
            if (Time.unscaledTime - lastScanAt < RescanCooldownSeconds) return false;
            lastScanAt = Time.unscaledTime;
            GameObject clone = null;   // outside the try: a partial-inject throw must destroy it (r2 nit)
            try
            {
                Component disc; object discClick; int discIdx;
                if (EscMenuLeaveGuard.FindDisconnectButton(out disc, out discClick, out discIdx) != 1
                    || disc == null) return false;
                var container = disc.transform.parent;
                if (container == null) return false;
                // Template: any SIBLING ListMenuButton that is not the
                // disconnect button (labels are localized — never match text).
                Transform template = null;
                for (int i = 0; i < container.childCount; i++)
                {
                    var ch = container.GetChild(i);
                    if (ch == null || ReferenceEquals(ch, disc.transform)) continue;
                    if (ch.GetComponent<ListMenuButton>() == null) continue;
                    template = ch; break;
                }
                if (template == null) return false;

                clone = UnityEngine.Object.Instantiate(template.gameObject, container);
                clone.name = "CR_LeaveMatchRow";
                clone.transform.SetSiblingIndex(disc.transform.GetSiblingIndex());

                // Strip behaviours that would act (#13) and DISABLE every
                // persistent call — RemoveAllListeners does not touch
                // serialized calls, so an Options-template clone would still
                // open Options without this.
                foreach (var qb in clone.GetComponentsInChildren<QuitButton>(true))
                    UnityEngine.Object.Destroy(qb);
                foreach (var gb in clone.GetComponentsInChildren<GoBack>(true))
                    UnityEngine.Object.Destroy(gb);
                var btnType = UIFactory.tButton;
                var btn = btnType != null ? clone.GetComponent(btnType) : null;
                if (btn == null) { UnityEngine.Object.Destroy(clone); return false; }
                var onClick = btnType.GetProperty("onClick")?.GetValue(btn) as UnityEngine.Events.UnityEventBase;
                if (onClick == null) { UnityEngine.Object.Destroy(clone); return false; }
                for (int i = 0; i < onClick.GetPersistentEventCount(); i++)
                {
                    try { onClick.SetPersistentListenerState(i, UnityEngine.Events.UnityEventCallState.Off); }
                    catch { UnityEngine.Object.Destroy(clone); return false; }
                }
                var add = onClick.GetType().GetMethod("AddListener", new Type[] { typeof(UnityEngine.Events.UnityAction) });
                if (add == null) { UnityEngine.Object.Destroy(clone); return false; }
                var removeAll = onClick.GetType().GetMethod("RemoveAllListeners");
                try { removeAll?.Invoke(onClick, null); } catch { }
                add.Invoke(onClick, new object[] { (UnityEngine.Events.UnityAction)OnRowClicked });

                // TMP label handle (TMP_Text reflected — no TMPro reference).
                rowTmp = null; tmpTextProp = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    var t = asm.GetType("TMPro.TMP_Text");
                    if (t == null) continue;
                    rowTmp = clone.GetComponentInChildren(t, true);
                    tmpTextProp = t.GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
                    break;
                }
                rowGO = clone;
                SetLabel(false);
                Plugin.Log?.LogInfo("[LEAVE-ROW] injected esc-menu LEAVE MATCH row");
                return true;
            }
            catch (Exception ex)
            {
                // Cleanup FIRST, logging second and independently guarded
                // (r3 finding 3: a throwing log listener between them would
                // leak the un-adopted clone — with template behavior — into
                // the menu).
                try { if (clone != null && !ReferenceEquals(clone, rowGO)) UnityEngine.Object.Destroy(clone); }
                catch { }
                try { Plugin.Log?.LogWarning("[LEAVE-ROW] inject failed: " + ex.Message); } catch { }
                return false;
            }
        }

        private static void SetRowVisible(bool on)
        {
            try { if (rowGO != null && rowGO.activeSelf != on) rowGO.SetActive(on); } catch { }
        }

        private static void SetLabel(bool confirming)
        {
            try
            {
                if (rowTmp == null || tmpTextProp == null) return;
                tmpTextProp.SetValue(rowTmp,
                    confirming ? I18n.Tr("CONFIRM LEAVE") : I18n.Tr("LEAVE MATCH"));
            }
            catch { }
        }

        private static void OnRowClicked()
        {
            try
            {
                string ctx = ComputeContext();
                if (ctx == null) { ResetConfirm(); SetRowVisible(false); return; }
                float now = Time.unscaledTime;
                if (pendingContext != null && pendingContext == ctx
                    && ReferenceEquals(pendingButton, rowGO)
                    && now - pendingAt >= ConfirmMinSeconds
                    && now - pendingAt <= ConfirmWindowSeconds)
                {
                    ResetConfirm();
                    CompetitiveExit.Request(ctx);
                    return;
                }
                // First (or stale) click: arm the confirm and say honestly
                // what leaving does in THIS mode — the copy promises leave
                // mechanics, never a forfeit result (design review q1: a UI
                // asserting settlement that does not occur crosses the bar).
                pendingContext = ctx;
                pendingAt = now;
                pendingButton = rowGO;
                SetLabel(true);
                string modeLine;
                if (ctx.StartsWith("2v2|", StringComparison.Ordinal))
                    // Wording matches the executable server rule EXACTLY
                    // (main.py dc lead-forfeit: other team has >=1 game win
                    // AND >=2 total points in the abandoned game) — r1
                    // finding 3 caught the "already lead" paraphrase
                    // promising settlement the server does not perform.
                    modeLine = I18n.Tr("2v2: the series settles for the other team only if they have already won a game and this game has at least 2 total points; otherwise it pauses as incomplete.");
                else if (ctx.StartsWith("1v2|", StringComparison.Ordinal))
                    modeLine = I18n.Tr("1v2: leaving ends your sitting; there is no automatic forfeit.");
                else if (ctx.StartsWith("ffa|", StringComparison.Ordinal))
                    modeLine = I18n.Tr("FFA: your tally is kept and scored from your exit under the early-leave rules.");
                else
                    modeLine = I18n.Tr("1v1: your opponent can take the game under the disconnect rules; the series may stay open.");
                CompetitiveUI.ShowNotificationCritical(
                    I18n.Tr("Leave this competitive match? Click again to confirm. Standard disconnect and early-leave rules apply - this is not a guaranteed forfeit.")
                    + "\n" + modeLine,
                    new Color(1f, 0.75f, 0.4f), ConfirmWindowSeconds);
            }
            catch { }
        }
    }
}
