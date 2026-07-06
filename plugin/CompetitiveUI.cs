using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    public static class CompetitiveUI
    {
        public static int LastKnownLevel = -1;

        // FPS
        private static float fpsTimer = 0f;
        private static int fpsCnt = 0;
        private static float fpsVal = 0f;
        private static GUIStyle fpsStyle;

        // Notification (IMGUI)
        private static string notifText = "";
        private static Color notifColor = Color.white;
        private static float notifTimer = 0f;
        private static List<QueuedNotif> notifQueue = new List<QueuedNotif>();
        private struct QueuedNotif { public string text; public Color color; public float dur; }
        private static GUIStyle notifStyle;

        // Match status
        private static GUIStyle statusStyle;

        public static void ToggleOverlay() => NativeUI.Toggle();

        public static void ShowNotification(string text, Color color, float duration = 3f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            notifText = text;
            notifColor = color;
            notifTimer = duration;
        }

        public static void QueueNotification(string text, Color color, float duration = 3f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            notifQueue.Add(new QueuedNotif { text = text, color = color, dur = duration });
        }

        // Match-found notification sound
        private static AudioClip matchFoundClip;
        private static GameObject soundObj;

        public static void PlayMatchFoundSound()
        {
            try
            {
                if (matchFoundClip == null)
                {
                    int sampleRate = 44100;
                    float dur = 0.45f;
                    int samples = (int)(sampleRate * dur);
                    matchFoundClip = AudioClip.Create("MatchFound", samples, 1, sampleRate, false);
                    float[] data = new float[samples];
                    int half = samples / 2;
                    for (int i = 0; i < samples; i++)
                    {
                        float t = (float)i / sampleRate;
                        float freq = i < half ? 660f : 880f; // two-tone ascending
                        data[i] = Mathf.Sin(2f * Mathf.PI * freq * t) * 0.35f;
                        // Fade within each tone
                        float pos = i < half ? (float)i / half : (float)(i - half) / (samples - half);
                        float env = Mathf.Clamp01(pos * 10f) * Mathf.Clamp01((1f - pos) * 5f);
                        data[i] *= env;
                    }
                    matchFoundClip.SetData(data, 0);
                }
                if (soundObj == null)
                {
                    soundObj = new GameObject("CR_Sound");
                    soundObj.hideFlags = HideFlags.HideAndDontSave;
                    UnityEngine.Object.DontDestroyOnLoad(soundObj);
                }
                var src = soundObj.GetComponent<AudioSource>();
                if (src == null) src = soundObj.AddComponent<AudioSource>();
                src.clip = matchFoundClip;
                src.volume = 0.7f;
                src.Play();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[SOUND] Match found sound failed: {ex.Message}");
            }
        }

        public static void ResetStyles() { }

        public static void CacheRaycasters() { }

        public static void MarkDirty() => NativeUI.MarkDirty();

        /// <summary>Called from Update. Ticks the native UI.</summary>
        public static void Tick() => NativeUI.Tick();

        /// <summary>Called from OnGUI. FPS + notifications + match status. The server-down
        /// banner moved to the F5 menu (NativeUI.RefreshServerBanner) — it was constantly
        /// firing in-game during quiet periods + felt obtrusive.</summary>
        public static void DrawUI()
        {
            DrawFPS();
            DrawNotification();
            DrawMatchStatus();
            DrawInGameChat();
            DrawChatInput();
            DrawAdminPrompt();
            DrawBugReportModal();
            DrawBugReportAdminViewer();
            DrawLogViewerModal();
            DrawBlockDebug();  // debug-only; toggle via BlockDebugEnabled below
            DrawInputOverlay();
            // v1.28: the physical "match-found stuck" escape-hatch overlay is retired.
            // Its real target — the EscapeMenuHandler/SetInputActive NRE that wedged
            // Escape and locked inputs — is now fixed in code (PlayerManagerSetInputActiveNullGuard
            // + EscapeMenuToggleEscFinalizer in PerfPatches.cs). The overlay also false-
            // positived during normal matchmaking (being in the queue room legitimately
            // looks like "in a room with no match"), which is the flicker Sid reported.
            // DrawMatchFoundStuckOverlay();  // intentionally not called — kept for reference
            DrawCardHoverTooltip();
            DrawCompareSearch();
            DrawMapColorToast();
            DrawCustomBetPrompt();
            // Block uGUI clicks to the F5 page behind any open IMGUI modal (lopi #14:
            // clicks on the bug-report form were also hitting F5 buttons underneath).
            NativeUI.SetClickBlocker(bugModalOpen || logViewerOpen || bugAdminOpen || NativeUI.CustomBetPromptOpen);
            // Consent modal drawn LAST so it paints on top of everything.
            DrawConsentModal();
        }

        // Bottom-center toast naming the map skin you just Shift-cycled to, so you can
        // hunt for a specific one (e.g. Magma) by sight. Driven by MapColorState.ShowToast.
        private static GUIStyle mapToastStyle;
        private static void DrawMapColorToast()
        {
            try
            {
                if (Time.unscaledTime >= MapColorState.ToastUntil) return;
                string t = MapColorState.ToastText;
                if (string.IsNullOrEmpty(t)) return;
                if (mapToastStyle == null)
                    mapToastStyle = new GUIStyle(GUI.skin.label)
                    { fontSize = 22, alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold, richText = true };
                float w = 460f, h = 40f;
                float x = (Screen.width - w) / 2f;
                float y = Screen.height - 120f;
                // Fade out over the last 0.6s.
                float remain = MapColorState.ToastUntil - Time.unscaledTime;
                float a = Mathf.Clamp01(remain / 0.6f);
                var prev = GUI.color;
                GUI.color = new Color(0f, 0f, 0f, 0.55f * a);
                GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture);
                GUI.color = new Color(1f, 1f, 1f, a);
                GUI.Label(new Rect(x, y, w, h), $"<color=#FFD94D>Map skin:</color> <color=#FFFFFF>{t}</color>", mapToastStyle);
                GUI.color = prev;
            }
            catch { }
        }

        // ── Custom bet amount prompt (v1.29, F6) ───────────────────────────────
        // Small centered IMGUI modal opened by the "..." button on a bet row.
        // Enter = place, Escape = cancel. Digits only; validation + placement
        // live in NativeUI.SubmitCustomBet.
        private static GUIStyle betPromptStyle, betPromptTitleStyle;
        private const string BET_AMOUNT_CTRL = "CustomBetAmount";
        private static void DrawCustomBetPrompt()
        {
            if (!NativeUI.CustomBetPromptOpen) return;
            try
            {
                var ev = Event.current;
                if (ev != null && ev.type == EventType.KeyDown)
                {
                    if (ev.keyCode == KeyCode.Return || ev.keyCode == KeyCode.KeypadEnter)
                    { ev.Use(); NativeUI.SubmitCustomBet(); return; }
                    if (ev.keyCode == KeyCode.Escape)
                    { ev.Use(); NativeUI.CancelCustomBet(); return; }
                }
                if (betPromptStyle == null)
                    betPromptStyle = new GUIStyle(GUI.skin.textField) { fontSize = 18, alignment = TextAnchor.MiddleCenter };
                if (betPromptTitleStyle == null)
                    betPromptTitleStyle = new GUIStyle(GUI.skin.label) { fontSize = 14, alignment = TextAnchor.MiddleCenter, richText = true, fontStyle = FontStyle.Bold };
                float w = 340f, h = 128f;
                float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
                // Dim backdrop + eat stray clicks outside the box (IMGUI side).
                GUI.color = new Color(0f, 0f, 0f, 0.55f);
                GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture);
                GUI.color = new Color(0.10f, 0.11f, 0.14f, 0.98f);
                GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture);
                GUI.color = Color.white;
                GUI.Label(new Rect(x, y + 6f, w, 22f),
                    $"<color=#FFD94D>Custom bet</color> on <color=#FFFFFF>{NativeUI.CustomBetTargetLabel}</color>", betPromptTitleStyle);
                GUI.SetNextControlName(BET_AMOUNT_CTRL);
                string next = GUI.TextField(new Rect(x + 40f, y + 34f, w - 80f, 30f), NativeUI.CustomBetAmountText ?? "", 5, betPromptStyle);
                // Digits only (commas allowed, stripped at submit).
                var filtered = new System.Text.StringBuilder(next.Length);
                foreach (char c in next) if (char.IsDigit(c) || c == ',') filtered.Append(c);
                NativeUI.CustomBetAmountText = filtered.ToString();
                GUI.FocusControl(BET_AMOUNT_CTRL);
                GUI.Label(new Rect(x, y + 64f, w, 16f), "<color=#8899AA>1 - 2,000 gold</color>", betPromptTitleStyle);
                if (GUI.Button(new Rect(x + 34f, y + 86f, 130f, 30f), "Place bet"))
                    NativeUI.SubmitCustomBet();
                if (GUI.Button(new Rect(x + w - 164f, y + 86f, 130f, 30f), "Cancel"))
                    NativeUI.CancelCustomBet();
            }
            catch { }
        }

        // IMGUI search field for the Compare tab's player picker. The native UI does
        // all text entry via IMGUI (no TMP InputField reflection), so this field is
        // drawn EXACTLY over the native placeholder label (NativeUI reports its real
        // screen rect from the overlay canvas's world corners — no layout guessing).
        // Writes to NativeUI.CompareSearch.
        private static GUIStyle compareSearchStyle, compareSearchHintStyle;
        // True while the Compare search IMGUI field has keyboard focus. Read by
        // DrawChatInput so typing (e.g. "t") into the search box doesn't also open
        // the in-game T chat. Reset every frame; set only when the field is focused.
        private static bool compareSearchFocused = false;
        public static bool IsCompareSearchFocused => compareSearchFocused;
        private const string CMP_SEARCH_CTRL = "CmpSearchField";
        private static void DrawCompareSearch()
        {
            compareSearchFocused = false;
            try
            {
                if (!NativeUI.IsOpen || NativeUI.CurrentTab != 9) return;
                Rect r = NativeUI.GetCompareSearchScreenRect();
                if (r.width < 1f || r.height < 1f) return;
                if (compareSearchStyle == null)
                    compareSearchStyle = new GUIStyle(GUI.skin.textField) { fontSize = 13, alignment = TextAnchor.MiddleLeft };
                if (compareSearchHintStyle == null)
                    compareSearchHintStyle = new GUIStyle(GUI.skin.label) { fontSize = 12, alignment = TextAnchor.MiddleLeft, richText = true };
                // Give the field a usable height/width even if the label is short.
                float h = Mathf.Max(r.height, 22f);
                var fieldRect = new Rect(r.x, r.y, Mathf.Max(r.width, 200f), h);
                string cur = NativeUI.CompareSearch ?? "";
                GUI.SetNextControlName(CMP_SEARCH_CTRL);
                string next = GUI.TextField(fieldRect, cur, compareSearchStyle);
                compareSearchFocused = GUI.GetNameOfFocusedControl() == CMP_SEARCH_CTRL;
                if (string.IsNullOrEmpty(next))
                    GUI.Label(new Rect(fieldRect.x + 6f, fieldRect.y, fieldRect.width - 8f, h),
                              "<color=#7788AA><i>search players...</i></color>", compareSearchHintStyle);
                if (next != cur)
                {
                    NativeUI.CompareSearch = next;
                    NativeUI.MarkDirty();
                }
            }
            catch { /* search is best-effort cosmetic */ }
        }

        // ── Card hover tooltip (v1.26.8) ───────────────────────────────
        // NativeUI.FillRow registers a screen-space rect + the full card list
        // for each history row's chips line. On every OnGUI tick we check
        // Input.mousePosition against those rects and render a floating IMGUI
        // panel near the cursor showing the long card names — Sid's "vanilla
        // 2-letter chip with hover tooltip" request.
        public struct CardHoverRegion
        {
            public Rect screenRect;       // screen coordinates (origin bottom-left for Input.mousePosition)
            public string fullCardLine;    // pre-formatted "Mayhem, Empower, Echo, ..." string from server
            public bool isOpponent;        // tint the tooltip accent accordingly
            // Overrides (used by the 2v2 tab). titleOverride: null = default
            // "Your/Opponent's picks" header; "" = render NO header. bodyOverride:
            // null = derive bulleted lines from fullCardLine; else render this
            // pre-formatted (possibly multi-line, rich-text) string verbatim.
            public string titleOverride;
            public string bodyOverride;
        }
        private static readonly List<CardHoverRegion> _cardHoverRegions = new List<CardHoverRegion>(40);
        public static void ClearCardHoverRegions()
        {
            _cardHoverRegions.Clear();
        }
        public static void RegisterCardHoverRegion(Rect screenRect, string fullCardLine, bool isOpponent)
            => RegisterCardHoverRegion(screenRect, fullCardLine, isOpponent, null, null);
        public static void RegisterCardHoverRegion(Rect screenRect, string fullCardLine, bool isOpponent,
                                                   string titleOverride, string bodyOverride)
        {
            // Need SOMETHING to show — either a legacy comma line or an explicit body.
            if (string.IsNullOrEmpty(fullCardLine) && string.IsNullOrEmpty(bodyOverride)) return;
            _cardHoverRegions.Add(new CardHoverRegion {
                screenRect = screenRect, fullCardLine = fullCardLine, isOpponent = isOpponent,
                titleOverride = titleOverride, bodyOverride = bodyOverride,
            });
        }

        private static GUIStyle _cardTipTitleStyle, _cardTipBodyStyle;
        private static void DrawCardHoverTooltip()
        {
            if (!NativeUI.IsOpen) return;
            // My Stats (tab 0) and the 2v2 tab (tab 8) both register card hover
            // regions. On any OTHER tab the regions from the last render would
            // falsely fire when the cursor crosses those screen positions over
            // the Shop / Admin / Settings panels. SwitchTab also clears the
            // regions on tab change; this is the cheap belt-and-suspenders.
            if (NativeUI.CurrentTab != 0 && NativeUI.CurrentTab != 8) return;
            if (_cardHoverRegions.Count == 0) return;

            Vector2 mp = Input.mousePosition;  // bottom-left origin
            CardHoverRegion? hit = null;
            // Last-registered first so newer rows on top of stacked layouts win.
            for (int i = _cardHoverRegions.Count - 1; i >= 0; i--)
            {
                if (_cardHoverRegions[i].screenRect.Contains(mp))
                {
                    hit = _cardHoverRegions[i];
                    break;
                }
            }
            if (hit == null) return;

            if (_cardTipTitleStyle == null)
            {
                _cardTipTitleStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 13, richText = true, fontStyle = FontStyle.Bold,
                    alignment = TextAnchor.MiddleLeft,
                };
                _cardTipBodyStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 12, richText = true, wordWrap = true,
                    alignment = TextAnchor.UpperLeft,
                };
            }

            // Body: either a pre-formatted override (2v2 — grouped by player,
            // one card per line) or the legacy comma-split bullet list (My Stats).
            string body;
            int lineCount;
            if (hit.Value.bodyOverride != null)
            {
                body = hit.Value.bodyOverride;
                lineCount = 1;
                for (int ci = 0; ci < body.Length; ci++) if (body[ci] == '\n') lineCount++;
            }
            else
            {
                string raw = hit.Value.fullCardLine;
                string[] cards;
                try { cards = raw.Split(','); }
                catch { cards = new[] { raw }; }
                lineCount = 0;
                var sb = new System.Text.StringBuilder();
                foreach (var c in cards)
                {
                    string name = c.Trim();
                    if (string.IsNullOrEmpty(name)) continue;
                    lineCount++;
                    sb.Append("• ").Append(name).Append('\n');
                }
                body = sb.ToString().TrimEnd();
            }

            // Title: default "Your/Opponent's picks", or an override ("" = no header).
            string title = hit.Value.titleOverride != null
                         ? hit.Value.titleOverride
                         : (hit.Value.isOpponent ? "Opponent's picks" : "Your picks");
            bool showTitle = !string.IsNullOrEmpty(title);

            float w = 260f;
            float lineH = 16f;
            float headH = showTitle ? 22f : 6f;   // title band height (or just top pad)
            float h = headH + lineCount * lineH + 8f;
            float x = Input.mousePosition.x + 14f;
            float y = (Screen.height - Input.mousePosition.y) + 14f;  // IMGUI y is top-down
            // Clamp inside screen
            if (x + w > Screen.width) x = Screen.width - w - 4f;
            if (y + h > Screen.height) y = Screen.height - h - 4f;
            if (y < 4f) y = 4f;

            // Backdrop + accent border that matches existing modals
            GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0,
                            new Color(0.06f, 0.07f, 0.10f, 0.97f), 0, 0);
            var accent = hit.Value.isOpponent
                       ? new Color(0.95f, 0.55f, 0.45f, 0.9f)
                       : new Color(0.40f, 0.70f, 1.00f, 0.9f);
            GUI.DrawTexture(new Rect(x, y, w, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, accent, 0, 0);
            GUI.DrawTexture(new Rect(x, y + h - 1, w, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, accent, 0, 0);
            GUI.DrawTexture(new Rect(x, y, 1, h), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, accent, 0, 0);
            GUI.DrawTexture(new Rect(x + w - 1, y, 1, h), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, accent, 0, 0);

            if (showTitle)
                GUI.Label(new Rect(x + 8, y + 6, w - 16, 18),
                          $"<color=#{(hit.Value.isOpponent ? "FF9988" : "8BB6FF")}>{title}</color>",
                          _cardTipTitleStyle);
            GUI.Label(new Rect(x + 8, y + headH, w - 16, h - headH - 4f),
                      $"<color=#DDDDDD>{body}</color>",
                      _cardTipBodyStyle);
        }

        // ── Stuck match-found overlay (v1.26.8) ─────────────────────────
        // Renders when GameStateWatcher's watchdog says we've been sitting in
        // a non-mod-issued Photon room for ≥20s without a match starting —
        // matches the symptom of the vanilla "press space to ready" freeze.
        // Player gets a single-click escape hatch (`PhotonNetwork.LeaveRoom`)
        // so they never need alt+F4. Also a "Dismiss (1 min)" so legitimate
        // custom-lobby waits aren't nagged.
        private static GUIStyle stuckTitleStyle;
        private static GUIStyle stuckTextStyle;
        private static GUIStyle stuckButtonStyle;
        private static void DrawMatchFoundStuckOverlay()
        {
            if (!GameStateWatcher.ShouldShowMatchFoundStuckOverlay) return;
            if (NativeUI.IsOpen) return;  // F5 menu already covers the screen

            if (stuckTitleStyle == null)
            {
                stuckTitleStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 17, richText = true, fontStyle = FontStyle.Bold,
                    alignment = TextAnchor.MiddleLeft,
                };
                stuckTextStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 13, richText = true, wordWrap = true,
                    alignment = TextAnchor.UpperLeft,
                };
                stuckButtonStyle = new GUIStyle(GUI.skin.button) { fontSize = 14 };
            }

            float w = 560f, h = 132f;
            float x = (Screen.width - w) / 2f;
            float y = 60f;

            GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0,
                            new Color(0.10f, 0.06f, 0.06f, 0.94f), 0, 0);
            // Thin amber border so it reads as a warning.
            var amber = new Color(0.95f, 0.65f, 0.20f, 0.9f);
            GUI.DrawTexture(new Rect(x, y, w, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, amber, 0, 0);
            GUI.DrawTexture(new Rect(x, y + h - 1, w, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, amber, 0, 0);
            GUI.DrawTexture(new Rect(x, y, 1, h), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, amber, 0, 0);
            GUI.DrawTexture(new Rect(x + w - 1, y, 1, h), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, amber, 0, 0);

            int secs = GameStateWatcher.SecondsInUnstartedRoom;
            GUI.Label(new Rect(x + 14, y + 8, w - 28, 22),
                      "<color=#FFD080>Match-found screen might be stuck</color>",
                      stuckTitleStyle);
            GUI.Label(new Rect(x + 14, y + 32, w - 28, 50),
                      $"<color=#CCCCCC>In this Photon room for <b>{secs}s</b> with no match started. " +
                      "Vanilla matchmaking sometimes hangs here when one player has ROUNDS unfocused. " +
                      "Click into the ROUNDS window first and try space again, or use the escape hatch below.</color>",
                      stuckTextStyle);

            if (GUI.Button(new Rect(x + 14, y + h - 38, 220, 28), "Force exit room", stuckButtonStyle))
            {
                try { Photon.Pun.PhotonNetwork.LeaveRoom(); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[STUCK] LeaveRoom failed: {ex.Message}"); }
                GameStateWatcher.DismissMatchFoundStuckOverlay();
            }
            if (GUI.Button(new Rect(x + w - 174, y + h - 38, 160, 28), "Dismiss (1 min)", stuckButtonStyle))
            {
                GameStateWatcher.DismissMatchFoundStuckOverlay();
            }
        }

        // ── Admin: bug-report viewer (v1.26.7) ─────────────────────────
        private static readonly string[] BUG_STATUSES = new[] { "open", "triaged", "resolved", "wontfix", "dupe" };
        private static bool bugAdminOpen = false;
        private static string bugAdminSelectedId = null;
        private static Vector2 bugAdminListScroll, bugAdminDetailScroll;
        private static bool bugAdminLoading = false;
        private static GUIStyle bugAdminRowStyle, bugAdminDetailStyle, bugAdminTabStyle, bugAdminTabActiveStyle;
        private static string bugAdminCommentDraft = "";
        private static int bugAdminStatusIdx = 0;
        private static string bugAdminActionStatus = "";
        private static string bugAdminLookup = "";

        public static void OpenBugReportAdminViewer()
        {
            bugAdminOpen = true;
            bugAdminSelectedId = null;
            ApiClient.CachedBugReportDetail = null;
            bugAdminLoading = true;
            bugAdminCommentDraft = "";
            bugAdminActionStatus = "";
            string sid = MatchTracker.LocalSteamId;
            ApiClient.FetchBugReports(sid, ok => { bugAdminLoading = false; });
        }

        private static void DrawBugReportAdminViewer()
        {
            if (!bugAdminOpen) return;
            if (!NativeUI.IsOpen) { bugAdminOpen = false; return; }

            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            { bugAdminOpen = false; ev.Use(); return; }

            if (bugAdminRowStyle == null)
            {
                bugAdminRowStyle = new GUIStyle(GUI.skin.label) { fontSize = 12, richText = true, wordWrap = false };
                bugAdminDetailStyle = new GUIStyle(GUI.skin.label) { fontSize = 12, richText = true, wordWrap = true, alignment = TextAnchor.UpperLeft };
                bugAdminTabStyle = new GUIStyle(GUI.skin.button) { fontSize = 12 };
                bugAdminTabActiveStyle = new GUIStyle(GUI.skin.button)
                {
                    fontSize = 12, fontStyle = FontStyle.Bold,
                    normal = { background = Texture2D.whiteTexture, textColor = Color.black },
                    hover  = { background = Texture2D.whiteTexture, textColor = Color.black },
                };
            }

            float w = Mathf.Min(Screen.width - 40, 1280);
            float h = Mathf.Min(Screen.height - 60, 760);
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.55f), 0, 0);
            GUI.DrawTexture(new Rect(x - 10, y - 10, w + 20, h + 20), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0.05f, 0.06f, 0.08f, 0.98f), 0, 0);

            GUI.Label(new Rect(x, y, w, 24), "<b>Bug Reports</b>", bugTitleStyle ?? GUI.skin.label);
            if (GUI.Button(new Rect(x + w - 100, y, 100, 26), "Close")) { bugAdminOpen = false; return; }
            if (GUI.Button(new Rect(x + w - 210, y, 100, 26), "Refresh"))
            {
                bugAdminLoading = true;
                string sid = MatchTracker.LocalSteamId;
                ApiClient.FetchBugReports(sid, ok => { bugAdminLoading = false; });
                if (!string.IsNullOrEmpty(bugAdminSelectedId))
                    ApiClient.FetchBugReportDetail(sid, bugAdminSelectedId);
            }
            if (bugAdminLoading)
                GUI.Label(new Rect(x + 200, y, 200, 24), "<color=#888>loading...</color>", bugAdminRowStyle);

            // Layout: left list (40%) + right detail (60%).
            float listW = w * 0.40f;
            float bodyY = y + 36;
            float bodyH = h - 46;

            // ── Left pane: report list ───────────────────────────────
            GUI.DrawTexture(new Rect(x, bodyY, listW - 6, bodyH), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0.08f, 0.10f, 0.13f, 0.95f), 0, 0);

            // Lookup box at top of list — filters cached reports by bug #
            // (exact match) or by case-insensitive substring of description/name.
            float lookupY = bodyY + 4;
            GUI.Label(new Rect(x + 6, lookupY + 2, 48, 22), "<b>Find:</b>", bugAdminRowStyle);
            bugAdminLookup = GUI.TextField(new Rect(x + 56, lookupY, listW - 70, 22), bugAdminLookup ?? "");

            var allReports = ApiClient.CachedBugReports ?? new List<ApiClient.BugReportSummary>();
            var reports = allReports;
            string q = (bugAdminLookup ?? "").Trim();
            if (!string.IsNullOrEmpty(q))
            {
                reports = new List<ApiClient.BugReportSummary>();
                bool numQ = int.TryParse(q, out int qNum);
                string qLower = q.ToLowerInvariant();
                foreach (var r in allReports)
                {
                    if (numQ && r.bug_number == qNum) { reports.Add(r); continue; }
                    if ((r.description ?? "").ToLowerInvariant().Contains(qLower)) { reports.Add(r); continue; }
                    if ((r.display_name ?? "").ToLowerInvariant().Contains(qLower)) { reports.Add(r); continue; }
                    if ((r.steam_id ?? "").Contains(q)) { reports.Add(r); }
                }
            }
            // Bigger rows so the 3-line content (badge / who-when / description)
            // never clips — each line is 20px, header pad 6px, footer pad 8px,
            // bottom margin 4px = 84px total. Previously 72px which cut the
            // user-name line off because per-line height + padding exceeded it.
            const float rowH = 84f;
            const float rowGap = 4f;
            const float linePadTop = 6f;
            const float lineH = 20f;
            float listBodyY = lookupY + 28;
            float listBodyH = bodyH - 28 - 4;
            float viewportW = listW - 18;            // scroll viewport
            float contentW  = viewportW - 16;        // minus scrollbar
            float contentH  = Mathf.Max(listBodyH - 8, reports.Count * (rowH + rowGap) + 8);
            bugAdminListScroll = GUI.BeginScrollView(new Rect(x + 4, listBodyY, viewportW, listBodyH),
                                                     bugAdminListScroll,
                                                     new Rect(0, 0, contentW, contentH));
            for (int i = 0; i < reports.Count; i++)
            {
                var r = reports[i];
                var rect = new Rect(2, i * (rowH + rowGap) + 2, contentW - 6, rowH);
                bool selected = r.id == bugAdminSelectedId;
                Color bg = selected ? new Color(0.20f, 0.30f, 0.45f, 0.95f) : new Color(0.13f, 0.15f, 0.19f, 0.95f);
                GUI.DrawTexture(rect, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, bg, 0, 0);
                string sevColor = r.severity == "crash" ? "#FF5555" : r.severity == "high" ? "#FF9966" : r.severity == "medium" ? "#FFCC66" : "#88AABB";
                string statusColor = r.status == "resolved" ? "#88FF88" : r.status == "wontfix" ? "#888888" : r.status == "dupe" ? "#888888" : r.status == "triaged" ? "#FFCC66" : "#FF6688";
                string idTag = r.bug_number > 0 ? $"<b><color=#FFFFFF>#{r.bug_number}</color></b>  " : "";
                string title = $"{idTag}<b><color={sevColor}>[{(r.severity ?? "?").ToUpper()}/{(r.category ?? "?").ToUpper()}]</color></b>  <color={statusColor}>{(r.status ?? "?").ToUpper()}</color>";
                string who = $"{r.display_name ?? r.steam_id ?? "?"} <color=#888>({r.mod_version ?? "?"})</color>";
                string when = ShortDate(r.created_at);
                string desc = (r.description ?? "").Replace("\n", " ");
                if (desc.Length > 70) desc = desc.Substring(0, 70) + "...";
                // 3 line slots, each 20px tall + 6px top pad. Total = 6+20+20+20 = 66, leaves 18px bottom breathing room.
                GUI.Label(new Rect(rect.x + 8, rect.y + linePadTop,                rect.width - 16, lineH), title, bugAdminRowStyle);
                GUI.Label(new Rect(rect.x + 8, rect.y + linePadTop + lineH,        rect.width - 16, lineH),
                          $"<color=#CCCCCC>{who}</color>  <color=#888>{when}</color>{(r.has_log ? "  <color=#88FF88>[log]</color>" : "")}", bugAdminRowStyle);
                GUI.Label(new Rect(rect.x + 8, rect.y + linePadTop + lineH * 2,    rect.width - 16, lineH),
                          $"<color=#EEEEEE>{desc}</color>", bugAdminRowStyle);
                if (GUI.Button(rect, GUIContent.none, GUIStyle.none))
                {
                    bugAdminSelectedId = r.id;
                    ApiClient.CachedBugReportDetail = null;
                    bugAdminCommentDraft = "";
                    bugAdminActionStatus = "";
                    string sid = MatchTracker.LocalSteamId;
                    ApiClient.FetchBugReportDetail(sid, r.id);
                }
            }
            if (reports.Count == 0)
            {
                string msg = string.IsNullOrEmpty(q)
                    ? "<color=#888>(no reports yet)</color>"
                    : $"<color=#888>(no reports match '{q}')</color>";
                GUI.Label(new Rect(8, 8, listW - 40, 30), msg, bugAdminRowStyle);
            }
            GUI.EndScrollView();

            // ── Right pane: detail + actions + activity ──────────────
            float detailX = x + listW;
            float detailW = w - listW;
            GUI.DrawTexture(new Rect(detailX, bodyY, detailW, bodyH), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0.05f, 0.07f, 0.10f, 0.95f), 0, 0);
            var d = ApiClient.CachedBugReportDetail;
            if (d == null || string.IsNullOrEmpty(bugAdminSelectedId))
            {
                GUI.Label(new Rect(detailX + 12, bodyY + 12, detailW - 24, 30),
                          "<color=#888>Click a report on the left to view full detail + log.</color>", bugAdminRowStyle);
                return;
            }

            // Status action row at top of detail.
            // Sync the dropdown index to the loaded status so the picker
            // doesn't display the previously-selected report's status.
            int curIdx = Array.IndexOf(BUG_STATUSES, (d.status ?? "open").ToLower());
            if (curIdx < 0) curIdx = 0;
            if (bugAdminStatusIdx < 0 || bugAdminStatusIdx >= BUG_STATUSES.Length)
                bugAdminStatusIdx = curIdx;

            float actY = bodyY + 8;
            GUI.Label(new Rect(detailX + 8, actY, 80, 22), "<b>Status:</b>", bugAdminRowStyle);
            for (int si = 0; si < BUG_STATUSES.Length; si++)
            {
                bool picked = si == bugAdminStatusIdx;
                if (GUI.Button(new Rect(detailX + 80 + si * 76, actY - 2, 72, 24),
                               BUG_STATUSES[si].ToUpper(),
                               picked ? bugAdminTabActiveStyle : bugAdminTabStyle))
                    bugAdminStatusIdx = si;
            }
            if (GUI.Button(new Rect(detailX + 80 + BUG_STATUSES.Length * 76 + 8, actY - 2, 96, 24), "Apply Status"))
            {
                string sid = MatchTracker.LocalSteamId;
                string ns = BUG_STATUSES[bugAdminStatusIdx];
                bugAdminActionStatus = "<color=#88CCFF>updating...</color>";
                ApiClient.AdminBugReportStatus(sid, d.id, ns, null, (ok, resp) =>
                {
                    bugAdminActionStatus = ok ? "<color=#88FF88>status updated</color>"
                                              : $"<color=#FF6666>fail: {(resp ?? "").Replace("\n", " ")}</color>";
                    if (ok)
                    {
                        ApiClient.FetchBugReportDetail(sid, d.id);
                        ApiClient.FetchBugReports(sid);
                    }
                });
            }
            if (!string.IsNullOrEmpty(bugAdminActionStatus))
                GUI.Label(new Rect(detailX + 8, actY + 24, detailW - 16, 18), bugAdminActionStatus, bugAdminRowStyle);

            // Detail body (description + repro + log + events).
            var sbDet = new System.Text.StringBuilder();
            string headerId = d.bug_number > 0 ? $"<color=#FFE580>#{d.bug_number}</color>  " : "";
            sbDet.AppendLine($"{headerId}<b>{(d.display_name ?? d.steam_id)}</b>  <color=#888>{d.steam_id}</color>");
            sbDet.AppendLine($"<color=#888>{ShortDate(d.created_at)} | mod={d.mod_version} | game={d.game_version}</color>");
            sbDet.AppendLine($"<b>severity:</b> {d.severity}   <b>category:</b> {d.category}   <b>status:</b> {d.status}");
            sbDet.AppendLine();
            sbDet.AppendLine($"<b><color=#FFD94D>Description:</color></b>");
            sbDet.AppendLine(d.description ?? "(empty)");
            if (!string.IsNullOrEmpty(d.repro_steps))
            {
                sbDet.AppendLine();
                sbDet.AppendLine($"<b><color=#FFD94D>Repro:</color></b>");
                sbDet.AppendLine(d.repro_steps);
            }
            if (d.events != null && d.events.Count > 0)
            {
                sbDet.AppendLine();
                sbDet.AppendLine($"<b><color=#99CCFF>Activity ({d.events.Count}):</color></b>");
                foreach (var e in d.events)
                {
                    string ts = ShortDate(e.created_at);
                    string who = e.actor_name ?? "?";
                    if (e.event_type == "status_change")
                        sbDet.AppendLine($"  <color=#888>{ts}</color> <b>{who}</b> <color=#FFCC66>{e.old_status ?? "?"} -> {e.new_status ?? "?"}</color>{(string.IsNullOrEmpty(e.comment) ? "" : "  -- " + e.comment)}");
                    else if (e.event_type == "created")
                        sbDet.AppendLine($"  <color=#888>{ts}</color> <b>{who}</b> <color=#88FF88>filed report</color>");
                    else
                        sbDet.AppendLine($"  <color=#888>{ts}</color> <b>{who}:</b> {e.comment ?? ""}");
                }
            }
            if (!string.IsNullOrEmpty(d.log_text))
            {
                sbDet.AppendLine();
                int fullLen = d.log_text.Length;
                const int DISPLAY_CAP = 400_000;
                string log = d.log_text;
                string truncNote = "";
                if (log.Length > DISPLAY_CAP)
                {
                    log = "[... earlier content trimmed for display - see ssh bug-log:" + d.bug_number + " for full ...]\n"
                          + log.Substring(log.Length - DISPLAY_CAP);
                    truncNote = $" — <color=#FFCC66>showing last {DISPLAY_CAP:N0} of {fullLen:N0} chars</color>";
                }
                sbDet.AppendLine($"<b><color=#88CCFF>Attached log ({d.log_bytes:N0} bytes gzipped on disk, {fullLen:N0} chars decoded){truncNote}:</color></b>");
                sbDet.AppendLine(log);
            }

            string body = sbDet.ToString();
            float scrollTop = actY + 48;
            float commentRowH = 96;      // reserved at bottom for comment input
            float scrollH = bodyH - (scrollTop - bodyY) - commentRowH - 8;
            float bw = detailW - 24;
            float bh = Mathf.Max(scrollH, body.Length / 90f * 14f + 80f);
            bugAdminDetailScroll = GUI.BeginScrollView(new Rect(detailX + 8, scrollTop, detailW - 12, scrollH),
                                                        bugAdminDetailScroll,
                                                        new Rect(0, 0, bw - 12, bh));
            GUI.Label(new Rect(4, 4, bw - 12, bh - 8), body, bugAdminDetailStyle);
            GUI.EndScrollView();

            // Comment input + submit at the bottom.
            float cY = bodyY + bodyH - commentRowH;
            GUI.Label(new Rect(detailX + 8, cY, 200, 18), "<b>Add comment:</b>", bugAdminRowStyle);
            bugAdminCommentDraft = GUI.TextArea(new Rect(detailX + 8, cY + 20, detailW - 130, commentRowH - 26),
                                                bugAdminCommentDraft ?? "", 2000);
            bool canSubmit = !string.IsNullOrEmpty((bugAdminCommentDraft ?? "").Trim());
            GUI.enabled = canSubmit;
            if (GUI.Button(new Rect(detailX + detailW - 116, cY + 20, 108, commentRowH - 26), "Post Comment"))
            {
                string sid = MatchTracker.LocalSteamId;
                string c = (bugAdminCommentDraft ?? "").Trim();
                bugAdminActionStatus = "<color=#88CCFF>posting...</color>";
                ApiClient.AdminBugReportComment(sid, d.id, c, (ok, resp) =>
                {
                    bugAdminActionStatus = ok ? "<color=#88FF88>comment posted</color>"
                                              : $"<color=#FF6666>fail: {(resp ?? "").Replace("\n", " ")}</color>";
                    if (ok)
                    {
                        bugAdminCommentDraft = "";
                        ApiClient.FetchBugReportDetail(sid, d.id);
                    }
                });
            }
            GUI.enabled = true;
        }

        private static string ShortDate(string isoStr)
        {
            if (string.IsNullOrEmpty(isoStr)) return "?";
            try
            {
                var dt = DateTime.Parse(isoStr, null, System.Globalization.DateTimeStyles.RoundtripKind).ToLocalTime();
                return dt.ToString("M/d HH:mm", System.Globalization.CultureInfo.InvariantCulture);
            }
            catch { return isoStr; }
        }

        // ── Input overlay (UI.ShowInputOverlay) ──────────────────
        // Bottom-left WASD + Space + LMB/RMB indicator. Pressed keys turn red.
        // Only drawn while in a match — useful for stream overlays and for
        // confirming inputs register (helps debug "block didn't fire" reports).
        private static GUIStyle inputKeyStyle;
        private static GUIStyle inputKeySmallStyle;
        private static void DrawInputOverlay()
        {
            if (Plugin.ShowInputOverlay == null || !Plugin.ShowInputOverlay.Value) return;
            if (!GameStateWatcher.IsInMatch) return;
            if (inputKeyStyle == null)
            {
                inputKeyStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 18, richText = true,
                    alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold,
                };
                inputKeySmallStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 12, richText = true,
                    alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold,
                };
            }

            bool w = Input.GetKey(KeyCode.W);
            bool a = Input.GetKey(KeyCode.A);
            bool s = Input.GetKey(KeyCode.S);
            bool d = Input.GetKey(KeyCode.D);
            bool space = Input.GetKey(KeyCode.Space);
            bool lmb = Input.GetMouseButton(0);
            bool rmb = Input.GetMouseButton(1);

            // Geometry: bottom-left, two stacked rows for keyboard, mouse row below.
            float keyW = 38, keyH = 38, gap = 4;
            float originX = 14;
            // Layout from the bottom up: mouse row, spacer, WASD rows.
            float bottomY = Screen.height - 14;
            // Mouse row (LMB + RMB, wider keys labeled).
            float mouseRowY = bottomY - keyH;
            float mKeyW = keyW * 1.6f;
            DrawKeyBox(new Rect(originX, mouseRowY, mKeyW, keyH), "LMB", lmb, true);
            DrawKeyBox(new Rect(originX + mKeyW + gap, mouseRowY, mKeyW, keyH), "RMB", rmb, true);
            float mouseRowW = (mKeyW * 2) + gap;
            // Spacer
            float wasdBottomY = mouseRowY - 10 - keyH;
            // Bottom WASD row: A S D
            float asdX = originX + keyW + gap;  // align under W
            DrawKeyBox(new Rect(originX,                 wasdBottomY, keyW, keyH), "A", a, false);
            DrawKeyBox(new Rect(originX + keyW + gap,    wasdBottomY, keyW, keyH), "S", s, false);
            DrawKeyBox(new Rect(originX + (keyW+gap)*2,  wasdBottomY, keyW, keyH), "D", d, false);
            // W row on top
            float wRowY = wasdBottomY - keyH - gap;
            DrawKeyBox(new Rect(originX + keyW + gap,    wRowY, keyW, keyH), "W", w, false);
            // Space bar (wide) under the WASD cluster, between WASD and mouse.
            float spaceY = mouseRowY - 6 - keyH;
            float spaceW = (keyW + gap) * 3 - gap;
            // But this collides with WASD layout — instead place SPACE to the
            // right of WASD on the same row as the bottom WASD line.
            DrawKeyBox(new Rect(originX + (keyW+gap)*3 + 8, wasdBottomY, spaceW, keyH), "SPACE", space, true);
        }

        private static void DrawKeyBox(Rect r, string label, bool pressed, bool small)
        {
            // Pressed = red fill + bright label; idle = dim gray fill, white label.
            Color fill = pressed
                ? new Color(0.85f, 0.18f, 0.18f, 0.92f)
                : new Color(0.10f, 0.10f, 0.13f, 0.78f);
            Color edge = pressed
                ? new Color(1f, 0.5f, 0.5f, 0.9f)
                : new Color(1f, 1f, 1f, 0.35f);
            GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, fill, 0, 0);
            // 1px edge — drawn as 4 thin rects.
            GUI.DrawTexture(new Rect(r.x, r.y, r.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            GUI.DrawTexture(new Rect(r.x, r.y + r.height - 1, r.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            GUI.DrawTexture(new Rect(r.x, r.y, 1, r.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            GUI.DrawTexture(new Rect(r.x + r.width - 1, r.y, 1, r.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            var prev = GUI.contentColor;
            GUI.contentColor = Color.white;
            GUI.Label(r, label, small ? inputKeySmallStyle : inputKeyStyle);
            GUI.contentColor = prev;
        }

        // ── Block debug overlay (opt-in, UI.ShowBlockDebug config) ────────
        // Top-right floating panel showing live Act/Succ counters plus the last
        // event type + flash, so players can eyeball every TryBlock + DoBlock
        // fire during a match. Also classifies hits (too early / too slow /
        // unblockable).
        private static GUIStyle blockDbgStyle;
        private static GUIStyle blockDbgSmallStyle;

        private static void DrawBlockDebug()
        {
            if (Plugin.ShowBlockDebug == null || !Plugin.ShowBlockDebug.Value) return;
            if (!GameStateWatcher.IsInMatch) return;

            if (blockDbgStyle == null)
            {
                blockDbgStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 15, richText = true, alignment = TextAnchor.UpperLeft,
                    fontStyle = FontStyle.Bold,
                };
                blockDbgSmallStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 12, richText = true, alignment = TextAnchor.UpperLeft,
                };
            }

            int act = GameStateWatcher.LocalBlocksActivatedThisMatch;
            int succ = GameStateWatcher.LocalBlocksSuccessfulThisMatch;
            int raw = GameStateWatcher.LocalBlockRawAbsorbs;
            int drops = GameStateWatcher.LocalBlockDedupeDrops;
            float now = Time.time;
            float sinceAct = now - GameStateWatcher.LastBlockActivatedTime;
            float sinceSucc = now - GameStateWatcher.LastBlockSuccessfulTime;
            float sinceAbs = now - GameStateWatcher.LastBlockAbsorbTime;
            float sinceMiss = now - GameStateWatcher.LastBlockMissTime;
            string lastEvent = GameStateWatcher.LastBlockEventLabel ?? "";

            // Panel geometry — top-right, about 260×120.
            float w = 270, h = 110, pad = 6;
            float x = Screen.width - w - 12, y = 12;

            // Flash: most-recent of {success, activation, deduped-absorb, miss}
            // wins the backdrop tint for ~0.35s. Miss = red (too slow/early/etc),
            // success = green, activation = blue, absorb-deduped = yellow.
            Color bg = new Color(0, 0, 0, 0.72f);
            float minAge = Mathf.Min(sinceAct, Mathf.Min(sinceSucc, Mathf.Min(sinceAbs, sinceMiss)));
            if (minAge >= 0f && minAge < 0.35f)
            {
                float t = 1f - (minAge / 0.35f);  // 1 → 0
                Color flash;
                if (sinceMiss <= minAge + 0.001f)
                    flash = new Color(0.95f, 0.25f, 0.25f, 0.9f);  // red = hit/miss
                else if (sinceSucc <= minAge + 0.001f)
                    flash = new Color(0.2f, 0.9f, 0.2f, 0.85f);    // green = credited success
                else if (sinceAct <= minAge + 0.001f)
                    flash = new Color(0.3f, 0.55f, 1f, 0.85f);     // blue = activation
                else
                    flash = new Color(0.95f, 0.7f, 0.1f, 0.85f);   // yellow = absorb-but-deduped
                bg = Color.Lerp(bg, flash, t);
            }

            GUI.DrawTexture(new Rect(x, y, w, h),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, bg, 0, 0);
            GUI.DrawTexture(new Rect(x, y, w, 1),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(1,1,1,0.5f), 0, 0);

            var prev = GUI.contentColor;
            GUI.contentColor = Color.white;
            GUI.Label(new Rect(x + pad, y + pad, w - pad*2, 20), "<color=#FFE580>BLOCK DEBUG</color>", blockDbgStyle);

            // Big counters line
            string counters =
                $"<color=#88CCFF>Act:</color> <b>{act}</b>   " +
                $"<color=#88FF88>Succ:</color> <b>{succ}</b>   " +
                $"<color=#CCCCCC>Raw:</color> {raw}";
            GUI.Label(new Rect(x + pad, y + pad + 22, w - pad*2, 20), counters, blockDbgStyle);

            // Secondary line — dedupe drops + pct
            string pct = act > 0 ? $"{(float)succ * 100f / act:F0}%" : "-";
            string line3 = $"<color=#AAAAAA>Drops:</color> {drops}   <color=#AAAAAA>Rate:</color> <b>{pct}</b>";
            GUI.Label(new Rect(x + pad, y + pad + 44, w - pad*2, 18), line3, blockDbgSmallStyle);

            // Last event
            string ageTxt = "";
            if (!string.IsNullOrEmpty(lastEvent) && minAge < 5f && minAge >= 0)
                ageTxt = $"{lastEvent}  <color=#888>(+{minAge:F1}s)</color>";
            GUI.Label(new Rect(x + pad, y + pad + 64, w - pad*2, 18), ageTxt, blockDbgSmallStyle);

            GUI.Label(new Rect(x + pad, y + pad + 82, w - pad*2, 14),
                "<color=#666><i>debug overlay — CompetitiveUI.BlockDebugEnabled</i></color>",
                blockDbgSmallStyle);
            GUI.contentColor = prev;
        }

        // ── In-game chat overlay ─────────────────────────────────
        // Persistent left-side panel so players see messages without opening F5.
        // Hidden while F5 is open (NativeUI has its own full log) and behind the
        // consent modal.
        private static GUIStyle ingameChatStyle;

        private static void DrawInGameChat()
        {
            if (Plugin.ShowIngameChat != null && !Plugin.ShowIngameChat.Value) return;
            if (!Plugin.DataConsentGranted) return;
            if (NativeUI.IsOpen) return;  // the F5 chat panel covers this

            var entries = NativeUI.SnapshotChat(8);
            if (entries == null || entries.Length == 0) return;

            if (ingameChatStyle == null)
            {
                ingameChatStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 14,
                    wordWrap = true,
                    richText = true,
                    alignment = TextAnchor.UpperLeft,
                };
            }

            // Compute alphas first so the backdrop can match the most-visible line.
            var now = DateTime.UtcNow;
            float[] alphas = new float[entries.Length];
            float maxAlpha = 0f;
            int visibleCount = 0;
            for (int i = 0; i < entries.Length; i++)
            {
                double age = (now - entries[i].AddedUtc).TotalSeconds;
                float a = age < 25 ? 1f : age < 35 ? 1f - (float)((age - 25) / 10.0) : 0f;
                alphas[i] = a;
                if (a > 0.02f) { visibleCount++; if (a > maxAlpha) maxAlpha = a; }
            }
            if (visibleCount == 0) return;

            // Anchor bottom-left, grow upward (newest at the bottom, older above).
            float w = 440, lineH = 20, padding = 6;
            float x = 12;
            float panelH = visibleCount * lineH + padding * 2;
            float yBottom = Screen.height - 90;   // above FPS/ping overlay, clear of HUD
            float yTop = yBottom - panelH;

            GUI.DrawTexture(new Rect(x - 4, yTop, w + 8, panelH),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0, 0, 0, 0.55f * maxAlpha), 0, 0);

            // Render newest-at-bottom. entries[last] is newest.
            int visIdx = 0;
            for (int i = entries.Length - 1; i >= 0; i--)
            {
                float a = alphas[i];
                if (a <= 0.02f) continue;
                var prev = GUI.contentColor;
                GUI.contentColor = new Color(1f, 1f, 1f, a);
                float lineY = yBottom - padding - (visIdx + 1) * lineH;
                GUI.Label(new Rect(x, lineY, w, lineH), entries[i].Line, ingameChatStyle);
                GUI.contentColor = prev;
                visIdx++;
            }
        }

        // ── Admin prompt (IMGUI overlay) ─────────────────────────
        // Modal called from the Admin tab buttons. Mode determines which fields are shown:
        //   "ban":     target_steam_id + reason
        //   "grant":   target_steam_id + achievement_key
        //   "reverse": series_id + reason
        // Submit invokes the matching ApiClient.Admin* call. Closes on Submit / Cancel / Escape.
        private static bool adminPromptOpen = false;
        private static string adminPromptMode = "";  // "ban" | "grant" | "unban" | "reverse"
        private static string adminInputA = "";       // primary id (steam_id or series_id)
        private static string adminInputB = "";       // secondary (reason or achievement_key)
        private static GUIStyle adminFieldStyle, adminLabelStyle;
        // Achievement key list for the grant prompt. Must match the keys in
        // ACHIEVEMENT_DEFS in backend/api/main.py — wrong keys here gave a 400
        // when picked. (Earlier list had "first_blood", "comeback_kid", "phoenix"
        // etc. that didn't exist server-side.)
        private static readonly string[] ADMIN_ACHIEVEMENT_KEYS = new[] {
            "untouchable", "silent_assassin", "total_mayhem", "fragile_perfection",
            "no_escape", "rise_from_the_ashes", "the_comeback_kid", "stacked_deck",
            "regicide", "pacifist", "immovable_object",
            "master_rank", "team_sweep",
        };

        public static void OpenAdminPrompt(string mode)
        {
            adminPromptMode = mode ?? "";
            adminInputA = "";
            adminInputB = mode == "grant" ? ADMIN_ACHIEVEMENT_KEYS[0] : "";
            adminPromptOpen = true;
        }

        private static void DrawAdminPrompt()
        {
            if (!adminPromptOpen) return;
            if (!NativeUI.IsOpen) { adminPromptOpen = false; return; }

            var ev = Event.current;
            bool submit = false, cancel = false;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            { cancel = true; ev.Use(); }

            if (adminFieldStyle == null) adminFieldStyle = new GUIStyle(GUI.skin.textField) { fontSize = 15 };
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label)     { fontSize = 14 };

            float w = 560, h = 220;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.92f), 0, 0);

            string title = adminPromptMode switch
            {
                "ban"     => "Ban a player",
                "grant"   => "Grant an achievement",
                "reverse" => "Reverse a ranked series",
                _         => "Admin action",
            };
            GUI.Label(new Rect(x + 10, y + 8, w - 20, 24), title, new GUIStyle(adminLabelStyle) { fontSize = 17, fontStyle = FontStyle.Bold });

            string aLabel, bLabel;
            switch (adminPromptMode)
            {
                case "ban":     aLabel = "Target Steam ID"; bLabel = "Reason"; break;
                case "grant":   aLabel = "Target Steam ID"; bLabel = "Achievement key"; break;
                case "reverse": aLabel = "Series ID (UUID)"; bLabel = "Reason"; break;
                default:        aLabel = "ID"; bLabel = "Detail"; break;
            }

            GUI.Label(new Rect(x + 10, y + 38, 200, 20), aLabel, adminLabelStyle);
            adminInputA = GUI.TextField(new Rect(x + 10, y + 60, w - 20, 26), adminInputA ?? "", adminFieldStyle);

            GUI.Label(new Rect(x + 10, y + 96, 200, 20), bLabel, adminLabelStyle);
            if (adminPromptMode == "grant")
            {
                // Grant: cycle through allowed achievement keys via prev/next buttons.
                if (GUI.Button(new Rect(x + 10, y + 118, 30, 26), "<"))
                {
                    int i = Math.Max(0, Array.IndexOf(ADMIN_ACHIEVEMENT_KEYS, adminInputB));
                    i = (i - 1 + ADMIN_ACHIEVEMENT_KEYS.Length) % ADMIN_ACHIEVEMENT_KEYS.Length;
                    adminInputB = ADMIN_ACHIEVEMENT_KEYS[i];
                }
                GUI.Label(new Rect(x + 50, y + 122, w - 100, 22), adminInputB, adminLabelStyle);
                if (GUI.Button(new Rect(x + w - 40, y + 118, 30, 26), ">"))
                {
                    int i = Math.Max(0, Array.IndexOf(ADMIN_ACHIEVEMENT_KEYS, adminInputB));
                    i = (i + 1) % ADMIN_ACHIEVEMENT_KEYS.Length;
                    adminInputB = ADMIN_ACHIEVEMENT_KEYS[i];
                }
            }
            else
            {
                adminInputB = GUI.TextField(new Rect(x + 10, y + 118, w - 20, 26), adminInputB ?? "", adminFieldStyle);
            }

            if (GUI.Button(new Rect(x + 10, y + h - 36, 100, 28), "Cancel")) cancel = true;
            if (GUI.Button(new Rect(x + w - 110, y + h - 36, 100, 28), "Submit")) submit = true;

            if (cancel) { adminPromptOpen = false; return; }

            if (submit)
            {
                var sid = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(sid))
                {
                    Plugin.Log.LogWarning("[ADMIN] No local Steam ID");
                    adminPromptOpen = false; return;
                }
                string a = (adminInputA ?? "").Trim();
                string b = (adminInputB ?? "").Trim();
                if (string.IsNullOrEmpty(a)) return;  // require primary id
                Action<bool, string> done = (ok, resp) =>
                {
                    Plugin.Log.LogInfo($"[ADMIN] {adminPromptMode} -> {(ok?"OK":"FAIL")} {resp}");
                    if (ok) { ApiClient.FetchFlaggedMatches(sid); ApiClient.FetchBannedUsers(sid); }
                };
                switch (adminPromptMode)
                {
                    case "ban":     ApiClient.AdminBan(sid, a, string.IsNullOrEmpty(b) ? "violation" : b, done); break;
                    case "grant":   ApiClient.AdminGrantAchievement(sid, a, b, done); break;
                    case "reverse": ApiClient.AdminReverseSeries(sid, a, string.IsNullOrEmpty(b) ? "admin_reverse" : b, done); break;
                }
                adminPromptOpen = false;
            }
        }

        // ── Bug report modal (v1.26.7) ─────────────────────────────────────
        // F5 → Help/About → "Report a Bug" opens this. Submits to the server's
        // /api/v1/bug-reports endpoint. Includes the active BepInEx/Unity log
        // tail when the "send logs" box stays checked. The log viewer button
        // pops the secondary modal below so users can preview what they're
        // sending.
        private static readonly string[] BUG_SEVERITIES = new[] { "low", "medium", "high", "crash" };
        private static readonly string[] BUG_CATEGORIES = new[] { "ui", "gameplay", "network", "other" };
        private static bool bugModalOpen = false;
        private static string bugDescription = "";
        private static string bugRepro = "";
        private static int bugSeverityIdx = 1;   // default = medium
        private static int bugCategoryIdx = 3;   // default = other
        private static bool bugSendLogs = true;  // pre-checked per requirement
        private static string bugSubmitStatus = "";
        private static bool bugSubmitting = false;
        private static Vector2 bugDescScroll, bugReproScroll;
        private static GUIStyle bugTitleStyle, bugLabelStyle, bugFieldStyle, bugAreaStyle, bugButtonStyle, bugBtnPickedStyle;

        public static void OpenBugReportModal()
        {
            bugModalOpen = true;
            bugSubmitStatus = "";
            bugSubmitting = false;
        }

        private static void EnsureBugStyles()
        {
            if (bugTitleStyle != null) return;
            bugTitleStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 19, fontStyle = FontStyle.Bold, richText = true,
                alignment = TextAnchor.MiddleLeft,
            };
            bugLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 13, richText = true };
            bugFieldStyle = new GUIStyle(GUI.skin.textField) { fontSize = 14 };
            bugAreaStyle = new GUIStyle(GUI.skin.textArea) { fontSize = 13, wordWrap = true };
            bugButtonStyle = new GUIStyle(GUI.skin.button) { fontSize = 13 };
            bugBtnPickedStyle = new GUIStyle(GUI.skin.button)
            {
                fontSize = 13, fontStyle = FontStyle.Bold,
                normal = { background = Texture2D.whiteTexture, textColor = Color.black },
                hover  = { background = Texture2D.whiteTexture, textColor = Color.black },
                active = { background = Texture2D.whiteTexture, textColor = Color.black },
            };
        }

        private static void DrawBugReportModal()
        {
            if (!bugModalOpen) return;
            if (!NativeUI.IsOpen) { bugModalOpen = false; return; }
            EnsureBugStyles();

            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            { bugModalOpen = false; ev.Use(); return; }

            float w = 680, h = 580;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            // Backdrop blocks click-through.
            GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.45f), 0, 0);
            GUI.DrawTexture(new Rect(x - 10, y - 10, w + 20, h + 20), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0.07f, 0.08f, 0.11f, 0.97f), 0, 0);
            GUI.DrawTexture(new Rect(x - 10, y - 10, w + 20, 1), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(1f, 1f, 1f, 0.4f), 0, 0);

            GUI.Label(new Rect(x, y, w, 28), "<color=#FFE580>Report a Bug</color>", bugTitleStyle);
            GUI.Label(new Rect(x, y + 30, w, 18),
                "<color=#AAAAAA>Reports go to the mod team. Be specific — what happened, when, what you were doing.</color>",
                bugLabelStyle);

            // Severity row
            GUI.Label(new Rect(x, y + 56, 120, 22), "<b>Severity:</b>", bugLabelStyle);
            for (int i = 0; i < BUG_SEVERITIES.Length; i++)
            {
                bool picked = i == bugSeverityIdx;
                if (GUI.Button(new Rect(x + 100 + i * 88, y + 54, 84, 26),
                               BUG_SEVERITIES[i].ToUpper(),
                               picked ? bugBtnPickedStyle : bugButtonStyle))
                    bugSeverityIdx = i;
            }

            // Category row
            GUI.Label(new Rect(x, y + 92, 120, 22), "<b>Category:</b>", bugLabelStyle);
            for (int i = 0; i < BUG_CATEGORIES.Length; i++)
            {
                bool picked = i == bugCategoryIdx;
                if (GUI.Button(new Rect(x + 100 + i * 88, y + 90, 84, 26),
                               BUG_CATEGORIES[i].ToUpper(),
                               picked ? bugBtnPickedStyle : bugButtonStyle))
                    bugCategoryIdx = i;
            }

            // Description (required)
            GUI.Label(new Rect(x, y + 126, w, 18), "<b>What happened?</b> <color=#FF9966>(required)</color>", bugLabelStyle);
            bugDescScroll = GUI.BeginScrollView(new Rect(x, y + 146, w, 140),
                                                bugDescScroll,
                                                new Rect(0, 0, w - 20, Mathf.Max(140, (bugDescription?.Length ?? 0) / 4)));
            bugDescription = GUI.TextArea(new Rect(0, 0, w - 20, Mathf.Max(140, (bugDescription?.Length ?? 0) / 4)),
                                          bugDescription ?? "", 4000, bugAreaStyle);
            GUI.EndScrollView();

            // Repro
            GUI.Label(new Rect(x, y + 296, w, 18), "<b>How to reproduce?</b> <color=#888>(optional)</color>", bugLabelStyle);
            bugReproScroll = GUI.BeginScrollView(new Rect(x, y + 316, w, 100),
                                                 bugReproScroll,
                                                 new Rect(0, 0, w - 20, Mathf.Max(100, (bugRepro?.Length ?? 0) / 4)));
            bugRepro = GUI.TextArea(new Rect(0, 0, w - 20, Mathf.Max(100, (bugRepro?.Length ?? 0) / 4)),
                                    bugRepro ?? "", 4000, bugAreaStyle);
            GUI.EndScrollView();

            // Send logs row: checkbox + label on the LEFT, "Preview logs" button
            // on the RIGHT. Clickable areas are split so clicking Preview doesn't
            // also toggle the checkbox.
            float togX = x;
            float togW = 280;            // hit area for the checkbox+label (NOT the whole row)
            var toggleRect = new Rect(togX, y + 428, togW, 26);
            if (GUI.Button(toggleRect, GUIContent.none, GUIStyle.none))
                bugSendLogs = !bugSendLogs;
            var boxRect = new Rect(togX + 2, y + 430, 20, 20);
            Color boxFill = bugSendLogs ? new Color(0.25f, 0.7f, 0.3f, 0.95f) : new Color(0.18f, 0.18f, 0.22f, 0.95f);
            GUI.DrawTexture(boxRect, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, boxFill, 0, 0);
            GUI.DrawTexture(new Rect(boxRect.x, boxRect.y, boxRect.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            GUI.DrawTexture(new Rect(boxRect.x, boxRect.y + boxRect.height - 1, boxRect.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            GUI.DrawTexture(new Rect(boxRect.x, boxRect.y, 1, boxRect.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            GUI.DrawTexture(new Rect(boxRect.x + boxRect.width - 1, boxRect.y, 1, boxRect.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            if (bugSendLogs)
            {
                var checkStyle = new GUIStyle(bugLabelStyle) { fontSize = 16, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
                GUI.Label(boxRect, "<color=#FFFFFF>X</color>", checkStyle);
            }
            // Label sits inside the toggle hit area.
            GUI.Label(new Rect(togX + 28, y + 428, togW - 32, 26),
                      "Attach game logs (recommended)",
                      bugLabelStyle);
            // Preview button far to the right of the toggle hit area + a gap.
            float prevX = togX + togW + 16;
            if (GUI.Button(new Rect(prevX, y + 428, 140, 24), "Preview logs", bugButtonStyle))
            {
                OpenLogViewer();
            }

            // Status line
            if (!string.IsNullOrEmpty(bugSubmitStatus))
                GUI.Label(new Rect(x, y + 460, w, 20), bugSubmitStatus, bugLabelStyle);

            // Buttons
            bool disabled = bugSubmitting || string.IsNullOrEmpty(bugDescription) || bugDescription.Trim().Length < 4;
            GUI.enabled = !bugSubmitting;
            if (GUI.Button(new Rect(x, y + h - 44, 120, 30), "Cancel", bugButtonStyle))
            {
                bugModalOpen = false; GUI.enabled = true; return;
            }
            GUI.enabled = !disabled;
            if (GUI.Button(new Rect(x + w - 160, y + h - 44, 160, 30),
                           bugSubmitting ? "Submitting..." : "Submit Report",
                           bugButtonStyle))
            {
                SubmitBugReportNow();
            }
            GUI.enabled = true;
        }

        private static void SubmitBugReportNow()
        {
            bugSubmitting = true;
            bugSubmitStatus = "<color=#88CCFF>Submitting...</color>";
            string sid = MatchTracker.LocalSteamId;
            string name = MatchTracker.LocalDisplayName ?? "";
            string desc = (bugDescription ?? "").Trim();
            string repro = (bugRepro ?? "").Trim();
            string sev = BUG_SEVERITIES[Mathf.Clamp(bugSeverityIdx, 0, BUG_SEVERITIES.Length - 1)];
            string cat = BUG_CATEGORIES[Mathf.Clamp(bugCategoryIdx, 0, BUG_CATEGORIES.Length - 1)];
            string logBundle = bugSendLogs ? BuildLogBundle() : null;

            ApiClient.SubmitBugReport(sid, name, desc, repro, sev, cat, logBundle,
                (ok, resp) =>
                {
                    bugSubmitting = false;
                    if (ok)
                    {
                        // Pull bug_number out of the response so the user sees a
                        // human-friendly ID they can quote in chat.
                        int bn = ApiClient.ExtractJsonIntPublic(resp ?? "", "bug_number");
                        string idTag = bn > 0 ? $" Filed as <b>#{bn}</b>." : "";
                        bugSubmitStatus = $"<color=#88FF88>Sent! Thank you.{idTag}</color>";
                        bugDescription = "";
                        bugRepro = "";
                        string notif = bn > 0 ? $"Bug report sent. Thanks! (#{bn})" : "Bug report sent. Thanks!";
                        ShowNotification(notif, new Color(0.5f, 1f, 0.5f), 5f);
                        bugModalOpen = false;
                    }
                    else
                    {
                        bugSubmitStatus = $"<color=#FF6666>Failed: {(resp ?? "").Replace("\n", " ")}</color>";
                    }
                });
        }

        // Builds the bug-report log bundle: previous-session BepInEx snapshot
        // + current BepInEx + Unity, each capped INDIVIDUALLY so all three
        // fit in the submit cap with all three represented. Without per-section
        // budgets the post-concat ApiClient cap would tail-trim — losing the
        // BepInEx logs (which are usually the triage signal) when Unity's log
        // happened to be large.
        //
        // Budget split (~3.4M total, under ApiClient.BUG_REPORT_LOG_CAP_CHARS=3.5M):
        //   BepInEx current     1.5M  — most important for live diagnosis
        //   BepInEx prev        1.0M  — crash-on-prior-launch context
        //   Unity Player.log    1.0M  — engine-side hint when needed
        // Tail-most slice of each (most recent N chars) is taken. Each section
        // emits a clearly delimited header so a triage reader can split the
        // concatenation back into pieces.
        private const int BUNDLE_CAP_BEP_CURRENT = 1_500_000;
        private const int BUNDLE_CAP_BEP_PREV    = 1_000_000;
        private const int BUNDLE_CAP_UNITY       = 1_000_000;

        private static string BuildLogBundle()
        {
            string bep     = ApiClient.ReadLogTail(BepInExLogPath(),         maxChars: BUNDLE_CAP_BEP_CURRENT);
            string bepPrev = ApiClient.ReadLogTail(BepInExLogPreviousPath(), maxChars: BUNDLE_CAP_BEP_PREV);
            string uni     = ApiClient.ReadLogTail(UnityLogPath(),           maxChars: BUNDLE_CAP_UNITY);
            var sb = new System.Text.StringBuilder();
            if (!string.IsNullOrEmpty(bepPrev))
            {
                sb.AppendLine($"===== BepInEx LogOutput-prev.log [{BepInExLogPreviousPath()}]  ({bepPrev.Length:N0} chars, cap {BUNDLE_CAP_BEP_PREV:N0}) =====");
                sb.AppendLine(bepPrev);
                sb.AppendLine();
            }
            sb.AppendLine($"===== BepInEx LogOutput.log [{BepInExLogPath() ?? "(path unknown)"}]  ({(bep?.Length ?? 0):N0} chars, cap {BUNDLE_CAP_BEP_CURRENT:N0}) =====");
            sb.AppendLine(string.IsNullOrEmpty(bep) ? "(not found)" : bep);
            sb.AppendLine();
            sb.AppendLine($"===== Unity Player.log [{UnityLogPath() ?? "(path unknown)"}]  ({(uni?.Length ?? 0):N0} chars, cap {BUNDLE_CAP_UNITY:N0}) =====");
            sb.AppendLine(string.IsNullOrEmpty(uni) ? "(not found)" : uni);
            return sb.ToString();
        }

        // Walks from the plugin assembly's location back to <ROUNDS>/BepInEx/.
        // Assembly is at <ROUNDS>/BepInEx/plugins/CompetitiveRounds/CompetitiveRounds.dll
        // so two GetDirectoryName calls land at <ROUNDS>/BepInEx/plugins, and one more
        // step up gets us to <ROUNDS>/BepInEx (where LogOutput.log lives by default).
        private static string BepInExDir()
        {
            try
            {
                string asm = typeof(Plugin).Assembly.Location;
                if (string.IsNullOrEmpty(asm)) return null;
                string pluginsDir = Path.GetDirectoryName(Path.GetDirectoryName(asm));
                if (string.IsNullOrEmpty(pluginsDir)) return null;
                return Path.GetDirectoryName(pluginsDir);
            }
            catch { return null; }
        }

        private static string GameRoot()
        {
            try
            {
                string bep = BepInExDir();
                return string.IsNullOrEmpty(bep) ? null : Path.GetDirectoryName(bep);
            }
            catch { return null; }
        }

        private static string BepInExLogPath()
        {
            string bep = BepInExDir();
            if (string.IsNullOrEmpty(bep)) return null;
            return Path.Combine(bep, "LogOutput.log");
        }

        // Public accessor for Plugin.Awake — needs to snapshot the current log
        // to LogOutput-prev.log at Application.quitting so the previous-session
        // crash data is recoverable after a relaunch (BepInEx 5 truncates the
        // active log on every startup by default, so without this snapshot the
        // crash trace is lost the moment the player reopens to file a report).
        public static string BepInExLogPathPublic() => BepInExLogPath();

        // Path to the previous-session snapshot. Always returned (caller checks
        // existence) so Plugin.Awake can write there at quit time.
        public static string BepInExLogPreviousPath()
        {
            string bep = BepInExDir();
            return string.IsNullOrEmpty(bep) ? null : Path.Combine(bep, "LogOutput-prev.log");
        }

        private static string UnityLogPath()
        {
            // Unity writes Player.log to LocalLow\Landfall Games\ROUNDS\Player.log
            // on a fresh ROUNDS install. Also try the legacy <ROUNDS>/output_log.txt
            // for backwards compatibility.
            try
            {
                string root = GameRoot();
                if (!string.IsNullOrEmpty(root))
                {
                    string legacy = Path.Combine(root, "output_log.txt");
                    if (System.IO.File.Exists(legacy)) return legacy;
                }
                string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (!string.IsNullOrEmpty(localApp))
                {
                    foreach (var publisher in new[] { "Landfall Games", "Landfall" })
                    {
                        string p = Path.GetFullPath(Path.Combine(localApp, "..", "LocalLow", publisher, "ROUNDS", "Player.log"));
                        if (System.IO.File.Exists(p)) return p;
                    }
                }
            }
            catch { }
            return null;
        }

        // ── Log viewer modal ────────────────────────────────────────────
        private static bool logViewerOpen = false;
        private static int logViewerTab = 0;     // 0=BepInEx, 1=BepInEx-prev, 2=Unity
        private static Vector2 logViewerScroll;
        private static string logViewerBepCache, logViewerBepPrevCache, logViewerUniCache;
        private static GUIStyle logViewerStyle, logViewerTabStyle, logViewerTabActiveStyle;

        private static void OpenLogViewer()
        {
            logViewerOpen = true;
            logViewerBepCache     = ApiClient.ReadLogTail(BepInExLogPath(), maxChars: 400_000);
            logViewerBepPrevCache = ApiClient.ReadLogTail(BepInExLogPreviousPath(), maxChars: 400_000);
            logViewerUniCache     = ApiClient.ReadLogTail(UnityLogPath(), maxChars: 400_000);
            Plugin.Log.LogInfo($"[BUG-REPORT-VIEWER] bep_path={BepInExLogPath()} bep_chars={logViewerBepCache?.Length ?? 0}; " +
                               $"prev_path={BepInExLogPreviousPath()} prev_chars={logViewerBepPrevCache?.Length ?? 0}; " +
                               $"uni_path={UnityLogPath()} uni_chars={logViewerUniCache?.Length ?? 0}");
        }

        private static void DrawLogViewerModal()
        {
            if (!logViewerOpen) return;
            if (!NativeUI.IsOpen) { logViewerOpen = false; return; }
            if (logViewerStyle == null)
            {
                logViewerStyle = new GUIStyle(GUI.skin.label)
                { fontSize = 12, richText = false, alignment = TextAnchor.UpperLeft, wordWrap = false };
                logViewerTabStyle = new GUIStyle(GUI.skin.button) { fontSize = 13 };
                logViewerTabActiveStyle = new GUIStyle(GUI.skin.button)
                {
                    fontSize = 13, fontStyle = FontStyle.Bold,
                    normal = { background = Texture2D.whiteTexture, textColor = Color.black },
                    hover  = { background = Texture2D.whiteTexture, textColor = Color.black },
                };
            }

            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            { logViewerOpen = false; ev.Use(); return; }

            float w = Mathf.Min(Screen.width - 60, 1100);
            float h = Mathf.Min(Screen.height - 80, 720);
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.55f), 0, 0);
            GUI.DrawTexture(new Rect(x - 10, y - 10, w + 20, h + 20), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0.05f, 0.06f, 0.08f, 0.98f), 0, 0);

            GUI.Label(new Rect(x, y, w, 24), "<b>Game logs (tail)</b> — included with your report when the box is checked.",
                      bugLabelStyle ?? GUI.skin.label);

            // Tab labels kept short so they fit inside the buttons without clipping
            // — earlier "BepInEx (previous session)" cut off the trailing "n)".
            if (GUI.Button(new Rect(x, y + 28, 160, 26), "BepInEx (current)",
                           logViewerTab == 0 ? logViewerTabActiveStyle : logViewerTabStyle))
                logViewerTab = 0;
            if (GUI.Button(new Rect(x + 168, y + 28, 180, 26), "BepInEx (prev session)",
                           logViewerTab == 1 ? logViewerTabActiveStyle : logViewerTabStyle))
                logViewerTab = 1;
            if (GUI.Button(new Rect(x + 356, y + 28, 140, 26), "Unity / Game",
                           logViewerTab == 2 ? logViewerTabActiveStyle : logViewerTabStyle))
                logViewerTab = 2;
            if (GUI.Button(new Rect(x + w - 200, y + 28, 90, 26), "Refresh", logViewerTabStyle))
            {
                logViewerBepCache     = ApiClient.ReadLogTail(BepInExLogPath(), maxChars: 400_000);
                logViewerBepPrevCache = ApiClient.ReadLogTail(BepInExLogPreviousPath(), maxChars: 400_000);
                logViewerUniCache     = ApiClient.ReadLogTail(UnityLogPath(), maxChars: 400_000);
            }
            if (GUI.Button(new Rect(x + w - 100, y + 28, 100, 26), "Close", logViewerTabStyle))
            { logViewerOpen = false; return; }

            string body, path;
            switch (logViewerTab)
            {
                case 0: body = logViewerBepCache;     path = BepInExLogPath();         break;
                case 1: body = logViewerBepPrevCache; path = BepInExLogPreviousPath(); break;
                default: body = logViewerUniCache;    path = UnityLogPath();           break;
            }
            if (string.IsNullOrEmpty(body))
            {
                if (logViewerTab == 1)
                    body = $"(no previous-session log yet — gets written by the mod when ROUNDS is closed cleanly, so on first ever launch this is empty)\n\nExpected path: {path ?? "unknown"}";
                else
                    body = $"(no log content read from: {path ?? "unknown path"})";
            }

            float bodyY = y + 64;
            float bodyH = h - 70;
            // Wide content rect so horizontal scrolling works for very long lines.
            float contentW = w - 30;
            float estLines = body.Length / 110f + 4;
            float contentH = Mathf.Max(bodyH - 12, estLines * 14f);
            logViewerScroll = GUI.BeginScrollView(new Rect(x, bodyY, w, bodyH),
                                                  logViewerScroll,
                                                  new Rect(0, 0, contentW, contentH));
            GUI.Label(new Rect(4, 4, contentW - 8, contentH - 4), body, logViewerStyle);
            GUI.EndScrollView();
        }

        // True when some OTHER uGUI/TMP text input field has focus — used to avoid stealing
        // T while the user is already typing into a different chat (Photon / another mod /
        // ROUNDS' own future chat). Detected via the EventSystem singleton's selected object;
        // we look for any component whose type name ends in "InputField" so we don't depend
        // on uGUI being a compile-time reference.
        private static Type s_eventSystemType;
        private static System.Reflection.PropertyInfo s_eventSystemCurrentProp;
        private static System.Reflection.PropertyInfo s_eventSystemSelectedProp;
        private static bool IsAnotherTextInputActive()
        {
            try
            {
                if (s_eventSystemType == null)
                {
                    foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                    {
                        s_eventSystemType = asm.GetType("UnityEngine.EventSystems.EventSystem");
                        if (s_eventSystemType != null) break;
                    }
                    if (s_eventSystemType == null) return false;
                    var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static;
                    s_eventSystemCurrentProp = s_eventSystemType.GetProperty("current", bf);
                    s_eventSystemSelectedProp = s_eventSystemType.GetProperty("currentSelectedGameObject",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                }
                var current = s_eventSystemCurrentProp?.GetValue(null);
                if (current == null) return false;
                var selected = s_eventSystemSelectedProp?.GetValue(current) as GameObject;
                if (selected == null) return false;
                // The selected GameObject can linger after its InputField has been hidden — closing
                // the other chat doesn't always clear EventSystem.currentSelectedGameObject. So
                // also require the GO to be active in the hierarchy AND the InputField component
                // to be enabled. Without these checks, T chat stays blocked indefinitely after
                // pressing Enter once.
                if (!selected.activeInHierarchy) return false;
                foreach (var co in selected.GetComponents<Component>())
                {
                    if (co == null) continue;
                    string n = co.GetType().Name;
                    if (n != "InputField" && n != "TMP_InputField" && !n.EndsWith("InputField"))
                        continue;
                    // Behaviour.isActiveAndEnabled covers both the GO and the component being on.
                    var isAEProp = co.GetType().GetProperty("isActiveAndEnabled",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                    bool live = isAEProp != null && (bool)isAEProp.GetValue(co);
                    if (live) return true;
                }
                return false;
            }
            catch { return false; }
        }

        // ── Chat input (IMGUI overlay) ───────────────────────────
        // Lives over the native F5 menu so we don't need TMP_InputField reflection
        // just for a one-line send box. Press T with the menu open to focus; Enter
        // sends, Escape cancels.
        private static bool chatInputOpen = false;
        /// <summary>True while the in-game chat IMGUI text field has focus. Used to
        /// suppress raw-key input tracking (Immovable Object achievement) so typing
        /// "wasd" in chat doesn't falsely flag movement.</summary>
        public static bool IsChatInputOpen => chatInputOpen;
        private static bool chatJustOpened = false;  // eats the 't' KeyDown-with-character event
        private static string chatInputText = "";
        private static GUIStyle chatStyle;

        private static void DrawChatInput()
        {
            // Chat input is now available outside the F5 menu too. Press T anywhere (including
            // mid-match in lobby/pick-phase/etc.) to open. Closed automatically if the player
            // is currently in active combat — we don't want T to swallow movement input. The
            // active-combat gate uses GameStateWatcher's existing pick/combat tracking.
            if (!Plugin.DataConsentGranted) return;
            bool combatActive = GameStateWatcher.IsInMatch && !NativeUI.IsOpen
                && GameStateWatcher.LocalAliveInCombatNow;
            // Don't hijack T while a modal IMGUI input is taking keystrokes —
            // bug report form, log viewer, admin bug viewer, and the Compare-tab
            // search field all have their own text entry that need T to type
            // "the", "tree", etc. (lopi: typing "t" in Compare search opened chat).
            if (bugModalOpen || logViewerOpen || bugAdminOpen || compareSearchFocused
                || NativeUI.CustomBetPromptOpen) return;

            var ev = Event.current;
            if (!chatInputOpen)
            {
                if (combatActive) return;
                // Don't open the T chat if some OTHER text input already has focus — covers
                // the user's "Enter chat" (Photon / mod chat) and any other uGUI/TMP InputField.
                // EventSystem.currentSelectedGameObject is non-null whenever a uGUI Selectable
                // owns focus; we additionally inspect it for any InputField-typed component so
                // we don't false-positive on plain buttons.
                if (IsAnotherTextInputActive()) return;
                if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.T)
                {
                    chatInputOpen = true;
                    chatJustOpened = true;
                    chatInputText = "";
                    ev.Use();
                }
                return;
            }

            // Unity IMGUI fires TWO KeyDown events per physical key: one with
            // keyCode set, and a second with ev.character set to the typed Unicode.
            // ev.Use() on the first doesn't stop the second. Skip the TextField
            // render for one frame so the 't' character event has no receiver.
            if (chatJustOpened)
            {
                chatJustOpened = false;
                if (ev != null && ev.type == EventType.KeyDown) ev.Use();
                return;
            }

            if (chatStyle == null)
            {
                chatStyle = new GUIStyle(GUI.skin.textField) { fontSize = 16 };
            }

            // Intercept Enter/Escape BEFORE TextField sees them — otherwise TextField
            // swallows the keystroke and our handlers never fire.
            bool submit = false, cancel = false;
            if (ev != null && ev.type == EventType.KeyDown)
            {
                if (ev.keyCode == KeyCode.Return || ev.keyCode == KeyCode.KeypadEnter)
                {
                    submit = true; ev.Use();
                }
                else if (ev.keyCode == KeyCode.Escape)
                {
                    cancel = true; ev.Use();
                }
            }

            // Position: above the F5 menu's bottom bar (Discord/GitHub/Refresh buttons
            // are around y=Screen.height-30). Doubled size per request.
            float w = 1000, h = 56;
            float x = 20, y = Screen.height - 130;

            GUI.DrawTexture(new Rect(x - 6, y - 24, w + 12, h + 30),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.82f), 0, 0);
            GUI.Label(new Rect(x, y - 22, w, 20),
                "Chat  —  Enter to send, Esc to cancel");

            GUI.SetNextControlName("CRChat");
            chatInputText = GUI.TextField(new Rect(x, y, w, h), chatInputText ?? "", 480, chatStyle);
            GUI.FocusControl("CRChat");

            if (submit)
            {
                string text = (chatInputText ?? "").Trim();
                if (!string.IsNullOrEmpty(text))
                {
                    // Local mute commands. Stays on this client only — never sent to the server.
                    // /mute <name>     hides that display name's messages from THIS client's chat log
                    // /unmute <name>   removes the mute
                    // /muted           prints the current mute list as a system line
                    if (text.StartsWith("/mute ", StringComparison.OrdinalIgnoreCase) ||
                        text.StartsWith("/unmute ", StringComparison.OrdinalIgnoreCase) ||
                        text.Equals("/muted", StringComparison.OrdinalIgnoreCase))
                    {
                        NativeUI.HandleMuteCommand(text);
                    }
                    else
                    {
                        ChatClient.Send(GameStateWatcher.LocalSteamId,
                                        GameStateWatcher.LocalDisplayName,
                                        text);
                        Plugin.Log.LogInfo($"[CHAT] -> sent: {text}");
                    }
                }
                chatInputText = "";
                chatInputOpen = false;
            }
            else if (cancel)
            {
                chatInputText = "";
                chatInputOpen = false;
            }
        }

        // ── Consent modal ────────────────────────────────────────
        // Blocking IMGUI overlay that appears at first launch (or any launch where
        // DataConsent is "" / unset). Until the user makes a choice, every
        // ApiClient call short-circuits at the helper level, so nothing leaves
        // the box. Decline → all reporting stays disabled. Allow → normal mode.

        private static GUIStyle consentTitleStyle;
        private static GUIStyle consentBodyStyle;

        // Full-screen uGUI raycast blocker that exists only while the consent modal is open.
        // IMGUI Event.Use() doesn't stop uGUI/main-menu clicks behind the modal — this Image
        // does (it sits on a high-sortingOrder Canvas with raycastTarget=true).
        private static GameObject consentBlockerGO;

        private static void EnsureConsentBlocker()
        {
            if (consentBlockerGO != null) return;
            try
            {
                consentBlockerGO = new GameObject("CR_ConsentBlocker");
                consentBlockerGO.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(consentBlockerGO);
                if (UIFactory.tCanvas != null)
                {
                    var cv = consentBlockerGO.AddComponent(UIFactory.tCanvas);
                    var bf = BindingFlags.Public | BindingFlags.Instance;
                    var rmProp = UIFactory.tCanvas.GetProperty("renderMode", bf);
                    rmProp?.SetValue(cv, Enum.ToObject(rmProp.PropertyType, 0));
                    UIFactory.tCanvas.GetProperty("sortingOrder", bf)?.SetValue(cv, 29998);  // just under F5's 30000
                }
                if (UIFactory.tGR != null) consentBlockerGO.AddComponent(UIFactory.tGR);
                var rt = consentBlockerGO.AddComponent<RectTransform>();
                rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one;
                rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;
                if (UIFactory.tImage != null)
                {
                    var img = consentBlockerGO.AddComponent(UIFactory.tImage);
                    var bf = BindingFlags.Public | BindingFlags.Instance;
                    UIFactory.tImage.GetProperty("color", bf)?.SetValue(img, new Color(0f, 0f, 0f, 0.001f));
                    UIFactory.tImage.GetProperty("raycastTarget", bf)?.SetValue(img, true);
                }
                Plugin.Log.LogInfo("[CONSENT] Blocker canvas created");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CONSENT] blocker create failed: {ex.Message}"); }
        }

        private static void DestroyConsentBlocker()
        {
            if (consentBlockerGO == null) return;
            try { UnityEngine.Object.Destroy(consentBlockerGO); } catch { }
            consentBlockerGO = null;
        }

        private static void DrawConsentModal()
        {
            if (Plugin.DataConsentAsked) { DestroyConsentBlocker(); return; }
            EnsureConsentBlocker();

            var bg = Texture2D.whiteTexture;

            // Dim everything behind
            GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), bg,
                ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.78f), 0, 0);

            float w = 680, h = 420;
            float x = (Screen.width - w) / 2f;
            float y = (Screen.height - h) / 2f;

            GUI.DrawTexture(new Rect(x, y, w, h), bg, ScaleMode.StretchToFill, true, 0,
                new Color(0.10f, 0.11f, 0.16f, 0.97f), 0, 0);

            if (consentTitleStyle == null)
                consentTitleStyle = new GUIStyle(GUI.skin.label) { fontSize = 22, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
            if (consentBodyStyle == null)
                consentBodyStyle = new GUIStyle(GUI.skin.label) { fontSize = 14, wordWrap = true, alignment = TextAnchor.UpperLeft };

            GUI.Label(new Rect(x, y + 14, w, 30), "Competitive ROUNDS — Data Consent", consentTitleStyle);

            string body =
                "This mod sends data to a private server run by the mod author to power the leaderboard " +
                "and ranked matchmaking.\n\n" +
                "What gets recorded if you allow:\n" +
                "  • Your Steam ID and in-game display name\n" +
                "  • Your Discord ID and username, ONLY if you link your Discord via the in-game link code\n" +
                "  • Each match you play: rounds won, points, duration, cards picked, cards offered, opponent\n" +
                "  • Your Glicko-2 rating history\n\n" +
                "What you can do later:\n" +
                "  • Revoke consent anytime (F5 → Settings → Revoke). Reporting stops.\n" +
                "  • Delete your data (F5 → Settings → Delete my data). Steam ID, display name, and Discord link " +
                "are scrubbed. Matches stay so other players' ratings and histories aren't disturbed. " +
                "Deletion is IRREVERSIBLE — you cannot re-register this Steam ID later.\n\n" +
                "Choose Allow to use the leaderboard. Choose Decline to run the mod fully offline.";
            GUI.Label(new Rect(x + 24, y + 50, w - 48, h - 120), body, consentBodyStyle);

            if (GUI.Button(new Rect(x + 50, y + h - 56, 260, 38), "Allow data reporting"))
            {
                Plugin.DataConsent.Value = "granted";
                Plugin.Log.LogInfo("[CONSENT] User granted data reporting");
                ApiClient.OnConsentChanged();
            }
            if (GUI.Button(new Rect(x + w - 310, y + h - 56, 260, 38), "Decline (offline mode)"))
            {
                Plugin.DataConsent.Value = "denied";
                Plugin.Log.LogInfo("[CONSENT] User declined data reporting");
                ApiClient.OnConsentChanged();
            }

            // Eat mouse / keyboard so the click doesn't pass through to the menu underneath
            if (Event.current != null)
            {
                var t = Event.current.type;
                if (t == EventType.MouseDown || t == EventType.MouseUp || t == EventType.KeyDown || t == EventType.KeyUp)
                    Event.current.Use();
            }
        }

        private static void DrawFPS()
        {
            // FPS counter — independently toggleable.
            bool showFps = Plugin.ShowFps == null || Plugin.ShowFps.Value;
            bool showRegion = Plugin.ShowRegionPing == null || Plugin.ShowRegionPing.Value;
            if (!showFps && !showRegion) return;

            fpsCnt++;
            fpsTimer += Time.deltaTime;
            if (fpsTimer >= 0.5f) { fpsVal = fpsCnt / fpsTimer; fpsCnt = 0; fpsTimer = 0f; }
            if (fpsStyle == null) { fpsStyle = new GUIStyle(GUI.skin.label); fpsStyle.fontSize = 11; fpsStyle.normal.textColor = new Color(0.5f, 0.5f, 0.5f, 0.7f); }

            string label = showFps ? $"{fpsVal:F0} FPS" : "";
            float width = 60;

            if (showRegion)
            {
                try
                {
                    if (PhotonNetwork.IsConnected && PhotonNetwork.InRoom)
                    {
                        int ping = PhotonNetwork.GetPing();
                        string region = PhotonNetwork.CloudRegion ?? "";
                        if (!string.IsNullOrEmpty(region))
                        {
                            int slash = region.IndexOf('/');
                            if (slash > 0) region = region.Substring(0, slash);
                            region = region.ToUpper();
                        }
                        string pingPart = $"{ping}ms  {region}";
                        label = showFps ? $"{label}  |  {pingPart}" : pingPart;
                        width = 200;
                    }
                }
                catch { }
            }

            if (!string.IsNullOrEmpty(label))
                GUI.Label(new Rect(6, 4, width, 18), label, fpsStyle);
        }

        private static void DrawNotification()
        {
            if (notifTimer <= 0f && notifQueue.Count > 0)
            {
                var n = notifQueue[0]; notifQueue.RemoveAt(0);
                notifText = n.text; notifColor = n.color; notifTimer = n.dur;
            }
            if (notifTimer <= 0f) return;
            notifTimer -= Time.deltaTime;
            float alpha = Mathf.Clamp01(notifTimer);

            if (notifStyle == null)
            {
                notifStyle = new GUIStyle(GUI.skin.label);
                notifStyle.fontSize = 16;
                notifStyle.fontStyle = FontStyle.Bold;
                notifStyle.alignment = TextAnchor.MiddleCenter;
            }

            var color = new Color(notifColor.r, notifColor.g, notifColor.b, alpha);
            var origColor = GUI.contentColor;
            GUI.contentColor = color;

            float width = 500;
            float x = (Screen.width - width) / 2f;
            float y = Screen.height - 80;

            var bgTex = Texture2D.whiteTexture;
            GUI.DrawTexture(new Rect(x, y - 2, width, 28), bgTex, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, alpha * 0.5f), 0, 0);
            GUI.Label(new Rect(x, y, width, 24), notifText, notifStyle);
            GUI.contentColor = origColor;
        }

        private static void DrawMatchStatus()
        {
            if (!MatchTracker.IsInMatch) return;
            bool isRanked = GameStateWatcher.MatchIsRanked;
            if (statusStyle == null)
            {
                statusStyle = new GUIStyle(GUI.skin.label);
                statusStyle.fontSize = 11;
                statusStyle.fontStyle = FontStyle.Bold;
                statusStyle.alignment = TextAnchor.MiddleCenter;
            }
            if (scoreStyle == null)
            {
                scoreStyle = new GUIStyle(GUI.skin.label);
                scoreStyle.fontSize = 14;
                scoreStyle.fontStyle = FontStyle.Bold;
                scoreStyle.alignment = TextAnchor.MiddleCenter;
            }
            var oc = GUI.contentColor;

            // Top banner: "RANKED - Recording" only on ranked. Casual gets no banner —
            // the score line below floats up so it sits where the banner would have.
            float scoreY;
            if (isRanked)
            {
                GUI.contentColor = Color.green;
                GUI.Label(new Rect((Screen.width - 140) / 2f, 8, 140, 18), "RANKED - Recording", statusStyle);
                scoreY = 28;
            }
            else
            {
                scoreY = 8;
            }

            // Two HUD lines under the RANKED banner — both pulled from
            // local counters in GameStateWatcher rather than the
            // /series/active cache, because that cache only refreshes
            // when the F5 leaderboard tab is open and is therefore stale
            // mid-match. Casual matches still get the per-opponent H2H
            // line (the only useful stat for a casual queue).
            float nextLineY = scoreY;
            if (isRanked)
            {
                int sgw = GameStateWatcher.CurrentSeriesGamesWon;
                int sgl = GameStateWatcher.CurrentSeriesGamesLost;
                int rgw = GameStateWatcher.SessionRankedWins;
                int rgl = GameStateWatcher.SessionRankedLosses;
                int rsw = GameStateWatcher.SessionRankedSeriesWins;
                int rsl = GameStateWatcher.SessionRankedSeriesLosses;

                GUI.contentColor = new Color(1f, 0.85f, 0.3f);
                GUI.Label(new Rect((Screen.width - 260) / 2f, scoreY, 260, 22),
                    $"Series: {sgw} - {sgl}", scoreStyle);
                GUI.contentColor = new Color(0.75f, 0.85f, 1f);
                GUI.Label(new Rect((Screen.width - 320) / 2f, scoreY + 18, 320, 20),
                    $"Session: {rgw}-{rgl} games  ({rsw}-{rsl} series)", scoreStyle);
                nextLineY = scoreY + 36;
            }

            // Per-opponent session H2H — fires on both ranked AND casual so a
            // regular game shows "vs Opponent: 2-1 this session" right under
            // the score line. Skip 2v2 (cr_ff) rooms: opponentSteamId latches
            // on one of the two opposing players which makes the H2H number
            // misleading.
            try
            {
                string oppSid = GameStateWatcher.OpponentSteamId;
                string oppName = GameStateWatcher.OpponentDisplayName;
                bool isCrFf = false;
                try
                {
                    var rp = Photon.Pun.PhotonNetwork.CurrentRoom?.CustomProperties;
                    isCrFf = rp != null && rp.ContainsKey("cr_ff");
                }
                catch { }
                if (!isCrFf
                    && !string.IsNullOrEmpty(oppName)
                    && oppName != "Opponent"
                    && !(oppSid != null && oppSid.StartsWith("photon_")))
                {
                    var dict = GameStateWatcher.SessionWLByOpponent;
                    int[] counts;
                    // sessionWLByOpponent is keyed by DISPLAY NAME, not steam_id
                    // (see GameStateWatcher.OnGameOver — uses opponentDisplayName).
                    if (dict != null && dict.TryGetValue(oppName, out counts) && counts != null && counts.Length >= 4)
                    {
                        int w = counts[0] + counts[2];   // ranked W + casual W
                        int l = counts[1] + counts[3];   // ranked L + casual L
                        if (w + l > 0)
                        {
                            Color tint = w > l ? new Color(0.6f, 1f, 0.6f)
                                       : w < l ? new Color(1f, 0.6f, 0.6f)
                                              : new Color(0.85f, 0.85f, 0.85f);
                            GUI.contentColor = tint;
                            string shortName = oppName.Length > 18 ? oppName.Substring(0, 18) : oppName;
                            GUI.Label(new Rect((Screen.width - 360) / 2f, nextLineY, 360, 20),
                                      $"vs {shortName}: {w}-{l} this session", scoreStyle);
                        }
                        else
                        {
                            GUI.contentColor = new Color(0.7f, 0.7f, 0.7f);
                            string shortName = oppName.Length > 18 ? oppName.Substring(0, 18) : oppName;
                            GUI.Label(new Rect((Screen.width - 360) / 2f, nextLineY, 360, 20),
                                      $"vs {shortName}: first game this session", scoreStyle);
                        }
                    }
                    else
                    {
                        GUI.contentColor = new Color(0.7f, 0.7f, 0.7f);
                        string shortName = oppName.Length > 18 ? oppName.Substring(0, 18) : oppName;
                        GUI.Label(new Rect((Screen.width - 360) / 2f, nextLineY, 360, 20),
                                  $"vs {shortName}: first game this session", scoreStyle);
                    }
                }
            }
            catch { }
            GUI.contentColor = oc;
        }

        private static GUIStyle scoreStyle;
    }
}
