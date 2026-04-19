using System;
using System.Collections.Generic;
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
            // Consent modal drawn LAST so it paints on top of everything.
            DrawConsentModal();
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
            if (!MatchTracker.IsInMatch || !GameStateWatcher.MatchIsRanked) return;
            if (statusStyle == null)
            {
                statusStyle = new GUIStyle(GUI.skin.label);
                statusStyle.fontSize = 11;
                statusStyle.fontStyle = FontStyle.Bold;
                statusStyle.alignment = TextAnchor.MiddleCenter;
            }
            var oc = GUI.contentColor;
            GUI.contentColor = Color.green;
            GUI.Label(new Rect((Screen.width - 140) / 2f, 8, 140, 18), "RANKED - Recording", statusStyle);
            GUI.contentColor = oc;
        }
    }
}
