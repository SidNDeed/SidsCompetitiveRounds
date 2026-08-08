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
        private static string fpsLabel = "";
        private static float fpsLabelWidth = 60f;
        private static bool fpsLabelShowFps, fpsLabelShowRegion;

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

        public static void ShowNotification(string text, Color color, float duration = 5f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            // L10n chokepoint for the IMGUI toast surface (Codex client
            // review find 7): these render via GUI.Label, never through
            // UIFactory, so without this the exact catalogue entries for
            // toast strings were unreachable. Tr is identity for unknown /
            // interpolated strings.
            try { text = I18n.Tr(text); } catch { }
            notifText = text;
            notifColor = color;
            notifTimer = duration;
        }

        public static void QueueNotification(string text, Color color, float duration = 5f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            try { text = I18n.Tr(text); } catch { }
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
        public static void Tick()
        {
            // Second, independent release path for the chat input lock: this call
            // site is try/caught in Plugin.Update, so it survives an OnGUI that
            // throws every frame (bug #128, FINDING 6).
            TickChatLockWatchdog();
            NativeUI.Tick();
        }

        /// <summary>Called from OnGUI. FPS + notifications + match status. The server-down
        /// banner moved to the F5 menu (NativeUI.RefreshServerBanner) — it was constantly
        /// firing in-game during quiet periods + felt obtrusive.</summary>
        public static void DrawUI()
        {
            // FIRST, before anything that can throw: releases the chat input lock
            // if the box stopped rendering (bug #128 — see TickChatLockWatchdog).
            TickChatLockWatchdog();
            // Spectator blackout/HUD draws EARLY (#255): it must not be
            // starveable by a later overlay throwing, and everything after it
            // may legitimately paint on top (notifications, Tab stats, chat).
            SpectatorHud.Draw();
            DrawFPS();
            TabStatsOverlay.Draw();   // hold-Tab scoreboard (bug batch item 3)
            PlayerEffectCosmetic.DrawPreview();  // shop effect preview (IMGUI sim, always above the menu)
            DrawSpawnSpotlight();
            DrawNotification();
            DrawSpectatorRoster();   // fighter-side "Spectators (N)" (design §6.8)
            DrawFfaScoreStrip();
            DrawMatchStatus();
            DrawInGameChat();
            DrawChatInput();
            DrawQuickChat();   // §2.6 key-based quick-chat (Y in an online room)
            DrawAdminPrompt();
            DrawConfirm();
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
            DrawScoreHoverGraph();
            DrawFpsHoverGraph();
            DrawCompareSearch();
            DrawPickerSearch();   // Aug 6 item 2 — searchable metric/card dropdown
            DrawLeaderboardSearch();
            DrawMapColorToast();
            DrawCustomBetPrompt();
            DrawLfpPrompt();
            DrawArtistInput();
            DrawArtistPicker();
            DrawPlayerSearch();
            DrawCosmeticTestPreview();
            DrawCosmeticReview();
            DrawCosmeticReleaseQueue();
            DrawFlagEvidence();
            DrawLeaverBanner();
            DrawTournamentBanner();
            // Block clicks to the F5 page behind any open IMGUI modal (lopi #14:
            // clicks on the bug-report form were also hitting F5 buttons underneath).
            // TWO independent input paths must be blocked: the uGUI EventSystem
            // (SetClickBlocker's raycast-absorbing Image) AND the mod's own
            // ClickHandler poller, which hit-tests Input.GetMouseButtonDown itself
            // and ignores the uGUI blocker (bug #75 — artist price/stock modal).
            // Consent modal has its OWN dedicated blocker (EnsureConsentBlocker) so
            // it isn't in this set; adminPromptOpen was previously missing from the
            // uGUI list too — added here so both paths cover it.
            bool anyModal = bugModalOpen || logViewerOpen || bugAdminOpen || NativeUI.CustomBetPromptOpen
                           || artistPromptOpen || artistPickerOpen || playerSearchOpen || cosTestOpen || cosReviewOpen
                           || cosReleaseOpen
                           || flagEvidenceOpen
                          || adminPromptOpen || NativeUI.LfpPromptOpen
                          // Wave-2 find 10: the quick-chat popup can overlap
                          // live F5 buttons — a phrase click must not ALSO
                          // fire the shop/queue control underneath, on
                          // EITHER input path.
                          || quickChatOpen
                          // Spectator leave-confirm: an IMGUI modal with no
                          // uGUI backdrop of its own, so it needs BOTH gates
                          // (#200) — a [Leave] click must not fall through to
                          // an F5 button underneath.
                          || SpectatorHud.MenuOpen
                          // Aug 7: the generic yes/no confirm was missing from
                          // this list since it was written — also backdrop-less,
                          // so while it was up a click outside its box still
                          // reached the very Unban/Reverse/Void rows it exists
                          // to guard, on both input paths. It can't strand
                          // either gate on: DrawConfirm runs earlier in this
                          // same DrawUI pass and clears confirmOpen on Escape,
                          // on either button, and on the menu closing.
                          || confirmOpen;
            NativeUI.SetClickBlocker(anyModal);
            // InfoPopupOpen: the uGUI info popup's backdrop absorbs EventSystem
            // clicks itself, but raw-polling ClickHandlers behind it need this
            // flag (learning #141); its own backdrop sets bypassModalBlock.
            // Aug 6 item 2: PickerOpen joins ModalBlockInput ONLY — deliberately
            // not anyModal/SetClickBlocker. The picker raises its own uGUI
            // backdrop, so it needs the raw-poll half of the gate (#141/#200)
            // and nothing else; adding it to anyModal would double-blocker it.
            // Mirrors InfoPopupOpen, which is in this list for the same reason.
            ClickHandler.ModalBlockInput = anyModal || NativeUI.InfoPopupOpen || NativeUI.PickerOpen || NativeUI.LangPromptOpen || !Plugin.DataConsentAsked;
            // Consent modal drawn LAST so it paints on top of everything.
            DrawConsentModal();
        }

        // -- Spectator roster (fighter-side, design §6.8) -------------------
        // Compact top-right line while any spectator is in the room. Names
        // come from the cr_spec_roster room property — validated identities
        // published by the master, never NickName (#162: 3s string cache,
        // Repaint draws cached only).
        private static string specRosterLine = "";
        private static float specRosterCachedAt = -999f;

        private static void DrawSpectatorRoster()
        {
            try
            {
                if (RoomActors.LocalIsSpectator) return;   // spectator has its own HUD
                if (Time.unscaledTime - specRosterCachedAt > 3f)
                {
                    specRosterCachedAt = Time.unscaledTime;
                    specRosterLine = "";
                    if (Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode)
                    {
                        int n = RoomActors.SpectatorCount();
                        if (n > 0)
                        {
                            string names = "";
                            try
                            {
                                var rp = Photon.Pun.PhotonNetwork.CurrentRoom?.CustomProperties;
                                if (rp != null && rp.ContainsKey("cr_spec_roster"))
                                    names = (rp["cr_spec_roster"] as string ?? "").Replace("|", ", ");
                            }
                            catch { }
                            // Neutralise rich-text (IMGUI label, same rule as quick-chat).
                            names = names.Replace("<", "(").Replace(">", ")");
                            if (names.Length > 60) names = names.Substring(0, 60);
                            specRosterLine = names.Length > 0
                                ? I18n.TrF("Spectators ({0}): {1}", n, names)
                                : I18n.TrF("Spectators ({0})", n);
                        }
                    }
                }
                if (specRosterLine.Length == 0) return;
                var style = GUI.skin.label;
                var prev = GUI.color;
                GUI.color = new Color(1f, 1f, 1f, 0.75f);
                // BOTTOM-right (Sid, playtest #169c): the top-right corner
                // already carries the card bars — the roster was crowding it.
                GUI.Label(new Rect(Screen.width - 420, Screen.height - 28, 412, 22), specRosterLine,
                          new GUIStyle(style) { alignment = TextAnchor.MiddleRight, fontStyle = FontStyle.Bold, clipping = TextClipping.Overflow });
                GUI.color = prev;
            }
            catch { }
        }

        // -- FFA score HUD --------------------------------------------------
        // Fixed slot rows mirror vanilla's small dot counter without relying
        // on its two-team object. Slow state is cached; Repaint only draws
        // cached strings, colors, positions and textures (learning #162).
        private const int FfaHudMaxRows = 10;
        private const int FfaHudNameChars = 12;
        private struct FfaHudRow
        {
            public bool active;
            public bool dead;
            public bool halfDot;
            public string name;
            public Color nameColor;
            public Color dotColor;
            public int fullDots;
            public Rect nameRect;
            public float dotX;
            public float dotY;
        }

        private static readonly FfaHudRow[] ffaHudRows = new FfaHudRow[FfaHudMaxRows];
        private static readonly char[] ffaHudNameBuffer = new char[FfaHudNameChars];
        private static readonly string[] ffaHudFallbackNames =
            { "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10" };
        private static int ffaHudRowExtent;
        private static int ffaHudLayoutExtent = -1;
        private static int ffaHudScreenWidth = -1;
        private static int ffaHudScreenHeight = -1;
        private static float ffaHudRowsCachedAt = -999f;
        private static float ffaVanillaCounterCheckedAt = -999f;
        private static float ffaHudScale = 1f;
        private static float ffaHudDotSize;
        private static float ffaHudDotPitch;
        private static Rect ffaHudBackingRect;
        private static Rect ffaPickBannerRect;
        private static GUIStyle ffaHudNameStyle;
        private static GUIStyle ffaPickBannerStyle;
        private static Texture2D ffaFullDotTexture;
        private static Texture2D ffaHalfDotTexture;
        private static string ffaPickBannerText = "";
        private static float ffaPickBannerCachedAt = -999f;
        private static int ffaPickBannerSeconds = -1;
        private static bool ffaPickBannerLocal;
        // Aug 8 (Sid): the banner rect is content-fitted at draw time (#237 —
        // never size an IMGUI text rect from a guess); measure cache keyed by
        // (text, fontSize), and the REAL bottom edge for the banners stacked
        // beneath.
        private static Vector2 ffaPickBannerMeasured;
        private static string ffaPickBannerMeasuredText;
        private static int ffaPickBannerMeasuredFont = -1;
        private static float ffaPickBannerYMax;

        // Bug #132: 5s "FFA starting" countdown between the host's Start and
        // the room join. Realtime clock — the countdown must tick at menu
        // timescale AND inside a casual game being left.
        private static float ffaStartCountdownUntil = -999f;

        public static void ShowFfaStartCountdown(float seconds)
        {
            ffaStartCountdownUntil = Time.realtimeSinceStartup + seconds;
        }

        public static bool FfaStartCountdownActive =>
            Time.realtimeSinceStartup < ffaStartCountdownUntil;

        /// <summary>Codex batch find 15: every path that abandons the pending
        /// join must also retire the banner, or "FFA STARTING..." lies on
        /// screen until the original deadline.</summary>
        public static void CancelFfaStartCountdown()
        {
            ffaStartCountdownUntil = -999f;
        }

        private static void DrawFfaScoreStrip()
        {
            if (Event.current == null) return;
            try
            {
                bool inMatch = FfaMode.InFfaMatch;
                bool pickActive = FfaMode.PickPhaseActive;
                bool startCountdown = Time.realtimeSinceStartup < ffaStartCountdownUntil;
                if (!inMatch && !pickActive && !startCountdown)
                {
                    ffaHudRowsCachedAt = -999f;
                    ffaHudRowExtent = 0;
                    ffaPickBannerText = "";
                    ffaPickBannerSeconds = -1;
                    ffaMpBannerText = "";      // item 10: never survive the match
                    ffaMpSignature = null;
                    return;
                }

                float now = Time.realtimeSinceStartup;
                // Refresh on Layout so the following Repaint performs no
                // string or row-cache allocations.
                if (Event.current.type == EventType.Layout)
                {
                    if (inMatch)
                    {
                        SuppressFfaVanillaCounter(now);
                        if (now - ffaHudRowsCachedAt >= 0.5f)
                        {
                            ffaHudRowsCachedAt = now;
                            RefreshFfaHudRows();
                        }
                    }
                    else ffaHudRowExtent = 0;
                    RefreshFfaPickBanner(now, pickActive);
                    RefreshFfaMatchPointBanner(now, inMatch);
                    return;
                }
                if (Event.current.type != EventType.Repaint) return;

                EnsureFfaHudResources();
                RefreshFfaHudLayout();
                if (inMatch) DrawFfaScoreRows();
                DrawFfaPickBanner(now);
                DrawFfaSettingsBanner(now);
                DrawFfaMatchPointBanner(now);
            }
            catch { }
        }

        private static void EnsureFfaHudResources()
        {
            if (ffaHudNameStyle == null)
            {
                ffaHudNameStyle = new GUIStyle(GUI.skin.label)
                {
                    alignment = TextAnchor.MiddleLeft,
                    fontStyle = FontStyle.Bold,
                    richText = false,
                    clipping = TextClipping.Clip,
                };
                ffaHudNameStyle.normal.textColor = Color.white;
            }
            if (ffaPickBannerStyle == null)
            {
                ffaPickBannerStyle = new GUIStyle(GUI.skin.label)
                {
                    alignment = TextAnchor.MiddleCenter,
                    fontStyle = FontStyle.Bold,
                    richText = false,
                    // #143 — IMGUI metrics run taller than the point size, and
                    // the skin's wordWrap can add a second line; Clip was
                    // shaving GET READY top and bottom (Sid, Aug 8 screenshot).
                    // The rect is content-fitted at draw time; Overflow is the
                    // backstop.
                    clipping = TextClipping.Overflow,
                };
                ffaPickBannerStyle.normal.textColor = Color.white;
            }
            if (ffaFullDotTexture == null)
                ffaFullDotTexture = BuildFfaDotTexture(false, "CR_FFA_FullDot");
            if (ffaHalfDotTexture == null)
                ffaHalfDotTexture = BuildFfaDotTexture(true, "CR_FFA_HalfDot");
        }

        private static Texture2D BuildFfaDotTexture(bool half, string textureName)
        {
            const int size = 32;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false);
            texture.name = textureName;
            texture.hideFlags = HideFlags.HideAndDontSave;
            texture.filterMode = FilterMode.Bilinear;
            texture.wrapMode = TextureWrapMode.Clamp;
            var pixels = new Color32[size * size];
            float center = size * 0.5f;
            float radius = center - 1f;
            for (int y = 0; y < size; y++)
            {
                float py = y + 0.5f - center;
                for (int x = 0; x < size; x++)
                {
                    float px = x + 0.5f - center;
                    float alpha = Mathf.Clamp01(radius + 0.5f - Mathf.Sqrt(px * px + py * py));
                    if (half && px > 0f) alpha = 0f; // left half filled
                    pixels[y * size + x] = new Color32(255, 255, 255,
                        (byte)Mathf.RoundToInt(alpha * 255f));
                }
            }
            texture.SetPixels32(pixels);
            texture.Apply(false, true);
            return texture;
        }

        private static void RefreshFfaHudRows()
        {
            for (int i = 0; i < FfaHudMaxRows; i++)
            {
                var empty = ffaHudRows[i];
                empty.active = false;
                empty.name = null;
                ffaHudRows[i] = empty;
            }
            ffaHudRowExtent = 0;

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return;
            foreach (var p in pm.players)
            {
                if (p == null || p.gameObject == null || p.data == null) continue;
                int slot = p.TeamID;
                if (slot < 0 || slot >= FfaHudMaxRows) continue;

                string rawName = null;
                try { rawName = p.data.view?.Owner?.NickName; } catch { }
                Color rawColor = Color.white;
                try
                {
                    // Aug 6 item 7: in FFA every player IS their own team, so the
                    // strip's identity colour is simply that player's equipped body
                    // colour when they have one. Falls through to the vanilla slot
                    // skin (which repeats every 4 slots — see the FFA clamp in
                    // PlayerSkinBank_GetPlayerSkinColors_2v2_Patch) otherwise.
                    Color equipped;
                    if (TeamColorIdentity.TryGetColor(slot, out equipped))
                    {
                        rawColor = equipped;
                    }
                    else
                    {
                        var skin = PlayerSkinBank.GetPlayerSkinColors(slot);
                        if (skin != null) rawColor = skin.color;
                    }
                }
                catch { }

                var row = ffaHudRows[slot];
                row.active = true;
                row.dead = p.data.dead;
                row.name = StripFfaHudName(rawName, slot);
                row.nameColor = FfaHudReadableNameColor(rawColor);
                row.dotColor = rawColor;
                row.fullDots = Mathf.Clamp(FfaMode.RoundsFor(slot), 0, FfaMode.RoundsToWin);
                row.halfDot = row.fullDots < FfaMode.RoundsToWin
                              && FfaMode.PointsFor(slot) >= 1;
                ffaHudRows[slot] = row;
                if (slot + 1 > ffaHudRowExtent) ffaHudRowExtent = slot + 1;
            }
        }

        private static string StripFfaHudName(string input, int slot)
        {
            if (string.IsNullOrEmpty(input)) return ffaHudFallbackNames[slot];
            int count = 0;
            bool inTag = false;
            for (int i = 0; i < input.Length && count < FfaHudNameChars; i++)
            {
                char c = input[i];
                if (c == '<') { inTag = true; continue; }
                if (inTag)
                {
                    if (c == '>') inTag = false;
                    continue;
                }
                ffaHudNameBuffer[count++] = c < ' ' ? ' ' : c;
            }
            while (count > 0 && ffaHudNameBuffer[count - 1] == ' ') count--;
            int start = 0;
            while (start < count && ffaHudNameBuffer[start] == ' ') start++;
            return start >= count
                ? ffaHudFallbackNames[slot]
                : new string(ffaHudNameBuffer, start, count - start);
        }

        private static Color FfaHudReadableNameColor(Color raw)
        {
            float max = Mathf.Max(raw.r, Mathf.Max(raw.g, raw.b));
            float min = Mathf.Min(raw.r, Mathf.Min(raw.g, raw.b));
            if (max <= 0.2f || min >= 0.82f) return Color.white;
            return new Color(raw.r, raw.g, raw.b, 1f);
        }

        private static int ffaHudLayoutTarget = -1;
        private static void RefreshFfaHudLayout()
        {
            int width = Screen.width;
            int height = Screen.height;
            // Score target joined the cache key in v1.36: RoundsToWin is
            // per-lobby config now, and the dot-strip width derives from it —
            // a config change between sittings must rebuild the layout (§4b).
            if (width == ffaHudScreenWidth && height == ffaHudScreenHeight
                && ffaHudLayoutExtent == ffaHudRowExtent
                && ffaHudLayoutTarget == FfaMode.RoundsToWin) return;

            ffaHudScreenWidth = width;
            ffaHudScreenHeight = height;
            ffaHudLayoutExtent = ffaHudRowExtent;
            ffaHudLayoutTarget = FfaMode.RoundsToWin;
            ffaHudScale = height / 1080f;
            float paddingX = 6f * ffaHudScale;
            float paddingY = 4f * ffaHudScale;
            float nameWidth = 100f * ffaHudScale;
            float nameToDots = 8f * ffaHudScale;
            float rowPitch = 18f * ffaHudScale;
            ffaHudDotSize = 12f * ffaHudScale;
            ffaHudDotPitch = 16f * ffaHudScale;
            float x = 16f * ffaHudScale;
            float y = 46f * ffaHudScale;
            float dotsWidth = FfaMode.RoundsToWin * ffaHudDotSize
                              + (FfaMode.RoundsToWin - 1) * 4f * ffaHudScale;
            ffaHudBackingRect = new Rect(x, y,
                paddingX + nameWidth + nameToDots + dotsWidth + paddingX,
                paddingY * 2f + ffaHudRowExtent * rowPitch);

            for (int slot = 0; slot < FfaHudMaxRows; slot++)
            {
                var row = ffaHudRows[slot];
                float rowY = y + paddingY + slot * rowPitch;
                row.nameRect = new Rect(x + paddingX, rowY, nameWidth, rowPitch);
                row.dotX = x + paddingX + nameWidth + nameToDots;
                row.dotY = rowY + (rowPitch - ffaHudDotSize) * 0.5f;
                ffaHudRows[slot] = row;
            }

            float bannerW = 260f * ffaHudScale;
            ffaPickBannerRect = new Rect((width - bannerW) * 0.5f, 6f * ffaHudScale,
                bannerW, 28f * ffaHudScale);
            // Default until a banner draws taller this frame — consumers below
            // the banner stack off the REAL drawn edge, not the layout slot.
            ffaPickBannerYMax = ffaPickBannerRect.yMax;
            ffaHudNameStyle.fontSize = Mathf.Max(1, Mathf.RoundToInt(12f * ffaHudScale));
            ffaPickBannerStyle.fontSize = Mathf.Max(1, Mathf.RoundToInt(14f * ffaHudScale));
        }

        private static void DrawFfaScoreRows()
        {
            if (ffaHudRowExtent <= 0) return;
            Color previous = GUI.color;
            // Bug #138 (Stan via Sid): no backing box — the strip sits directly
            // on the scene like vanilla's counter. Names keep their contrast
            // via a 1px drop shadow instead.

            for (int slot = 0; slot < ffaHudRowExtent; slot++)
            {
                var row = ffaHudRows[slot];
                if (!row.active) continue;
                float nameAlpha = row.dead ? 0.5f : 1f;
                GUI.color = new Color(0f, 0f, 0f, 0.75f * nameAlpha);
                GUI.Label(new Rect(row.nameRect.x + ffaHudScale, row.nameRect.y + ffaHudScale,
                    row.nameRect.width, row.nameRect.height), row.name, ffaHudNameStyle);
                GUI.color = new Color(row.nameColor.r, row.nameColor.g, row.nameColor.b, nameAlpha);
                GUI.Label(row.nameRect, row.name, ffaHudNameStyle);

                // Bug #138: every unscored point renders as a teeny grey dot
                // (vanilla-style) so the win target is legible at a glance.
                int placeholderFrom = row.fullDots + (row.halfDot ? 1 : 0);
                GUI.color = new Color(0.62f, 0.62f, 0.62f, 0.55f);
                float tinySize = ffaHudDotSize * 0.45f;
                float tinyInset = (ffaHudDotSize - tinySize) * 0.5f;
                for (int dot = placeholderFrom; dot < FfaMode.RoundsToWin; dot++)
                    GUI.DrawTexture(new Rect(row.dotX + dot * ffaHudDotPitch + tinyInset,
                        row.dotY + tinyInset, tinySize, tinySize), ffaFullDotTexture);

                GUI.color = row.dotColor;
                for (int dot = 0; dot < row.fullDots; dot++)
                    GUI.DrawTexture(new Rect(row.dotX + dot * ffaHudDotPitch, row.dotY,
                        ffaHudDotSize, ffaHudDotSize), ffaFullDotTexture);
                if (row.halfDot)
                    GUI.DrawTexture(new Rect(row.dotX + row.fullDots * ffaHudDotPitch, row.dotY,
                        ffaHudDotSize, ffaHudDotSize), ffaHalfDotTexture);
            }
            GUI.color = previous;
        }

        private static void RefreshFfaPickBanner(float now, bool active)
        {
            if (!active)
            {
                // Bug #132: the start countdown owns this slot between the
                // host's Start and the room join. LOCAL styling with the live
                // second — it is a call to act (your game is about to begin,
                // possibly pulling you out of a casual room).
                float cdLeft = ffaStartCountdownUntil - now;
                if (cdLeft > 0f)
                {
                    int cdSec = Mathf.CeilToInt(cdLeft);
                    if (cdSec != ffaPickBannerSeconds || !ffaPickBannerLocal
                        || string.IsNullOrEmpty(ffaPickBannerText))
                    {
                        ffaPickBannerLocal = true;
                        ffaPickBannerSeconds = cdSec;
                        ffaPickBannerText = I18n.TrF("FFA STARTING IN {0}...", cdSec);
                    }
                    return;
                }
                // Bug #119: outside the pick phase this banner slot carries the
                // spawn grace cue, so players can see WHY the trigger is dead
                // for the first second of a round rather than reading it as a
                // hitch. Non-local styling (dim grey) - it is information, not
                // a call to act.
                if (FfaMode.SpawnGraceActive)
                {
                    ffaPickBannerLocal = false;
                    ffaPickBannerSeconds = -1;
                    ffaPickBannerText = I18n.Tr("GET READY - fire and block unlock in a moment");
                    return;
                }
                ffaPickBannerText = "";
                ffaPickBannerSeconds = -1;
                return;
            }

            bool localOpen = FfaMode.LocalPickOpen;
            if (string.IsNullOrEmpty(ffaPickBannerText)
                || now - ffaPickBannerCachedAt >= 0.25f
                || localOpen != ffaPickBannerLocal)
            {
                ffaPickBannerCachedAt = now;
                ffaPickBannerLocal = localOpen;
                // Pickers see the auto-confirm clock (0 = your highlighted
                // card locks in); spectators of the phase see the REAL window
                // close, which runs ~5s later (Codex Jul-29 find 11).
                ffaPickBannerSeconds = Mathf.CeilToInt(
                    localOpen ? FfaMode.PickSecondsLeft : FfaMode.PickWindowSecondsLeft);
                ffaPickBannerText = localOpen
                    ? I18n.TrF("PICK YOUR CARD - {0}s", ffaPickBannerSeconds)
                    : I18n.TrF("Card picks close in {0}s", ffaPickBannerSeconds);
            }
        }

        // ── v1.36 settings banner (§7c/§8): the lobby's rules in force, shown
        // large during load-in at every game start. Fed by FfaMode.OnGameStart
        // AFTER the config latch, so it reads the same statics the engine
        // reads and cannot disagree with the rules actually applied. ──
        private static string ffaCfgBannerText = "";
        private static float ffaCfgBannerUntil;
        private static Vector2 ffaCfgBannerSize;
        private static GUIStyle ffaCfgBannerStyle;

        public static void ShowFfaSettingsBanner(string text, float seconds)
        {
            ffaCfgBannerText = text ?? "";
            ffaCfgBannerUntil = Time.realtimeSinceStartup + seconds;
            ffaCfgBannerSize = Vector2.zero;   // re-measure on next draw
        }

        private static void DrawFfaSettingsBanner(float now)
        {
            if (string.IsNullOrEmpty(ffaCfgBannerText) || now > ffaCfgBannerUntil) return;
            if (Event.current.type != EventType.Repaint) return;   // #162
            if (ffaCfgBannerStyle == null)
            {
                ffaCfgBannerStyle = new GUIStyle(GUI.skin.label)
                {
                    alignment = TextAnchor.MiddleCenter,
                    fontSize = Mathf.Max(14, Mathf.RoundToInt(19f * (Screen.height / 1080f))),
                    fontStyle = FontStyle.Bold,
                    clipping = TextClipping.Overflow,   // #143 — IMGUI metrics run tall
                };
            }
            if (ffaCfgBannerSize == Vector2.zero)
                ffaCfgBannerSize = ffaCfgBannerStyle.CalcSize(new GUIContent(ffaCfgBannerText));
            float w = ffaCfgBannerSize.x + 34f, h = ffaCfgBannerSize.y + 14f;
            var rect = new Rect((Screen.width - w) * 0.5f, ffaPickBannerYMax + 8f, w, h);
            float fade = Mathf.Clamp01(ffaCfgBannerUntil - now);   // last second fades out
            Color previous = GUI.color;
            GUI.color = new Color(0.10f, 0.13f, 0.20f, 0.90f * fade);
            GUI.DrawTexture(rect, Texture2D.whiteTexture);
            GUI.color = new Color(1f, 0.86f, 0.30f, fade);
            GUI.Label(rect, ffaCfgBannerText, ffaCfgBannerStyle);
            GUI.color = previous;
        }

        // ── Aug 6 item 10: match-point warning banner ─────────────────────────
        // "When someone is half a point from winning, warn everyone so they know
        // to target them." Yellow, names the player(s), and carries the sudden-
        // death note when that lobby option is on. Multiple players can sit at
        // match point at once (they each need one more half point), so the plural
        // case is first-class rather than an afterthought.
        //
        // Names keep their rich-text styling (same choice as the leaver banner) —
        // this is the one FFA surface that does NOT strip tags, because "who do I
        // shoot" is exactly the moment a player's nametag should be recognisable.
        private const int FfaMpMaxNames = 4;
        private static string ffaMpBannerText = "";
        private static string ffaMpSignature;
        private static float ffaMpCachedAt = -999f;
        private static Vector2 ffaMpBannerSize;
        private static GUIStyle ffaMpBannerStyle;
        private static readonly List<int> ffaMpTeams = new List<int>(10);

        private static void RefreshFfaMatchPointBanner(float now, bool inMatch)
        {
            if (!inMatch)
            {
                ffaMpBannerText = "";
                ffaMpSignature = null;
                return;
            }
            if (now - ffaMpCachedAt < 0.5f) return;
            ffaMpCachedAt = now;

            FfaMode.CollectMatchPointTeams(ffaMpTeams);
            if (ffaMpTeams.Count == 0)
            {
                // Cleared as soon as nobody is at match point any more — a
                // converted point or a fresh game both land here.
                ffaMpBannerText = "";
                ffaMpSignature = null;
                return;
            }

            // Signature covers the roster AND the sudden-death flag, so the
            // string is rebuilt only when the banner's meaning changes.
            var sig = new System.Text.StringBuilder(24);
            foreach (int t in ffaMpTeams) sig.Append(t).Append(',');
            sig.Append(FfaMode.SuddenDeath ? '1' : '0');
            string signature = sig.ToString();
            if (signature == ffaMpSignature && !string.IsNullOrEmpty(ffaMpBannerText)) return;
            ffaMpSignature = signature;

            var names = new System.Text.StringBuilder(96);
            int shown = 0, extra = 0;
            foreach (int t in ffaMpTeams)
            {
                string nm = FfaMatchPointName(t);
                if (string.IsNullOrEmpty(nm)) continue;
                if (shown >= FfaMpMaxNames) { extra++; continue; }
                if (shown > 0) names.Append(", ");
                names.Append(nm);
                shown++;
            }
            if (shown == 0) { ffaMpBannerText = ""; return; }
            // Whole phrase, not a bare " +N more" connector: a fragment with
            // under three letters can never be harvested as a key (#295c), and
            // composing after Tr is the recurring i18n bug shape (#298c).
            string who = extra > 0
                ? I18n.TrF("{0} and {1} more", names.ToString(), extra)
                : names.ToString();
            string text = shown == 1
                ? I18n.TrF("MATCH POINT - {0} is half a point from the win!", who)
                : I18n.TrF("MATCH POINT - {0} are half a point from the win!", who);
            if (FfaMode.SuddenDeath)
                text += I18n.Tr("   -   SUDDEN DEATH: everyone else cannot damage each other");
            ffaMpBannerText = text;
            ffaMpBannerSize = Vector2.zero;   // re-measure on the next Repaint
        }

        /// <summary>Styled nickname for the player holding a match-point slot.
        /// Rich text is preserved, but an absurdly long nickname falls back to the
        /// tag-stripped form rather than being cut mid-tag (a truncated
        /// "&lt;colo" would corrupt the rest of the banner's markup).</summary>
        private static string FfaMatchPointName(int teamId)
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return null;
                foreach (var p in pm.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    if (p.TeamID != teamId) continue;
                    string raw = null;
                    try { raw = p.data.view != null && p.data.view.Owner != null ? p.data.view.Owner.NickName : null; }
                    catch { }
                    if (string.IsNullOrEmpty(raw)) return "P" + (teamId + 1);
                    // Control characters are hostile input for a GUI label (#100).
                    var sb = new System.Text.StringBuilder(raw.Length);
                    foreach (char c in raw) sb.Append(c < ' ' ? ' ' : c);
                    string safe = sb.ToString();
                    if (safe.Length <= 64) return safe;
                    string clean = NametagStyler.Clean(safe) ?? "";
                    if (clean.Length > 16) clean = clean.Substring(0, 16);
                    return clean.Length == 0 ? "P" + (teamId + 1) : clean;
                }
            }
            catch { }
            return null;
        }

        private static void DrawFfaMatchPointBanner(float now)
        {
            if (string.IsNullOrEmpty(ffaMpBannerText)) return;
            if (Event.current.type != EventType.Repaint) return;   // #162
            if (ffaMpBannerStyle == null)
            {
                ffaMpBannerStyle = new GUIStyle(GUI.skin.label)
                {
                    alignment = TextAnchor.MiddleCenter,
                    fontSize = Mathf.Max(14, Mathf.RoundToInt(19f * (Screen.height / 1080f))),
                    fontStyle = FontStyle.Bold,
                    richText = true,                    // styled nametags
                    clipping = TextClipping.Overflow,   // #143 — IMGUI metrics run tall
                };
            }
            if (ffaMpBannerSize == Vector2.zero)
                ffaMpBannerSize = ffaMpBannerStyle.CalcSize(new GUIContent(ffaMpBannerText));
            float w = Mathf.Min(ffaMpBannerSize.x + 34f, Screen.width - 20f);
            float h = ffaMpBannerSize.y + 14f;
            // Sits in the settings banner's slot. In practice they never collide
            // (the settings banner runs for 9s at game start, when every score is
            // 0 and match point is arithmetically impossible), but stacking below
            // a live one costs two lines and removes the question entirely.
            float y = ffaPickBannerYMax + 8f;
            if (!string.IsNullOrEmpty(ffaCfgBannerText) && now <= ffaCfgBannerUntil)
                y += ffaCfgBannerSize.y + 20f;
            var rect = new Rect((Screen.width - w) * 0.5f, y, w, h);
            float pulse = 0.80f + 0.20f * Mathf.Sin(now * 5f);
            Color previous = GUI.color;
            GUI.color = new Color(0.36f, 0.26f, 0.03f, 0.92f * pulse);
            GUI.DrawTexture(rect, Texture2D.whiteTexture);
            GUI.color = new Color(1f, 0.88f, 0.22f, 1f);
            GUI.Label(rect, ffaMpBannerText, ffaMpBannerStyle);
            GUI.color = previous;
        }

        private static void DrawFfaPickBanner(float now)
        {
            if (string.IsNullOrEmpty(ffaPickBannerText))
            {
                ffaPickBannerYMax = ffaPickBannerRect.yMax;
                return;
            }
            Color background;
            Color foreground;
            if (!ffaPickBannerLocal)
            {
                background = new Color(0.08f, 0.08f, 0.09f, 0.66f);
                foreground = new Color(0.62f, 0.62f, 0.64f, 0.9f);
            }
            else if (ffaPickBannerSeconds <= 5)
            {
                float pulse = 0.5f + 0.5f * Mathf.Sin(now * 7f);
                background = Color.Lerp(new Color(0.78f, 0.08f, 0.04f, 0.92f),
                    new Color(0.92f, 0.55f, 0.04f, 0.94f), pulse);
                foreground = Color.Lerp(new Color(1f, 0.78f, 0.16f, 1f), Color.white, pulse);
            }
            else
            {
                background = new Color(0.12f, 0.20f, 0.31f, 0.88f);
                foreground = new Color(1f, 0.86f, 0.30f, 1f);
            }

            // Fit the rect to the RENDERED text (#237): the 260px layout slot
            // clipped the two-line GET READY string top and bottom. Measured
            // once per (text, fontSize); the slot keeps the anchor (center x,
            // top y) and acts as the minimum footprint so the short countdown
            // strings don't shrink the box frame-to-frame.
            if (ffaPickBannerText != ffaPickBannerMeasuredText
                || ffaPickBannerStyle.fontSize != ffaPickBannerMeasuredFont)
            {
                ffaPickBannerMeasuredText = ffaPickBannerText;
                ffaPickBannerMeasuredFont = ffaPickBannerStyle.fontSize;
                ffaPickBannerMeasured = ffaPickBannerStyle.CalcSize(new GUIContent(ffaPickBannerText));
            }
            float bw = Mathf.Min(Mathf.Max(ffaPickBannerRect.width, ffaPickBannerMeasured.x + 26f),
                Screen.width - 20f);
            float bh = Mathf.Max(ffaPickBannerRect.height, ffaPickBannerMeasured.y + 8f);
            var bannerRect = new Rect((Screen.width - bw) * 0.5f, ffaPickBannerRect.y, bw, bh);
            ffaPickBannerYMax = bannerRect.yMax;

            Color previous = GUI.color;
            GUI.color = background;
            GUI.DrawTexture(bannerRect, Texture2D.whiteTexture);
            GUI.color = foreground;
            GUI.Label(bannerRect, ffaPickBannerText, ffaPickBannerStyle);
            GUI.color = previous;
        }

        private static void SuppressFfaVanillaCounter(float now)
        {
            if (now - ffaVanillaCounterCheckedAt < 1f) return;
            ffaVanillaCounterCheckedAt = now;
            try
            {
                var ui = UIHandler.instance;
                var counter = ui != null ? ui.roundCounterSmall : null;
                if (counter != null && counter.gameObject.activeSelf)
                    counter.gameObject.SetActive(false);
            }
            catch { }
        }

        // ── Tournament banner (item 3, v1.30) ─────────────────────────────
        // Big top-center banner so nobody misses a sync tournament. Four states:
        //   yellow  — signed-up tournament starts in <=15 min: "stay in ROUNDS"
        //   green   — my match is ready, auto-connect in progress
        //   red     — my match is ready but I'm sitting in ANOTHER room: leave!
        //             (shows the live no-show countdown)
        //   thin blue — tournament running, I'm alive in the bracket, waiting
        //             for my next match (menu only, so it never clutters games)
        // Plays the match-found sound + flashes the taskbar once per match.
        private static readonly HashSet<string> _tourneyBannerAnnounced = new HashSet<string>();
        private static GUIStyle tourneyBannerStyle;

        // ── July 22 item 2 (bug #81): "player left" banner ─────────────────
        // Full-width top bar naming who disconnected/quit, shown on every
        // remaining seat in every mode (casual/ranked/2v2/1v2). Red = mid-game
        // DC, orange = between-games leave with the series unfinished. NOT
        // gated on Plugin.ShowNotifications — match-critical information.
        private static string _leaverText;
        private static float _leaverUntil;
        private static bool _leaverRed;
        private static GUIStyle _leaverStyle;
        public static void ShowLeaverBanner(string text, bool red)
        {
            if (string.IsNullOrEmpty(text)) return;
            bool live = Time.unscaledTime < _leaverUntil && !string.IsNullOrEmpty(_leaverText);
            // A second leaver inside the display window (duo rage-quit) appends
            // rather than replaces, so both names are visible.
            if (live && _leaverText != text && _leaverText.Length < 160)
                _leaverText = _leaverText + "    +    " + text;
            else
                _leaverText = text;
            _leaverRed = red || (live && _leaverRed);
            _leaverUntil = Time.unscaledTime + 9f;
            try { TaskbarFlash.Flash(); } catch { }
        }
        public static void ClearLeaverBanner() { _leaverUntil = 0f; _leaverText = null; _leaverRed = false; }
        private static void DrawLeaverBanner()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            if (string.IsNullOrEmpty(_leaverText) || Time.unscaledTime >= _leaverUntil) return;
            float barH = 34f;
            Color bg = _leaverRed ? new Color(0.72f, 0.10f, 0.10f, 0f) : new Color(0.82f, 0.52f, 0.08f, 0f);
            // Same pulse family as the tournament banner; fade out over the last second.
            float pulse = 0.78f + 0.14f * Mathf.Sin(Time.unscaledTime * 5f);
            float fade = Mathf.Clamp01(_leaverUntil - Time.unscaledTime);
            bg.a = 0.92f * pulse * fade;
            GUI.DrawTexture(new Rect(0, 0, Screen.width, barH), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, bg, 0, 0);
            if (_leaverStyle == null)
                _leaverStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 16, fontStyle = FontStyle.Bold, richText = true,
                    alignment = TextAnchor.MiddleCenter, clipping = TextClipping.Overflow,
                };
            var prev = GUI.color;
            GUI.color = new Color(1f, 1f, 1f, Mathf.Clamp01(fade * 1.5f));
            GUI.Label(new Rect(0, 0, Screen.width, barH), _leaverText, _leaverStyle);
            GUI.color = prev;
        }

        private static void DrawTournamentBanner()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            try
            {
                ApiClient.ActiveTournamentMatch ready = null;
                ApiClient.ActiveTournamentMatch scheduled = null;
                var list = ApiClient.CachedMyActiveTournamentMatches;
                if (list != null)
                    foreach (var m in list)
                    {
                        if (m == null || m.kind != "sync") continue;
                        if (m.status == "ready") { ready = m; break; }
                        if (m.status == "scheduled" && scheduled == null) scheduled = m;
                    }

                string text = null;
                Color bg = Color.black;
                float barH = 44f;

                // Break state (July 17 round 2): slim countdown to the next
                // match — informational, no urgency (the break can't forfeit).
                if (ready == null && scheduled != null)
                {
                    int bsecs = -1;
                    if (scheduled.scheduled_seconds_left >= 0)
                        bsecs = Mathf.Max(0, scheduled.scheduled_seconds_left - (int)(Time.realtimeSinceStartup - scheduled.fetched_at_realtime));
                    // i18n: this banner is GUI.Label-drawn (no Tr chokepoint), so
                    // every fragment translates at composition. The clock stays
                    // pre-formatted (a {N:00} spec would be translator bait) and
                    // the in/soon wording lives INSIDE the main templates — a
                    // bare " in {0}" fragment has under 3 letters, which
                    // looks_translatable rejects, so it could never be keyed.
                    string bopp = scheduled.opponent_display_name ?? I18n.Tr("opponent");
                    string early = scheduled.my_early_ok
                        ? I18n.Tr(" (Play Now sent - waiting on them)")
                        : I18n.Tr(" (both press Play Now in F5 to start early)");
                    text = bsecs >= 0
                        ? I18n.TrF("Next tournament match vs {0} in {1}{2}", bopp, $"{bsecs / 60}:{bsecs % 60:00}", early)
                        : I18n.TrF("Next tournament match vs {0} soon{1}", bopp, early);
                    bg = new Color(0.12f, 0.25f, 0.45f, 0.85f);
                    barH = 26f;
                }
                else if (ready != null)
                {
                    bool inRoom = false, inTargetRoom = false;
                    try
                    {
                        inRoom = Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode;
                        var room = Photon.Pun.PhotonNetwork.CurrentRoom;
                        inTargetRoom = inRoom && room != null && room.Name == ready.photon_room_name;
                    }
                    catch { }
                    if (inTargetRoom) return; // we're where we should be

                    if (!_tourneyBannerAnnounced.Contains(ready.match_id))
                    {
                        _tourneyBannerAnnounced.Add(ready.match_id);
                        try { PlayMatchFoundSound(); } catch { }
                        try { TaskbarFlash.Flash(); } catch { }
                    }
                    // Live countdown from the snapshot + elapsed-since-fetch.
                    int secs = -1;
                    if (ready.ready_seconds_left >= 0)
                        secs = Mathf.Max(0, ready.ready_seconds_left - (int)(Time.realtimeSinceStartup - ready.fetched_at_realtime));
                    string clock = secs >= 0 ? $"   {secs / 60}:{secs % 60:00}" : "";
                    string opp = ready.opponent_display_name ?? I18n.Tr("opponent");
                    if (inRoom)
                    {
                        text = I18n.TrF("TOURNAMENT MATCH vs {0} IS WAITING - LEAVE THIS GAME NOW!{1}", opp, clock);
                        bg = new Color(0.72f, 0.10f, 0.10f, 0.93f);
                    }
                    else
                    {
                        text = I18n.TrF("TOURNAMENT MATCH vs {0} - connecting automatically, hold tight...{1}", opp, clock);
                        bg = new Color(0.08f, 0.48f, 0.20f, 0.93f);
                    }
                }
                else
                {
                    var t = ApiClient.CachedTournament;
                    if (t == null || t.kind != "sync" || string.IsNullOrEmpty(t.my_signup_id)) return;
                    if (t.status == "locked" && !string.IsNullOrEmpty(t.scheduled_start_ts))
                    {
                        DateTime start;
                        if (DateTime.TryParse(t.scheduled_start_ts, null,
                                System.Globalization.DateTimeStyles.RoundtripKind, out start))
                        {
                            double mins = (start.ToUniversalTime() - DateTime.UtcNow).TotalMinutes;
                            if (mins > 0 && mins <= 15)
                            {
                                int s = (int)((start.ToUniversalTime() - DateTime.UtcNow).TotalSeconds);
                                text = I18n.TrF("TOURNAMENT STARTS IN {0} - stay in ROUNDS at the main menu!",
                                    $"{s / 60}:{s % 60:00}");
                                bg = new Color(0.75f, 0.60f, 0.05f, 0.93f);
                            }
                            else if (mins <= 0 && mins > -10)
                            {
                                text = I18n.Tr("TOURNAMENT STARTING - matches are being created, hold tight...");
                                bg = new Color(0.75f, 0.60f, 0.05f, 0.93f);
                            }
                        }
                    }
                    else if (t.status == "running")
                    {
                        // Alive in the bracket, between matches, at the menu.
                        bool inRoom = false;
                        try { inRoom = Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode; } catch { }
                        if (inRoom) return;
                        bool alive = false;
                        if (t.signups != null)
                            foreach (var s in t.signups)
                                if (s != null && s.signup_id == t.my_signup_id)
                                { alive = !s.forfeited && s.placed_rank <= 0; break; }
                        if (!alive) return;
                        text = I18n.Tr("Tournament in progress - your next match will connect automatically. Keep ROUNDS open.");
                        bg = new Color(0.12f, 0.25f, 0.45f, 0.85f);
                        barH = 26f;
                    }
                }

                if (text == null) return;
                if (tourneyBannerStyle == null)
                    tourneyBannerStyle = new GUIStyle(GUI.skin.label)
                    { fontSize = 17, alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold, richText = false };
                tourneyBannerStyle.fontSize = barH > 30f ? 17 : 13;
                // Pulse the big banners' alpha slightly so they read as live.
                float pulse = barH > 30f ? 0.85f + 0.15f * Mathf.PingPong(Time.unscaledTime * 1.6f, 1f) : 1f;
                var prev = GUI.color;
                GUI.color = new Color(bg.r, bg.g, bg.b, bg.a * pulse);
                GUI.DrawTexture(new Rect(0, 0, Screen.width, barH), Texture2D.whiteTexture, ScaleMode.StretchToFill);
                GUI.color = Color.white;
                GUI.Label(new Rect(0, 0, Screen.width, barH), text, tourneyBannerStyle);
                GUI.color = prev;
            }
            catch { }
        }

        // Bottom-center toast naming the map skin you just Shift-cycled to, so you can
        // hunt for a specific one (e.g. Magma) by sight. Driven by MapColorState.ShowToast.
        private static GUIStyle mapToastStyle;
        private static void DrawMapColorToast()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
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
                GUI.Label(new Rect(x, y, w, h),
                    I18n.TrF("<color=#FFD94D>Map skin:</color> <color=#FFFFFF>{0}</color>", t), mapToastStyle);
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
                    I18n.TrF("<color=#FFD94D>Custom bet</color> on <color=#FFFFFF>{0}</color>",
                             NativeUI.CustomBetTargetLabel), betPromptTitleStyle);
                GUI.SetNextControlName(BET_AMOUNT_CTRL);
                string next = GUI.TextField(new Rect(x + 40f, y + 34f, w - 80f, 30f), NativeUI.CustomBetAmountText ?? "", 5, betPromptStyle);
                // Digits only (commas allowed, stripped at submit).
                var filtered = new System.Text.StringBuilder(next.Length);
                foreach (char c in next) if (char.IsDigit(c) || c == ',') filtered.Append(c);
                NativeUI.CustomBetAmountText = filtered.ToString();
                GUI.FocusControl(BET_AMOUNT_CTRL);
                GUI.Label(new Rect(x, y + 64f, w, 16f), I18n.Tr("<color=#8899AA>1 - 2,000 gold</color>"), betPromptTitleStyle);
                if (GUI.Button(new Rect(x + 34f, y + 86f, 130f, 30f), I18n.Tr("Place bet")))
                    NativeUI.SubmitCustomBet();
                if (GUI.Button(new Rect(x + w - 164f, y + 86f, 130f, 30f), I18n.Tr("Cancel")))
                    NativeUI.CancelCustomBet();
            }
            catch { }
        }

        // ── LFP Discord ping prompt (July 21 item 8) ──────────────────────
        // Message box + expiry picker. The LfpPromptOpen flag is in BOTH the
        // anyModal set (uGUI + ClickHandler blocking, learning #141) and the
        // DrawChatInput guard (typing 't' must not open chat).
        private static GUIStyle lfpFieldStyle, lfpTitleStyle;
        private const string LFP_MSG_CTRL = "LfpMsgField";
        private static void DrawLfpPrompt()
        {
            if (!NativeUI.LfpPromptOpen) return;
            try
            {
                var ev = Event.current;
                if (ev != null && ev.type == EventType.KeyDown)
                {
                    if (ev.keyCode == KeyCode.Return || ev.keyCode == KeyCode.KeypadEnter)
                    { ev.Use(); NativeUI.SubmitLfpPing(); return; }
                    if (ev.keyCode == KeyCode.Escape)
                    { ev.Use(); NativeUI.CancelLfpPing(); return; }
                }
                if (lfpFieldStyle == null)
                    lfpFieldStyle = new GUIStyle(GUI.skin.textField) { fontSize = 15, alignment = TextAnchor.MiddleLeft };
                if (lfpTitleStyle == null)
                    lfpTitleStyle = new GUIStyle(GUI.skin.label) { fontSize = 14, alignment = TextAnchor.MiddleCenter, richText = true, fontStyle = FontStyle.Bold, clipping = TextClipping.Overflow };
                // Aug 7 item 11: +48px for the mode row; Send/Cancel shift down
                // with it (absolute-offset IMGUI — grow the box or overlap, #199).
                float w = 520f, h = 256f;
                float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
                GUI.color = new Color(0f, 0f, 0f, 0.55f);
                GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture);
                GUI.color = new Color(0.10f, 0.11f, 0.14f, 0.98f);
                GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture);
                GUI.color = Color.white;
                GUI.Label(new Rect(x, y + 6f, w, 22f),
                    I18n.Tr("<color=#FFD94D>Ranked Looking For Player</color> - Discord ping"), lfpTitleStyle);
                GUI.Label(new Rect(x, y + 28f, w, 18f),
                    I18n.Tr("<color=#8899AA>Pings the Ranked Looking For Player role (max 1 per hour). Optional message:</color>"), lfpTitleStyle);
                GUI.SetNextControlName(LFP_MSG_CTRL);
                string next = GUI.TextField(new Rect(x + 20f, y + 52f, w - 40f, 30f), NativeUI.LfpMessageText ?? "", 200, lfpFieldStyle);
                NativeUI.LfpMessageText = next;
                GUI.FocusControl(LFP_MSG_CTRL);
                GUI.Label(new Rect(x, y + 90f, w, 18f),
                    I18n.Tr("<color=#8899AA>How long are you searching? (shown to players as an expiry)</color>"), lfpTitleStyle);
                float bw = 70f, bx = x + (w - (bw * 4 + 24f)) / 2f;
                for (int i = 0; i < 4; i++)
                {
                    bool sel = NativeUI.LfpExpiryIdx == i;
                    GUI.color = sel ? new Color(0.35f, 0.55f, 0.85f, 1f) : new Color(0.22f, 0.24f, 0.30f, 1f);
                    GUI.DrawTexture(new Rect(bx + i * (bw + 8f), y + 112f, bw, 26f), Texture2D.whiteTexture);
                    GUI.color = Color.white;
                    if (GUI.Button(new Rect(bx + i * (bw + 8f), y + 112f, bw, 26f), NativeUI.LfpExpiryLabels[i], lfpTitleStyle))
                        NativeUI.LfpExpiryIdx = i;
                }
                // Mode multi-select: TOGGLES (any combination), not radio.
                GUI.Label(new Rect(x, y + 144f, w, 18f),
                    I18n.Tr("<color=#8899AA>Which modes? (pick any)</color>"), lfpTitleStyle);
                float mbx = x + (w - (bw * 3 + 16f)) / 2f;
                for (int i = 0; i < 3; i++)
                {
                    bool sel = NativeUI.LfpModeSel[i];
                    GUI.color = sel ? new Color(0.35f, 0.55f, 0.85f, 1f) : new Color(0.22f, 0.24f, 0.30f, 1f);
                    GUI.DrawTexture(new Rect(mbx + i * (bw + 8f), y + 166f, bw, 26f), Texture2D.whiteTexture);
                    GUI.color = Color.white;
                    if (GUI.Button(new Rect(mbx + i * (bw + 8f), y + 166f, bw, 26f), NativeUI.LfpModeLabels[i], lfpTitleStyle))
                        NativeUI.LfpModeSel[i] = !NativeUI.LfpModeSel[i];
                }
                if (GUI.Button(new Rect(x + 60f, y + 204f, 180f, 32f), I18n.Tr("Send ping")))
                    NativeUI.SubmitLfpPing();
                if (GUI.Button(new Rect(x + w - 240f, y + 204f, 180f, 32f), I18n.Tr("Cancel")))
                    NativeUI.CancelLfpPing();
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
                    /* Aug 7 item 2 — one shared field, two lists. The Cards
                     * sub-tab's chooser used to be a modal dropdown with its own
                     * search; it is now a persistent left-column list filtered by
                     * THIS box, so the placeholder has to name what it filters or
                     * it reads as the wrong control. Both literals sit inside
                     * their own Tr call — I18n.Tr(variable) harvests nothing
                     * (#295a), so a composed string would never be translatable. */
                    GUI.Label(new Rect(fieldRect.x + 6f, fieldRect.y, fieldRect.width - 8f, h),
                              NativeUI.CompareCardsSubTab
                                ? I18n.Tr("<color=#7788AA><i>search cards...</i></color>")
                                : I18n.Tr("<color=#7788AA><i>search players...</i></color>"),
                              compareSearchHintStyle);
                if (next != cur)
                {
                    NativeUI.CompareSearch = next;
                    NativeUI.MarkDirty();
                }
            }
            catch { /* search is best-effort cosmetic */ }
        }

        // Aug 6 item 2: the searchable metric/card dropdown. Same
        // IMGUI-over-anchor clone as the two searches above, but gated on the
        // PICKER being open rather than on a tab index — the overlay can be
        // raised from more than one tab, and it must stop painting the instant
        // it closes or the field would linger over whatever is underneath.
        //
        // Two contracts that are easy to get wrong:
        //  - Do NOT MarkDirty() on change. NativeUI's PickerSearch setter
        //    rebuilds the filtered list itself; a second rebuild per keystroke
        //    is pure waste on a per-frame IMGUI path (#162).
        //  - pickerSearchFocused MUST feed the same chat mutex the other two
        //    do, or typing "t" here opens the in-game chat box mid-search.
        private static bool pickerSearchFocused = false;
        public static bool IsPickerSearchFocused => pickerSearchFocused;
        private const string PICKER_SEARCH_CTRL = "PickerSearchField";
        private static GUIStyle pickerSearchStyle, pickerSearchHintStyle;
        private static void DrawPickerSearch()
        {
            pickerSearchFocused = false;
            try
            {
                if (!NativeUI.IsOpen || !NativeUI.PickerOpen) return;
                Rect r = NativeUI.GetPickerSearchScreenRect();
                if (r.width < 1f || r.height < 1f) return;
                if (pickerSearchStyle == null)
                    pickerSearchStyle = new GUIStyle(GUI.skin.textField) { fontSize = 13, alignment = TextAnchor.MiddleLeft };
                if (pickerSearchHintStyle == null)
                    pickerSearchHintStyle = new GUIStyle(GUI.skin.label) { fontSize = 12, alignment = TextAnchor.MiddleLeft, richText = true };
                float h = Mathf.Max(r.height, 22f);
                var fieldRect = new Rect(r.x, r.y, Mathf.Max(r.width, 200f), h);
                string cur = NativeUI.PickerSearch ?? "";
                GUI.SetNextControlName(PICKER_SEARCH_CTRL);
                string next = GUI.TextField(fieldRect, cur, pickerSearchStyle);
                pickerSearchFocused = GUI.GetNameOfFocusedControl() == PICKER_SEARCH_CTRL;
                if (string.IsNullOrEmpty(next))
                    GUI.Label(new Rect(fieldRect.x + 6f, fieldRect.y, fieldRect.width - 8f, h),
                              I18n.Tr("<color=#7788AA><i>search...</i></color>"), pickerSearchHintStyle);
                if (next != cur)
                    NativeUI.PickerSearch = next;   // setter rebuilds the list
            }
            catch { /* search is best-effort cosmetic */ }
        }

        // July 22 item 8: leaderboard search — same IMGUI-over-anchor clone,
        // gated to tab 1, own focus flag feeding the T-chat mutex.
        private static bool lbSearchFocused = false;
        public static bool IsLbSearchFocused => lbSearchFocused;
        private const string LB_SEARCH_CTRL = "LbSearchField";
        private static void DrawLeaderboardSearch()
        {
            lbSearchFocused = false;
            try
            {
                if (!NativeUI.IsOpen || NativeUI.CurrentTab != 1) return;
                Rect r = NativeUI.GetLbSearchScreenRect();
                if (r.width < 1f || r.height < 1f) return;
                if (compareSearchStyle == null)
                    compareSearchStyle = new GUIStyle(GUI.skin.textField) { fontSize = 13, alignment = TextAnchor.MiddleLeft };
                if (compareSearchHintStyle == null)
                    compareSearchHintStyle = new GUIStyle(GUI.skin.label) { fontSize = 12, alignment = TextAnchor.MiddleLeft, richText = true };
                float h = Mathf.Max(r.height, 22f);
                var fieldRect = new Rect(r.x, r.y, Mathf.Max(r.width, 200f), h);
                string cur = NativeUI.LeaderboardSearch ?? "";
                GUI.SetNextControlName(LB_SEARCH_CTRL);
                string next = GUI.TextField(fieldRect, cur, compareSearchStyle);
                lbSearchFocused = GUI.GetNameOfFocusedControl() == LB_SEARCH_CTRL;
                if (string.IsNullOrEmpty(next))
                    GUI.Label(new Rect(fieldRect.x + 6f, fieldRect.y, fieldRect.width - 8f, h),
                              I18n.Tr("<color=#7788AA><i>search players...</i></color>"), compareSearchHintStyle);
                if (next != cur)
                {
                    NativeUI.LeaderboardSearch = next;
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
            // Bug #61: live tracking. When sourceRT is set the hit test recomputes
            // the screen rect from the element's CURRENT world corners each frame,
            // so scrolling the history list can't desync the region from its text.
            // screenRect stays as the fallback if the element is destroyed.
            public RectTransform sourceRT;
            public Camera sourceCam;      // null = overlay canvas (corners are screen coords)
            public float widthFrac;       // rendered-text width fraction (learning #90); <=0 = full
            public RectTransform clipRT;  // scroll Viewport (Mask) — rows scrolled out don't hover
            // Bug #72: the width fraction froze at REGISTRATION time, and on the
            // first render after open/data-arrival TMP hasn't generated the text
            // yet — preferredWidth reads tiny/zero and the region registered
            // nearly unhittable ("hover doesn't work until the page is
            // refreshed"). Keep the text component and compute the fraction LIVE
            // at hit-test time, same treatment #61 gave the rect itself.
            public object sourceTxt;
        }
        private static readonly List<CardHoverRegion> _cardHoverRegions = new List<CardHoverRegion>(40);
        public static void ClearCardHoverRegions()
        {
            _cardHoverRegions.Clear();
            _scoreGraphRegions.Clear();
            _fpsGraphRegions.Clear();
        }

        // Bug #61: recompute a region's screen rect from its source element every
        // hit test. GetWorldCorners reflects the ScrollRect's current content
        // offset, so regions follow their rows while the user scrolls. Falls back
        // to the registration-time rect when the element is gone (pooled rows are
        // reused, not destroyed, so this only happens in teardown races).
        private static readonly Vector3[] _liveCornerBuf = new Vector3[4];
        private static readonly Rect _offscreenRect = new Rect(-99999f, -99999f, 1f, 1f);

        // Bug #72: rendered-text width fraction computed LIVE (see sourceTxt note).
        private static System.Reflection.PropertyInfo _pPrefWidth;
        internal static float LiveWidthFrac(object txt, RectTransform rt, float fallback)
        {
            try
            {
                if (txt == null || rt == null) return fallback;
                if (_pPrefWidth == null)
                    _pPrefWidth = txt.GetType().GetProperty("preferredWidth",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                if (_pPrefWidth == null) return fallback;
                float localW = rt.rect.width;
                if (localW <= 0f) return fallback;
                float pref = (float)_pPrefWidth.GetValue(txt);
                if (pref <= 0f) return fallback;
                return Mathf.Clamp01(pref / localW);
            }
            catch { return fallback; }
        }
        internal static Rect LiveRegionRect(RectTransform rt, Camera cam, float frac, RectTransform clip, Rect fallback,
                                            RectTransform outerClip = null)
        {
            try
            {
                if (rt == null) return fallback;          // Unity fake-null when destroyed
                if (!rt.gameObject.activeInHierarchy) return _offscreenRect;
                Rect r = ScreenRectOf(rt, cam);
                if (frac > 0f && frac <= 1f) r.width = Mathf.Min(r.width, r.width * frac + 12f);
                // Clip against the scroll Viewport (its Mask hides rows visually;
                // without this a row scrolled out of the box would still hover).
                if (clip != null)
                {
                    Rect c = ScreenRectOf(clip, cam);
                    float xMin = Mathf.Max(r.xMin, c.xMin), xMax = Mathf.Min(r.xMax, c.xMax);
                    float yMin = Mathf.Max(r.yMin, c.yMin), yMax = Mathf.Min(r.yMax, c.yMax);
                    if (xMax - xMin < 1f || yMax - yMin < 1f) return _offscreenRect;
                    r = new Rect(xMin, yMin, xMax - xMin, yMax - yMin);
                }
                // F9: second mask — the FFA tab's whole-page outer viewport. A
                // row can be visible inside its list scroll yet outer-scrolled
                // beneath the page chrome; clip at hit-test time exactly like
                // the FFA cards/header path (TryGetFfaViewportClippedRect).
                if (outerClip != null)
                {
                    Rect c = ScreenRectOf(outerClip, cam);
                    float xMin = Mathf.Max(r.xMin, c.xMin), xMax = Mathf.Min(r.xMax, c.xMax);
                    float yMin = Mathf.Max(r.yMin, c.yMin), yMax = Mathf.Min(r.yMax, c.yMax);
                    if (xMax - xMin < 1f || yMax - yMin < 1f) return _offscreenRect;
                    r = new Rect(xMin, yMin, xMax - xMin, yMax - yMin);
                }
                return r;
            }
            catch { return fallback; }
        }
        private static Rect ScreenRectOf(RectTransform rt, Camera cam)
        {
            rt.GetWorldCorners(_liveCornerBuf);
            Vector2 sMin, sMax;
            if (cam == null)
            {
                sMin = new Vector2(_liveCornerBuf[0].x, _liveCornerBuf[0].y);
                sMax = new Vector2(_liveCornerBuf[2].x, _liveCornerBuf[2].y);
            }
            else
            {
                Vector3 p0 = cam.WorldToScreenPoint(_liveCornerBuf[0]);
                Vector3 p2 = cam.WorldToScreenPoint(_liveCornerBuf[2]);
                sMin = new Vector2(p0.x, p0.y);
                sMax = new Vector2(p2.x, p2.y);
            }
            return new Rect(sMin.x, sMin.y, Mathf.Max(1f, sMax.x - sMin.x), Mathf.Max(1f, sMax.y - sMin.y));
        }

        // ── Score-history hover graph (item 4, v1.30) ──────────────────
        // FillRow registers each history row's W/L score text with the match's
        // cumulative scoring timeline ("myTotal:oppTotal,..."). Hovering pops a
        // small line graph: green = you, red = opponent, x = scoring events.
        public struct ScoreGraphRegion
        {
            public Rect screenRect;   // bottom-left-origin screen coords
            public string timeline;
            public bool won;
            public RectTransform sourceRT;   // bug #61: live tracking (see CardHoverRegion)
            public Camera sourceCam;
            public float widthFrac;
            public RectTransform clipRT;
            public object sourceTxt;         // bug #72: live width fraction (see CardHoverRegion)
        }
        private static readonly List<ScoreGraphRegion> _scoreGraphRegions = new List<ScoreGraphRegion>(40);
        public static void RegisterScoreGraphRegion(Rect screenRect, string timeline, bool won)
            => RegisterScoreGraphRegion(screenRect, timeline, won, null, null, -1f, null);
        public static void RegisterScoreGraphRegion(Rect screenRect, string timeline, bool won,
                                                    RectTransform sourceRT, Camera sourceCam, float widthFrac,
                                                    RectTransform clipRT, object sourceTxt = null)
        {
            if (string.IsNullOrEmpty(timeline)) return;
            _scoreGraphRegions.Add(new ScoreGraphRegion {
                screenRect = screenRect, timeline = timeline, won = won,
                sourceRT = sourceRT, sourceCam = sourceCam, widthFrac = widthFrac, clipRT = clipRT,
                sourceTxt = sourceTxt,
            });
        }

        // Rotated-texture line segment — IMGUI has no native line primitive.
        private static void GuiLine(Vector2 a, Vector2 b, Color color, float width)
        {
            var prev = GUI.color;
            GUI.color = color;
            float len = Vector2.Distance(a, b);
            if (len < 0.5f) { GUI.color = prev; return; }
            float ang = Mathf.Atan2(b.y - a.y, b.x - a.x) * Mathf.Rad2Deg;
            var mtx = GUI.matrix;
            GUIUtility.RotateAroundPivot(ang, a);
            GUI.DrawTexture(new Rect(a.x, a.y - width / 2f, len, width), Texture2D.whiteTexture);
            GUI.matrix = mtx;
            GUI.color = prev;
        }

        private static GUIStyle _scoreGraphLbl;
        private static void DrawScoreHoverGraph()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            // July 22: tab 8 (2v2) hosts hover graphs too.
            if (!NativeUI.IsOpen || (NativeUI.CurrentTab != 0 && NativeUI.CurrentTab != 8)) return;
            if (_scoreGraphRegions.Count == 0) return;
            Vector2 mp = Input.mousePosition;
            ScoreGraphRegion? hit = null;
            for (int i = _scoreGraphRegions.Count - 1; i >= 0; i--)
            {
                var reg = _scoreGraphRegions[i];
                // Bug #61: live rect so scrolling can't desync region from row.
                // Bug #72: live width fraction too (frozen frac was ~0 on first render).
                float liveFrac = LiveWidthFrac(reg.sourceTxt, reg.sourceRT, reg.widthFrac);
                Rect rr = LiveRegionRect(reg.sourceRT, reg.sourceCam, liveFrac, reg.clipRT, reg.screenRect);
                if (rr.Contains(mp)) { hit = reg; break; }
            }
            if (hit == null) return;

            // Parse "a:b,a:b,..." into two cumulative series (prepend 0:0).
            var parts = hit.Value.timeline.Split(',');
            int n = parts.Length + 1;
            if (n < 3) return;
            var mine = new int[n]; var theirs = new int[n];
            int maxV = 1;
            for (int i = 1; i < n; i++)
            {
                var ab = parts[i - 1].Split(':');
                if (ab.Length != 2) return;
                int a, b;
                if (!int.TryParse(ab[0], out a) || !int.TryParse(ab[1], out b)) return;
                mine[i] = a; theirs[i] = b;
                if (a > maxV) maxV = a; if (b > maxV) maxV = b;
            }

            if (_scoreGraphLbl == null)
                _scoreGraphLbl = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 12, richText = true, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft,
                    // Bug #72 part 2: ROUNDS' IMGUI skin has taller font metrics than
                    // 12pt suggests — glyphs were clipped top+bottom inside the short
                    // label rects ("totally unreadable"). Overflow lets glyphs render
                    // past the rect instead of clipping; rects also got taller.
                    clipping = TextClipping.Overflow, wordWrap = false,
                };

            float w = 280f, h = 178f, pad = 30f;
            // IMGUI is top-left origin; mousePosition is bottom-left.
            float gx = Mathf.Min(mp.x + 18f, Screen.width - w - 8f);
            float gy = Mathf.Clamp(Screen.height - mp.y - h / 2f, 8f, Screen.height - h - 8f);
            GUI.DrawTexture(new Rect(gx - 4, gy - 4, w + 8, h + 8), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, new Color(0f, 0f, 0f, 0.93f), 0, 0);
            GUI.Label(new Rect(gx + 8, gy + 2, w - 16, 24),
                I18n.Tr("<color=#CCCCCC>Scoring history</color>  <color=#66DD66>you</color> <color=#888>vs</color> <color=#DD7777>opponent</color>"),
                _scoreGraphLbl);

            Rect plot = new Rect(gx + pad, gy + 30f, w - pad - 10f, h - 30f - 26f);
            // Gridlines at each full round (2 points).
            for (int v = 0; v <= maxV; v += 2)
            {
                float y = plot.yMax - plot.height * v / maxV;
                GuiLine(new Vector2(plot.xMin, y), new Vector2(plot.xMax, y), new Color(1f, 1f, 1f, 0.08f), 1f);
                GUI.Label(new Rect(gx + 4, y - 11f, pad - 6f, 22f), $"<color=#777>{v / 2}</color>", _scoreGraphLbl);
            }
            // Polylines.
            for (int i = 1; i < n; i++)
            {
                float x0 = plot.xMin + plot.width * (i - 1) / (n - 1);
                float x1 = plot.xMin + plot.width * i / (n - 1);
                float myY0 = plot.yMax - plot.height * mine[i - 1] / maxV;
                float myY1 = plot.yMax - plot.height * mine[i] / maxV;
                float opY0 = plot.yMax - plot.height * theirs[i - 1] / maxV;
                float opY1 = plot.yMax - plot.height * theirs[i] / maxV;
                GuiLine(new Vector2(x0, opY0), new Vector2(x1, opY1), new Color(0.87f, 0.47f, 0.47f, 0.95f), 2f);
                GuiLine(new Vector2(x0, myY0), new Vector2(x1, myY1), new Color(0.40f, 0.87f, 0.40f, 0.95f), 2f);
            }
            GUI.Label(new Rect(gx + 8, gy + h - 24f, w - 16, 22f),
                I18n.Tr("<color=#777>rounds on the left - each step is one point scored</color>"), _scoreGraphLbl);
        }

        // ── FPS / Ping hover graphs (July 21 item 2 · July 22 item 3) ────────
        // FillRow registers the FPS text and the Ping text as SEPARATE regions —
        // hovering FPS pops only the FPS chart, hovering Ping pops only the ping
        // chart, each using the full popup so both get plenty of room. `isPing`
        // just picks the axis units/gridlines. Colors match the row tags
        // (blue #99B3E6 = you, red-ish #E69988 = opponent). You-series samples
        // at 5s (fps) / 3s (ping); opponent at 3s — a shared time axis aligns
        // them so a genuine network hiccup shows on both lines together.
        public struct FpsGraphRegion
        {
            public Rect screenRect;
            public string mySeries;
            public string oppSeries;
            public int kind;            // 0=fps 1=ping 2=hit pairs 3=block pairs 4=player combo (2v2) 5=dps
            public float myStep;        // seconds per "my" sample (5 = 1v1 fps buckets, else 3)
            public bool subjectIsOpp;   // kind 2/3/4: hovered player uses the red/orange palette
            public string pairHit;      // kind 4: "fired:hit,..." for the combo popup
            public string pairBlock;    // kind 4: "dmgTaken:blocksSucc,..."
            public string subjectLabel; // kind 4: player name for the popup title
            public string pointTimes;   // "12,47,..." seconds since match start (marker X)
            public string pointTimeline;// "mine:theirs,..." viewer-relative (marker color = scorer)
            // F9: FFA regions also carry the whole-tab OUTER viewport — the
            // hit test clips against BOTH masks live (the inner list clip
            // alone let a row outer-scrolled under the page chrome keep a
            // live hover region). Null for tabs 0/8 = behavior unchanged.
            public RectTransform outerClipRT;
            public RectTransform sourceRT;
            public Camera sourceCam;
            public float widthFrac;
            public RectTransform clipRT;
            public object sourceTxt;
        }
        private static readonly List<FpsGraphRegion> _fpsGraphRegions = new List<FpsGraphRegion>(60);
        public static void RegisterFpsGraphRegion(Rect screenRect, string mySeries, string oppSeries, bool isPing,
                                                  RectTransform sourceRT, Camera sourceCam, float widthFrac,
                                                  RectTransform clipRT, object sourceTxt = null,
                                                  string pointTimes = null, string pointTimeline = null,
                                                  float myStep = 0f,
                                                  RectTransform outerClipRT = null, string subjectLabel = null)
        {
            if (string.IsNullOrEmpty(mySeries) && string.IsNullOrEmpty(oppSeries)) return;
            _fpsGraphRegions.Add(new FpsGraphRegion {
                screenRect = screenRect, mySeries = mySeries ?? "", oppSeries = oppSeries ?? "",
                kind = isPing ? 1 : 0, myStep = myStep > 0f ? myStep : (isPing ? 3f : 5f),
                pointTimes = pointTimes, pointTimeline = pointTimeline,
                outerClipRT = outerClipRT, subjectLabel = subjectLabel,
                sourceRT = sourceRT, sourceCam = sourceCam, widthFrac = widthFrac, clipRT = clipRT,
                sourceTxt = sourceTxt,
            });
        }

        // Aug 7 item 3d: damage-per-second. Shares the fps/ping popup (one big
        // plot, point markers, auto Y) but is its OWN kind because a DPS series
        // is DERIVED — an idle interval is a genuine 0, and kind 0/1's parser
        // drops zeros, which would shift every later sample left and make the
        // time axis lie. `myStep` is the emitter's sample interval; unlike
        // fps/ping (where the opponent line is always the 3s heartbeat) BOTH
        // DPS lines come from the same cadence, so the caller's step drives both.
        public static void RegisterDpsGraphRegion(Rect screenRect, string mySeries, string oppSeries,
                                                  RectTransform sourceRT, Camera sourceCam, float widthFrac,
                                                  RectTransform clipRT, object sourceTxt = null,
                                                  string pointTimes = null, string pointTimeline = null,
                                                  float myStep = 0f,
                                                  RectTransform outerClipRT = null, string subjectLabel = null)
        {
            if (string.IsNullOrEmpty(mySeries) && string.IsNullOrEmpty(oppSeries)) return;
            _fpsGraphRegions.Add(new FpsGraphRegion {
                screenRect = screenRect, mySeries = mySeries ?? "", oppSeries = oppSeries ?? "",
                kind = 5, myStep = myStep > 0f ? myStep : 3f,
                pointTimes = pointTimes, pointTimeline = pointTimeline,
                outerClipRT = outerClipRT, subjectLabel = subjectLabel,
                sourceRT = sourceRT, sourceCam = sourceCam, widthFrac = widthFrac, clipRT = clipRT,
                sourceTxt = sourceTxt,
            });
        }

        // July 22 item 1: hover region for a single player's cumulative PAIR
        // series — Hit% ("fired:hit,...") or Block% ("dmgTaken:blocksSucc,...").
        public static void RegisterPairGraphRegion(Rect screenRect, string pairSeries, bool isBlock, bool subjectIsOpp,
                                                   RectTransform sourceRT, Camera sourceCam, float widthFrac,
                                                   RectTransform clipRT, object sourceTxt,
                                                   string pointTimes, string pointTimeline,
                                                   RectTransform outerClipRT = null, string subjectLabel = null)
        {
            if (string.IsNullOrEmpty(pairSeries) || pairSeries.IndexOf(':') < 0) return;
            _fpsGraphRegions.Add(new FpsGraphRegion {
                screenRect = screenRect, mySeries = pairSeries, oppSeries = "",
                kind = isBlock ? 3 : 2, myStep = 3f, subjectIsOpp = subjectIsOpp,
                pointTimes = pointTimes, pointTimeline = pointTimeline,
                outerClipRT = outerClipRT, subjectLabel = subjectLabel,
                sourceRT = sourceRT, sourceCam = sourceCam, widthFrac = widthFrac, clipRT = clipRT,
                sourceTxt = sourceTxt,
            });
        }

        // July 22 item 7: one hover target per 2v2 player — pops a 2x2 combo
        // popup (FPS / Ping / Hit / Block) for that player.
        public static void RegisterPlayerComboRegion(Rect screenRect, string fpsSeries, string pingSeries,
                                                     string hitPairs, string blockPairs,
                                                     string playerName, bool isRightTeam,
                                                     RectTransform sourceRT, Camera sourceCam, float widthFrac,
                                                     RectTransform clipRT, object sourceTxt)
        {
            if (string.IsNullOrEmpty(fpsSeries) && string.IsNullOrEmpty(pingSeries)
                && string.IsNullOrEmpty(hitPairs) && string.IsNullOrEmpty(blockPairs)) return;
            _fpsGraphRegions.Add(new FpsGraphRegion {
                screenRect = screenRect, mySeries = fpsSeries ?? "", oppSeries = pingSeries ?? "",
                kind = 4, myStep = 3f, subjectIsOpp = isRightTeam,
                pairHit = hitPairs, pairBlock = blockPairs, subjectLabel = playerName,
                sourceRT = sourceRT, sourceCam = sourceCam, widthFrac = widthFrac, clipRT = clipRT,
                sourceTxt = sourceTxt,
            });
        }

        private static int[] ParseFpsSeries(string csv)
        {
            if (string.IsNullOrEmpty(csv)) return null;
            var parts = csv.Split(',');
            var vals = new List<int>(parts.Length);
            foreach (var s in parts) { int v; if (int.TryParse(s, out v) && v > 0) vals.Add(v); }
            return vals.Count >= 2 ? vals.ToArray() : null;
        }

        // Parse "a:b,a:b,..." cumulative pairs into two aligned arrays. Unlike
        // ParseFpsSeries, zeros are KEPT (a 0-damage or 0-hit prefix is real
        // data on a cumulative series); a 0:0 origin is prepended.
        private static bool ParsePairSeries(string csv, out int[] first, out int[] second)
        {
            first = null; second = null;
            if (string.IsNullOrEmpty(csv)) return false;
            var parts = csv.Split(',');
            var a = new List<int>(parts.Length + 1) { 0 };
            var b = new List<int>(parts.Length + 1) { 0 };
            foreach (var s in parts)
            {
                int ci = s.IndexOf(':');
                if (ci <= 0) continue;
                int x, y;
                if (!int.TryParse(s.Substring(0, ci), out x) || !int.TryParse(s.Substring(ci + 1), out y)) continue;
                a.Add(x); b.Add(y);
            }
            if (a.Count < 3) return false;
            first = a.ToArray(); second = b.ToArray();
            return true;
        }

        // Flat int series that KEEPS zeros — same rule as ParsePairSeries, no
        // pair split and no prepended origin (a DPS sample IS an interval, so
        // the caller's first entry is already the first one). Dropping a 0 here
        // would not just lose a point, it would slide every later sample one
        // interval earlier on the shared time axis.
        private static int[] ParseIntSeriesKeepZeros(string csv)
        {
            if (string.IsNullOrEmpty(csv)) return null;
            var parts = csv.Split(',');
            var vals = new List<int>(parts.Length);
            foreach (var s in parts) { int v; if (int.TryParse(s, out v)) vals.Add(v); }
            return vals.Count >= 2 ? vals.ToArray() : null;
        }

        // July 22 item 1: vertical marker per point scored, colored by scorer
        // (green = the viewer, red = opponent side). Times come from point_times
        // (seconds since start); who-scored is derived by diffing the
        // viewer-relative point_timeline pairs. Drawn UNDER the series lines.
        private static float DrawPointMarkers(Rect plot, float maxT, string pointTimes, string pointTimeline, bool drawNow)
        {
            if (string.IsNullOrEmpty(pointTimes) || string.IsNullOrEmpty(pointTimeline)) return 0f;
            var tParts = pointTimes.Split(',');
            var sParts = pointTimeline.Split(',');
            int n = Mathf.Min(tParts.Length, sParts.Length);
            float lastT = 0f;
            int prevMine = 0, prevTheirs = 0;
            for (int i = 0; i < n; i++)
            {
                int t;
                if (!int.TryParse(tParts[i], out t)) continue;
                if (t > lastT) lastT = t;
                if (!drawNow) { }
                int ci = sParts[i].IndexOf(':');
                if (ci <= 0) continue;
                int mv, tv;
                if (!int.TryParse(sParts[i].Substring(0, ci), out mv) || !int.TryParse(sParts[i].Substring(ci + 1), out tv)) continue;
                bool mineScored = mv > prevMine;
                bool theirsScored = tv > prevTheirs;
                prevMine = mv; prevTheirs = tv;
                if (drawNow && maxT > 0f)
                {
                    float x = plot.xMin + plot.width * Mathf.Clamp01(t / maxT);
                    // Both changed in one poll tick (rare) → draw both, offset 2px.
                    if (mineScored)
                        GuiLine(new Vector2(x, plot.yMin), new Vector2(x, plot.yMax), new Color(0.30f, 0.85f, 0.30f, 0.35f), 2f);
                    if (theirsScored)
                        GuiLine(new Vector2(x + (mineScored ? 2f : 0f), plot.yMin), new Vector2(x + (mineScored ? 2f : 0f), plot.yMax), new Color(0.90f, 0.30f, 0.30f, 0.35f), 2f);
                }
            }
            return lastT;
        }

        private static void DrawFpsHoverGraph()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            // Gate = the set of tabs that REGISTER into _fpsGraphRegions: My
            // Stats (0), 2v2 (8) and the FFA tab (12 — per-player Hit/Block/
            // FPS/ping cells). Safe because SwitchTab clears every region list
            // on tab change, so allowing a tab here can't resurrect stale
            // regions from another tab's last render.
            if (!NativeUI.IsOpen || (NativeUI.CurrentTab != 0 && NativeUI.CurrentTab != 8 && NativeUI.CurrentTab != 12)) return;
            if (_fpsGraphRegions.Count == 0) return;
            Vector2 mp = Input.mousePosition;
            FpsGraphRegion? hit = null;
            for (int i = _fpsGraphRegions.Count - 1; i >= 0; i--)
            {
                var reg = _fpsGraphRegions[i];
                float liveFrac = LiveWidthFrac(reg.sourceTxt, reg.sourceRT, reg.widthFrac);
                Rect rr = LiveRegionRect(reg.sourceRT, reg.sourceCam, liveFrac, reg.clipRT, reg.screenRect, reg.outerClipRT);
                if (rr.Contains(mp)) { hit = reg; break; }
            }
            if (hit == null) return;

            if (_scoreGraphLbl == null)
                _scoreGraphLbl = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 12, richText = true, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft,
                    clipping = TextClipping.Overflow, wordWrap = false,
                };

            int kind = hit.Value.kind;
            if (kind == 4) { DrawPlayerComboGraph(hit.Value, mp); return; }
            // Only 2/3 are the pair chart — 5 (dps) is a flat series and falls
            // through to this popup, so the old `kind >= 2` catch-all would have
            // sent it to the wrong renderer.
            if (kind == 2 || kind == 3) { DrawPairHoverGraph(hit.Value, mp); return; }

            bool isPing = kind == 1;
            bool isDps = kind == 5;
            float myStep = hit.Value.myStep;
            // DPS keeps its zeros (see ParseIntSeriesKeepZeros); fps/ping drop
            // theirs, where a 0 means "no sample", not "zero frames".
            var mine = isDps ? ParseIntSeriesKeepZeros(hit.Value.mySeries) : ParseFpsSeries(hit.Value.mySeries);
            var opp = isDps ? ParseIntSeriesKeepZeros(hit.Value.oppSeries) : ParseFpsSeries(hit.Value.oppSeries);
            if (mine == null && opp == null) return;
            // Both DPS lines share the emitter cadence; fps/ping opponent
            // samples are always the 3s heartbeat.
            float oppStep = isDps ? myStep : 3f;

            // One big chart per hover (July 22): the whole popup is the plot, so
            // a 600-vs-30 FPS gap or a big latency spike still reads clearly.
            float w = 360f, h = 230f, pad = 44f;
            float gx = Mathf.Min(mp.x + 18f, Screen.width - w - 8f);
            float gy = Mathf.Clamp(Screen.height - mp.y - h / 2f, 8f, Screen.height - h - 8f);
            GUI.DrawTexture(new Rect(gx - 4, gy - 4, w + 8, h + 8), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, new Color(0f, 0f, 0f, 0.93f), 0, 0);
            // F13: FFA regions carry a subject label — a single participant's
            // series, so the you-vs-opponent phrasing (and its legend) would
            // misattribute the line. Name the player instead and drop the
            // opponent legend. Tabs 0/8 never set the label → byte-identical.
            // Aug 3: the UNLABELED branch (tabs 0/8) is now two whole templates
            // too. It used to interpolate a `title` local into the sentence, so
            // the finished string could never match a catalogue key — and the
            // you/vs/opponent legend has to travel WITH the sentence to be
            // translatable as one unit.
            // Aug 7: the metric name is baked INTO each sentence, so a new kind
            // needs its own pair of whole templates — there is no hole a caller
            // could fill to stop the fps one saying FPS.
            string header = !string.IsNullOrEmpty(hit.Value.subjectLabel)
                ? (isDps
                    ? I18n.TrF("<color=#CCCCCC>Damage per second over the match</color>  <color=#99B3E6>{0}</color>", hit.Value.subjectLabel)
                    : isPing
                    ? I18n.TrF("<color=#CCCCCC>Latency (ms) over the match</color>  <color=#99B3E6>{0}</color>", hit.Value.subjectLabel)
                    : I18n.TrF("<color=#CCCCCC>FPS over the match</color>  <color=#99B3E6>{0}</color>", hit.Value.subjectLabel))
                : (isDps
                    ? I18n.Tr("<color=#CCCCCC>Damage per second over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>")
                    : isPing
                    ? I18n.Tr("<color=#CCCCCC>Latency (ms) over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>")
                    : I18n.Tr("<color=#CCCCCC>FPS over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>"));
            GUI.Label(new Rect(gx + 8, gy + 2, w - 16, 24),
                header,
                _scoreGraphLbl);

            float maxT = 1f;
            if (mine != null) maxT = Mathf.Max(maxT, (mine.Length - 1) * myStep);
            if (opp != null) maxT = Mathf.Max(maxT, (opp.Length - 1) * oppStep);
            // Marker times can outrun the series (samples cap earlier) — include
            // them in the axis so late points still land inside the plot.
            Rect plotProbe = default(Rect);
            float lastMarkT = DrawPointMarkers(plotProbe, 0f, hit.Value.pointTimes, hit.Value.pointTimeline, false);
            if (lastMarkT > maxT) maxT = lastMarkT;

            // Auto-scaled Y so a huge FPS ceiling or a latency spike both fit,
            // with a small headroom margin so the peak isn't glued to the top.
            // DPS seeds low (a quiet match genuinely peaks in single digits) and
            // auto-scales up from there like the other two.
            int maxV = isDps ? 10 : isPing ? 60 : 90;
            if (mine != null) foreach (var v in mine) if (v > maxV) maxV = v;
            if (opp != null) foreach (var v in opp) if (v > maxV) maxV = v;
            maxV = Mathf.CeilToInt(maxV * 1.08f);

            Rect plot = new Rect(gx + pad, gy + 34f, w - pad - 12f, h - 34f - 14f);

            // Adaptive gridlines: a "nice" step that yields ~4-6 lines across the
            // current range — so a 30-FPS chart and a 600-FPS chart both read.
            // DPS borrows the pair chart's finer ladder: its range often ends at
            // ~11, where the fps ladder's 10 floor draws exactly one line.
            int[] steps = isDps
                ? new[] { 1, 2, 5, 10, 20, 25, 50, 100, 150, 200, 300, 500, 1000 }
                : new[] { 10, 20, 25, 30, 50, 60, 100, 120, 150, 200, 250, 300, 500, 600, 1000 };
            int gstep = steps[steps.Length - 1];
            foreach (int s in steps) { if (maxV / s <= 6) { gstep = s; break; } }
            for (int gl = gstep; gl <= maxV; gl += gstep)
            {
                float y = plot.yMax - plot.height * gl / maxV;
                GuiLine(new Vector2(plot.xMin, y), new Vector2(plot.xMax, y), new Color(1f, 1f, 1f, 0.08f), 1f);
                GUI.Label(new Rect(gx + 2, y - 11f, pad - 6f, 22f), $"<color=#777>{gl}</color>", _scoreGraphLbl);
            }

            // Point-scored markers (July 22 item 1) — under the series lines.
            DrawPointMarkers(plot, maxT, hit.Value.pointTimes, hit.Value.pointTimeline, true);

            System.Action<int[], float, Color> drawSeries = (vals, step, col) =>
            {
                if (vals == null) return;
                for (int i = 1; i < vals.Length; i++)
                {
                    float x0 = plot.xMin + plot.width * ((i - 1) * step / maxT);
                    float x1 = plot.xMin + plot.width * (i * step / maxT);
                    float y0 = plot.yMax - plot.height * Mathf.Min(vals[i - 1], maxV) / maxV;
                    float y1 = plot.yMax - plot.height * Mathf.Min(vals[i], maxV) / maxV;
                    GuiLine(new Vector2(x0, y0), new Vector2(x1, y1), col, 2f);
                }
            };
            drawSeries(opp, oppStep, new Color(0.90f, 0.60f, 0.53f, 0.95f));
            drawSeries(mine, myStep, new Color(0.60f, 0.70f, 0.90f, 0.95f));
        }

        // July 22 item 1: single-player cumulative pair chart.
        // kind 2 (Hit%): shots fired (dim) vs shots hit (bright), one Y scale.
        // kind 3 (Block%): damage taken (left scale, dim) vs successful blocks
        // (right scale, bright) — dual axes because damage is ~100x block counts.
        private static void DrawPairHoverGraph(FpsGraphRegion reg, Vector2 mp)
        {
            int[] a, b;
            if (!ParsePairSeries(reg.mySeries, out a, out b)) return;
            bool isBlock = reg.kind == 3;
            bool oppSubject = reg.subjectIsOpp;
            Color bright = oppSubject ? new Color(0.95f, 0.55f, 0.45f, 0.95f) : new Color(0.55f, 0.75f, 0.98f, 0.95f);
            Color dim = oppSubject ? new Color(0.70f, 0.42f, 0.38f, 0.80f) : new Color(0.42f, 0.52f, 0.70f, 0.80f);
            string brightHex = oppSubject ? "#F28C73" : "#8CBFFA";
            string dimHex = oppSubject ? "#B36B61" : "#6B85B3";

            if (_scoreGraphLbl == null)
                _scoreGraphLbl = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 12, richText = true, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft,
                    clipping = TextClipping.Overflow, wordWrap = false,
                };

            float w = 360f, h = 230f, pad = 44f, padR = isBlock ? 34f : 12f;
            float gx = Mathf.Min(mp.x + 18f, Screen.width - w - 8f);
            float gy = Mathf.Clamp(Screen.height - mp.y - h / 2f, 8f, Screen.height - h - 8f);
            GUI.DrawTexture(new Rect(gx - 4, gy - 4, w + 8, h + 8), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, new Color(0f, 0f, 0f, 0.93f), 0, 0);
            // F13: FFA rows register per-participant series with a subject
            // label — the title names that player instead of the you/opponent
            // phrasing. The hex holes ({1}-{3}) keep palette correctness for
            // either subject side; tabs 0/8 never set the label → they take
            // the unlabeled branches below.
            bool hasSubject = !string.IsNullOrEmpty(reg.subjectLabel);
            string subjHex = oppSubject ? "#E69988" : "#99B3E6";
            string title;
            if (hasSubject)
                title = isBlock
                    ? I18n.TrF("<color=#CCCCCC>Block — <color={1}>{0}</color></color>  <color={2}>dmg taken</color> <color=#888>·</color> <color={3}>blocks</color>", reg.subjectLabel, subjHex, dimHex, brightHex)
                    : I18n.TrF("<color=#CCCCCC>Hit — <color={1}>{0}</color></color>  <color={2}>shots fired</color> <color=#888>·</color> <color={3}>hits</color>", reg.subjectLabel, subjHex, dimHex, brightHex);
            // Aug 3: the unlabeled (tabs 0/8) branch is four whole templates —
            // one per subject side — instead of one interpolating a pre-built
            // `who` fragment. The subject WORD has to sit inside the sentence
            // to be translatable at all (a bare "you"/"opponent" key is
            // unusable in languages that inflect it), and the two palette
            // hexes stay holes so a palette tweak can't retire the key.
            else if (oppSubject)
                title = isBlock
                    ? I18n.TrF("<color=#CCCCCC>Block — <color=#E69988>opponent</color></color>  <color={0}>dmg taken</color> <color=#888>·</color> <color={1}>blocks</color>", dimHex, brightHex)
                    : I18n.TrF("<color=#CCCCCC>Hit — <color=#E69988>opponent</color></color>  <color={0}>shots fired</color> <color=#888>·</color> <color={1}>hits</color>", dimHex, brightHex);
            else
                title = isBlock
                    ? I18n.TrF("<color=#CCCCCC>Block — <color=#99B3E6>you</color></color>  <color={0}>dmg taken</color> <color=#888>·</color> <color={1}>blocks</color>", dimHex, brightHex)
                    : I18n.TrF("<color=#CCCCCC>Hit — <color=#99B3E6>you</color></color>  <color={0}>shots fired</color> <color=#888>·</color> <color={1}>hits</color>", dimHex, brightHex);
            GUI.Label(new Rect(gx + 8, gy + 2, w - 16, 24), title, _scoreGraphLbl);

            int n = a.Length;
            float maxT = Mathf.Max(1f, (n - 1) * 3f);
            float lastMarkT = DrawPointMarkers(default(Rect), 0f, reg.pointTimes, reg.pointTimeline, false);
            if (lastMarkT > maxT) maxT = lastMarkT;

            int maxA = 1, maxB = 1;
            foreach (var v in a) if (v > maxA) maxA = v;
            foreach (var v in b) if (v > maxB) maxB = v;
            maxA = Mathf.CeilToInt(maxA * 1.08f);
            // Hit chart shares one scale (hits <= fired structurally); block
            // chart scales each line to its own max.
            int maxBAxis = isBlock ? Mathf.CeilToInt(maxB * 1.08f) : maxA;
            if (maxBAxis < 1) maxBAxis = 1;

            Rect plot = new Rect(gx + pad, gy + 34f, w - pad - padR, h - 34f - 26f);

            // Left-axis gridlines from the A series (fired / damage).
            int[] steps = { 1, 2, 5, 10, 20, 25, 50, 100, 150, 200, 300, 500, 1000, 2000 };
            int gstep = steps[steps.Length - 1];
            foreach (int s in steps) { if (maxA / s <= 6) { gstep = s; break; } }
            for (int gl = gstep; gl <= maxA; gl += gstep)
            {
                float y = plot.yMax - plot.height * gl / maxA;
                GuiLine(new Vector2(plot.xMin, y), new Vector2(plot.xMax, y), new Color(1f, 1f, 1f, 0.08f), 1f);
                GUI.Label(new Rect(gx + 2, y - 11f, pad - 6f, 22f), $"<color=#777>{gl}</color>", _scoreGraphLbl);
            }
            if (isBlock)
            {
                // Right-axis reference for the blocks line — label the AXIS
                // ceiling (maxBAxis, what the line is actually scaled to),
                // not the raw series max (review [9]).
                GUI.Label(new Rect(plot.xMax + 4f, plot.yMin - 11f, padR - 4f, 22f),
                    $"<color={brightHex}>{maxBAxis}</color>", _scoreGraphLbl);
                GUI.Label(new Rect(plot.xMax + 4f, plot.yMax - 11f, padR - 4f, 22f),
                    $"<color={brightHex}>0</color>", _scoreGraphLbl);
            }

            DrawPointMarkers(plot, maxT, reg.pointTimes, reg.pointTimeline, true);

            System.Action<int[], int, Color> drawSeries = (vals, maxV, col) =>
            {
                for (int i = 1; i < vals.Length; i++)
                {
                    float x0 = plot.xMin + plot.width * ((i - 1) * 3f / maxT);
                    float x1 = plot.xMin + plot.width * (i * 3f / maxT);
                    float y0 = plot.yMax - plot.height * Mathf.Min(vals[i - 1], maxV) / (float)maxV;
                    float y1 = plot.yMax - plot.height * Mathf.Min(vals[i], maxV) / (float)maxV;
                    GuiLine(new Vector2(x0, y0), new Vector2(x1, y1), col, 2f);
                }
            };
            drawSeries(a, maxA, dim);
            drawSeries(b, maxBAxis, bright);

            // Footer: final tallies + the resulting percentage. Aug 3: the two
            // branches produced BYTE-IDENTICAL English, so the subject-labeled
            // (FFA) split is gone and both paths share the existing key — no
            // new key, and the tabs-0/8 path picks up the FFA translation for
            // free. Side effect worth naming: {2:F0} now formats under
            // InvariantCulture (TrF), where the old interpolated branch used
            // the current culture — a comma decimal separator on an es/ru OS.
            string footer;
            if (isBlock)
                footer = I18n.TrF("<color=#777>{0} dmg taken · {1} successful blocks · markers = points scored</color>", a[n - 1], b[n - 1]);
            else
            {
                float pct = a[n - 1] > 0 ? 100f * b[n - 1] / a[n - 1] : 0f;
                footer = I18n.TrF("<color=#777>{0} fired · {1} hit · {2:F0}% · markers = points scored</color>", a[n - 1], b[n - 1], pct);
            }
            GUI.Label(new Rect(gx + 8, gy + h - 22f, w - 16, 22f), footer, _scoreGraphLbl);
        }

        // July 22 item 7: 2v2 per-player combo popup — 2x2 mini panels
        // (FPS / Ping / shots fired-vs-hit / dmg-vs-blocks) for one player.
        private static void DrawPlayerComboGraph(FpsGraphRegion reg, Vector2 mp)
        {
            var fps = ParseFpsSeries(reg.mySeries);
            var ping = ParseFpsSeries(reg.oppSeries);
            int[] hA = null, hB = null, bA = null, bB = null;
            ParsePairSeries(reg.pairHit, out hA, out hB);
            ParsePairSeries(reg.pairBlock, out bA, out bB);
            if (fps == null && ping == null && hA == null && bA == null) return;

            bool right = reg.subjectIsOpp;
            Color bright = right ? new Color(1.00f, 0.69f, 0.53f, 0.95f) : new Color(0.55f, 0.80f, 1.00f, 0.95f);
            Color dim = right ? new Color(0.72f, 0.50f, 0.40f, 0.85f) : new Color(0.42f, 0.58f, 0.72f, 0.85f);
            string nameHex = right ? "#FFB086" : "#8CCFFF";

            if (_scoreGraphLbl == null)
                _scoreGraphLbl = new GUIStyle(GUI.skin.label)
                {
                    fontSize = 12, richText = true, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft,
                    clipping = TextClipping.Overflow, wordWrap = false,
                };

            float w = 430f, h = 306f;
            float gx = Mathf.Min(mp.x + 18f, Screen.width - w - 8f);
            float gy = Mathf.Clamp(Screen.height - mp.y - h / 2f, 8f, Screen.height - h - 8f);
            GUI.DrawTexture(new Rect(gx - 4, gy - 4, w + 8, h + 8), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, new Color(0f, 0f, 0f, 0.93f), 0, 0);
            GUI.Label(new Rect(gx + 8, gy + 2, w - 16, 22),
                I18n.TrF("<color={1}>{0}</color> <color=#888>— match telemetry</color>",
                         reg.subjectLabel, nameHex), _scoreGraphLbl);

            // Panel grid: 2 x 2, each panel has its own auto Y scale.
            float pw = (w - 30f) / 2f, ph = (h - 40f) / 2f;
            System.Action<Rect, string, int[], int[], Color, Color, string> panel =
                (r, title, s1, s2, c1, c2, foot) =>
            {
                GUI.Label(new Rect(r.x, r.y - 4f, r.width, 18f), title, _scoreGraphLbl);
                Rect plot = new Rect(r.x + 26f, r.y + 16f, r.width - 30f, r.height - 40f);
                int maxV = 1;
                if (s1 != null) foreach (var v in s1) if (v > maxV) maxV = v;
                if (s2 != null) foreach (var v in s2) if (v > maxV) maxV = v;
                maxV = Mathf.CeilToInt(maxV * 1.08f);
                GuiLine(new Vector2(plot.xMin, plot.yMax), new Vector2(plot.xMax, plot.yMax), new Color(1f, 1f, 1f, 0.15f), 1f);
                GuiLine(new Vector2(plot.xMin, plot.yMin), new Vector2(plot.xMax, plot.yMin), new Color(1f, 1f, 1f, 0.06f), 1f);
                GUI.Label(new Rect(r.x - 2f, plot.yMin - 10f, 30f, 20f), $"<color=#777>{maxV}</color>", _scoreGraphLbl);
                int nMax = Mathf.Max(s1 != null ? s1.Length : 0, s2 != null ? s2.Length : 0);
                if (nMax < 2) return;
                System.Action<int[], Color> line = (vals, col) =>
                {
                    if (vals == null || vals.Length < 2) return;
                    for (int i = 1; i < vals.Length; i++)
                    {
                        float x0 = plot.xMin + plot.width * (i - 1) / (nMax - 1);
                        float x1 = plot.xMin + plot.width * i / (nMax - 1);
                        float y0 = plot.yMax - plot.height * Mathf.Min(vals[i - 1], maxV) / (float)maxV;
                        float y1 = plot.yMax - plot.height * Mathf.Min(vals[i], maxV) / (float)maxV;
                        GuiLine(new Vector2(x0, y0), new Vector2(x1, y1), col, 2f);
                    }
                };
                line(s1, c1);
                line(s2, c2);
                if (!string.IsNullOrEmpty(foot))
                    GUI.Label(new Rect(r.x + 4f, r.yMax - 18f, r.width - 8f, 18f), foot, _scoreGraphLbl);
            };

            string hitFoot = hA != null && hA.Length > 1
                ? I18n.TrF("<color=#777>{0} fired / {1} hit ({2:F0}%)</color>",
                           hA[hA.Length - 1], hB[hB.Length - 1],
                           hA[hA.Length - 1] > 0 ? 100f * hB[hB.Length - 1] / hA[hA.Length - 1] : 0f) : "";
            string blkFoot = bA != null && bA.Length > 1
                ? I18n.TrF("<color=#777>{0} dmg / {1} blocks</color>",
                           bA[bA.Length - 1], bB[bB.Length - 1]) : "";
            // Blocks are ~100x smaller than damage — rescale the blocks line to
            // the damage axis so the mini panel shows both trends (real numbers
            // live in the footer; the full-size 1v1 popup uses true dual axes).
            int[] bBScaled = null;
            if (bA != null && bB != null)
            {
                int maxDmg = 1, maxBlk = 1;
                foreach (var v in bA) if (v > maxDmg) maxDmg = v;
                foreach (var v in bB) if (v > maxBlk) maxBlk = v;
                bBScaled = new int[bB.Length];
                for (int i = 0; i < bB.Length; i++) bBScaled[i] = (int)((long)bB[i] * maxDmg / maxBlk);
            }
            panel(new Rect(gx + 10f, gy + 40f, pw, ph), I18n.Tr("<color=#CCC>FPS</color>"), fps, null, bright, bright, "");
            panel(new Rect(gx + 20f + pw, gy + 40f, pw, ph), I18n.Tr("<color=#CCC>Ping (ms)</color>"), ping, null, bright, bright, "");
            panel(new Rect(gx + 10f, gy + 44f + ph, pw, ph), I18n.Tr("<color=#CCC>Shots fired vs hits</color>"), hA, hB, dim, bright, hitFoot);
            panel(new Rect(gx + 20f + pw, gy + 44f + ph, pw, ph), I18n.Tr("<color=#CCC>Dmg taken vs blocks</color>"), bA, bBScaled, dim, bright, blkFoot);
        }
        public static void RegisterCardHoverRegion(Rect screenRect, string fullCardLine, bool isOpponent)
            => RegisterCardHoverRegion(screenRect, fullCardLine, isOpponent, null, null, null, null, -1f, null);
        public static void RegisterCardHoverRegion(Rect screenRect, string fullCardLine, bool isOpponent,
                                                   string titleOverride, string bodyOverride)
            => RegisterCardHoverRegion(screenRect, fullCardLine, isOpponent, titleOverride, bodyOverride, null, null, -1f, null);
        public static void RegisterCardHoverRegion(Rect screenRect, string fullCardLine, bool isOpponent,
                                                   string titleOverride, string bodyOverride,
                                                   RectTransform sourceRT, Camera sourceCam, float widthFrac,
                                                   RectTransform clipRT, object sourceTxt = null)
        {
            // Need SOMETHING to show — either a legacy comma line or an explicit body.
            if (string.IsNullOrEmpty(fullCardLine) && string.IsNullOrEmpty(bodyOverride)) return;
            _cardHoverRegions.Add(new CardHoverRegion {
                screenRect = screenRect, fullCardLine = fullCardLine, isOpponent = isOpponent,
                titleOverride = titleOverride, bodyOverride = bodyOverride,
                sourceRT = sourceRT, sourceCam = sourceCam, widthFrac = widthFrac, clipRT = clipRT,
                sourceTxt = sourceTxt,
            });
        }

        private static GUIStyle _cardTipTitleStyle, _cardTipBodyStyle;
        // Comma-split tooltip body memo: rebuilt only when the hovered row's
        // raw card line (or the translation state) changes, not per Repaint —
        // the CardTextLocalizer.DisplayName lookups ride this cache so card
        // localization adds zero steady-state per-frame work (#162).
        //
        // Aug-3 review F10 sweep: this is the file's other memo holding
        // translated text behind a locale-only key. Unlike the chat header it
        // is NOT reachable today — the body resolves through ROUNDS' own
        // localization table (CardTextLocalizer), and the only I18n input is
        // PrettyCase's IsEnglish check, which the locale key already covers. So
        // the generation is carried defensively: it costs one int compare, and
        // it means the memo cannot silently rot the day a card display name
        // starts routing through the catalogue.
        private static string _cardTipCacheKey, _cardTipCacheBody, _cardTipCacheLocale;
        private static int _cardTipCacheLines;
        private static int _cardTipCacheGen = -1;
        private static void DrawCardHoverTooltip()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
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
                var reg = _cardHoverRegions[i];
                // Bug #61: live rect so scrolling can't desync region from row.
                // Bug #72: live width fraction too (frozen frac was ~0 on first render).
                float liveFrac = LiveWidthFrac(reg.sourceTxt, reg.sourceRT, reg.widthFrac);
                Rect rr = LiveRegionRect(reg.sourceRT, reg.sourceCam, liveFrac, reg.clipRT, reg.screenRect);
                if (rr.Contains(mp))
                {
                    hit = reg;
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
                int tipGen = I18n.CatalogueGeneration;
                if (!string.Equals(raw, _cardTipCacheKey, StringComparison.Ordinal)
                    || _cardTipCacheLocale != I18n.Locale
                    || _cardTipCacheGen != tipGen)
                {
                    string[] cards;
                    try { cards = raw.Split(','); }
                    catch { cards = new[] { raw }; }
                    int lines = 0;
                    var sb = new System.Text.StringBuilder();
                    foreach (var c in cards)
                    {
                        string name = c.Trim();
                        if (string.IsNullOrEmpty(name)) continue;
                        lines++;
                        // The server comma-list carries the frozen English
                        // card names (identity — never changed on any data
                        // path); display resolves through the game's own
                        // card localization, falling back to the English
                        // name when the game has none.
                        string disp = null;
                        try { disp = CardTextLocalizer.PrettyName(name, name); } catch { }
                        sb.Append("• ").Append(disp ?? name).Append('\n');
                    }
                    _cardTipCacheKey = raw;
                    _cardTipCacheLocale = I18n.Locale;
                    _cardTipCacheGen = tipGen;
                    _cardTipCacheBody = sb.ToString().TrimEnd();
                    _cardTipCacheLines = lines;
                }
                body = _cardTipCacheBody;
                lineCount = _cardTipCacheLines;
            }

            // Title: default "Your/Opponent's picks", or an override ("" = no header).
            string title = hit.Value.titleOverride != null
                         ? hit.Value.titleOverride
                         : (hit.Value.isOpponent ? I18n.Tr("Opponent's picks") : I18n.Tr("Your picks"));
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
                      I18n.Tr("<color=#FFD080>Match-found screen might be stuck</color>"),
                      stuckTitleStyle);
            GUI.Label(new Rect(x + 14, y + 32, w - 28, 50),
                      I18n.TrF("<color=#CCCCCC>In this Photon room for <b>{0}s</b> with no match started. Vanilla matchmaking sometimes hangs here when one player has ROUNDS unfocused. Click into the ROUNDS window first and try space again, or use the escape hatch below.</color>", secs),
                      stuckTextStyle);

            if (GUI.Button(new Rect(x + 14, y + h - 38, 220, 28), I18n.Tr("Force exit room"), stuckButtonStyle))
            {
                try { Photon.Pun.PhotonNetwork.LeaveRoom(); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[STUCK] LeaveRoom failed: {ex.Message}"); }
                GameStateWatcher.DismissMatchFoundStuckOverlay();
            }
            if (GUI.Button(new Rect(x + w - 174, y + h - 38, 160, 28), I18n.Tr("Dismiss (1 min)"), stuckButtonStyle))
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
        // richText = FALSE: an attached game log contains real rich-text tags
        // and tag-shaped stack frames, so it must be drawn verbatim (#115).
        private static GUIStyle bugAdminLogStyle;
        // Measured chunk layout, recomputed only when the selected report, its
        // log, or the pane width changes.
        private static List<string> bugAdminLogChunks;
        private static List<float> bugAdminLogHeights;
        private static float bugAdminLogTotalH, bugAdminMetaH, bugAdminLayoutW = -1f;
        private static string bugAdminLayoutKey = null;

        private static void EnsureBugLogLayout(string reportId, string meta, string log, float width)
        {
            string key = (reportId ?? "") + "|" + (meta == null ? 0 : meta.Length)
                         + "|" + (log == null ? 0 : log.Length);
            if (key == bugAdminLayoutKey && Mathf.Approximately(width, bugAdminLayoutW)) return;
            bugAdminLayoutKey = key;
            bugAdminLayoutW = width;
            bugAdminLogChunks = new List<string>();
            bugAdminLogHeights = new List<float>();
            bugAdminLogTotalH = 0f;
            try
            {
                bugAdminMetaH = bugAdminDetailStyle.CalcHeight(new GUIContent(meta ?? ""), width) + 8f;
                if (!string.IsNullOrEmpty(log))
                {
                    const int LOG_CHUNK = 12_000;
                    for (int start = 0; start < log.Length; start += LOG_CHUNK)
                    {
                        string piece = log.Substring(start, Math.Min(LOG_CHUNK, log.Length - start));
                        float h = bugAdminLogStyle.CalcHeight(new GUIContent(piece), width);
                        bugAdminLogChunks.Add(piece);
                        bugAdminLogHeights.Add(h);
                        bugAdminLogTotalH += h;
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[BUG-ADMIN] log layout: {ex.Message}");
                bugAdminMetaH = 400f;
            }
        }
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
                bugAdminLogStyle = new GUIStyle(GUI.skin.label) { fontSize = 12, richText = false, wordWrap = true, alignment = TextAnchor.UpperLeft };
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

            // #115 companion: bugTitleStyle is created by EnsureBugStyles(),
            // whose only other caller is the SUBMIT modal — so opening this
            // viewer without having filed a report first left it null and the
            // fallback GUI.skin.label (richText defaults to FALSE) rendered the
            // title as the literal text "<b>Bug Reports</b>".
            try { EnsureBugStyles(); } catch { }
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
            // Bug #115: the attached log is drawn SEPARATELY, below, in a
            // richText=FALSE style — it is never concatenated into this
            // rich-text label. Two independent reasons:
            //  1. A raw game log is hostile input for rich text. It is full of
            //     real tags (our own nametag publishes emit <b><i><color=...>)
            //     and tag-shaped stack frames (<4ed2dee7...>), so rendering it
            //     as rich text mangles the log even when it "works" — and
            //     concatenating ~400k characters of it into one GUI.Label is
            //     what made the whole pane render its tags verbatim.
            //  2. It keeps this label a few hundred characters, which is the
            //     only structural difference between this pane and the report
            //     LIST pane that has always rendered its colours correctly.
            string logBody = null;
            string logHeader = null;
            if (!string.IsNullOrEmpty(d.log_text))
            {
                int fullLen = d.log_text.Length;
                const int DISPLAY_CAP = 200_000;
                logBody = d.log_text;
                string truncNote = "";
                if (logBody.Length > DISPLAY_CAP)
                {
                    logBody = "[... earlier content trimmed for display - see ssh bug-log:" + d.bug_number + " for full ...]\n"
                              + logBody.Substring(logBody.Length - DISPLAY_CAP);
                    truncNote = $" — <color=#FFCC66>showing last {DISPLAY_CAP:N0} of {fullLen:N0} chars</color>";
                }
                sbDet.AppendLine();
                logHeader = $"<b><color=#88CCFF>Attached log ({d.log_bytes:N0} bytes gzipped on disk, {fullLen:N0} chars decoded){truncNote}:</color></b>";
                sbDet.AppendLine(logHeader);
            }

            string body = sbDet.ToString();
            float scrollTop = actY + 48;
            float commentRowH = 96;      // reserved at bottom for comment input
            float scrollH = bodyH - (scrollTop - bodyY) - commentRowH - 8;
            float bw = detailW - 24;
            float labelW = bw - 12;
            // The log is split across several labels of LOG_CHUNK characters
            // each so no single IMGUI label ever carries a mesh-breaking string
            // (the previous single 400k-char label is what broke this pane).
            //
            // Heights are MEASURED, not estimated. A chars-per-line guess is
            // wrong by 2-3x on real attachments — sampled bug logs average
            // 39-81 characters per line, not the ~90 an eyeballed constant
            // assumes — and an undersized rect makes each chunk overpaint the
            // one below it. CalcHeight is exact and also accounts for wrapping;
            // it is cached per report because it is far too expensive to run
            // over ~200k characters on every IMGUI event (#162).
            EnsureBugLogLayout(d.id, body, logBody, labelW);
            float metaH = bugAdminMetaH;
            float bh = Mathf.Max(scrollH, bugAdminLogTotalH + metaH + 40f);
            bugAdminDetailScroll = GUI.BeginScrollView(new Rect(detailX + 8, scrollTop, detailW - 12, scrollH),
                                                        bugAdminDetailScroll,
                                                        new Rect(0, 0, labelW, bh));
            GUI.Label(new Rect(4, 4, labelW, metaH), body, bugAdminDetailStyle);
            if (bugAdminLogChunks != null)
            {
                float ly = 4 + metaH;
                for (int ci = 0; ci < bugAdminLogChunks.Count; ci++)
                {
                    GUI.Label(new Rect(4, ly, labelW, bugAdminLogHeights[ci]),
                              bugAdminLogChunks[ci], bugAdminLogStyle);
                    ly += bugAdminLogHeights[ci];
                }
            }
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
                // Date half via DateFmt (locale-aware day/month ORDER, numeric
                // only — #47: no localized month names through the SDF font);
                // time half stays invariant HH:mm.
                return DateFmt.Short(dt) + " " + dt.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture);
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
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
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
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
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

        // Item 7: lines were drawn into a fixed 20px rect, which clipped
        // descenders on the bottom row and silently cut wrapped messages after
        // the first visual line. Each entry now gets its measured wrapped
        // height, capped at CHAT_MAX_WRAP_LINES with an explicit indicator.
        private const int CHAT_MAX_WRAP_LINES = 3;
        private const string CHAT_CUT_SUFFIX = " ... [see F5]";
        private struct ChatLineLayout { public string Disp; public float H; }
        private static readonly Dictionary<string, ChatLineLayout> chatLayoutCache =
            new Dictionary<string, ChatLineLayout>();
        private static readonly List<NativeUI.ChatEntry> _chatEntryScratch =
            new List<NativeUI.ChatEntry>(8);
        private static ChatLineLayout[] _chatLayoutScratch = new ChatLineLayout[8];
        private static float[] _chatAlphaScratch = new float[8];

        private static ChatLineLayout MeasureChatLine(string line, float w)
        {
            ChatLineLayout cached;
            if (chatLayoutCache.TryGetValue(line, out cached)) return cached;
            if (chatLayoutCache.Count > 256) chatLayoutCache.Clear();

            float maxH = ingameChatStyle.lineHeight * CHAT_MAX_WRAP_LINES + 4f;
            var layout = new ChatLineLayout { Disp = line };
            layout.H = ingameChatStyle.CalcHeight(new GUIContent(line), w);
            if (layout.H > maxH)
            {
                // Too tall even at 3 wrapped lines: trim until it fits with the
                // indicator appended. Never cut before the last rich-text tag
                // (name/title markup lives at the head; only the plain message
                // tail is trimmable — user-typed <> are converted to parens
                // upstream by NativeUI.Escape, so '>' only appears in our own
                // markup), and binary-search so the once-per-entry cost stays
                // trivial.
                int minCut = line.LastIndexOf('>') + 1;
                if (minCut < 1) minCut = 1;
                if (minCut >= line.Length - 1)
                {
                    // Nothing trimmable after the markup (markup-final line):
                    // keep the full measured height rather than appending a
                    // false truncation indicator to an uncut line.
                    chatLayoutCache[line] = layout;
                    return layout;
                }
                int lo = Math.Min(minCut + 1, line.Length), hi = line.Length, best = lo;
                while (lo <= hi)
                {
                    int mid = (lo + hi) / 2;
                    string candidate = line.Substring(0, mid).TrimEnd() + CHAT_CUT_SUFFIX;
                    if (ingameChatStyle.CalcHeight(new GUIContent(candidate), w) <= maxH)
                    { best = mid; lo = mid + 1; }
                    else hi = mid - 1;
                }
                layout.Disp = line.Substring(0, best).TrimEnd() + CHAT_CUT_SUFFIX;
                layout.H = ingameChatStyle.CalcHeight(new GUIContent(layout.Disp), w);
            }
            chatLayoutCache[line] = layout;
            return layout;
        }

        private static void DrawInGameChat()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            if (Plugin.ShowIngameChat != null && !Plugin.ShowIngameChat.Value) return;
            if (!Plugin.DataConsentGranted) return;
            /* Aug 7 item 3: the old `if (NativeUI.IsOpen) return;` assumed "the
             * F5 chat panel covers this" — true only on the Home tab. Now chat
             * stays visible on every OTHER menu tab, repositioned to the right
             * edge so it sits over dead chrome instead of the left-column
             * tables. Display-only IMGUI (no input path), so #141/#200 are
             * moot; IMGUI paints above the uGUI page, and DrawUI order keeps
             * every modal painting above THIS. */
            if (NativeUI.HomeChatPaneVisible) return;  // the Home tab chat pane covers this

            NativeUI.CopyChatTail(_chatEntryScratch, 8);
            var entries = _chatEntryScratch;
            if (entries.Count == 0) return;

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
            if (_chatAlphaScratch.Length < entries.Count)
                _chatAlphaScratch = new float[entries.Count];
            var alphas = _chatAlphaScratch;
            float maxAlpha = 0f;
            int visibleCount = 0;
            for (int i = 0; i < entries.Count; i++)
            {
                double age = (now - entries[i].AddedUtc).TotalSeconds;
                float a = age < 25 ? 1f : age < 35 ? 1f - (float)((age - 25) / 10.0) : 0f;
                alphas[i] = a;
                if (a > 0.02f) { visibleCount++; if (a > maxAlpha) maxAlpha = a; }
            }
            if (visibleCount == 0) return;

            // Anchor bottom-left always (Sid, Aug 8: the right-edge menu
            // placement was jarring — chat lives on the left everywhere except
            // the Home tab, where the dedicated pane shows instead).
            float w = 440, padding = 6, lineGap = 2;
            float x = 12;

            // Measure every visible line first so the backdrop matches the
            // true stacked height (wrapped lines are taller than one row).
            // Scratch buffer reused across frames — OnGUI runs multiple times
            // per rendered frame, so a fresh array here would be steady GC
            // pressure in the in-match hot path.
            if (_chatLayoutScratch.Length < entries.Count)
                _chatLayoutScratch = new ChatLineLayout[entries.Count];
            var layouts = _chatLayoutScratch;
            float totalH = 0f;
            for (int i = 0; i < entries.Count; i++)
            {
                if (alphas[i] <= 0.02f) continue;
                layouts[i] = MeasureChatLine(entries[i].Line, w);
                totalH += layouts[i].H + lineGap;
            }
            float panelH = totalH - lineGap + padding * 2;
            float yBottom = Screen.height - 90;   // above FPS/ping overlay, clear of HUD
            float yTop = yBottom - panelH;

            GUI.DrawTexture(new Rect(x - 4, yTop, w + 8, panelH),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0, 0, 0, 0.55f * maxAlpha), 0, 0);

            // Render newest-at-bottom. entries[last] is newest. The y cursor
            // walks upward by each line's own measured height, so every row —
            // including the bottom one — gets its full rect (no clipped
            // descenders).
            float yCursor = yBottom - padding;
            for (int i = entries.Count - 1; i >= 0; i--)
            {
                float a = alphas[i];
                if (a <= 0.02f) continue;
                var prev = GUI.contentColor;
                GUI.contentColor = new Color(1f, 1f, 1f, a);
                yCursor -= layouts[i].H;
                GUI.Label(new Rect(x, yCursor, w, layouts[i].H), layouts[i].Disp, ingameChatStyle);
                GUI.contentColor = prev;
                yCursor -= lineGap;
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
            "regicide", "stan_slayer", "pacifist", "immovable_object",
            "master_rank", "team_sweep", "grand_master",
            // v1.30 expansion (item 5, revised July 12)
            "flawless", "bullet_hell", "spray_and_pray", "demolitionist",
            "controlled_burst", "field_medic", "god_build", "double_nova",
            "lumberjack", "pristine_perfection", "silent_drill", "double_glass",
            "sustained_power", "deep_end", "clutch", "collector",
            "grounded", "instinct", "rising_star", "on_fire", "unstoppable",
            "immortal", "casual_century", "casual_conqueror", "touch_grass",
            "twins",   // July 21: was missing — admin grant couldn't select it
        };

        public static void OpenAdminPrompt(string mode)
        {
            adminPromptMode = mode ?? "";
            adminInputA = "";
            adminInputB = mode == "grant" ? ADMIN_ACHIEVEMENT_KEYS[0] : "";
            adminPromptOpen = true;
        }

        // Generic yes/no confirm modal, used by the admin recent-series resolve/reverse
        // buttons so a destructive ranked action can't be a single misclick.
        private static bool confirmOpen = false;
        private static string confirmMessage = "";
        private static Action confirmOnYes = null;

        public static void OpenConfirm(string message, Action onYes)
        {
            confirmMessage = message ?? "Are you sure?";
            confirmOnYes = onYes;
            confirmOpen = true;
        }

        private static void DrawConfirm()
        {
            if (!confirmOpen) return;
            if (!NativeUI.IsOpen) { confirmOpen = false; confirmOnYes = null; return; }
            var ev = Event.current;
            bool yes = false, no = false;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape) { no = true; ev.Use(); }
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };

            float w = 540, h = 170;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.94f), 0, 0);
            GUI.Label(new Rect(x + 12, y + 10, w - 24, 26), I18n.Tr("Confirm"),
                new GUIStyle(adminLabelStyle) { fontSize = 17, fontStyle = FontStyle.Bold });
            GUI.Label(new Rect(x + 12, y + 42, w - 24, 70), confirmMessage,
                new GUIStyle(adminLabelStyle) { fontSize = 14, wordWrap = true });
            if (GUI.Button(new Rect(x + 12, y + h - 40, 120, 30), I18n.Tr("Cancel"))) no = true;
            if (GUI.Button(new Rect(x + w - 132, y + h - 40, 120, 30), I18n.Tr("Confirm"))) yes = true;

            if (no) { confirmOpen = false; confirmOnYes = null; return; }
            if (yes)
            {
                var cb = confirmOnYes;
                confirmOpen = false; confirmOnYes = null;
                try { cb?.Invoke(); } catch (Exception ex) { Plugin.Log.LogWarning($"[ADMIN] confirm action: {ex.Message}"); }
            }
        }

        // ── Artist input modal (v1.30) ─────────────────────────
        // Generic one-field prompt used by the Artist tab (set price / set
        // stock / gift / block). Mirrors the admin prompt's IMGUI pattern:
        // Escape cancels, Submit invokes the callback with the field text.
        private static bool artistPromptOpen = false;
        private static string artistPromptTitle = "", artistPromptLabel = "", artistPromptValue = "";
        private static Action<string> artistPromptOnSubmit = null;

        public static void OpenArtistInput(string title, string label, string initial, Action<string> onSubmit)
        {
            artistPromptTitle = title ?? "Artist action";
            artistPromptLabel = label ?? "Value";
            artistPromptValue = initial ?? "";
            artistPromptOnSubmit = onSubmit;
            artistPromptOpen = true;
        }

        public static bool ArtistPromptOpen => artistPromptOpen || artistPickerOpen || playerSearchOpen
                                            || cosTestOpen || cosReviewOpen;

        // ── Artist picker modal (July 12 item 3; list form per bug batch item 5) ──
        // Lists the full artist roster so admins assign/revoke without typing steam
        // ids. Click a row to select, then confirm with the action button. onPick
        // receives the steam id ("" = clear/house item, assignment mode only).
        private static bool artistPickerOpen = false;
        private static string artistPickerTitle = "";
        private static string[] artistPickerNames = null;
        private static string[] artistPickerIds = null;
        private static int artistPickerIdx = 0;
        private static string artistPickerNoun = "artist";
        private static Action<string> artistPickerOnPick = null;
        private static string artistPickerAction = "Assign";
        private static bool artistPickerShowClear = true;
        private static Vector2 artistPickerScroll = Vector2.zero;
        private static GUIStyle pickerRowStyle;

        /// <param name="itemNoun">What the rows ARE. The picker is reused for
        /// artists, translators and languages, so the count line must not say
        /// "artists" for a language list (Codex review). Pass "" to omit it.</param>
        /// <param name="selectedId">Pre-selects the current value, so pressing
        /// the action button without clicking a row keeps what you already had
        /// instead of silently choosing the first row.</param>
        public static void OpenArtistPicker(string title, string[] names, string[] ids, Action<string> onPick,
                                            string actionLabel = "Assign", bool showClear = true,
                                            string itemNoun = "artist", string selectedId = null)
        {
            if (names == null || ids == null || names.Length == 0 || names.Length != ids.Length) return;
            artistPickerTitle = title ?? "Pick an artist";
            artistPickerNames = names;
            artistPickerIds = ids;
            artistPickerNoun = itemNoun ?? "";
            artistPickerIdx = 0;
            if (!string.IsNullOrEmpty(selectedId))
                for (int i = 0; i < ids.Length; i++)
                    if (ids[i] == selectedId) { artistPickerIdx = i; break; }
            artistPickerOnPick = onPick;
            artistPickerAction = string.IsNullOrEmpty(actionLabel) ? "Assign" : actionLabel;
            artistPickerShowClear = showClear;
            artistPickerScroll = Vector2.zero;
            artistPickerOpen = true;
        }

        private static void DrawArtistPicker()
        {
            if (!artistPickerOpen) return;
            if (!NativeUI.IsOpen) { artistPickerOpen = false; artistPickerOnPick = null; return; }
            var ev = Event.current;
            bool cancel = false;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape) { cancel = true; ev.Use(); }
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };
            if (pickerRowStyle == null)
                pickerRowStyle = new GUIStyle(GUI.skin.button)
                { fontSize = 14, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft, richText = true };

            int n = artistPickerNames.Length;
            artistPickerIdx = Mathf.Clamp(artistPickerIdx, 0, n - 1);
            float rowH = 32f;
            float listH = Mathf.Min(n * rowH + 4f, 330f);
            float w = 540, h = 118f + listH;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.93f), 0, 0);
            string countNote = string.IsNullOrEmpty(artistPickerNoun) ? ""
                : $"  <color=#999>({n} {artistPickerNoun}{(n == 1 ? "" : "s")})</color>";
            GUI.Label(new Rect(x + 12, y + 10, w - 24, 26), $"{artistPickerTitle}{countNote}",
                new GUIStyle(adminLabelStyle) { fontSize = 17, fontStyle = FontStyle.Bold, richText = true });

            artistPickerScroll = GUI.BeginScrollView(new Rect(x + 12, y + 44, w - 24, listH),
                artistPickerScroll, new Rect(0, 0, w - 45, n * rowH));
            for (int i = 0; i < n; i++)
            {
                bool sel = (i == artistPickerIdx);
                if (sel)
                    GUI.DrawTexture(new Rect(0, i * rowH, w - 45, rowH - 2), Texture2D.whiteTexture,
                        ScaleMode.StretchToFill, true, 0, new Color(0.25f, 0.45f, 0.25f, 0.85f), 0, 0);
                string line = $"{(sel ? "> " : "")}{artistPickerNames[i]}   <color=#888><size=11>{artistPickerIds[i]}</size></color>";
                if (GUI.Button(new Rect(0, i * rowH, w - 45, rowH - 2), line, pickerRowStyle))
                    artistPickerIdx = i;
            }
            GUI.EndScrollView();

            if (GUI.Button(new Rect(x + 12, y + h - 40, 110, 30), "Cancel")) cancel = true;
            if (artistPickerShowClear &&
                GUI.Button(new Rect(x + (w - 130) / 2f, y + h - 40, 130, 30), "Clear (house)"))
            {
                var cb = artistPickerOnPick;
                artistPickerOpen = false; artistPickerOnPick = null;
                try { cb?.Invoke(""); } catch (Exception ex) { Plugin.Log.LogWarning($"[ARTIST] picker clear: {ex.Message}"); }
                return;
            }
            if (GUI.Button(new Rect(x + w - 122, y + h - 40, 110, 30), artistPickerAction))
            {
                var cb = artistPickerOnPick;
                string picked = artistPickerIds[artistPickerIdx];
                artistPickerOpen = false; artistPickerOnPick = null;
                try { cb?.Invoke(picked); } catch (Exception ex) { Plugin.Log.LogWarning($"[ARTIST] picker pick: {ex.Message}"); }
                return;
            }
            if (cancel) { artistPickerOpen = false; artistPickerOnPick = null; }
        }

        // ── Player search modal (bug batch item 8) ──────────────────────
        // Search players by steam display name; each result shows the CURRENT elo
        // beside the name so a rename-imposter can't pass as the real player.
        // onPick receives (steam_id, display_name).
        private static bool playerSearchOpen = false;
        private static string playerSearchTitle = "";
        private static string playerSearchQuery = "", playerSearchPrevQuery = "";
        private static string playerSearchLastFetched = null;
        private static float playerSearchTypedAt = 0f;
        private static bool playerSearchBusy = false;
        private static string playerSearchStatus = "";
        private static List<ApiClient.PlayerSearchResult> playerSearchResults = new List<ApiClient.PlayerSearchResult>();
        private static Action<string, string> playerSearchOnPick = null;

        public static void OpenPlayerSearch(string title, Action<string, string> onPick)
        {
            playerSearchTitle = title ?? "Find a player";
            playerSearchQuery = ""; playerSearchPrevQuery = "";
            playerSearchLastFetched = null;
            playerSearchBusy = false;
            playerSearchStatus = "Type at least 2 letters of the player's name.";
            playerSearchResults.Clear();
            playerSearchOnPick = onPick;
            playerSearchOpen = true;
        }

        private static void DrawPlayerSearch()
        {
            if (!playerSearchOpen) return;
            if (!NativeUI.IsOpen) { playerSearchOpen = false; playerSearchOnPick = null; return; }
            var ev = Event.current;
            bool cancel = false;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape) { cancel = true; ev.Use(); }
            if (adminFieldStyle == null) adminFieldStyle = new GUIStyle(GUI.skin.textField) { fontSize = 15 };
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };
            if (pickerRowStyle == null)
                pickerRowStyle = new GUIStyle(GUI.skin.button)
                { fontSize = 14, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft, richText = true };

            int n = playerSearchResults.Count;
            float rowH = 32f;
            float listH = Mathf.Max(64f, Mathf.Min(n * rowH + 4f, 8 * rowH));
            float w = 560, h = 158f + listH;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.93f), 0, 0);
            GUI.Label(new Rect(x + 12, y + 10, w - 24, 26), playerSearchTitle,
                new GUIStyle(adminLabelStyle) { fontSize = 17, fontStyle = FontStyle.Bold });
            GUI.Label(new Rect(x + 12, y + 40, w - 24, 20), "Steam name", adminLabelStyle);
            playerSearchQuery = GUI.TextField(new Rect(x + 12, y + 62, w - 24, 28), playerSearchQuery ?? "", adminFieldStyle);
            if (playerSearchQuery != playerSearchPrevQuery)
            {
                playerSearchPrevQuery = playerSearchQuery;
                playerSearchTypedAt = Time.unscaledTime;
            }

            // Debounced auto-search: 0.35s after the last keystroke, once per query.
            // Repaint-gated so IMGUI's multiple per-frame passes can't double-fire.
            string q = (playerSearchQuery ?? "").Trim();
            if (ev != null && ev.type == EventType.Repaint && !playerSearchBusy
                && q.Length >= 2 && q != playerSearchLastFetched
                && Time.unscaledTime - playerSearchTypedAt > 0.35f)
            {
                playerSearchBusy = true;
                playerSearchStatus = "Searching...";
                string sent = q;
                ApiClient.SearchPlayers(sent, (ok, list) =>
                {
                    playerSearchBusy = false;
                    if (!playerSearchOpen) return;
                    playerSearchLastFetched = sent;
                    if (ok)
                    {
                        playerSearchResults = list ?? new List<ApiClient.PlayerSearchResult>();
                        playerSearchStatus = playerSearchResults.Count == 0
                            ? "No players match."
                            : "Click a player. The elo beside the name is live - an imposter with a copied name won't have their rating.";
                    }
                    else playerSearchStatus = "Search failed - server unreachable?";
                });
            }

            GUI.Label(new Rect(x + 12, y + 92, w - 24, 20), playerSearchStatus,
                new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = false });

            float listY = y + 114;
            for (int i = 0; i < n && i < 8; i++)
            {
                var r = playerSearchResults[i];
                string line = $"{r.display_name}   <color=#FFD75E>{r.rating} elo</color>   <color=#777><size=11>{r.steam_id}</size></color>";
                if (GUI.Button(new Rect(x + 12, listY + i * rowH, w - 24, rowH - 2), line, pickerRowStyle))
                {
                    var cb = playerSearchOnPick;
                    string sid = r.steam_id, sname = r.display_name;
                    playerSearchOpen = false; playerSearchOnPick = null;
                    try { cb?.Invoke(sid, sname); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[SEARCH] pick: {ex.Message}"); }
                    return;
                }
            }

            if (GUI.Button(new Rect(x + 12, y + h - 40, 110, 30), "Cancel")) cancel = true;
            if (cancel) { playerSearchOpen = false; playerSearchOnPick = null; }
        }

        // ── Cosmetic review modal (July 12 round 3, item 2) ──────────────
        // Admin queue for artist-submitted cosmetics: real art preview (decoded
        // from the server's base64), Approve mints the shop row (born out of
        // stock), Deny asks for a note the artist will see.
        // Artist-side scale preview. A 512px canvas does not equal one player
        // body: with the game's 100 PPU sprite and 0.16 item-parent scale, the
        // body is approximately 662.5 source pixels across at render scale 1.
        // The fixed orange circle below is the body; the submitted canvas grows
        // around it exactly as the in-game render scale changes.
        private static bool cosTestOpen = false;
        private static Texture2D cosTestTex = null;
        private static string cosTestName = "", cosTestSlot = "";
        private static float cosTestScale = 1.30f;
        private static Vector2 cosTestOffset = Vector2.zero;
        // The offset the item CAME IN with — what Submit sends back out,
        // regardless of any preview dragging (item 5: drags are never saved).
        private static Vector2 cosTestInitialOffset = Vector2.zero;
        private static bool cosTestDragging = false;
        private static Vector2 cosTestLastMouse = Vector2.zero;
        private static string cosTestSubmitLabel = "Submit";
        private static bool cosTestIsRevision = false;
        private static Action<float, float, float> cosTestOnSubmit = null;
        // Aug 7 item 10: view-only mode (shop body preview). Frames are the
        // SHARED catalog sprites — never destroyed here; only cosTestTex (our
        // own decode) is owned by this modal.
        private static bool cosTestViewOnly = false;
        private static Sprite[] cosTestFrames = null;
        private static float cosTestFps = 2.5f;
        // Aug 7 item 8: animated ARTIST upload preview — these textures are
        // OURS (decoded from the artist's files) and are destroyed on close;
        // fps is artist-editable via a slider and rides the submit callback.
        private static Texture2D[] cosTestOwnedFrames = null;
        private static float cosTestFpsEdit = 2.5f;
        private static Action<float, float, float, float> cosTestOnSubmitAnim = null;
        private const float COS_BODY_SOURCE_PX = 662.5f;
        // CharacterItem.offset is expressed before the face-parent's 0.16
        // scale. A 1.06-world-unit body is therefore about 6.625 local units.
        private const float COS_BODY_LOCAL_DIAMETER = 6.625f;
        private static readonly Color COS_BODY_ORANGE = new Color(0.96f, 0.55f, 0.23f, 0.82f);

        public static void OpenCosmeticTestPreview(byte[] pngBytes, string name, string slot,
            Action<float, float, float> onSubmit, float initialScale = 1.30f,
            float initialOffsetX = 0f, float initialOffsetY = 0f,
            string submitLabel = "Submit", bool isRevision = false)
        {
            Texture2D tex = null;
            try
            {
                tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (pngBytes == null || !tex.LoadImage(pngBytes))
                {
                    UnityEngine.Object.Destroy(tex);
                    ShowNotification("Could not open that cosmetic preview.", new Color(1f, 0.45f, 0.4f), 5f);
                    return;
                }
            }
            catch
            {
                try { if (tex != null) UnityEngine.Object.Destroy(tex); } catch { }
                ShowNotification("Could not open that cosmetic preview.", new Color(1f, 0.45f, 0.4f), 5f);
                return;
            }

            CloseCosmeticTestPreview(false);
            // A delayed preview fetch can finish after the artist reopened the
            // selector. The preview owns the next step, so retire that selector
            // explicitly instead of drawing two IMGUI modals on top of each
            // other until the user cancels one.
            artistPickerOpen = false;
            artistPickerOnPick = null;
            cosTestTex = tex;
            cosTestName = name ?? "Cosmetic";
            cosTestSlot = slot ?? "detail";
            cosTestScale = Mathf.Clamp(initialScale, 0.50f, 2.25f);
            // July 26 (Sid item 5) + adversarial-review correction: the DRAG is
            // a preview-only visual aid and is never persisted — the modal
            // submits the item's INITIAL offset back unchanged (see
            // CloseCosmeticTestPreview). New submissions open and submit
            // centered (callers pass 0,0), so new cosmetics spawn centered for
            // player customization; revisions of EXISTING items carry their
            // stored placement through untouched (zeroing them would have
            // recentered Crown/Halo/etc. at the next release — offsets are
            // load-bearing at render time, CustomCosmetics.cs item.offset).
            cosTestInitialOffset = Vector2.ClampMagnitude(
                new Vector2(initialOffsetX, initialOffsetY), 4.50f);
            cosTestOffset = cosTestInitialOffset;
            cosTestDragging = false;
            cosTestSubmitLabel = string.IsNullOrEmpty(submitLabel) ? "Submit" : submitLabel;
            cosTestIsRevision = isRevision;
            cosTestOnSubmit = onSubmit;
            cosTestViewOnly = false;
            cosTestFrames = null;
            DestroyOwnedFrames();
            cosTestOnSubmitAnim = null;
            cosTestOpen = true;
        }

        /// <summary>Aug 7 item 8: animated ARTIST preview — all frames decoded
        /// locally (multi-PNG path), cycling live, with an fps slider whose
        /// value rides the submit callback (scale, offsetX, offsetY, fps).</summary>
        public static void OpenCosmeticAnimTestPreview(List<byte[]> framePngs, string name, string slot,
            Action<float, float, float, float> onSubmit, float initialFps = 2.5f)
        {
            if (framePngs == null || framePngs.Count < 2) return;
            var frames = new Texture2D[framePngs.Count];
            for (int i = 0; i < framePngs.Count; i++)
            {
                var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (framePngs[i] == null || !tex.LoadImage(framePngs[i]))
                {
                    try { UnityEngine.Object.Destroy(tex); } catch { }
                    for (int k = 0; k < i; k++) { try { UnityEngine.Object.Destroy(frames[k]); } catch { } }
                    ShowNotification("Could not decode one of the animation frames.", new Color(1f, 0.45f, 0.4f), 5f);
                    return;
                }
                frames[i] = tex;
            }
            // Reuse the static open for all the shared state (it clears any
            // previous animated state), then layer the animation on top. The
            // static path already decoded frame 1 into cosTestTex; the owned
            // array is the cycling source and is destroyed on close.
            OpenCosmeticTestPreview(framePngs[0], name, slot, null);
            if (!cosTestOpen)
            {
                foreach (var f in frames) { try { UnityEngine.Object.Destroy(f); } catch { } }
                return;
            }
            cosTestOwnedFrames = frames;
            cosTestFpsEdit = Mathf.Clamp(initialFps, 0.5f, 15f);
            cosTestOnSubmitAnim = onSubmit;
        }

        private static void DestroyOwnedFrames()
        {
            if (cosTestOwnedFrames == null) return;
            foreach (var f in cosTestOwnedFrames)
            {
                if (f == null || ReferenceEquals(f, cosTestTex)) continue;  // cosTestTex has its own Destroy
                try { UnityEngine.Object.Destroy(f); } catch { }
            }
            cosTestOwnedFrames = null;
        }

        /// <summary>Aug 7 item 10: view-only body preview for any BUNDLED
        /// catalog cosmetic (shop browsing — "see it on the body before you
        /// buy"). Reuses the artist modal wholesale: same body-circle renderer,
        /// same input gating (cosTestOpen is already in the anyModal set), with
        /// the editing chrome hidden. Placement comes from the COMPILED catalog
        /// via TryGetPublishedPlacement — the shipped values, never the
        /// server's mutable proposal columns (#164/#165).</summary>
        public static void OpenCosmeticBodyPreview(string sku, string displayName)
        {
            try
            {
                if (!CustomCosmetics.TryGetPublishedPlacement(sku, out string slot, out float scale,
                        out Vector2 off, out byte[] png) || png == null)
                {
                    // GitHub installs can be mid-bootstrap (cosmetics.zip
                    // download in flight) — degrade like the Home fill does.
                    ShowNotification("Preview art isn't downloaded yet - try again in a minute.",
                        new Color(1f, 0.75f, 0.4f), 5f);
                    return;
                }
                OpenCosmeticTestPreview(png, displayName, slot, null, scale, off.x, off.y, "Close");
                if (!cosTestOpen) return;   // decode failed; the notification already fired
                cosTestViewOnly = true;
                var frames = CustomCosmetics.GetShopFrames(sku, out float fps);
                // Honor the player's animation toggle (a frozen preview is the
                // "Animated Cosmetics: OFF" contract, not a bug).
                if (frames != null && frames.Length > 1 && fps > 0f
                    && (Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value))
                {
                    cosTestFrames = frames;
                    cosTestFps = fps;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[SHOP] body preview: {ex.Message}"); }
        }

        private static void CloseCosmeticTestPreview(bool submit)
        {
            var cb = submit ? cosTestOnSubmit : null;
            var cbAnim = submit ? cosTestOnSubmitAnim : null;
            float fpsOut = Mathf.Clamp(cosTestFpsEdit, 0.5f, 15f);
            float scale = Mathf.Clamp(cosTestScale, 0.50f, 2.25f);
            cosTestOpen = false;
            cosTestDragging = false;
            cosTestOnSubmit = null;
            cosTestOnSubmitAnim = null;
            cosTestViewOnly = false;
            cosTestFrames = null;   // shared catalog sprites — do NOT destroy
            DestroyOwnedFrames();   // artist-upload frame decodes — OURS
            try { if (cosTestTex != null) UnityEngine.Object.Destroy(cosTestTex); } catch { }
            cosTestTex = null;
            cosTestName = "";
            cosTestSlot = "";
            cosTestOffset = Vector2.zero;
            Vector2 initialOffset = cosTestInitialOffset;
            cosTestInitialOffset = Vector2.zero;
            if (cb != null)
            {
                // The drag is a visual aid only (Sid item 5): submit the
                // INITIAL offset unchanged. New submissions came in at 0,0 and
                // stay centered; placement revisions of shipped items keep
                // their load-bearing stored offset. Scale is the only number
                // the modal actually edits.
                try { cb(scale, initialOffset.x, initialOffset.y); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] preview submit: {ex.Message}"); }
            }
            if (cbAnim != null)
            {
                // Animated submit: same placement contract + the edited fps.
                try { cbAnim(scale, initialOffset.x, initialOffset.y, fpsOut); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] anim preview submit: {ex.Message}"); }
            }
        }

        private static void DrawRectOutline(Rect r, Color color, float thickness = 1f)
        {
            GUI.DrawTexture(new Rect(r.x, r.y, r.width, thickness), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, color, 0, 0);
            GUI.DrawTexture(new Rect(r.x, r.yMax - thickness, r.width, thickness), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, color, 0, 0);
            GUI.DrawTexture(new Rect(r.x, r.y, thickness, r.height), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, color, 0, 0);
            GUI.DrawTexture(new Rect(r.xMax - thickness, r.y, thickness, r.height), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, color, 0, 0);
        }

        private static void DrawCosmeticScalePreview(
            Rect bounds, Texture2D tex, float scale, Vector2 offset)
        {
            GUI.DrawTexture(bounds, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0.16f, 0.17f, 0.20f, 1f), 0, 4);

            float bodyD = bounds.width * 0.50f;
            Rect body = new Rect(bounds.center.x - bodyD / 2f, bounds.center.y - bodyD / 2f, bodyD, bodyD);
            GUI.DrawTexture(body, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                COS_BODY_ORANGE, 0, bodyD / 2f);

            float canvasD = bodyD * (512f / COS_BODY_SOURCE_PX) * Mathf.Clamp(scale, 0.50f, 2.25f);
            float pixelsPerOffsetUnit = bodyD / COS_BODY_LOCAL_DIAMETER;
            Vector2 center = new Vector2(
                bounds.center.x + offset.x * pixelsPerOffsetUnit,
                bounds.center.y - offset.y * pixelsPerOffsetUnit);
            Rect canvas = new Rect(center.x - canvasD / 2f, center.y - canvasD / 2f,
                                   canvasD, canvasD);
            DrawRectOutline(canvas, new Color(1f, 1f, 1f, 0.55f), 1f);
            if (tex != null) GUI.DrawTexture(canvas, tex, ScaleMode.ScaleToFit, true);
        }

        private static void HandleCosmeticPlacementDrag(
            Rect bounds, ref Vector2 offset, ref bool dragging, ref Vector2 lastMouse)
        {
            var ev = Event.current;
            if (ev == null) return;
            if (ev.type == EventType.MouseDown && ev.button == 0 && bounds.Contains(ev.mousePosition))
            {
                dragging = true;
                lastMouse = ev.mousePosition;
                ev.Use();
                return;
            }
            if (ev.type == EventType.MouseDrag && ev.button == 0 && dragging)
            {
                float bodyD = bounds.width * 0.50f;
                float unitsPerPixel = COS_BODY_LOCAL_DIAMETER / Mathf.Max(1f, bodyD);
                Vector2 delta = ev.mousePosition - lastMouse;
                offset += new Vector2(delta.x * unitsPerPixel, -delta.y * unitsPerPixel);
                offset = Vector2.ClampMagnitude(offset, 4.50f);
                lastMouse = ev.mousePosition;
                ev.Use();
                return;
            }
            if (ev.type == EventType.MouseUp && ev.button == 0 && dragging)
            {
                dragging = false;
                ev.Use();
            }
        }

        private static void DrawCosmeticTestPreview()
        {
            if (!cosTestOpen) return;
            if (!NativeUI.IsOpen) { CloseCosmeticTestPreview(false); return; }
            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            { ev.Use(); CloseCosmeticTestPreview(false); return; }
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };

            float w = Mathf.Min(760f, Mathf.Max(500f, Screen.width - 24f));
            float h = Mathf.Min(560f, Mathf.Max(450f, Screen.height - 24f));
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0, 0, 0, 0.96f), 0, 0);
            GUI.Label(new Rect(x + 12, y + 10, w - 24, 26),
                $"Placement preview: '{cosTestName}' ({cosTestSlot})",
                new GUIStyle(adminLabelStyle) { fontSize = 17, fontStyle = FontStyle.Bold });
            GUI.Label(new Rect(x + 12, y + 40, w - 24, 38),
                cosTestViewOnly
                    ? "Orange circle = player body, shown at this item's shipped scale and position. Drag the art to peek around - nothing is saved."
                    : "Orange circle = player body. Drag to preview positions (visual aid only - position is never saved; items spawn centered and players drag them in the character editor). White square = your 512x512 canvas.",
                new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = true });

            float previewSize = Mathf.Min(h - 142f, w - 330f);
            previewSize = Mathf.Clamp(previewSize, 300f, 414f);
            Rect preview = new Rect(x + 12, y + 80, previewSize, previewSize);
            // Aug 7 item 10: animated catalog items cycle in view-only mode
            // (IMGUI repaints continuously, so this is free).
            Texture2D drawTex = cosTestTex;
            if (cosTestViewOnly && cosTestFrames != null && cosTestFrames.Length > 1 && cosTestFps > 0f)
            {
                int fi = (int)(Time.unscaledTime * cosTestFps) % cosTestFrames.Length;
                var ft = cosTestFrames[fi] != null ? cosTestFrames[fi].texture : null;
                if (ft != null) drawTex = ft;
            }
            // Aug 7 item 8: artist animated upload — cycle the OWNED frames at
            // the fps the slider currently holds, so the artist sees exactly
            // what they are submitting.
            else if (cosTestOwnedFrames != null && cosTestOwnedFrames.Length > 1)
            {
                int fi = (int)(Time.unscaledTime * Mathf.Max(0.5f, cosTestFpsEdit)) % cosTestOwnedFrames.Length;
                if (cosTestOwnedFrames[fi] != null) drawTex = cosTestOwnedFrames[fi];
            }
            DrawCosmeticScalePreview(preview, drawTex, cosTestScale, cosTestOffset);
            HandleCosmeticPlacementDrag(
                preview, ref cosTestOffset, ref cosTestDragging, ref cosTestLastMouse);

            float rx = preview.xMax + 18f;
            float rw = x + w - 12f - rx;
            if (cosTestViewOnly)
            {
                // Buyer-facing chrome only: no slider/presets/submit copy — the
                // artist controls would read as editable (and 403 for
                // non-artists on submit).
                GUI.Label(new Rect(rx, y + 84, rw, 24), $"Render scale: {cosTestScale:F2}x",
                    new GUIStyle(adminLabelStyle) { fontSize = 16, fontStyle = FontStyle.Bold });
                GUI.Label(new Rect(rx, y + 112, rw, 76),
                    "This is exactly how the item renders on a player in-game.",
                    new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = true });
                if (cosTestFrames != null && cosTestFrames.Length > 1)
                    GUI.Label(new Rect(rx, y + 192, rw, 22),
                        $"Animated - {cosTestFrames.Length} frames @ {cosTestFps:0.#} fps", adminLabelStyle);
                if (GUI.Button(new Rect(x + w - 152, y + h - 42, 140, 30), "Close"))
                { CloseCosmeticTestPreview(false); return; }
                return;
            }
            GUI.Label(new Rect(rx, y + 84, rw, 24), $"Render scale: {cosTestScale:F2}x",
                new GUIStyle(adminLabelStyle) { fontSize = 16, fontStyle = FontStyle.Bold });
            int bodyPx = Mathf.RoundToInt(COS_BODY_SOURCE_PX / cosTestScale);
            GUI.Label(new Rect(rx, y + 112, rw, 52),
                $"At this scale, the player body is about {bodyPx}px across in your source image.\n" +
                "Transparent pixels still count toward the 512px canvas.",
                new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = true });
            cosTestScale = GUI.HorizontalSlider(new Rect(rx, y + 158, rw, 22),
                cosTestScale, 0.50f, 2.25f);
            cosTestScale = Mathf.Round(cosTestScale * 20f) / 20f;

            if (GUI.Button(new Rect(rx, y + 184, 42, 28), "-")) cosTestScale -= 0.05f;
            if (GUI.Button(new Rect(rx + 50, y + 184, 42, 28), "+")) cosTestScale += 0.05f;
            if (GUI.Button(new Rect(rx + 100, y + 184, Mathf.Max(64f, rw - 100f), 28), "Center"))
                cosTestOffset = Vector2.zero;
            cosTestScale = Mathf.Clamp(cosTestScale, 0.50f, 2.25f);

            GUI.Label(new Rect(rx, y + 218, rw, 22),
                $"Preview offset: {cosTestOffset.x:F2}, {cosTestOffset.y:F2} (not saved)", adminLabelStyle);
            if (cosTestOwnedFrames != null && cosTestOwnedFrames.Length > 1)
            {
                // Aug 7 item 8: the artist sets the animation speed here — it
                // rides the submission. Replaces the scale presets (the slider
                // and +/- still cover scale).
                GUI.Label(new Rect(rx, y + 244, rw, 22),
                    $"Frame rate: {cosTestFpsEdit:0.0} fps  ({cosTestOwnedFrames.Length} frames, "
                    + $"loop {cosTestOwnedFrames.Length / Mathf.Max(0.5f, cosTestFpsEdit):0.0}s)",
                    adminLabelStyle);
                cosTestFpsEdit = GUI.HorizontalSlider(new Rect(rx, y + 270, rw, 22), cosTestFpsEdit, 0.5f, 15f);
                cosTestFpsEdit = Mathf.Round(cosTestFpsEdit * 10f) / 10f;
            }
            else
            {
                GUI.Label(new Rect(rx, y + 244, rw, 22), "Useful scale presets:", adminLabelStyle);
                float bw = (rw - 8f) / 2f;
                if (GUI.Button(new Rect(rx, y + 268, bw, 28), "1.00  compact")) cosTestScale = 1.00f;
                if (GUI.Button(new Rect(rx + bw + 8, y + 268, bw, 28), "1.30  body")) cosTestScale = 1.30f;
                if (GUI.Button(new Rect(rx, y + 302, bw, 28), "1.70  cape")) cosTestScale = 1.70f;
                if (GUI.Button(new Rect(rx + bw + 8, y + 302, bw, 28), "2.10  wings")) cosTestScale = 2.10f;
            }
            GUI.Label(new Rect(rx, y + 336, rw, 72),
                (cosTestIsRevision
                    ? "Changing scale or placement sends this cosmetic back to admin review. Its last approved placement stays active meanwhile. "
                    : "Scale and placement are part of approval. ")
                + "Badly scaled, obstructive, or misplaced art will be rejected or rescaled/repositioned by an admin.",
                new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = true });

            if (GUI.Button(new Rect(x + 12, y + h - 42, 110, 30), "Cancel"))
            { CloseCosmeticTestPreview(false); return; }
            if (GUI.Button(new Rect(x + w - 152, y + h - 42, 140, 30), cosTestSubmitLabel))
            { CloseCosmeticTestPreview(true); return; }
        }

        private static bool cosReviewOpen = false;
        private static List<ApiClient.CosmeticSubmission> cosReviewSubs = null;
        private static int cosReviewIdx = 0;
        private static bool cosReviewBusy = false;
        private static string cosReviewStatus = "";
        private static string cosReviewDenialReason = "";
        private static bool cosReviewDragging = false;
        // Local, per-submission preview drag state — visual aid only, never
        // written back to the submission or sent to the server (item 5).
        private static Vector2 cosReviewPreviewOffset = Vector2.zero;
        private static int cosReviewPreviewSubId = -1;
        private static Vector2 cosReviewLastMouse = Vector2.zero;
        private static GUIStyle cosReviewReasonStyle;
        private static readonly Dictionary<int, Texture2D> cosReviewTex = new Dictionary<int, Texture2D>();

        public static bool CosmeticReviewOpen => cosReviewOpen;

        public static void OpenCosmeticReview()
        {
            cosReleaseOpen = false;
            cosReviewOpen = true;
            cosReviewSubs = null;
            cosReviewIdx = 0;
            cosReviewBusy = true;
            cosReviewStatus = "Loading pending submissions...";
            cosReviewDenialReason = "";
            cosReviewDragging = false;
            ApiClient.FetchCosmeticSubmissionsAdmin(MatchTracker.LocalSteamId, (ok, list) =>
            {
                cosReviewBusy = false;
                if (!cosReviewOpen) return;
                if (!ok) { cosReviewStatus = "Fetch failed - are you an admin?"; return; }
                cosReviewSubs = list;
                cosReviewStatus = list.Count == 0 ? "No pending submissions." : "";
            });
        }

        private static void CloseCosmeticReview()
        {
            cosReviewOpen = false;
            foreach (var t in cosReviewTex.Values) { try { if (t != null) UnityEngine.Object.Destroy(t); } catch { } }
            cosReviewTex.Clear();
            // Aug 7 item 8: animation frames too (index 0 aliases the frame-1
            // texture destroyed above — DropCosReviewFrames skips it).
            var animIds = new List<int>(cosReviewFrames.Keys);
            foreach (int id in animIds) DropCosReviewFrames(id);
            cosReviewSubs = null;
            cosReviewDenialReason = "";
            cosReviewDragging = false;
        }

        private static Texture2D CosReviewTexture(ApiClient.CosmeticSubmission s)
        {
            Texture2D t;
            if (cosReviewTex.TryGetValue(s.id, out t)) return t;
            try
            {
                var bytes = Convert.FromBase64String(s.png_base64 ?? "");
                t = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (!t.LoadImage(bytes)) { UnityEngine.Object.Destroy(t); t = null; }
            }
            catch { t = null; }
            cosReviewTex[s.id] = t;
            return t;
        }

        private static void RemoveCosReview(int id)
        {
            if (cosReviewSubs == null) return;
            cosReviewSubs.RemoveAll(q => q.id == id);
            Texture2D t;
            if (cosReviewTex.TryGetValue(id, out t)) { try { if (t != null) UnityEngine.Object.Destroy(t); } catch { } cosReviewTex.Remove(id); }
            DropCosReviewFrames(id);
            if (cosReviewSubs.Count == 0) cosReviewStatus = "All reviewed!";
            cosReviewDenialReason = "";
            cosReviewDragging = false;
        }

        // ── Aug 7 item 8: animated review preview ────────────────────────────
        // Frames 2..N are fetched LAZILY per submission (the list response
        // deliberately carries only frame 1) and decoded once; index 0 aliases
        // the frame-1 texture owned by cosReviewTex, so cleanup skips it.
        private static readonly Dictionary<int, Texture2D[]> cosReviewFrames =
            new Dictionary<int, Texture2D[]>();

        private static void DropCosReviewFrames(int id)
        {
            Texture2D[] frames;
            if (!cosReviewFrames.TryGetValue(id, out frames)) return;
            for (int i = 1; i < frames.Length; i++)   // 0 = cosReviewTex's texture
                { try { if (frames[i] != null) UnityEngine.Object.Destroy(frames[i]); } catch { } }
            cosReviewFrames.Remove(id);
        }

        private static Texture2D CosReviewFrameTexture(ApiClient.CosmeticSubmission s, Texture2D frame1)
        {
            if (s == null || s.frame_count <= 1 || frame1 == null) return frame1;
            Texture2D[] frames;
            if (!cosReviewFrames.TryGetValue(s.id, out frames))
            {
                // Kick the lazy fetch (deduped inside); build the local decode
                // set only once the payload has arrived.
                ApiClient.FetchCosmeticFrames(MatchTracker.LocalSteamId, s.id);
                List<string> b64s;
                if (!ApiClient.CachedCosmeticFrames.TryGetValue(s.id, out b64s) || b64s.Count == 0)
                    return frame1;
                frames = new Texture2D[b64s.Count + 1];
                frames[0] = frame1;
                for (int i = 0; i < b64s.Count; i++)
                {
                    try
                    {
                        var t = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                        if (t.LoadImage(Convert.FromBase64String(b64s[i]))) frames[i + 1] = t;
                        else UnityEngine.Object.Destroy(t);
                    }
                    catch { }
                }
                cosReviewFrames[s.id] = frames;
            }
            float fps = s.anim_fps > 0f ? s.anim_fps : 2.5f;
            int fi = (int)(Time.unscaledTime * fps) % frames.Length;
            return frames[fi] != null ? frames[fi] : frame1;
        }

        private static string CosTrunc(string s, int n) => string.IsNullOrEmpty(s) ? "" : (s.Length <= n ? s : s.Substring(0, n));

        private static void DrawCosmeticReview()
        {
            if (!cosReviewOpen) return;
            if (!NativeUI.IsOpen) { CloseCosmeticReview(); return; }
            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape) { ev.Use(); CloseCosmeticReview(); return; }
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };
            if (cosReviewReasonStyle == null)
                cosReviewReasonStyle = new GUIStyle(GUI.skin.textArea) { fontSize = 13, wordWrap = true };

            // Clamp to the actual game window. The previous fixed 720x650
            // panel put the title/Close button above a 1024x576 window.
            float w = Mathf.Min(720f, Mathf.Max(500f, Screen.width - 24f));
            float h = Mathf.Min(620f, Mathf.Max(500f, Screen.height - 24f));
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.94f), 0, 0);
            GUI.Label(new Rect(x + 12, y + 10, w - 24, 26), "Cosmetic submissions",
                new GUIStyle(adminLabelStyle) { fontSize = 17, fontStyle = FontStyle.Bold });
            if (GUI.Button(new Rect(x + w - 90, y + 10, 78, 26), "Close")) { CloseCosmeticReview(); return; }

            GUI.Label(new Rect(x + 12, y + 42, w - 24, 118),
                "<b>Approval guidelines</b>\n" +
                "1. All cosmetics must have a transparent background.\n" +
                "2. All cosmetics must be tasteful, attractive, and fitting with the current cosmetics.\n" +
                "3. Cosmetics must not be large just to be large, purposely distracting or flashing, or made only for one player's personal use.\n" +
                "4. The cosmetic type must fit the art (for example, no mouths in the eyes section).\n" +
                "5. Scale and placement must fit the body/slot and not obscure play; reject or adjust anything disproportionate or misplaced.",
                new GUIStyle(adminLabelStyle) { fontSize = 11, richText = true, wordWrap = true });

            var subs = cosReviewSubs;
            if (cosReviewBusy || subs == null || subs.Count == 0)
            {
                GUI.Label(new Rect(x + 12, y + 164, w - 24, 30),
                    string.IsNullOrEmpty(cosReviewStatus) ? "..." : cosReviewStatus, adminLabelStyle);
                return;
            }
            cosReviewIdx = Mathf.Clamp(cosReviewIdx, 0, subs.Count - 1);
            var s = subs[cosReviewIdx];
            int approxKb = (s.png_base64 != null ? s.png_base64.Length * 3 / 4 : 0) / 1024;
            string reviewKind = s.review_kind == "placement" ? "PLACEMENT CHANGE" : "NEW COSMETIC";
            // Aug 7 item 8: an animated submission announces itself — an admin
            // approving one must see it MOVE (#161's cycling-preview rule).
            string animTag = s.frame_count > 1
                ? $"  ANIMATED {s.frame_count}f @ {(s.anim_fps > 0f ? s.anim_fps : 2.5f):0.0}fps"
                : "";
            GUI.Label(new Rect(x + 12, y + 164, w - 24, 22),
                $"[{reviewKind}]{animTag}  #{s.id} rev {s.placement_revision}  '{s.name}' ({s.slot}) by {s.artist_name}  {approxKb} KB   -   {cosReviewIdx + 1}/{subs.Count}",
                new GUIStyle(adminLabelStyle) { fontStyle = FontStyle.Bold });
            float prevSize = Mathf.Clamp(h - 320f, 170f, 235f);
            Rect prev = new Rect(x + 12, y + 192, prevSize, prevSize);
            var tex = CosReviewFrameTexture(s, CosReviewTexture(s));
            if (s.render_scale <= 0f) s.render_scale = 1f;
            // Adversarial-review correction (item 5): the drag lives in a LOCAL
            // preview offset and is never written back onto the submission —
            // Approve/Deny send the STORED proposal offset untouched. (The old
            // write-back meant an admin's idle drag became the approved
            // placement; combined with zeroing it would have recentered
            // shipped items like Crown at their next revision.)
            if (cosReviewPreviewSubId != s.id)
            {
                cosReviewPreviewSubId = s.id;
                cosReviewPreviewOffset = new Vector2(s.render_offset_x, s.render_offset_y);
            }
            DrawCosmeticScalePreview(prev, tex, s.render_scale, cosReviewPreviewOffset);
            HandleCosmeticPlacementDrag(
                prev, ref cosReviewPreviewOffset, ref cosReviewDragging, ref cosReviewLastMouse);
            if (tex == null)
                GUI.Label(new Rect(prev.x, prev.center.y - 15, prev.width, 30), "  (preview failed to decode)", adminLabelStyle);

            float rx = prev.xMax + 14f;
            float rw = x + w - 12f - rx;
            GUI.Label(new Rect(rx, y + 194, rw, 24), $"Render scale: {s.render_scale:F2}x",
                new GUIStyle(adminLabelStyle) { fontSize = 15, fontStyle = FontStyle.Bold });
            s.render_scale = GUI.HorizontalSlider(
                new Rect(rx, y + 222, rw, 20), s.render_scale, 0.50f, 2.25f);
            s.render_scale = Mathf.Round(s.render_scale * 20f) / 20f;
            if (GUI.Button(new Rect(rx, y + 248, 42, 27), "-")) s.render_scale -= 0.05f;
            if (GUI.Button(new Rect(rx + 50, y + 248, 42, 27), "+")) s.render_scale += 0.05f;
            if (GUI.Button(new Rect(rx + 100, y + 248, Mathf.Max(64f, rw - 100f), 27), "Center"))
            {
                cosReviewPreviewOffset = Vector2.zero;  // visual only, never saved
            }
            s.render_scale = Mathf.Clamp(s.render_scale, 0.50f, 2.25f);
            // July 26 (Sid item 5): the drag is a preview-only visual aid — the
            // dragged position is NEVER saved (Approve sends offset 0,0, and
            // cosmetics always spawn centered). Players position items with
            // ROUNDS' own character-editor drag; artists compose placement
            // into the 512px canvas itself. Scale is the only reviewed number.
            GUI.Label(new Rect(rx, y + 282, rw, 38),
                "Drag to preview positions (visual aid only - the position is\nnever saved; items spawn centered and players drag them).",
                new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = true });
            // Re-placements: show the ORIGINAL (currently approved) scale beside
            // the proposed one so the change being reviewed is explicit.
            string approved = s.approved_placement_revision > 0
                ? $"Scale: {s.approved_render_scale:F2}x (current, rev {s.approved_placement_revision})"
                  + $"   ->   {s.render_scale:F2}x (proposed)"
                  + (Mathf.Abs(s.render_scale - s.approved_render_scale) < 0.005f
                      ? "   [unchanged]" : "")
                : $"First placement for this art — proposed scale {s.render_scale:F2}x.";
            GUI.Label(new Rect(rx, y + 324, rw, 34), approved,
                new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = true, fontStyle = FontStyle.Bold });
            float reasonY = y + h - 108f;
            GUI.Label(new Rect(rx, y + 360, rw, Mathf.Max(24f, reasonY - (y + 366))),
                "Approve saves the values shown here. New art and approved revisions take effect only after those exact values ship in a mod update.",
                new GUIStyle(adminLabelStyle) { fontSize = 11, wordWrap = true });
            GUI.Label(new Rect(x + 12, reasonY + 4, 130, 22), "Denial reason:", adminLabelStyle);
            float by = y + h - 46;
            cosReviewDenialReason = GUI.TextArea(
                new Rect(x + 142, reasonY, w - 154, Mathf.Max(42f, by - reasonY - 8f)),
                cosReviewDenialReason ?? "", 200,
                cosReviewReasonStyle);

            if (!cosReviewBusy && GUI.Button(new Rect(x + 12, by, 120, 32), "Approve"))
            {
                cosReviewBusy = true;
                int sid = s.id; string nm = s.name;
                ApiClient.AdminReviewCosmetic(
                    MatchTracker.LocalSteamId, sid, true, s.placement_revision,
                    s.render_scale, s.render_offset_x, s.render_offset_y, "", (ok, resp) =>  // stored proposal offset — the drag is never saved (item 5)
                {
                    cosReviewBusy = false;
                    if (!cosReviewOpen) return;
                    if (ok) { ShowNotification($"Approved '{nm}'.", new Color(0.4f, 0.9f, 0.5f), 5f); RemoveCosReview(sid); }
                    else ShowNotification("Approve failed: " + CosTrunc(resp, 90), new Color(1f, 0.45f, 0.4f), 6f);
                });
            }
            if (!cosReviewBusy && GUI.Button(new Rect(x + 142, by, 120, 32), "Deny"))
            {
                int sid = s.id; string nm = s.name;
                string note = (cosReviewDenialReason ?? "").Trim();
                if (string.IsNullOrEmpty(note))
                {
                    ShowNotification("Enter a denial reason first.", new Color(1f, 0.7f, 0.4f), 4f);
                }
                else
                {
                    cosReviewBusy = true;
                    ApiClient.AdminReviewCosmetic(
                        MatchTracker.LocalSteamId, sid, false, s.placement_revision,
                        s.render_scale, s.render_offset_x, s.render_offset_y, note, (ok, resp) =>  // stored proposal offset — the drag is never saved (item 5)
                    {
                        cosReviewBusy = false;
                        if (!cosReviewOpen) return;
                        if (ok) { ShowNotification($"Denied '{nm}'.", new Color(1f, 0.7f, 0.4f), 4f); RemoveCosReview(sid); }
                        else ShowNotification("Deny failed: " + CosTrunc(resp, 90), new Color(1f, 0.45f, 0.4f), 6f);
                    });
                }
            }
            if (subs.Count > 1 && GUI.Button(new Rect(x + w - 132, by, 120, 32), "Next >"))
            {
                cosReviewIdx = (cosReviewIdx + 1) % subs.Count;
                cosReviewDenialReason = "";
                cosReviewDragging = false;
            }
        }

        private static bool cosReleaseOpen = false;
        private static bool cosReleaseBusy = false;
        private static string cosReleaseStatus = "";
        private static Vector2 cosReleaseScroll = Vector2.zero;
        private static List<ApiClient.CosmeticReleaseCandidate> cosReleaseCandidates =
            new List<ApiClient.CosmeticReleaseCandidate>();

        public static void OpenCosmeticReleaseQueue()
        {
            if (cosReviewOpen) CloseCosmeticReview();
            cosReleaseOpen = true;
            cosReleaseBusy = true;
            cosReleaseStatus = "Loading approved cosmetics...";
            cosReleaseScroll = Vector2.zero;
            cosReleaseCandidates.Clear();
            ApiClient.FetchCosmeticReleaseCandidatesAdmin(
                MatchTracker.LocalSteamId, (ok, list, resp) =>
                {
                    cosReleaseBusy = false;
                    if (!cosReleaseOpen) return;
                    if (!ok)
                    {
                        cosReleaseStatus = "Fetch failed: " + CosTrunc(resp, 120);
                        return;
                    }
                    cosReleaseCandidates = list
                        ?? new List<ApiClient.CosmeticReleaseCandidate>();
                    cosReleaseStatus = cosReleaseCandidates.Count == 0
                        ? "Nothing is waiting for a client update."
                        : "";
                });
        }

        private static string CosReleaseSafe(string value)
        {
            return string.IsNullOrEmpty(value)
                ? ""
                : value.Replace("<", "[").Replace(">", "]");
        }

        private static void DrawCosmeticReleaseQueue()
        {
            if (!cosReleaseOpen) return;
            if (!NativeUI.IsOpen) { cosReleaseOpen = false; return; }
            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            {
                ev.Use();
                cosReleaseOpen = false;
                return;
            }
            if (adminLabelStyle == null)
                adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };

            float w = Mathf.Min(780f, Mathf.Max(520f, Screen.width - 24f));
            float h = Mathf.Min(600f, Mathf.Max(480f, Screen.height - 24f));
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(
                new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0, 0, 0, 0.96f), 0, 0);
            GUI.Label(
                new Rect(x + 12, y + 10, w - 118, 28),
                "Approved cosmetics awaiting a client update",
                new GUIStyle(adminLabelStyle)
                { fontSize = 17, fontStyle = FontStyle.Bold });
            if (GUI.Button(new Rect(x + w - 92, y + 10, 80, 28), "Close"))
            {
                cosReleaseOpen = false;
                return;
            }
            GUI.Label(
                new Rect(x + 12, y + 45, w - 24, 58),
                "This is the implementation queue. Approval saves an exact PNG, scale, and offset, "
                + "but installed clients do not change until those values are copied into the "
                + "append-only catalog and released. Rows disappear only after that revision is marked published.",
                new GUIStyle(adminLabelStyle) { fontSize = 12, wordWrap = true });

            if (cosReleaseBusy || cosReleaseCandidates.Count == 0)
            {
                GUI.Label(
                    new Rect(x + 12, y + 112, w - 150, 30),
                    string.IsNullOrEmpty(cosReleaseStatus) ? "..." : cosReleaseStatus,
                    adminLabelStyle);
                if (!cosReleaseBusy
                    && GUI.Button(new Rect(x + w - 132, y + 108, 120, 28), "Refresh"))
                    OpenCosmeticReleaseQueue();
                return;
            }

            float listY = y + 108f;
            float listH = h - 158f;
            float rowH = 104f;
            float innerW = w - 45f;
            cosReleaseScroll = GUI.BeginScrollView(
                new Rect(x + 12, listY, w - 24, listH),
                cosReleaseScroll,
                new Rect(0, 0, innerW,
                    Mathf.Max(listH - 2f, cosReleaseCandidates.Count * rowH)));
            for (int i = 0; i < cosReleaseCandidates.Count; i++)
            {
                var c = cosReleaseCandidates[i];
                float ry = i * rowH;
                GUI.DrawTexture(
                    new Rect(0, ry, innerW, rowH - 6f),
                    Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                    new Color(0.11f, 0.13f, 0.17f, 0.98f), 0, 4);
                string kind = c.catalog_ready
                    ? "PLACEMENT UPDATE"
                    : "NEW COSMETIC";
                string status = c.catalog_ready
                    ? $"Published rev {c.published_placement_revision} remains live"
                    : "Not yet available in any released client";
                GUI.Label(
                    new Rect(10, ry + 7, innerW - 20, 23),
                    $"<b>{kind}</b>  #{c.id}  {CosReleaseSafe(c.name)} "
                    + $"<color=#888>by {CosReleaseSafe(c.artist_name)}</color>",
                    new GUIStyle(adminLabelStyle)
                    { fontSize = 14, richText = true });
                GUI.Label(
                    new Rect(10, ry + 31, innerW - 20, 21),
                    $"{CosReleaseSafe(c.shop_sku)}  <color=#888>({c.slot}, "
                    + $"{Mathf.Max(0, c.png_bytes) / 1024} KB)</color>",
                    new GUIStyle(adminLabelStyle)
                    { fontSize = 12, richText = true });
                GUI.Label(
                    new Rect(10, ry + 53, innerW - 20, 21),
                    // Scale is what the integrator must transcribe into
                    // CustomCosmetics.cs; offset is only a default start position
                    // the player can drag, so it stays out of this tracker line.
                    $"Approved rev {c.placement_revision}: {c.render_scale:F2}x",
                    new GUIStyle(adminLabelStyle)
                    { fontSize = 13, fontStyle = FontStyle.Bold });
                GUI.Label(
                    new Rect(10, ry + 75, innerW - 20, 20),
                    $"<color=#FFD94D>{status}</color>",
                    new GUIStyle(adminLabelStyle)
                    { fontSize = 12, richText = true });
            }
            GUI.EndScrollView();

            GUI.Label(
                new Rect(x + 12, y + h - 38, w - 160, 25),
                $"{cosReleaseCandidates.Count} approved revision(s) waiting",
                adminLabelStyle);
            if (GUI.Button(new Rect(x + w - 132, y + h - 42, 120, 30), "Refresh"))
                OpenCosmeticReleaseQueue();
        }

        private static bool flagEvidenceOpen = false;
        private static bool flagEvidenceBusy = false;
        private static bool flagRepairConfirm = false;
        private static ApiClient.FlaggedMatchEntry flagEvidenceEntry;
        private static Vector2 flagEvidenceScroll = Vector2.zero;

        public static void OpenFlagEvidence(ApiClient.FlaggedMatchEntry entry)
        {
            if (entry == null) return;
            flagEvidenceEntry = entry;
            flagEvidenceScroll = Vector2.zero;
            flagEvidenceBusy = false;
            flagRepairConfirm = false;
            flagEvidenceOpen = true;
        }

        private static void CloseFlagEvidence()
        {
            flagEvidenceOpen = false;
            flagEvidenceBusy = false;
            flagRepairConfirm = false;
            flagEvidenceEntry = null;
        }

        private static void SubmitFlagEvidenceVerdict(string action)
        {
            var entry = flagEvidenceEntry;
            string adminId = MatchTracker.LocalSteamId;
            if (entry == null || string.IsNullOrEmpty(entry.id) || string.IsNullOrEmpty(adminId)) return;
            flagEvidenceBusy = true;
            ApiClient.AdminReviewFlag(
                adminId, entry.id, action, entry.discord_evidence_revision,
                (ok, resp) =>
            {
                flagEvidenceBusy = false;
                if (!flagEvidenceOpen || flagEvidenceEntry != entry) return;
                if (!ok)
                {
                    ShowNotification("Flag review failed: " + CosTrunc(resp, 100),
                        new Color(1f, 0.45f, 0.4f), 6f);
                    return;
                }
                bool restorationRequired = resp != null
                    && (resp.Contains("\"restoration_required\":true")
                        || resp.Contains("\"restoration_required\": true"));
                ShowNotification(
                    restorationRequired
                        ? "Marked false positive. You still need to repair the rewards and series by hand."
                        : action == "confirmed_cheat"
                            ? "Flag marked as confirmed."
                            : "Flag marked false positive.",
                    restorationRequired
                        ? new Color(1f, 0.72f, 0.32f)
                        : new Color(0.45f, 0.9f, 0.55f),
                    restorationRequired ? 9f : 5f);
                CloseFlagEvidence();
                ApiClient.FetchFlaggedMatches(adminId);
            });
        }

        private static void SubmitFlagRestorationComplete()
        {
            var entry = flagEvidenceEntry;
            string adminId = MatchTracker.LocalSteamId;
            if (entry == null || !entry.restoration_required
                || string.IsNullOrEmpty(entry.id) || string.IsNullOrEmpty(adminId)) return;
            flagEvidenceBusy = true;
            ApiClient.AdminResolveFlagRestoration(adminId, entry.id, (ok, resp) =>
            {
                flagEvidenceBusy = false;
                if (!flagEvidenceOpen || flagEvidenceEntry != entry) return;
                if (!ok)
                {
                    ShowNotification("Could not close repair reminder: " + CosTrunc(resp, 100),
                        new Color(1f, 0.45f, 0.4f), 6f);
                    return;
                }
                ShowNotification("Manual restoration marked complete.",
                    new Color(0.45f, 0.9f, 0.55f), 5f);
                CloseFlagEvidence();
                ApiClient.FetchFlaggedMatches(adminId);
            });
        }

        private static void DrawFlagEvidence()
        {
            if (!flagEvidenceOpen) return;
            if (!NativeUI.IsOpen || flagEvidenceEntry == null) { CloseFlagEvidence(); return; }
            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            { ev.Use(); CloseFlagEvidence(); return; }
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };
            var e = flagEvidenceEntry;
            float w = Mathf.Min(920f, Mathf.Max(540f, Screen.width - 24f));
            float h = Mathf.Min(700f, Mathf.Max(500f, Screen.height - 24f));
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0, 0, 0, 0.96f), 0, 0);
            var titleStyle = new GUIStyle(adminLabelStyle)
                { fontSize = 17, fontStyle = FontStyle.Bold, richText = false };
            GUI.Label(new Rect(x + 12, y + 10, w - 112, 28),
                $"Flag evidence: {e.flag_reason}", titleStyle);
            if (GUI.Button(new Rect(x + w - 90, y + 10, 78, 26), "Close"))
            { CloseFlagEvidence(); return; }

            string participants =
                $"{e.p1_name} [{e.p1_steam_id}]\n{e.p2_name} [{e.p2_steam_id}]\n"
                + $"Suspect(s): {e.suspect_steam_text}";
            string match =
                $"{(e.is_ranked ? "Ranked" : "Casual")} | game code {e.game_code} | match {e.match_id}"
                + (string.IsNullOrEmpty(e.series_id) ? "" : $" | series {e.series_id}")
                + $"\n{e.score_summary}\n"
                + $"Detector action: {(e.auto_invalidated ? "auto-invalidated" : "advisory only")}; "
                + $"match is currently {(e.match_invalidated ? "invalidated" : "valid")}"
                + (e.match_invalidated && !string.IsNullOrEmpty(e.match_invalidation_reason)
                    ? $" ({e.match_invalidation_reason})" : "")
                + "."
                + (e.restoration_required
                    ? "\nFALSE POSITIVE RECORDED — manual reward/series repair remains required."
                        + (flagRepairConfirm
                            ? "\nCONFIRM ONLY after rewards, rating, and series state have been repaired."
                            : "")
                    : "");
            string[] headings = {
                "Participants / Steam IDs", "Match and point state", "Detector evidence",
                "Point progression", "Cards picked", "Combat and input telemetry",
                "FPS / connection telemetry", "Reporter context"
            };
            string[] bodies = {
                participants, match, e.evidence_summary, e.point_progress,
                e.cards_summary, e.telemetry_summary, e.connection_summary, e.match_context
            };
            var headingStyle = new GUIStyle(adminLabelStyle)
                { fontSize = 13, fontStyle = FontStyle.Bold, richText = false };
            var bodyStyle = new GUIStyle(adminLabelStyle)
                { fontSize = 12, wordWrap = true, richText = false };
            float contentW = w - 54f;
            float contentH = 10f;
            for (int i = 0; i < headings.Length; i++)
            {
                contentH += 20f;
                contentH += Mathf.Max(22f, bodyStyle.CalcHeight(
                    new GUIContent(bodies[i] ?? "not recorded"), contentW));
                contentH += 10f;
            }
            Rect view = new Rect(x + 12, y + 46, w - 24, h - 104);
            flagEvidenceScroll = GUI.BeginScrollView(
                view, flagEvidenceScroll, new Rect(0, 0, view.width - 18, contentH));
            float cy = 4f;
            for (int i = 0; i < headings.Length; i++)
            {
                GUI.Label(new Rect(4, cy, contentW, 20), headings[i], headingStyle);
                cy += 20f;
                string body = string.IsNullOrEmpty(bodies[i]) ? "not recorded" : bodies[i];
                float bh = Mathf.Max(22f, bodyStyle.CalcHeight(new GUIContent(body), contentW));
                GUI.Label(new Rect(4, cy, contentW, bh), body, bodyStyle);
                cy += bh + 10f;
            }
            GUI.EndScrollView();

            float by = y + h - 46f;
            if (GUI.Button(new Rect(x + 12, by, 92, 30), "Copy P1 ID"))
                GUIUtility.systemCopyBuffer = e.p1_steam_id ?? "";
            if (GUI.Button(new Rect(x + 112, by, 92, 30), "Copy P2 ID"))
                GUIUtility.systemCopyBuffer = e.p2_steam_id ?? "";
            if (GUI.Button(new Rect(x + 212, by, 104, 30), "Copy game ID"))
                GUIUtility.systemCopyBuffer = e.game_code ?? e.match_id ?? "";
            if (e.restoration_required)
            {
                if (!flagEvidenceBusy && !flagRepairConfirm && GUI.Button(
                        new Rect(x + w - 182, by, 170, 30), "Mark repair complete..."))
                    flagRepairConfirm = true;
                else if (!flagEvidenceBusy && flagRepairConfirm)
                {
                    if (GUI.Button(new Rect(x + w - 292, by, 140, 30), "Not repaired yet"))
                        flagRepairConfirm = false;
                    if (GUI.Button(new Rect(x + w - 142, by, 130, 30), "Repair is done"))
                        SubmitFlagRestorationComplete();
                }
            }
            else
            {
                if (!flagEvidenceBusy && GUI.Button(
                        new Rect(x + w - 292, by, 140, 30),
                        e.auto_invalidated ? "False+ (manual fix)" : "False positive"))
                    SubmitFlagEvidenceVerdict("false_positive");
                if (!flagEvidenceBusy && GUI.Button(
                        new Rect(x + w - 142, by, 130, 30), "Confirm cheat"))
                    SubmitFlagEvidenceVerdict("confirmed_cheat");
            }
        }

        private static void DrawArtistInput()
        {
            if (!artistPromptOpen) return;
            if (!NativeUI.IsOpen) { artistPromptOpen = false; artistPromptOnSubmit = null; return; }
            var ev = Event.current;
            bool submit = false, cancel = false;
            if (ev != null && ev.type == EventType.KeyDown)
            {
                if (ev.keyCode == KeyCode.Escape) { cancel = true; ev.Use(); }
                else if (ev.keyCode == KeyCode.Return || ev.keyCode == KeyCode.KeypadEnter) { submit = true; ev.Use(); }
            }
            if (adminFieldStyle == null) adminFieldStyle = new GUIStyle(GUI.skin.textField) { fontSize = 15 };
            if (adminLabelStyle == null) adminLabelStyle = new GUIStyle(GUI.skin.label) { fontSize = 14 };

            float w = 520, h = 168;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.93f), 0, 0);
            GUI.Label(new Rect(x + 12, y + 10, w - 24, 26), artistPromptTitle,
                new GUIStyle(adminLabelStyle) { fontSize = 17, fontStyle = FontStyle.Bold });
            GUI.Label(new Rect(x + 12, y + 44, w - 24, 20), artistPromptLabel, adminLabelStyle);
            artistPromptValue = GUI.TextField(new Rect(x + 12, y + 68, w - 24, 28), artistPromptValue ?? "", adminFieldStyle);
            if (GUI.Button(new Rect(x + 12, y + h - 40, 110, 30), I18n.Tr("Cancel"))) cancel = true;
            if (GUI.Button(new Rect(x + w - 122, y + h - 40, 110, 30), I18n.Tr("Submit"))) submit = true;

            if (cancel) { artistPromptOpen = false; artistPromptOnSubmit = null; return; }
            if (submit)
            {
                var cb = artistPromptOnSubmit;
                string v = artistPromptValue;
                artistPromptOpen = false; artistPromptOnSubmit = null;
                try { cb?.Invoke(v?.Trim() ?? ""); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[ARTIST] prompt action: {ex.Message}"); }
            }
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

            if (GUI.Button(new Rect(x + 10, y + h - 36, 100, 28), I18n.Tr("Cancel"))) cancel = true;
            if (GUI.Button(new Rect(x + w - 110, y + h - 36, 100, 28), I18n.Tr("Submit"))) submit = true;

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

        // DISPLAY labels for the severity/category buttons. The arrays above
        // are the API wire contract and must stay English (SubmitBugReportNow
        // sends them verbatim); only the button face is translated, keyed by
        // wire value. "UI" is under the extractor's 3-letter floor (#295c) so
        // it can never become a catalogue key — Tr passes it through, which is
        // acceptable for a universal abbreviation.
        private static string BugChoiceLabel(string wire)
        {
            switch (wire)
            {
                case "low":      return I18n.Tr("LOW");
                case "medium":   return I18n.Tr("MEDIUM");
                case "high":     return I18n.Tr("HIGH");
                case "crash":    return I18n.Tr("CRASH");
                case "ui":       return I18n.Tr("UI");
                case "gameplay": return I18n.Tr("GAMEPLAY");
                case "network":  return I18n.Tr("NETWORK");
                case "other":    return I18n.Tr("OTHER");
                default:         return (wire ?? "").ToUpper();
            }
        }
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

            GUI.Label(new Rect(x, y, w, 28), I18n.Tr("<color=#FFE580>Report a Bug</color>"), bugTitleStyle);
            GUI.Label(new Rect(x, y + 30, w, 18),
                I18n.Tr("<color=#AAAAAA>Reports go to the mod team. Be specific — what happened, when, what you were doing.</color>"),
                bugLabelStyle);

            // Severity row
            GUI.Label(new Rect(x, y + 56, 120, 22), "<b>" + I18n.Tr("Severity:") + "</b>", bugLabelStyle);
            for (int i = 0; i < BUG_SEVERITIES.Length; i++)
            {
                bool picked = i == bugSeverityIdx;
                if (GUI.Button(new Rect(x + 100 + i * 88, y + 54, 84, 26),
                               BugChoiceLabel(BUG_SEVERITIES[i]),
                               picked ? bugBtnPickedStyle : bugButtonStyle))
                    bugSeverityIdx = i;
            }

            // Category row
            GUI.Label(new Rect(x, y + 92, 120, 22), "<b>" + I18n.Tr("Category:") + "</b>", bugLabelStyle);
            for (int i = 0; i < BUG_CATEGORIES.Length; i++)
            {
                bool picked = i == bugCategoryIdx;
                if (GUI.Button(new Rect(x + 100 + i * 88, y + 90, 84, 26),
                               BugChoiceLabel(BUG_CATEGORIES[i]),
                               picked ? bugBtnPickedStyle : bugButtonStyle))
                    bugCategoryIdx = i;
            }

            // Description (required)
            GUI.Label(new Rect(x, y + 126, w, 18), I18n.Tr("<b>What happened?</b> <color=#FF9966>(required)</color>"), bugLabelStyle);
            bugDescScroll = GUI.BeginScrollView(new Rect(x, y + 146, w, 140),
                                                bugDescScroll,
                                                new Rect(0, 0, w - 20, Mathf.Max(140, (bugDescription?.Length ?? 0) / 4)));
            bugDescription = GUI.TextArea(new Rect(0, 0, w - 20, Mathf.Max(140, (bugDescription?.Length ?? 0) / 4)),
                                          bugDescription ?? "", 4000, bugAreaStyle);
            GUI.EndScrollView();

            // Repro
            GUI.Label(new Rect(x, y + 296, w, 18), I18n.Tr("<b>How to reproduce?</b> <color=#888>(optional)</color>"), bugLabelStyle);
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
                      I18n.Tr("Attach game logs (recommended)"),
                      bugLabelStyle);
            // Preview button far to the right of the toggle hit area + a gap.
            float prevX = togX + togW + 16;
            if (GUI.Button(new Rect(prevX, y + 428, 140, 24), I18n.Tr("Preview logs"), bugButtonStyle))
            {
                OpenLogViewer();
            }

            // Status line
            if (!string.IsNullOrEmpty(bugSubmitStatus))
                GUI.Label(new Rect(x, y + 460, w, 20), bugSubmitStatus, bugLabelStyle);

            // Buttons
            bool disabled = bugSubmitting || string.IsNullOrEmpty(bugDescription) || bugDescription.Trim().Length < 4;
            GUI.enabled = !bugSubmitting;
            if (GUI.Button(new Rect(x, y + h - 44, 120, 30), I18n.Tr("Cancel"), bugButtonStyle))
            {
                bugModalOpen = false; GUI.enabled = true; return;
            }
            GUI.enabled = !disabled;
            if (GUI.Button(new Rect(x + w - 160, y + h - 44, 160, 30),
                           bugSubmitting ? I18n.Tr("Submitting...") : I18n.Tr("Submit Report"),
                           bugButtonStyle))
            {
                SubmitBugReportNow();
            }
            GUI.enabled = true;
        }

        private static void SubmitBugReportNow()
        {
            bugSubmitting = true;
            bugSubmitStatus = "<color=#88CCFF>" + I18n.Tr("Submitting...") + "</color>";
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
                        bugSubmitStatus = bn > 0
                            ? I18n.TrF("<color=#88FF88>Sent! Thank you. Filed as <b>#{0}</b>.</color>", bn)
                            : I18n.Tr("<color=#88FF88>Sent! Thank you.</color>");
                        bugDescription = "";
                        bugRepro = "";
                        string notif = bn > 0 ? I18n.TrF("Bug report sent. Thanks! (#{0})", bn)
                                              : I18n.Tr("Bug report sent. Thanks!");
                        ShowNotification(notif, new Color(0.5f, 1f, 0.5f), 5f);
                        bugModalOpen = false;
                    }
                    else
                    {
                        // The failure detail is server-sent English (class D) —
                        // it stays raw inside the translated template's hole.
                        // Colour lives OUTSIDE the translated literal so the key is
                        // the plain sentence. Baked-in markup made this the same
                        // message as NativeUI's "Failed: {0}" under two different
                        // keys, so translators had to translate it twice (reported
                        // by a translator, 2026-08-07).
                        bugSubmitStatus = "<color=#FF6666>"
                                        + I18n.TrF("Failed: {0}", (resp ?? "").Replace("\n", " "))
                                        + "</color>";
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

            GUI.Label(new Rect(x, y, w, 24), I18n.Tr("<b>Game logs (tail)</b> — included with your report when the box is checked."),
                      bugLabelStyle ?? GUI.skin.label);

            // Tab labels kept short so they fit inside the buttons without clipping
            // — earlier "BepInEx (previous session)" cut off the trailing "n)".
            if (GUI.Button(new Rect(x, y + 28, 160, 26), I18n.Tr("BepInEx (current)"),
                           logViewerTab == 0 ? logViewerTabActiveStyle : logViewerTabStyle))
                logViewerTab = 0;
            if (GUI.Button(new Rect(x + 168, y + 28, 180, 26), I18n.Tr("BepInEx (prev session)"),
                           logViewerTab == 1 ? logViewerTabActiveStyle : logViewerTabStyle))
                logViewerTab = 1;
            if (GUI.Button(new Rect(x + 356, y + 28, 140, 26), I18n.Tr("Unity / Game"),
                           logViewerTab == 2 ? logViewerTabActiveStyle : logViewerTabStyle))
                logViewerTab = 2;
            if (GUI.Button(new Rect(x + w - 200, y + 28, 90, 26), I18n.Tr("Refresh"), logViewerTabStyle))
            {
                logViewerBepCache     = ApiClient.ReadLogTail(BepInExLogPath(), maxChars: 400_000);
                logViewerBepPrevCache = ApiClient.ReadLogTail(BepInExLogPreviousPath(), maxChars: 400_000);
                logViewerUniCache     = ApiClient.ReadLogTail(UnityLogPath(), maxChars: 400_000);
            }
            if (GUI.Button(new Rect(x + w - 100, y + 28, 100, 26), I18n.Tr("Close"), logViewerTabStyle))
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
                    body = I18n.TrF("(no previous-session log yet — gets written by the mod when ROUNDS is closed cleanly, so on first ever launch this is empty)\n\nExpected path: {0}",
                                    path ?? I18n.Tr("unknown"));
                else
                    body = I18n.TrF("(no log content read from: {0})", path ?? I18n.Tr("unknown path"));
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
                if (!selected.activeInHierarchy) return false;
                foreach (var co in selected.GetComponents<Component>())
                {
                    if (co == null) continue;
                    string n = co.GetType().Name;
                    if (n != "InputField" && n != "TMP_InputField" && !n.EndsWith("InputField"))
                        continue;
                    // v1.33 root fix (Sid's item 5, "chat sometimes disables itself"):
                    // the old check used isActiveAndEnabled, but a field stays SELECTED
                    // + enabled long after the user stops typing (ROUNDS never clears
                    // EventSystem.currentSelectedGameObject) — so T went permanently
                    // dead after touching any input field. isFocused is the signal
                    // that actually means "this field is consuming keystrokes": true
                    // only while the caret is live. Both InputField and TMP_InputField
                    // expose it; unknown InputField-ish types fall back to the old
                    // conservative isActiveAndEnabled check.
                    var focProp = co.GetType().GetProperty("isFocused",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                    if (focProp != null)
                    {
                        if ((bool)focProp.GetValue(co)) return true;
                        continue;
                    }
                    var isAEProp = co.GetType().GetProperty("isActiveAndEnabled",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                    if (isAEProp != null && (bool)isAEProp.GetValue(co)) return true;
                }
                return false;
            }
            catch { return false; }
        }

        // ── Vanilla "Enter" chat detection (bug #128) ────────────
        // ROUNDS' own chat is `DevConsole`. Its Update() is literally
        //     if (Input.GetKeyDown(KeyCode.Return)) ToggleConsole();
        // and ToggleConsole() does
        //     inputField.gameObject.SetActive(!active);
        //     isTyping = inputField.gameObject.activeSelf;
        //     GameManager.lockInput = isTyping;
        // so `DevConsole.isTyping` is a game-authored, exact "the Enter chat is
        // consuming keystrokes" signal. That — and ONLY that — may suppress our
        // T chat: the old active-combat gate was a bandaid that made T dead for
        // the whole match (Sid's report).
        //
        // Read by reflection rather than as a direct `DevConsole.isTyping`: the
        // type carries a `public TMP_InputField inputField` field and this csproj
        // deliberately references no TMPro assembly (learning #15). Reflection
        // also degrades the right way — a failed lookup returns false, i.e.
        // "vanilla chat is not typing", i.e. our chat stays available.
        private static System.Reflection.FieldInfo s_devConsoleIsTyping;
        private static bool s_devConsoleLookedUp;
        private static System.Reflection.FieldInfo DevConsoleIsTypingField()
        {
            if (s_devConsoleLookedUp) return s_devConsoleIsTyping;
            s_devConsoleLookedUp = true;
            try
            {
                Type dc = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    try { dc = asm.GetType("DevConsole"); } catch { }
                    if (dc != null) break;
                }
                if (dc != null)
                    s_devConsoleIsTyping = dc.GetField("isTyping",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
            }
            catch { }
            // Learning #83: a reflection lookup that silently fails is a
            // forever-no-op. Say which way it went, once, at first use.
            Plugin.Log.LogInfo(s_devConsoleIsTyping != null
                ? "[CHAT] Vanilla chat detection armed (DevConsole.isTyping)"
                : "[CHAT] DevConsole.isTyping NOT found — T chat will not defer to the Enter chat");
            return s_devConsoleIsTyping;
        }

        /// <summary>True while ROUNDS' OWN Enter chat is consuming keystrokes.
        /// Masked while we hold the flag ourselves (see SetGameplayInputLock) so
        /// this always answers the question it's named after.</summary>
        private static bool IsVanillaChatTyping()
        {
            try
            {
                var f = DevConsoleIsTypingField();
                if (f == null) return false;
                return (bool)f.GetValue(null) && !weHoldTypingFlag;
            }
            catch { return false; }
        }

        /// <summary>True while EITHER chat box is taking keystrokes. The telemetry
        /// and achievement input gates need this rather than just our own box:
        /// a left-click to place the caret in ROUNDS' Enter chat still counted as
        /// a shot fired, which is the accuracy DENOMINATOR (#137).</summary>
        public static bool AnyChatTyping => chatInputOpen || quickChatOpen || IsVanillaChatTypingRaw();

        // The vanilla box's own truth, unmasked — used both by AnyChatTyping and
        // as the authoritative value to restore isTyping to when we let go.
        private static bool IsVanillaChatTypingRaw()
        {
            try
            {
                var f = DevConsoleIsTypingField();
                return f != null && (bool)f.GetValue(null);
            }
            catch { return false; }
        }

        // Is vanilla's chat input field ACTUALLY on screen? `isTyping` is a
        // mirror we may be holding, but `inputField.gameObject.activeSelf` is
        // what ToggleConsole itself derives isTyping from, so it is the only
        // honest answer to "does vanilla currently own a text box?" — and
        // therefore the only safe value to restore isTyping to (a blind `false`
        // can leave a live, focused vanilla field with gameplay input ON).
        // Reached as a plain Component so no TMPro reference is needed.
        private static object s_devConsoleInstance;
        private static System.Reflection.FieldInfo s_devConsoleField;
        private static bool VanillaChatBoxActive()
        {
            try
            {
                Type dc = DevConsoleIsTypingField()?.DeclaringType;
                if (dc == null) return false;
                var inst = s_devConsoleInstance as UnityEngine.Object;
                if (inst == null)
                {
                    s_devConsoleInstance = UnityEngine.Object.FindObjectOfType(dc);
                    inst = s_devConsoleInstance as UnityEngine.Object;
                    if (inst == null) return false;
                }
                if (s_devConsoleField == null)
                    s_devConsoleField = dc.GetField("inputField",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                var field = s_devConsoleField?.GetValue(s_devConsoleInstance) as Component;
                return field != null && field.gameObject.activeSelf;
            }
            catch { return false; }
        }

        /// <summary>True while vanilla's chat box is on screen — used by the
        /// ToggleConsole guard so Enter can ALWAYS close a genuinely-open vanilla
        /// box even if our own box somehow stayed open at the same time.</summary>
        internal static bool VanillaChatBoxOnScreen => VanillaChatBoxActive();

        // While our chat box has focus we hold ROUNDS' own two "a text field owns
        // the keyboard" flags — exactly the pair DevConsole.ToggleConsole sets:
        //
        //   GameManager.lockInput  — GeneralInput.Update() early-returns on it
        //                            before reading Move/Aim/shoot/block, so
        //                            typing "wasd" can't drive the player.
        //   DevConsole.isTyping    — PlayerAssigner.LateUpdate() early-returns on
        //                            it before its raw Space/B reads, so a SPACE
        //                            inside a message can't ready-up or spawn a
        //                            local player. lockInput does NOT cover that
        //                            path; only isTyping does.
        //
        // Deliberately NOT PlayerManager.SetInputActive — that path NREs on
        // half-wired players (learning #75). Asserted every IMGUI frame from our
        // own state so no early-return path can strand the flags on; ROUNDS also
        // zeroes both on scene load / quit-to-menu, which is a free self-heal.
        private static bool gameplayInputLockHeld;
        private static bool weHoldTypingFlag;
        private static void SetGameplayInputLock(bool on)
        {
            try
            {
                if (on)
                {
                    gameplayInputLockHeld = true;
                    GameManager.lockInput = true;
                    var f = DevConsoleIsTypingField();
                    if (f != null) { f.SetValue(null, true); weHoldTypingFlag = true; }
                }
                else if (gameplayInputLockHeld)
                {
                    gameplayInputLockHeld = false;
                    // Restore to what VANILLA wants, never to a blind false.
                    // If DevConsoleToggleGuardPatch failed to attach (learning
                    // #83 — per-class patch failures are non-fatal and only
                    // logged), an Enter could have opened the real box under us;
                    // clearing both flags then would leave a live, focused
                    // vanilla text field with gameplay input fully ENABLED —
                    // WASD would type AND move. inputField.activeSelf is the
                    // same source ToggleConsole itself derives isTyping from.
                    bool vanillaWants = VanillaChatBoxActive();
                    if (weHoldTypingFlag)
                    {
                        weHoldTypingFlag = false;
                        var f = DevConsoleIsTypingField();
                        if (f != null) f.SetValue(null, vanillaWants);
                    }
                    GameManager.lockInput = vanillaWants;
                }
            }
            catch { gameplayInputLockHeld = false; weHoldTypingFlag = false; }
        }

        // Bug #128 / spec FINDING 6: every assert and release of the two input
        // flags lives inside DrawChatInput, which is the EIGHTH call in DrawUI —
        // and Plugin.OnGUI has no try/catch. A throw in any earlier overlay while
        // the box is open would mean DrawChatInput never runs again, stranding
        // lockInput + isTyping true and the ToggleConsole guard armed: no
        // movement, no shooting, no ready-up, and no way to open the vanilla chat
        // to break out (learnings #75/#82's exact symptom, self-inflicted).
        // So: stamp every draw, and force-close from two paths that cannot be
        // starved by a mid-DrawUI throw — the very top of DrawUI, and Tick().
        private static float chatDrawStampedAt = -999f;
        internal static void TickChatLockWatchdog()
        {
            try
            {
                if (!chatInputOpen && !gameplayInputLockHeld) return;
                if (Time.unscaledTime - chatDrawStampedAt < 0.5f) return;
                Plugin.Log.LogWarning("[CHAT] chat box went unrendered for >0.5s — "
                                      + "force-closing and releasing the input lock");
                quickChatOpen = false;   // the popup shares the lock (§2.6)
                // Forced close: an upstream throw starved the renderer. The
                // player never ended their message, so keep it (F4).
                CloseChatInput(discardDraft: false);
            }
            catch { }
        }

        // Aug-3 review F4: a half-typed message survives an INCIDENTAL close.
        // Every path that stops rendering the box funnels through
        // CloseChatInput (see its summary) and CloseChatInput used to clear the
        // text unconditionally — so opening the "Change view" / "Typing
        // channel" pickers, which register as ArtistPromptOpen modals and trip
        // the modal guard below, silently ate whatever the player had typed.
        // The distinction is INTENT, not call site: Esc and a successful send
        // end the message, so they discard; a close FORCED on us (a modal
        // taking the keyboard, vanilla's Enter box, the liveness watchdog)
        // stashes it and the next open resumes.
        private static string chatDraftStash;
        private static float chatDraftStashAt = -999f;
        // Ceiling on a resumed draft. The stash only ever bridges an
        // involuntary interruption — a picker round-trip, a yield to vanilla
        // chat — which is a seconds-scale detour, so 3 minutes is generous for
        // "went to look at the channel list and came back" while being far too
        // short to resurrect a forgotten line in what is effectively a later
        // sitting. Time.unscaledTime is the right clock here: monotonic from
        // game start, unaffected by scene loads AND by the pick-phase slow-mo
        // that makes Time.time crawl (#221).
        private const float CHAT_DRAFT_STASH_TTL = 180f;

        /// <summary>Returns a stashed draft to resume (one-shot — the stash is
        /// consumed either way), or "" when there is none or it has expired.</summary>
        private static string TakeStashedDraft()
        {
            string d = chatDraftStash;
            chatDraftStash = null;
            if (string.IsNullOrEmpty(d)) return "";
            if (Time.unscaledTime - chatDraftStashAt > CHAT_DRAFT_STASH_TTL) return "";
            return d;
        }

        /// <summary>Closes the chat box and releases the gameplay-input lock.
        /// Every path that stops rendering the box must come through here.
        /// <paramref name="discardDraft"/> is deliberately REQUIRED, not
        /// defaulted: a future close path that quietly inherits the wrong
        /// intent is exactly how F4 happened, so every caller has to say which
        /// it is.</summary>
        private static void CloseChatInput(bool discardDraft)
        {
            if (discardDraft) chatDraftStash = null;
            // Only overwrite the stash when there is something to stash. The
            // modal and consent guards call this EVERY frame the modal is up,
            // and by the second call chatInputText is already "" — an
            // unconditional write there would erase the draft one frame after
            // saving it, which is the original bug with extra steps.
            else if (!string.IsNullOrEmpty(chatInputText) && chatInputText.Trim().Length > 0)
            {
                chatDraftStash = chatInputText;
                chatDraftStashAt = Time.unscaledTime;
            }
            chatInputOpen = false;
            chatJustOpened = false;
            chatInputText = "";
            // Item 13: never carry a half-observed shift hold into the next
            // time the box opens — a KeyUp we never saw would otherwise leave
            // the tap armed and switch channels on the next release.
            chatAltHeld = false;
            chatAltTapClean = false;
            // Disarm the resume-caret window with the box — it is re-armed by
            // the next open that actually resumes something.
            chatCaretToEndUntil = -999f;
            SetGameplayInputLock(false);
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

        // §2.6: display label for a send channel's WIRE value ("global"/"es"/
        // "ru" — the wire strings stay English everywhere; this maps them for
        // the chat header's {0} hole only).
        //
        // Item 13: this used to render "Global/ES/RU" while
        // NativeUI.ChatChannelDisplayName rendered "Global/Español/Русский" for
        // the SAME wire values, so the F5 Home picker and this header named the
        // channels differently. Both now use the endonyms. They are deliberately
        // NOT passed through Tr — a language names itself the same way in every
        // locale — and "ES"/"RU" were never translatable anyway (under the
        // extractor's 3-letter floor, #295c). "global" reads "English" rather
        // than "Global" because this label names the channel you are TYPING
        // into, and beside two endonyms the language is the useful word.
        private static string ChannelDisplayLabel(string channel)
        {
            switch (channel)
            {
                case "global": return I18n.Tr("English");
                case "es":     return "Español";
                case "ru":     return "Русский";
                default:       return (channel ?? "").ToUpperInvariant();
            }
        }

        // Item 13: the send channel rotates through the FULL allowed set
        // (ChatClient.IsAllowedChannel), not just this locale's channel — an
        // English client can type into es/ru too, which is the whole point of
        // the change. Hoisted so the rotation allocates nothing per keystroke.
        private static readonly string[] ChatSendCycle = { "global", "es", "ru" };
        private static void CycleChatSendChannel()
        {
            string cur = ChatClient.SendChannel;
            int idx = -1;
            for (int i = 0; i < ChatSendCycle.Length; i++)
                if (ChatSendCycle[i] == cur) { idx = i; break; }
            // idx == -1 (a stale/unknown value) lands on "global".
            ChatClient.SendChannel = ChatSendCycle[(idx + 1) % ChatSendCycle.Length];
            chatHeaderCache = null;
        }

        // Shift-tap state for the channel cycle (see the KeyUp handler in
        // DrawChatInput for why a tap, not a press, is the trigger).
        private static bool chatAltHeld, chatAltTapClean;
        private static float chatAltDownAt;
        // F4 companion, armed only when a stashed draft is resumed. Runtime
        // IMGUI's TextEditor.DetectFocusChange calls OnFocus() -> SelectAll()
        // on a single-line field the frame after keyboard focus lands, which is
        // invisible for the normal empty open but would leave a RESUMED draft
        // fully selected — the player's first keystroke would then replace it,
        // i.e. the draft would look preserved and vanish anyway. Deadline (not
        // a bool) so it can never stick: if the editor never shows up we simply
        // stop trying after a second. See the block below the TextField.
        private static float chatCaretToEndUntil = -999f;
        // Header memo: TrF + string.Format on every IMGUI event (OnGUI runs
        // 2+ times a frame, #162) for a line that changes only when the send
        // channel, the locale, or the translation DATA changes.
        //
        // Aug-3 review F10: (channel, locale) was not a complete key. A server
        // pack arriving mid-session changes the effective translation without
        // touching either, so the header kept the bundled English/stale line
        // for as long as the box stayed open — the "cleared when the box opens"
        // escape hatch only bounded it to one chat session, and NativeUI's
        // repaint doesn't reach an IMGUI memo. I18n.CatalogueGeneration is
        // bumped by every path that changes the effective data (SetLocale,
        // ApplyPack, RegisterCatalogue, LoadCachedPack), so keying on it makes
        // the memo correct by construction rather than by enumeration.
        private static string chatHeaderCache, chatHeaderChan, chatHeaderLocale;
        private static int chatHeaderGen = -1;

        private static void DrawChatInput()
        {
            // Liveness stamp for TickChatLockWatchdog — first statement, so it is
            // set even on the frames this method early-returns.
            chatDrawStampedAt = Time.unscaledTime;
            // Bug #128: T chat is available whenever the game is running —
            // menus, lobby, pick phase AND active combat. The previous
            // active-combat gate was a bandaid for "don't fight the Enter
            // chat"; the real gate is DevConsole.isTyping (below), and the
            // reason combat used to be excluded (typing would drive the
            // player) is handled properly now by holding ROUNDS' own
            // GameManager.lockInput while the box has focus.
            // Discard: consent has been revoked, so chat is gone entirely —
            // there is no "next open" to resume into, and holding the player's
            // typed text after they opted out is the wrong default (F4).
            if (!Plugin.DataConsentGranted) { CloseChatInput(discardDraft: true); return; }
            // Don't hijack T while a modal IMGUI input is taking keystrokes —
            // bug report form, log viewer, admin bug viewer, and the Compare-tab
            // search field all have their own text entry that need T to type
            // "the", "tree", etc. (lopi: typing "t" in Compare search opened chat).
            // CloseChatInput (not a bare return): a modal opening while the box
            // is up must not leave it "open" and holding the input lock with
            // nothing rendering it.
            // F4: this is THE incidental close — the two Aug-3 chat pickers
            // (Change view / Typing channel) are ArtistPromptOpen modals, so
            // clicking either used to eat the draft. Stashing here fixes every
            // modal in this list at once, not just those two.
            if (bugModalOpen || logViewerOpen || bugAdminOpen || compareSearchFocused
                // July 22 item 8: leaderboard search takes typed text too.
                || lbSearchFocused
                // Aug 6 item 2: the metric/card dropdown's search field.
                || pickerSearchFocused
                || NativeUI.CustomBetPromptOpen
                // July 21 item 8: the LFP message box takes typed text — 't'
                // there must not open chat.
                || NativeUI.LfpPromptOpen
                // July 12 round 2 item 4: the artist input / roster picker / player
                // search modals all take typed text — 't' there must not open chat.
                || ArtistPromptOpen) { quickChatOpen = false; CloseChatInput(discardDraft: false); return; }

            var ev = Event.current;
            if (!chatInputOpen)
            {
                // Quick-chat guardian (#255 pattern): DrawQuickChat runs LATER
                // in the DrawUI chain, so a throw between here and there could
                // leave quickChatOpen set with nothing rendering it — and this
                // method's lock assert below would hold gameplay input hostage.
                // DrawChatInput is the reliable early runner, so it polices the
                // popup's liveness stamp.
                if (quickChatOpen && Time.unscaledTime - quickChatDrawStampedAt > 2f)
                {
                    Plugin.Log.LogWarning("[QUICKCHAT] popup went unrendered for >2s — force-closing");
                    quickChatOpen = false;
                }
                // Assert-from-state, SINGLE WRITER (#200): the desired lock
                // state is the union of every IMGUI surface that owns typing/
                // clicking — currently the T-chat box and the quick-chat popup.
                SetGameplayInputLock(quickChatOpen);
                // Vanilla's Enter chat owns the keyboard while it's open — T there
                // is a literal 't' in their message, not our hotkey (bug #128).
                if (IsVanillaChatTyping()) return;
                // Don't open the T chat if some OTHER text input already has focus — covers
                // any other uGUI/TMP InputField (another mod, a future ROUNDS field).
                // EventSystem.currentSelectedGameObject is non-null whenever a uGUI Selectable
                // owns focus; we additionally inspect it for any InputField-typed component so
                // we don't false-positive on plain buttons.
                if (IsAnotherTextInputActive()) return;
                if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.T)
                {
                    chatInputOpen = true;
                    chatJustOpened = true;
                    // F4: resume a draft an incidental close stashed (one-shot,
                    // TTL-bounded). "" when there is nothing to resume, which
                    // is the old behaviour.
                    chatInputText = TakeStashedDraft();
                    if (chatInputText.Length > 0)
                        chatCaretToEndUntil = Time.unscaledTime + 1f;
                    chatAltHeld = false;
                    chatAltTapClean = false;
                    // Belt-and-suspenders re-derive. Since F10 the memo's key
                    // covers every input that can change the line (channel,
                    // locale, catalogue generation), so this is no longer the
                    // thing that picks up a mid-session translation pack — it
                    // just costs one TrF per opening and keeps the box honest
                    // if a future header input escapes the key.
                    chatHeaderCache = null;
                    ev.Use();
                    // Take the lock on the same frame the box opens, so the 't'
                    // that opened it can't also be read as gameplay input.
                    SetGameplayInputLock(true);
                }
                return;
            }

            // Vanilla chat opening on top of ours (Enter is our submit key, so this
            // is only reachable if something else toggles DevConsole) — yield to it.
            // Yielding to vanilla is not the player ending their message (F4).
            if (IsVanillaChatTyping()) { CloseChatInput(discardDraft: false); return; }
            // Re-assert every frame: GameManager.lockInput is a shared global that
            // vanilla also writes, and GameManager.Start() zeroes it on every scene
            // load (which is also our free self-heal if we ever miss a release).
            SetGameplayInputLock(true);

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
                if (ev.keyCode == KeyCode.LeftAlt || ev.keyCode == KeyCode.RightAlt)
                {
                    // Aug 6 item 11: the channel cycle moved from Shift to Alt
                    // (Shift kept firing while players typed capitals). Arm a
                    // tap on the FIRST alt-down of a hold (key repeat must not
                    // re-arm a hold that already typed something).
                    // Deliberately not ev.Use()'d: a bare alt KeyDown carries
                    // no character, and TextField reads the modifier off the
                    // keys that follow, not off this event.
                    if (!chatAltHeld)
                    {
                        chatAltHeld = true;
                        chatAltTapClean = true;
                        chatAltDownAt = Time.unscaledTime;
                    }
                }
                else if (ev.keyCode != KeyCode.None || ev.character != '\0')
                {
                    // ANY other real KeyDown during the hold means alt was a
                    // MODIFIER (Alt+Tab, AltGr-typed characters on intl
                    // layouts), not a tap. Unity fires TWO KeyDown events per
                    // physical key (one with keyCode, one with ev.character —
                    // see the chatJustOpened note above) and either one
                    // disarms. Padding events with neither are skipped, or the
                    // alt's own key-down pair could disarm the tap it just
                    // armed.
                    chatAltTapClean = false;
                }

                if (ev.keyCode == KeyCode.Return || ev.keyCode == KeyCode.KeypadEnter)
                {
                    submit = true; ev.Use();
                }
                else if (ev.keyCode == KeyCode.Escape)
                {
                    cancel = true; ev.Use();
                }
                else if (ev.keyCode == KeyCode.Tab)
                {
                    // Tab no longer cycles (Shift does), but keep swallowing it:
                    // unconsumed, IMGUI treats Tab as focus navigation and would
                    // yank the caret out of the box mid-message.
                    ev.Use();
                }
            }
            else if (ev != null && ev.type == EventType.KeyUp
                     && (ev.keyCode == KeyCode.LeftAlt || ev.keyCode == KeyCode.RightAlt))
            {
                // Item 13 (Shift->Alt per Aug 6 item 11): a TAP of alt rotates
                // the SEND channel through the whole allowed set
                // (global -> es -> ru -> global), ungated by locale — the old
                // Tab cycle only existed when the player HAD a locale channel,
                // so English clients had no cycle at all.
                //
                // The discriminator is the whole trick: acting on the RELEASE,
                // and only when nothing was typed between the press and the
                // release (chatAltTapClean, cleared above by any other
                // KeyDown) and the hold was shorter than 0.6s, means an alt
                // used as a modifier (Alt+Tab, AltGr) can never trigger it —
                // the other key's own KeyDown always lands inside the hold.
                bool tap = chatAltHeld && chatAltTapClean
                           && Time.unscaledTime - chatAltDownAt < 0.6f;
                chatAltHeld = false;
                chatAltTapClean = false;
                if (tap) { CycleChatSendChannel(); ev.Use(); }
            }

            // Alt+Tab safety: if focus left while alt was held, the KeyUp
            // never arrives — clear the armed state so the first alt tap
            // after returning doesn't act on a stale hold.
            if (!Application.isFocused && (chatAltHeld || chatAltTapClean))
            {
                chatAltHeld = false;
                chatAltTapClean = false;
            }

            // Position: above the F5 menu's bottom bar (Discord/GitHub/Refresh buttons
            // are around y=Screen.height-30). Doubled size per request.
            float w = 1000, h = 56;
            float x = 20, y = Screen.height - 130;

            GUI.DrawTexture(new Rect(x - 6, y - 24, w + 12, h + 30),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.82f), 0, 0);
            // Item 13: ONE header for every locale — the cycle is ungated now,
            // so the old "English clients get a shorter line with no channel
            // name" branch would hide the very feature it needs to announce.
            string hdrChan = ChatClient.SendChannel;
            string hdrLoc = I18n.Locale;
            int hdrGen = I18n.CatalogueGeneration;   // F10 — see the memo's note
            if (chatHeaderCache == null || hdrChan != chatHeaderChan
                || hdrLoc != chatHeaderLocale || hdrGen != chatHeaderGen)
            {
                chatHeaderChan = hdrChan; chatHeaderLocale = hdrLoc; chatHeaderGen = hdrGen;
                chatHeaderCache = I18n.TrF(
                    "Chat [{0}]  —  Enter to send, Esc to cancel, Alt switches channel",
                    ChannelDisplayLabel(hdrChan));
            }
            GUI.Label(new Rect(x, y - 22, w, 20), chatHeaderCache);

            GUI.SetNextControlName("CRChat");
            chatInputText = GUI.TextField(new Rect(x, y, w, h), chatInputText ?? "", 480, chatStyle);
            GUI.FocusControl("CRChat");

            // F4: collapse the focus-gain SelectAll to an append caret for a
            // RESUMED draft (see chatCaretToEndUntil). Focus lands a frame or
            // two after the box opens, so poll until the editor holding OUR
            // exact text turns up, then disarm. The text equality is the guard
            // against touching some other control's editor if keyboardControl
            // is stale — and this only ever runs inside the 1s window opened by
            // a non-empty restore, never on a normal open.
            if (Time.unscaledTime < chatCaretToEndUntil)
            {
                try
                {
                    // Fully qualified: an unqualified TextEditor could bind to a
                    // type in Assembly-CSharp or a future using.
                    int kc = GUIUtility.keyboardControl;
                    var te = kc != 0
                        ? GUIUtility.GetStateObject(typeof(UnityEngine.TextEditor), kc)
                            as UnityEngine.TextEditor
                        : null;
                    if (te != null && te.text == chatInputText)
                    {
                        te.cursorIndex = te.selectIndex = (chatInputText ?? "").Length;
                        chatCaretToEndUntil = -999f;
                    }
                }
                catch { chatCaretToEndUntil = -999f; }
            }

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
                    else if (text.StartsWith("/report ", StringComparison.OrdinalIgnoreCase))
                    {
                        // §2.6 v1 moderation groundwork: files a bug-report row
                        // with the local chat lines mentioning that name.
                        NativeUI.HandleReportCommand(text);
                    }
                    else
                    {
                        ChatClient.Send(GameStateWatcher.LocalSteamId,
                                        GameStateWatcher.LocalDisplayName,
                                        text);
                        Plugin.Log.LogInfo($"[CHAT] -> sent: {text}");
                    }
                }
                // Sent (or consumed as a slash command) — the message is over.
                CloseChatInput(discardDraft: true);
            }
            else if (cancel)
            {
                // Esc IS the discard gesture — it must also drop any older
                // stash, or a resumed-then-cancelled draft would come back.
                CloseChatInput(discardDraft: true);
            }
        }

        // ── Quick chat (§2.6 — key-based canned phrases) ─────────
        // Y in an online room opens a phrase list; click or 1-9/0 sends the
        // phrase KEY over Photon (QuickChat.Send); every recipient renders it
        // in their OWN locale. While open, the same gameplay-input lock as the
        // T-chat box is held (asserted by DrawChatInput, the single writer),
        // so a click on a phrase can never also fire the gun.
        private static bool quickChatOpen = false;
        private static float quickChatDrawStampedAt = -999f;
        public static bool IsQuickChatOpen => quickChatOpen;

        private static void DrawQuickChat()
        {
            // Liveness stamp read by DrawChatInput's guardian.
            quickChatDrawStampedAt = Time.unscaledTime;
            if (!Plugin.DataConsentGranted) { quickChatOpen = false; return; }
            // Same modal-typing exclusions as the chat box: Y must type into
            // those inputs, not open the popup — and an already-open popup
            // yields to them.
            if (chatInputOpen || bugModalOpen || logViewerOpen || bugAdminOpen
                || compareSearchFocused || lbSearchFocused || pickerSearchFocused
                || NativeUI.CustomBetPromptOpen || NativeUI.LfpPromptOpen
                || ArtistPromptOpen) { quickChatOpen = false; return; }
            if (IsVanillaChatTyping()) { quickChatOpen = false; return; }

            bool inRoom = false;
            try { inRoom = Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode; } catch { }
            var ev = Event.current;

            if (!quickChatOpen)
            {
                if (inRoom && ev != null && ev.type == EventType.KeyDown
                    && ev.keyCode == KeyCode.Y && !IsAnotherTextInputActive())
                {
                    quickChatOpen = true;
                    ev.Use();
                }
                return;
            }
            if (!inRoom) { quickChatOpen = false; return; }

            if (ev != null && ev.type == EventType.KeyDown)
            {
                if (ev.keyCode == KeyCode.Escape || ev.keyCode == KeyCode.Y)
                {
                    quickChatOpen = false; ev.Use(); return;
                }
                int sel = -1;
                if (ev.keyCode >= KeyCode.Alpha1 && ev.keyCode <= KeyCode.Alpha9)
                    sel = ev.keyCode - KeyCode.Alpha1;
                else if (ev.keyCode == KeyCode.Alpha0) sel = 9;
                if (sel >= 0 && sel < QuickChat.Phrases.Length)
                {
                    QuickChat.Send(sel);
                    quickChatOpen = false; ev.Use(); return;
                }
            }

            int n = QuickChat.Phrases.Length;
            const int cols = 2;
            int rows = (n + cols - 1) / cols;
            float bw = 250, bh = 26, pad = 6;
            float w = cols * bw + pad * 3, h = rows * (bh + 4) + 38;
            float x = 20, y = Screen.height - h - 150;
            GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.85f), 0, 0);
            GUI.Label(new Rect(x + 8, y + 6, w - 16, 20),
                I18n.Tr("Quick chat — click a phrase (or keys 1-0). Y/Esc closes."));
            for (int i = 0; i < n; i++)
            {
                int c = i % cols, r = i / cols;
                var rect = new Rect(x + pad + c * (bw + pad), y + 30 + r * (bh + 4), bw, bh);
                string digit = i < 10 ? $"{(i + 1) % 10}. " : "";
                if (GUI.Button(rect, digit + I18n.Tr(QuickChat.Phrases[i])))
                {
                    QuickChat.Send(i);
                    quickChatOpen = false;
                }
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

            // i18n: IMGUI has no Tr chokepoint (GUI.Label/GUI.Button draw the raw
            // string), so every consent string is translated here explicitly.
            // The +-folded body is ONE compile-time literal and therefore ONE
            // whole-string catalogue key (the extractor joins folded literals).
            // (Tr is throw-free by construction — dictionary TryGetValue chains
            // with an English passthrough — so no try/catch is needed on an
            // IMGUI path; a literal argument is REQUIRED for the extractor.)
            GUI.Label(new Rect(x, y + 14, w, 30),
                I18n.Tr("Competitive ROUNDS — Data Consent"), consentTitleStyle);

            string body = I18n.Tr(
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
                "Choose Allow to use the leaderboard. Choose Decline to run the mod fully offline.");
            GUI.Label(new Rect(x + 24, y + 50, w - 48, h - 120), body, consentBodyStyle);

            string allowLabel = I18n.Tr("Allow data reporting");
            string declineLabel = I18n.Tr("Decline (offline mode)");
            if (GUI.Button(new Rect(x + 50, y + h - 56, 260, 38), allowLabel))
            {
                Plugin.DataConsent.Value = "granted";
                Plugin.Log.LogInfo("[CONSENT] User granted data reporting");
                ApiClient.OnConsentChanged();
            }
            if (GUI.Button(new Rect(x + w - 310, y + h - 56, 260, 38), declineLabel))
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
            // OnGUI runs Layout + Repaint (and once per input event). Count and
            // render only Repaint so the overlay reports real rendered frames.
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            // FPS counter — independently toggleable.
            bool showFps = Plugin.ShowFps == null || Plugin.ShowFps.Value;
            bool showRegion = Plugin.ShowRegionPing == null || Plugin.ShowRegionPing.Value;
            if (!showFps && !showRegion) return;

            fpsCnt++;
            fpsTimer += Time.deltaTime;
            if (fpsStyle == null) { fpsStyle = new GUIStyle(GUI.skin.label); fpsStyle.fontSize = 11; fpsStyle.normal.textColor = new Color(0.5f, 0.5f, 0.5f, 0.7f); }

            // FPS/ping/region change slowly. Rebuilding four formatted strings
            // every rendered frame created steady managed garbage in every match.
            bool refreshLabel = fpsTimer >= 0.5f
                             || fpsLabelShowFps != showFps
                             || fpsLabelShowRegion != showRegion;
            if (refreshLabel)
            {
                if (fpsTimer >= 0.5f)
                {
                    fpsVal = fpsCnt / fpsTimer;
                    fpsCnt = 0;
                    fpsTimer = 0f;
                }
                fpsLabelShowFps = showFps;
                fpsLabelShowRegion = showRegion;
                fpsLabel = showFps ? $"{fpsVal:F0} FPS" : "";
                fpsLabelWidth = 60f;

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
                                region = region.ToUpperInvariant();
                            }
                            string pingPart = $"{ping}ms  {region}";
                            fpsLabel = showFps ? $"{fpsLabel}  |  {pingPart}" : pingPart;
                            fpsLabelWidth = 200f;
                        }
                    }
                    catch { }
                }
            }

            if (!string.IsNullOrEmpty(fpsLabel))
                GUI.Label(new Rect(6, 4, fpsLabelWidth, 18), fpsLabel, fpsStyle);
        }

        // ── FFA spawn spotlight (Sid, Aug 3) ────────────────────────────────
        // "In game for FFAs, it's a bit confusing when you spawn in where you
        // are." With up to 10 near-identical bodies, finding yourself costs
        // the first second of the round.
        //
        // Drawn as an OVERLAY on purpose. The obvious implementation —
        // recolouring bodies — was reviewed and rejected: the ROUNDS body is
        // largely particle-rendered (so the brightest layer would not dim),
        // the cosmetics system rewrites those colours at 30 Hz for animated
        // skins, and any interrupted restore would leave a player permanently
        // mis-coloured. This touches no game state at all: it darkens the
        // screen AROUND the local player and fades out.
        private static Transform spotlightTarget;
        private static float spotlightUntil;
        private const float SPOT_HOLD = 0.75f, SPOT_FADE = 0.45f;
        private static Texture2D spotlightTex;
        private static Texture2D spotlightHoleTex;
        // Radial-tile geometry: alpha 0 inside SPOT_HOLE_INNER of the tile's
        // half-width, full at SPOT_HOLE_OUTER and beyond, soft between so the
        // circle doesn't alias. The draw scales the tile by 1/SPOT_HOLE_INNER
        // so the fully-clear core lands exactly on the requested radius.
        private const float SPOT_HOLE_INNER = 0.72f, SPOT_HOLE_OUTER = 0.98f;

        // One cached radial-alpha tile (same recipe as BuildFfaDotTexture, but
        // with the alpha INVERTED — clear in the middle, opaque at the edge) so
        // the cutout can be a circle without generating anything per Repaint.
        private static Texture2D BuildSpotlightHoleTexture()
        {
            const int size = 128;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false);
            texture.name = "CR_FFA_SpotlightHole";
            texture.hideFlags = HideFlags.HideAndDontSave;
            texture.filterMode = FilterMode.Bilinear;
            texture.wrapMode = TextureWrapMode.Clamp;
            var pixels = new Color32[size * size];
            float center = size * 0.5f;
            float rIn = SPOT_HOLE_INNER * center, rOut = SPOT_HOLE_OUTER * center;
            for (int y = 0; y < size; y++)
            {
                float py = y + 0.5f - center;
                for (int x = 0; x < size; x++)
                {
                    float px = x + 0.5f - center;
                    float d = Mathf.Sqrt(px * px + py * py);
                    float alpha = Mathf.Clamp01((d - rIn) / (rOut - rIn));
                    pixels[y * size + x] = new Color32(255, 255, 255,
                        (byte)Mathf.RoundToInt(alpha * 255f));
                }
            }
            texture.SetPixels32(pixels);
            texture.Apply(false, true);
            return texture;
        }

        public static void BeginSpawnSpotlight(Transform target)
        {
            spotlightTarget = target;
            spotlightUntil = Time.unscaledTime + SPOT_HOLD + SPOT_FADE;
        }

        private static void DrawSpawnSpotlight()
        {
            if (spotlightTarget == null || Time.unscaledTime >= spotlightUntil) return;
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            Camera cam = null;
            try { cam = MainCam.instance != null ? MainCam.instance.cam : Camera.main; } catch { }
            if (cam == null) return;

            float left = spotlightUntil - Time.unscaledTime;
            // Full strength through the hold, then ease out over the fade.
            float k = left > SPOT_FADE ? 1f : Mathf.Clamp01(left / SPOT_FADE);
            float alpha = 0.55f * k;
            if (alpha <= 0.01f) return;

            Vector3 sp;
            try { sp = cam.WorldToScreenPoint(spotlightTarget.position); } catch { return; }
            if (sp.z < 0f) return;
            float cx = sp.x, cy = Screen.height - sp.y;   // IMGUI y is top-down

            // Radius comes from the PLAYER, not from the screen (Sid, item 9).
            // The old `Mathf.Max(70f, Screen.height * 0.13f)` was 140px at
            // 1080p — about 7.4x the ~38px ROUNDS body — and, being a pure
            // screen fraction, it did not shrink on scaled FFA maps either
            // (CameraZoomHandler lerps orthographicSize toward Map.size, so the
            // bodies get smaller while a fixed fraction does not). Project a
            // point 0.53 world units "up" from the target — half the ~1.06-unit
            // body (learning #160) — and measure the screen distance.
            float playerR = 0f;
            try
            {
                Vector3 up = cam.WorldToScreenPoint(spotlightTarget.position + cam.transform.up * 0.53f);
                playerR = Vector2.Distance(new Vector2(sp.x, sp.y), new Vector2(up.x, up.y));
            }
            catch { }
            float r;
            if (playerR >= 6f)
                r = 3f * playerR;                 // "3x player size" = 3x the body diameter
            else if (cam.orthographic && cam.orthographicSize > 0.01f)
                // Closed form for a degenerate measurement: 3 * 0.53 world
                // units * (pixels per world unit).
                r = 1.59f * (Screen.height / (2f * cam.orthographicSize));
            else
                r = 18f;                          // 3x the 6px floor
            if (r < 18f) r = 18f;

            if (spotlightTex == null)
            {
                spotlightTex = new Texture2D(1, 1);
                spotlightTex.SetPixel(0, 0, Color.white);
                spotlightTex.Apply();
                spotlightTex.hideFlags = HideFlags.HideAndDontSave;
            }
            if (spotlightHoleTex == null) spotlightHoleTex = BuildSpotlightHoleTexture();
            var prev = GUI.color;
            GUI.color = new Color(0f, 0f, 0f, alpha);
            // IMGUI has no cutout, so the dim is the cached radial tile over the
            // player (clear core, opaque rim) plus four full-alpha bands
            // covering everything outside the tile — the far screen therefore
            // stays perfectly flat with zero texture stretch. 5 DrawTexture
            // calls, 5 stack Rects, no per-frame allocation.
            /* Bug #162 ("2-3 horizontal lines at the start of a round"): every
             * one of these rects must land on INTEGER pixel boundaries, and the
             * bands must be derived from the SAME integers as the tile.
             *
             * The edges used to be raw floats (cx - R etc). GUI.DrawTexture
             * rasterizes to whole pixels, so a fractional boundary rounds each
             * rect independently and the band and the tile disagree by a pixel:
             * where they fall short you get an UNDIMMED hairline (the bright
             * lines reported), and the naive fix — overlapping them — is just as
             * visible in the other direction, because two 0.55-alpha blacks
             * composite to 0.80 and draw a DARK hairline instead.
             *
             * Snapping first and slicing from the snapped values makes the edges
             * exactly coincident: no gap to shine through, no overlap to double.
             * The tile may still hang off-screen; that is free. */
            float R = r / SPOT_HOLE_INNER;
            int tx0 = Mathf.FloorToInt(cx - R), ty0 = Mathf.FloorToInt(cy - R);
            int tSz = Mathf.CeilToInt(2f * R);
            int x0 = Mathf.Clamp(tx0, 0, Screen.width);
            int x1 = Mathf.Clamp(tx0 + tSz, 0, Screen.width);
            int y0 = Mathf.Clamp(ty0, 0, Screen.height);
            int y1 = Mathf.Clamp(ty0 + tSz, 0, Screen.height);
            if (y0 > 0) GUI.DrawTexture(new Rect(0, 0, Screen.width, y0), spotlightTex);
            if (y1 < Screen.height) GUI.DrawTexture(new Rect(0, y1, Screen.width, Screen.height - y1), spotlightTex);
            if (x0 > 0) GUI.DrawTexture(new Rect(0, y0, x0, y1 - y0), spotlightTex);
            if (x1 < Screen.width) GUI.DrawTexture(new Rect(x1, y0, Screen.width - x1, y1 - y0), spotlightTex);
            GUI.DrawTexture(new Rect(tx0, ty0, tSz, tSz), spotlightHoleTex);
            GUI.color = prev;
        }

        private static void DrawNotification()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            if (notifTimer <= 0f && notifQueue.Count > 0)
            {
                var n = notifQueue[0]; notifQueue.RemoveAt(0);
                notifText = n.text; notifColor = n.color; notifTimer = n.dur;
            }
            if (notifTimer <= 0f) return;
            // OnGUI runs 2+ times per frame (Layout + Repaint + one per input event);
            // only tick the timer on Repaint or toasts live at half nominal duration or less.
            notifTimer -= Time.unscaledDeltaTime;
            float alpha = Mathf.Clamp01(notifTimer / 0.75f);

            if (notifStyle == null)
            {
                notifStyle = new GUIStyle(GUI.skin.label);
                notifStyle.fontSize = 16;
                notifStyle.fontStyle = FontStyle.Bold;
                notifStyle.alignment = TextAnchor.MiddleCenter;
                notifStyle.wordWrap = true;
                // ROUNDS' IMGUI skin has taller font metrics than nominal point size;
                // Clip halves the top/bottom lines of any wrapped message.
                notifStyle.clipping = TextClipping.Overflow;
            }

            var color = new Color(notifColor.r, notifColor.g, notifColor.b, alpha);
            var origColor = GUI.contentColor;
            GUI.contentColor = color;

            float width = 500;
            float x = (Screen.width - width) / 2f;
            // Size to rendered content (multi-line grows upward from the same baseline).
            float h = Mathf.Clamp(notifStyle.CalcHeight(new GUIContent(notifText), width), 24f, 120f);
            float y = Screen.height - 80 - (h - 24f);

            var bgTex = Texture2D.whiteTexture;
            GUI.DrawTexture(new Rect(x, y - 6, width, h + 12), bgTex, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, alpha * 0.5f), 0, 0);
            GUI.Label(new Rect(x, y, width, h), notifText, notifStyle);
            GUI.contentColor = origColor;
        }

        private static float matchStatusCacheUntil = 0f;
        private static bool matchStatusCachedRanked = false;
        // Set by RefreshMatchStatusCache: this match is 1v2 (unranked beta), so
        // the banner/series/participant lines use the 1v2 shape.
        private static bool matchStatusIsOvt = false;
        private static string matchStatusSeries = "", matchStatusH2H = "";
        private static Color matchStatusH2HTint = new Color(0.7f, 0.7f, 0.7f);

        private static void RefreshMatchStatusCache(bool isRanked)
        {
            matchStatusCacheUntil = Time.unscaledTime + 0.25f;
            matchStatusCachedRanked = isRanked;
            matchStatusSeries = "";

            matchStatusH2H = "";

            // ── 1v2 (bug #91 comments 2/3) ────────────────────────────────
            // The whole line below is 1v1-shaped: it reads matchIsRanked (which
            // is forced true for ANY mod-issued room, 1v2 included, so the HUD
            // claimed "RANKED - Recording" in an unranked beta mode), the 1v1
            // BO3 counters (deliberately frozen at 0-0 in ovt rooms), and a
            // single opponentDisplayName (so a 3-player game read "vs <one
            // player>"). Give 1v2 its own honest line. This changes only what
            // is DISPLAYED — matchIsRanked itself is load-bearing for report
            // routing and stays exactly as it is.
            matchStatusIsOvt = false;
            string ovtRoom = "";
            try { ovtRoom = Photon.Pun.PhotonNetwork.CurrentRoom?.Name ?? ""; } catch { }
            if (ovtRoom.StartsWith("ovt_", StringComparison.Ordinal))
            {
                matchStatusIsOvt = true;
                int solo = GameStateWatcher.OvtSoloWins, duo = GameStateWatcher.OvtDuoWins;
                bool localIsSolo = GameStateWatcher.LocalTeamId == 0;
                matchStatusSeries = localIsSolo
                    ? I18n.TrF("1v2 Series: You {0} - {1} Duo", solo, duo)
                    : I18n.TrF("1v2 Series: Duo {0} - {1} Solo", duo, solo);

                var mates = new List<string>();
                var foes = new List<string>();
                try
                {
                    int myTeam = -1;
                    var mp = Photon.Pun.PhotonNetwork.LocalPlayer?.CustomProperties;
                    if (mp != null && mp.ContainsKey("t_id"))
                        int.TryParse(mp["t_id"]?.ToString(), out myTeam);
                    foreach (var pp in RoomActors.ActiveFighters())   // census: a spectator is neither mate nor foe
                    {
                        if (pp == null || pp.IsLocal) continue;
                        string nm = GameStateWatcher.StripRichText(pp.NickName ?? "?");
                        if (string.IsNullOrEmpty(nm)) nm = "?";
                        if (nm.Length > 14) nm = nm.Substring(0, 14);
                        int t = -1;
                        if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey("t_id"))
                            int.TryParse(pp.CustomProperties["t_id"]?.ToString(), out t);
                        // Missing t_id => treat as opponent (same convention the
                        // leaver banner uses); self-corrects on the next refresh.
                        if (t >= 0 && myTeam >= 0 && t == myTeam) mates.Add(nm); else foes.Add(nm);
                    }
                }
                catch { }
                matchStatusH2HTint = new Color(0.82f, 0.82f, 0.82f);
                /* ONE whole template per shape, never composed from Tr'd pieces
                 * (learning #298c). The old form was TrF("w/ {0}   ") + TrF("vs {0}"),
                 * and neither half could ever become a key: "w/ {0}   " has one
                 * letter plus trailing spaces, and "vs {0}" is a two-letter
                 * connector the extractor deliberately refuses. So this line
                 * rendered English in every locale. Three templates because the
                 * teammate-only and enemy-only cases are real (a 1v2 solo has no
                 * mates; a spectator-shaped read can have no foes), and a
                 * translator needs the whole sentence to order it correctly. */
                string _mates = string.Join(" + ", mates.ToArray());
                string _foes  = string.Join(" + ", foes.ToArray());
                matchStatusH2H = mates.Count > 0 && foes.Count > 0
                        ? I18n.TrF("w/ {0}   vs {1}", _mates, _foes)
                        : mates.Count > 0 ? I18n.TrF("w/ {0}", _mates)
                        : foes.Count > 0  ? I18n.TrF("vs {0}", _foes)
                        : "";
                return;
            }

            if (isRanked)
            {
                // July 26 (Sid item 4): "(session X-X)" was a rolling 3h-window
                // tally across ALL opponents — confusing and reading as wrong.
                // Replaced with the lifetime head-to-head SERIES record vs the
                // CURRENT opponent, served by GET /players/{opp}?viewer_steam_id=
                // (h2h_series_wins/losses, already computed server-side) and
                // kept live locally by OnSeriesCompletedVsOpponent. Until the
                // fetch lands (or when the opponent has no real Steam ID) the
                // line shows just the series score — never a wrong number.
                matchStatusSeries = I18n.TrF("Series Score: {0} - {1}",
                    GameStateWatcher.CurrentSeriesGamesWon, GameStateWatcher.CurrentSeriesGamesLost);
                try
                {
                    string sid = GameStateWatcher.OpponentSteamId;
                    if (!string.IsNullOrEmpty(sid) && !sid.StartsWith("photon_"))
                    {
                        ApiClient.FetchOpponentLifetime(sid);  // no-op after first call per opponent
                        int[] h2h;
                        if (ApiClient.CachedOppLifetime.TryGetValue(sid, out h2h)
                            && h2h != null && h2h.Length >= 4)
                            matchStatusSeries += I18n.TrF("   (Total Series {0} - {1})", h2h[2], h2h[3]);
                    }
                }
                catch { }
            }

            try
            {
                string oppSid = GameStateWatcher.OpponentSteamId;
                string oppName = GameStateWatcher.OpponentDisplayName;
                var rp = Photon.Pun.PhotonNetwork.CurrentRoom?.CustomProperties;
                bool isCrFf = rp != null && rp.ContainsKey("cr_ff");
                if (isCrFf || string.IsNullOrEmpty(oppName) || oppName == "Opponent"
                    || (oppSid != null && oppSid.StartsWith("photon_")))
                    return;

                int w = 0, l = 0;
                int[] counts;
                var dict = GameStateWatcher.SessionWLByOpponent;
                if (dict != null && dict.TryGetValue(oppName, out counts)
                    && counts != null && counts.Length >= 4)
                {
                    w = counts[0] + counts[2];
                    l = counts[1] + counts[3];
                }
                string shortName = oppName.Length > 18 ? oppName.Substring(0, 18) : oppName;
                if (w + l > 0)
                {
                    matchStatusH2HTint = w > l ? new Color(0.6f, 1f, 0.6f)
                                           : w < l ? new Color(1f, 0.6f, 0.6f)
                                                   : new Color(0.85f, 0.85f, 0.85f);
                    matchStatusH2H = I18n.TrF("vs {0}: {1}-{2} this session", shortName, w, l);
                }
                else
                {
                    matchStatusH2HTint = new Color(0.7f, 0.7f, 0.7f);
                    matchStatusH2H = I18n.TrF("vs {0}: first game this session", shortName);
                }
            }
            catch { }
        }

        private static void DrawMatchStatus()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            if (!MatchTracker.IsInMatch) return;
            // FFA draws its own per-player score strip at the very top
            // (DrawFfaScoreStrip). This 1v1-shaped block would paint a "RANKED -
            // Recording" banner straight over it — ffa_ rooms force
            // matchIsRanked true like every mod-issued room.
            try { if (FfaMode.EngineActive()) return; } catch { }
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
            if (Time.unscaledTime >= matchStatusCacheUntil || matchStatusCachedRanked != isRanked)
                RefreshMatchStatusCache(isRanked);
            var oc = GUI.contentColor;

            // Top banner: "RANKED - Recording" only on ranked; 1v2 gets its own
            // honest label (unranked beta). Casual gets no banner — the score
            // line below floats up so it sits where the banner would have.
            bool ovt = matchStatusIsOvt;
            bool showBanner = ovt || isRanked;
            float scoreY;
            if (showBanner)
            {
                GUI.contentColor = ovt ? new Color(0.55f, 0.8f, 1f) : Color.green;
                GUI.Label(new Rect((Screen.width - 220) / 2f, 8, 220, 18),
                    ovt ? I18n.Tr("1v2 - UNRATED") : I18n.Tr("RANKED - Recording"), statusStyle);
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
            if (showBanner && !string.IsNullOrEmpty(matchStatusSeries))
            {
                // Wider rect: the Series line now carries the session series
                // record too. The old blue "Session:" row is gone, so the H2H
                // line below moves up one row instead of leaving a gap.
                GUI.contentColor = new Color(1f, 0.85f, 0.3f);
                GUI.Label(new Rect((Screen.width - 380) / 2f, scoreY, 380, 22),
                    matchStatusSeries, scoreStyle);
                nextLineY = scoreY + 18;
            }

            if (!string.IsNullOrEmpty(matchStatusH2H))
            {
                // 1v2 names up to three players on this line — needs the room.
                float hw = ovt ? 560f : 360f;
                GUI.contentColor = matchStatusH2HTint;
                GUI.Label(new Rect((Screen.width - hw) / 2f, nextLineY, hw, 20),
                    matchStatusH2H, scoreStyle);
            }
            GUI.contentColor = oc;
        }

        private static GUIStyle scoreStyle;
    }
}
