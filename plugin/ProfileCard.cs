using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Sept 6 Group 4 item a: the mini-profile card that opens when the
    /// pointer dwells on a player's name on the F5 page, with the viewer's
    /// head-to-head against that player in every mode.
    ///
    /// DATA. One request: the strict-session H2H read the in-room line already
    /// uses (ApiClient.FetchH2HSummary) — its two ADDITIVE members `profile`
    /// and `modes` (design v2 A-4), sliced with the string-aware brace matcher
    /// scoped to each member and never a repeated key search. The response is
    /// cached per (viewer, target) for the session; every card OPEN issues one
    /// refresh, which the server refuses as an echo inside its 5 s pair
    /// debounce (RefreshFloorSeconds keeps the client from asking sooner), so
    /// the header re-reads the profile at most once per floor and the cached
    /// card shows meanwhile. The client cannot fetch `profile` alone — the
    /// members ride one response — so a refresh renews both.
    ///
    /// HOVER (A-6). A name is a target only when its TMP component names ONE
    /// player: the surfaces register through RegisterNameHover with the steam
    /// id the row already carries, and the hit rect is the component's
    /// RENDERED width, read live (#90, #143), intersected with every ancestor
    /// RectMask2D / Mask / Viewport, read live. 300 ms of dwell arms the
    /// request; the card opens when the data is in AND the pointer is still on
    /// the name, and it follows the row while the list scrolls.
    ///
    /// INPUT (A-1). The unpinned card is raycast-free — it never intercepts a
    /// click — and hides whenever ClickHandler.ModalBlockInput is on or a match
    /// is tracking. A click on the name pins it; a pinned card owns a blocker
    /// over its own body ONLY (the panel backdrop's raycast target, plus the
    /// ClickHandler poll skips a point inside the body — that handler never saw
    /// uGUI raycasts, #141), and closes on the first ModalBlockInput after the
    /// pin, on Escape (consumed: the page stays open) or on a click outside it.
    /// Leaving the F5 page tears everything down through
    /// NativeUI.TeardownOverlaySurfaces (#369).
    ///
    /// RENDER. TextMeshPro on a mod-owned overlay canvas (TmpOverlayPanel,
    /// sortingOrder 30001) so names with emoji or non-Latin glyphs render (bug
    /// 333's mechanism). Read-only end to end: nothing here moves a result, a
    /// rating, gold or another player's state.</summary>
    internal static class ProfileCard
    {
        internal const float DwellSeconds = 0.3f;
        internal const float CardW = 420f;
        // The server debounces the pair 5 s (main._H2H_DEBOUNCE_SECONDS) and
        // refuses a sooner request as an echo; H2HRules.DEBOUNCE_RETRY_FALLBACK
        // is the same 6 s for the in-room line.
        internal const float RefreshFloorSeconds = 6f;
        private const int MaxTargets = 800;
        private const int MaxRows = 7;

        // Layout, in screen pixels (ConstantPixelSize canvas).
        private const float PAD = 12f, NAME_Y = 8f, NAME_H = 26f, LINE2_Y = 36f, LINE2_H = 20f, PRES_Y = 57f, PRES_H = 18f;
        private const float DIV_Y = 78f, ROWS_Y = 86f, ROW_H = 24f, LABEL_W = 156f, BAR_X = 174f, BAR_W = 140f, BAR_H = 10f;
        private const float NUMS_X = 322f, NUMS_W = 86f, FOOT_H = 18f, PAD_BOTTOM = 10f;

        private static readonly Color C_BG = new Color(0.06f, 0.07f, 0.10f, 0.94f);
        private static readonly Color C_TEXT = new Color(0.86f, 0.88f, 0.93f);
        private static readonly Color C_DIM = new Color(0.62f, 0.65f, 0.72f);
        private static readonly Color C_VIEWER = new Color(0.36f, 0.80f, 0.45f);
        private static readonly Color C_THEM = new Color(0.88f, 0.38f, 0.38f);
        private static readonly Color C_BARBG = new Color(1f, 1f, 1f, 0.10f);
        private static readonly Color C_DIVIDER = new Color(1f, 1f, 1f, 0.12f);
        private static readonly Rect Offscreen = new Rect(-99999f, -99999f, 1f, 1f);

        private sealed class Target
        {
            public object txt;
            public RectTransform rt;
            public Camera cam;
            public RectTransform[] masks;
            public string steamId;
        }
        private static readonly List<Target> targets = new List<Target>(160);
        private static readonly Dictionary<object, Target> byTxt = new Dictionary<object, Target>(160);

        internal sealed class WinLoss { public int w, l; }

        internal sealed class CardData
        {
            public bool hasProfile;
            public string displayName = "", title = "", titleColor = "", tier = "", tierColor = "";
            public int rating = 1500, rd = 350, level;
            public bool? isOnline;
            public int? lastSeenS;
            public bool hasModes;
            public int seriesW, seriesL, gamesW, gamesL;
            public WinLoss casual = new WinLoss(), team = new WinLoss(), ffa = new WinLoss();
            public WinLoss ovtSolo = new WinLoss(), ovtDuo = new WinLoss();
            public string lastAt, lastMode, lastResult;   // null = never met
            public int streakN;
            public string streakHolder;                    // "viewer" | "target" | null
            public int netRating;
            public float fetchedAt;
        }
        private static readonly Dictionary<string, CardData> cache = new Dictionary<string, CardData>();
        private static readonly HashSet<string> inFlight = new HashSet<string>();
        private static readonly Dictionary<string, float> notBefore = new Dictionary<string, float>();
        private static string cacheViewer;

        // hover / open / pin
        private static Target hover;
        private static float hoverSince;
        private static bool hoverAsked;
        private static int hoverRetries;
        private static string openFor;
        private static bool pinned;
        private static Rect cardRect = Offscreen;
        private static float cardH = 260f;
        private static int generation;

        // objects (rebuilt whenever the panel's root is)
        private static TmpOverlayPanel panel;
        private static object txtName, txtLine2, txtPresence, txtEmpty, txtFoot1, txtFoot2, txtFoot3;
        private static GameObject accent, divider;
        private static readonly object[] rowLabel = new object[MaxRows], rowNums = new object[MaxRows];
        private static readonly GameObject[] rowBarBg = new GameObject[MaxRows], rowBarL = new GameObject[MaxRows], rowBarR = new GameObject[MaxRows];

        internal static bool IsPinned => pinned;
        internal static bool IsOpen => openFor != null && panel != null && panel.Visible;

        // ── registration (called by the surfaces while they fill their rows) ──

        /// <summary>Make `txt` (a TMP component whose text is ONE player's name)
        /// a hover target for that player. Re-registering the same component
        /// replaces its id, so a board refreshed every tick stays bounded by its
        /// row count. Nothing is registered for an empty/invalid id or for the
        /// viewer's own name (the server refuses a self pair; there is nothing
        /// to show).</summary>
        internal static void RegisterNameHover(object txt, string steamId)
        {
            try
            {
                var comp = txt as Component;
                if (comp == null) return;
                if (!IsSteamId64(steamId)) { Unregister(txt); return; }
                string me = MatchTracker.LocalSteamId;
                if (!string.IsNullOrEmpty(me) && me == steamId) { Unregister(txt); return; }
                Target t;
                if (byTxt.TryGetValue(txt, out t)) { t.steamId = steamId; return; }
                if (targets.Count >= MaxTargets) return;
                var rt = comp.GetComponent<RectTransform>();
                if (rt == null) return;
                Camera cam = null;
                var masks = new List<RectTransform>(4);
                Transform p = rt.parent;
                var bf = BindingFlags.Public | BindingFlags.Instance;
                while (p != null)
                {
                    bool clips = (UIFactory.tMask != null && p.GetComponent(UIFactory.tMask) != null)
                              || (UIFactory.tRectMask2D != null && p.GetComponent(UIFactory.tRectMask2D) != null)
                              || p.gameObject.name == "Viewport";
                    if (clips)
                    {
                        var mrt = p as RectTransform;
                        if (mrt != null && !masks.Contains(mrt)) masks.Add(mrt);
                    }
                    if (UIFactory.tCanvas != null)
                    {
                        var cc = p.GetComponent(UIFactory.tCanvas);
                        if (cc != null)
                        {
                            try
                            {
                                var rmProp = UIFactory.tCanvas.GetProperty("renderMode", bf);
                                if (rmProp != null && (int)rmProp.GetValue(cc) != 0)
                                    cam = (UIFactory.tCanvas.GetProperty("worldCamera", bf)?.GetValue(cc) as Camera) ?? Camera.main;
                            }
                            catch { }
                            break;
                        }
                    }
                    p = p.parent;
                }
                t = new Target { txt = txt, rt = rt, cam = cam, masks = masks.ToArray(), steamId = steamId };
                targets.Add(t);
                byTxt[txt] = t;
            }
            catch { /* a target that failed to register simply has no card */ }
        }

        private static void Unregister(object txt)
        {
            Target t;
            if (txt == null || !byTxt.TryGetValue(txt, out t)) return;
            byTxt.Remove(txt);
            targets.Remove(t);
            if (ReferenceEquals(hover, t)) hover = null;
        }

        /// <summary>Forget every target (the page's hover regions were cleared:
        /// tab switch, list refresh). A pinned card stays until its own
        /// dismissal; an unpinned one hides on the next tick.</summary>
        internal static void ClearHoverTargets()
        {
            targets.Clear();
            byTxt.Clear();
            hover = null;
        }

        // ── per-frame (NativeUI.Tick, while the page is open) ──

        internal static void Tick()
        {
            if (!NativeUI.IsOpen) { if (pinned || openFor != null) CloseCard(); return; }
            bool blocked = ClickHandler.ModalBlockInput || MatchTracker.IsInMatch;
            float now = Time.realtimeSinceStartup;
            Vector3 mp = Input.mousePosition;
            if (pinned)
            {
                if (blocked || panel == null || !panel.Visible) { CloseCard(); return; }
                // Click-away: the click itself proceeds to whatever it hit.
                if (Input.GetMouseButtonDown(0) && !cardRect.Contains(mp)) CloseCard();
                return;
            }
            if (blocked) { HideCard(); hover = null; return; }
            Target t = HitTest(mp);
            if (!ReferenceEquals(t, hover))
            {
                hover = t; hoverSince = now; hoverAsked = false; hoverRetries = 0;
                if (t == null || openFor != t.steamId) HideCard();
            }
            if (t == null) return;
            if (now - hoverSince < DwellSeconds) return;
            CardData d;
            cache.TryGetValue(t.steamId, out d);
            if (!hoverAsked) { hoverAsked = true; RequestData(t.steamId, now); }
            else if (d == null && hoverRetries < 1 && !inFlight.Contains(t.steamId))
            {
                float nb;
                if (notBefore.TryGetValue(t.steamId, out nb) && now >= nb) { hoverRetries++; RequestData(t.steamId, now); }
            }
            if (d == null) return;
            if (openFor != t.steamId || panel == null || !panel.Visible) Render(d, t.steamId);
            if (openFor != t.steamId) return;                  // render refused (no canvas)
            Position(LiveRectOf(t), mp);
            if (Input.GetMouseButtonDown(0)) Pin();
        }

        /// <summary>NativeUI.Tick's Escape: a pinned card is the topmost surface
        /// and takes the key; the page stays open. An unpinned card is transient
        /// and never consumes Escape.</summary>
        internal static bool ConsumeEscape()
        {
            if (!pinned) return false;
            CloseCard();
            return true;
        }

        /// <summary>ClickHandler's poll: a pinned card owns the clicks over its
        /// own body and nothing else (A-1).</summary>
        internal static bool SwallowsClickAt(Vector3 screenPoint)
        {
            return pinned && openFor != null && panel != null && panel.Visible && cardRect.Contains(screenPoint);
        }

        /// <summary>The shared page teardown (#369): pinned or not, the card
        /// closes, every target is forgotten and a late response can only fill
        /// the cache.</summary>
        internal static void Teardown()
        {
            CloseCard();
            ClearHoverTargets();
            generation++;
        }

        // ── hit-testing ──

        private static Target HitTest(Vector3 mp)
        {
            // Last-registered first so newer rows on top of stacked layouts win.
            for (int i = targets.Count - 1; i >= 0; i--)
            {
                var t = targets[i];
                if (t.rt == null) { byTxt.Remove(t.txt); targets.RemoveAt(i); continue; }   // destroyed with its page
                if (!t.rt.gameObject.activeInHierarchy) continue;
                // Cheap reject on the whole element before the reflection read.
                Rect full = CompetitiveUI.LiveRegionRect(t.rt, t.cam, -1f, null, Offscreen);
                if (!full.Contains(mp)) continue;
                if (LiveRectOf(t).Contains(mp)) return t;
            }
            return null;
        }

        /// <summary>The element's rect trimmed to its RENDERED text width, read
        /// live (#90/#143), then intersected with every clipping ancestor, read
        /// live; Offscreen when any of them hides it.</summary>
        private static Rect LiveRectOf(Target t)
        {
            if (t == null || t.rt == null) return Offscreen;
            float frac = CompetitiveUI.LiveWidthFrac(t.txt, t.rt, -1f);
            Rect r = CompetitiveUI.LiveRegionRect(t.rt, t.cam, frac, null, Offscreen);
            if (r.width < 1f || r.height < 1f) return Offscreen;
            var masks = t.masks;
            for (int i = 0; i < masks.Length; i++)
            {
                var m = masks[i];
                if (m == null) continue;
                Rect c = CompetitiveUI.LiveRegionRect(m, t.cam, -1f, null, Offscreen);
                float xMin = Mathf.Max(r.xMin, c.xMin), xMax = Mathf.Min(r.xMax, c.xMax);
                float yMin = Mathf.Max(r.yMin, c.yMin), yMax = Mathf.Min(r.yMax, c.yMax);
                if (xMax - xMin < 1f || yMax - yMin < 1f) return Offscreen;
                r = new Rect(xMin, yMin, xMax - xMin, yMax - yMin);
            }
            return r;
        }

        // ── data ──

        private static void RequestData(string steamId, float now)
        {
            string me = MatchTracker.LocalSteamId;
            if (!IsSteamId64(me) || me == steamId) return;
            if (cacheViewer != me) { cache.Clear(); notBefore.Clear(); cacheViewer = me; }
            if (inFlight.Contains(steamId)) return;
            float nb;
            if (notBefore.TryGetValue(steamId, out nb) && now < nb) return;
            CardData have;
            if (cache.TryGetValue(steamId, out have) && now - have.fetchedAt < RefreshFloorSeconds) return;
            inFlight.Add(steamId);
            notBefore[steamId] = now + RefreshFloorSeconds;
            try
            {
                ApiClient.FetchH2HSummary(me, steamId, (ok, resp) => OnResponse(me, steamId, ok, resp));
            }
            catch (Exception ex)
            {
                inFlight.Remove(steamId);
                VanillaFixSupport.DiagLimited("ProfileCard", "fetch failed to start: " + ex.Message, 5);
            }
        }

        private static void OnResponse(string me, string steamId, bool ok, string resp)
        {
            try
            {
                inFlight.Remove(steamId);
                float now = Time.realtimeSinceStartup;
                if (cacheViewer != me) return;
                if (ok)
                {
                    var d = Parse(resp);
                    if (d == null)
                    {
                        // An older server (no card members yet): nothing to show, no re-ask this floor.
                        VanillaFixSupport.DiagLimited("ProfileCard", "response carries no card members", 3);
                        return;
                    }
                    d.fetchedAt = now;
                    cache[steamId] = d;
                    // A refresh that lands while this target's card is open (and not
                    // pinned) repaints it in place: the header is the fresh profile.
                    if (openFor == steamId && !pinned && panel != null && panel.Visible) Render(d, steamId);
                    return;
                }
                string err = resp ?? "";
                if (err.StartsWith("HTTP 429", StringComparison.Ordinal))
                {
                    int ra = ApiClient.ExtractJsonIntPublic(err, "retry_after");
                    notBefore[steamId] = now + Mathf.Clamp(ra, 1, 30) + 1f;
                }
                else notBefore[steamId] = now + RefreshFloorSeconds;
                int colon = err.IndexOf(':');
                Plugin.Log.LogInfo("[PROFILE-CARD] fetch failed: " + (colon > 0 ? err.Substring(0, colon) : "transport"));
            }
            catch (Exception ex)
            {
                VanillaFixSupport.DiagLimited("ProfileCard", "response handling failed: " + ex.Message, 5);
            }
        }

        /// <summary>The two card members, each sliced ONCE with the string-aware
        /// brace matcher and read only inside its own slice — a key search
        /// never spans the whole response (A-4). `"member":null` (unknown
        /// opponent, or a card statement that failed server-side) yields no
        /// slice. Returns null when neither member is present.</summary>
        internal static CardData Parse(string json)
        {
            if (string.IsNullOrEmpty(json)) return null;
            var d = new CardData();
            string prof = SliceObject(json, "profile");
            if (prof != null)
            {
                d.hasProfile = true;
                d.displayName = ApiClient.ExtractJsonStringPublic(prof, "display_name");
                d.title = ApiClient.ExtractJsonStringPublic(prof, "title");
                d.titleColor = ApiClient.ExtractJsonStringPublic(prof, "title_color");
                d.tier = ApiClient.ExtractJsonStringPublic(prof, "tier");
                d.tierColor = ApiClient.ExtractJsonStringPublic(prof, "tier_color");
                d.rating = ApiClient.ExtractJsonIntPublic(prof, "rating_1v1");
                d.rd = ApiClient.ExtractJsonIntPublic(prof, "rd_1v1");
                d.level = ApiClient.ExtractJsonIntPublic(prof, "level");
                d.isOnline = MemberIsNull(prof, "is_online") ? (bool?)null : ApiClient.ExtractJsonBoolPublic(prof, "is_online");
                d.lastSeenS = MemberIsNull(prof, "last_seen_s") ? (int?)null : ApiClient.ExtractJsonIntPublic(prof, "last_seen_s");
            }
            string modes = SliceObject(json, "modes");
            if (modes != null)
            {
                d.hasModes = true;
                string r = SliceObject(modes, "ranked_1v1");
                if (r != null)
                {
                    d.seriesW = ApiClient.ExtractJsonIntPublic(r, "series_w");
                    d.seriesL = ApiClient.ExtractJsonIntPublic(r, "series_l");
                    d.gamesW = ApiClient.ExtractJsonIntPublic(r, "games_w");
                    d.gamesL = ApiClient.ExtractJsonIntPublic(r, "games_l");
                }
                ReadWL(SliceObject(modes, "casual_1v1"), d.casual, "w", "l");
                ReadWL(SliceObject(modes, "team_2v2"), d.team, "w", "l");
                ReadWL(SliceObject(modes, "ffa"), d.ffa, "above", "below");
                string o = SliceObject(modes, "ovt");
                if (o != null)
                {
                    ReadWL(SliceObject(o, "as_solo"), d.ovtSolo, "w", "l");
                    ReadWL(SliceObject(o, "as_duo"), d.ovtDuo, "w", "l");
                }
                string lm = SliceObject(modes, "last_meeting");
                if (lm != null)
                {
                    d.lastAt = ApiClient.ExtractJsonStringPublic(lm, "at");
                    d.lastMode = ApiClient.ExtractJsonStringPublic(lm, "mode");
                    d.lastResult = ApiClient.ExtractJsonStringPublic(lm, "result");
                    if (string.IsNullOrEmpty(d.lastMode)) d.lastMode = null;
                }
                string st = SliceObject(modes, "streak");
                if (st != null)
                {
                    d.streakN = ApiClient.ExtractJsonIntPublic(st, "n");
                    d.streakHolder = ApiClient.ExtractJsonStringPublic(st, "holder");
                    if (string.IsNullOrEmpty(d.streakHolder) || d.streakN <= 0) d.streakHolder = null;
                }
                d.netRating = ApiClient.ExtractJsonIntPublic(modes, "net_rating_1v1");
            }
            return d.hasProfile || d.hasModes ? d : null;
        }

        private static void ReadWL(string obj, WinLoss into, string wKey, string lKey)
        {
            if (obj == null) return;
            into.w = Math.Max(0, ApiClient.ExtractJsonIntPublic(obj, wKey));
            into.l = Math.Max(0, ApiClient.ExtractJsonIntPublic(obj, lKey));
        }

        /// <summary>`"key":{...}` inside `json` → the object text, braces
        /// included; null when the key is absent, its value is not an object
        /// (null), or the braces do not close. The key pattern cannot match
        /// inside a string value: a quote inside a JSON string arrives escaped,
        /// so the `"` that must follow the key name is never there.</summary>
        internal static string SliceObject(string json, string key)
        {
            if (string.IsNullOrEmpty(json)) return null;
            string k = "\"" + key + "\":";
            int i = json.IndexOf(k, StringComparison.Ordinal);
            if (i < 0) return null;
            int p = i + k.Length;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t' || json[p] == '\r' || json[p] == '\n')) p++;
            if (p >= json.Length || json[p] != '{') return null;
            int close = ApiClient.FindMatchingBraceStringAware(json, p);
            if (close < 0) return null;
            return json.Substring(p, close - p + 1);
        }

        internal static bool MemberIsNull(string obj, string key)
        {
            if (string.IsNullOrEmpty(obj)) return true;
            string k = "\"" + key + "\":";
            int i = obj.IndexOf(k, StringComparison.Ordinal);
            if (i < 0) return true;
            int p = i + k.Length;
            while (p < obj.Length && (obj[p] == ' ' || obj[p] == '\t')) p++;
            return p + 4 <= obj.Length && string.CompareOrdinal(obj, p, "null", 0, 4) == 0;
        }

        internal static bool IsSteamId64(string s)
        {
            if (string.IsNullOrEmpty(s) || s.Length != 17) return false;
            for (int i = 0; i < s.Length; i++) if (s[i] < '0' || s[i] > '9') return false;
            return true;
        }

        // ── rendering ──

        private static void BuildChildren()
        {
            accent = panel.AddPanel("Accent", 0f, 0f, CardW, 3f, C_DIVIDER);
            txtName = panel.AddText("Name", PAD, NAME_Y, CardW - 2f * PAD, NAME_H, 20f, Color.white, UIFactory.AlignMidLeft);
            txtLine2 = panel.AddText("L2", PAD, LINE2_Y, CardW - 2f * PAD, LINE2_H, 14f, C_TEXT, UIFactory.AlignMidLeft);
            txtPresence = panel.AddText("Pres", PAD, PRES_Y, CardW - 2f * PAD, PRES_H, 13f, C_DIM, UIFactory.AlignMidLeft);
            divider = panel.AddPanel("Div", PAD, DIV_Y, CardW - 2f * PAD, 1f, C_DIVIDER);
            for (int i = 0; i < MaxRows; i++)
            {
                rowLabel[i] = panel.AddText("RL" + i, PAD, ROWS_Y, LABEL_W, ROW_H, 14f, C_DIM, UIFactory.AlignMidLeft);
                rowBarBg[i] = panel.AddPanel("RB" + i, BAR_X, ROWS_Y, BAR_W, BAR_H, C_BARBG);
                rowBarL[i] = panel.AddPanel("RV" + i, BAR_X, ROWS_Y, 0f, BAR_H, C_VIEWER);
                rowBarR[i] = panel.AddPanel("RT" + i, BAR_X, ROWS_Y, 0f, BAR_H, C_THEM);
                rowNums[i] = panel.AddText("RN" + i, NUMS_X, ROWS_Y, NUMS_W, ROW_H, 14f, C_TEXT, UIFactory.AlignMidRight);
            }
            txtEmpty = panel.AddText("Empty", PAD, ROWS_Y, CardW - 2f * PAD, ROW_H, 13f, C_DIM, UIFactory.AlignMidLeft);
            txtFoot1 = panel.AddText("F1", PAD, ROWS_Y, CardW - 2f * PAD, FOOT_H, 13f, C_DIM, UIFactory.AlignMidLeft);
            txtFoot2 = panel.AddText("F2", PAD, ROWS_Y, CardW - 2f * PAD, FOOT_H, 13f, C_DIM, UIFactory.AlignMidLeft);
            txtFoot3 = panel.AddText("F3", PAD, ROWS_Y, CardW - 2f * PAD, FOOT_H, 13f, C_DIM, UIFactory.AlignMidLeft);
        }

        private static void Render(CardData d, string steamId)
        {
            try
            {
                if (panel == null) panel = new TmpOverlayPanel("CR_ProfileCard", TmpOverlayPanel.DefaultSortingOrder, true);
                bool rebuilt;
                if (!panel.Ensure(out rebuilt)) { openFor = null; return; }
                if (rebuilt || txtName == null) BuildChildren();

                // Header: the name in the title colour, then title / tier / rating / level.
                string name = GameStateWatcher.StripRichText(d.displayName ?? "").Trim();
                if (string.IsNullOrEmpty(name)) name = I18n.Tr("Unknown player");
                UIFactory.SetColor(txtName, ParseHex(d.titleColor, Color.white));
                UIFactory.SetTextRaw(txtName, TmpOverlayPanel.FitOneLine(txtName, name, CardW - 2f * PAD));
                var l2 = new StringBuilder(96);
                string title = GameStateWatcher.StripRichText(d.title ?? "").Trim();
                // The dynamic "Current Rank" title resolves to the tier text itself: show it once.
                if (title.Length > 0 && !string.Equals(title, d.tier, StringComparison.Ordinal))
                    l2.Append("<color=").Append(HexOr(d.titleColor, "#FFFFFF")).Append(">[")
                      .Append(TruncSafe(title, 22)).Append("]</color>  ");
                if (!string.IsNullOrEmpty(d.tier))
                    l2.Append("<color=").Append(HexOr(d.tierColor, "#FFFFFF")).Append(">")
                      .Append(GameStateWatcher.StripRichText(d.tier)).Append("</color>  ");
                l2.Append(d.rating).Append(" <size=80%><color=#9AA0A6>±").Append(d.rd).Append("</color></size>  ");
                l2.Append("<color=#8FA3B8>").Append(I18n.TrF("Lv {0}", d.level)).Append("</color>");
                UIFactory.SetTextRaw(txtLine2, l2.ToString());
                string pres = "";
                if (d.isOnline == true) pres = "<color=#66FF88>●</color> <color=#66FF88>" + I18n.Tr("Online") + "</color>";
                else if (d.lastSeenS.HasValue) pres = "<color=#8FA3B8>" + I18n.TrF("Last seen {0}", Ago(d.lastSeenS.Value)) + "</color>";
                UIFactory.SetTextRaw(txtPresence, pres);
                SetActive(txtPresence, pres.Length > 0);
                UIFactory.SetImageColor(accent, ParseHex(d.tierColor, C_DIVIDER));

                // One row per mode with games; a mode never played together is not a row.
                float y = ROWS_Y;
                int rows = 0;
                rows = FillRow(rows, ref y, I18n.Tr("Ranked 1v1 series"), d.seriesW, d.seriesL);
                rows = FillRow(rows, ref y, I18n.Tr("Ranked 1v1 games"), d.gamesW, d.gamesL);
                rows = FillRow(rows, ref y, I18n.Tr("Casual 1v1"), d.casual.w, d.casual.l);
                rows = FillRow(rows, ref y, I18n.Tr("2v2 (opposite teams)"), d.team.w, d.team.l);
                rows = FillRow(rows, ref y, I18n.Tr("FFA (placed above / below)"), d.ffa.w, d.ffa.l);
                rows = FillRow(rows, ref y, I18n.Tr("1v2 as solo"), d.ovtSolo.w, d.ovtSolo.l);
                rows = FillRow(rows, ref y, I18n.Tr("1v2 as duo"), d.ovtDuo.w, d.ovtDuo.l);
                for (int i = rows; i < MaxRows; i++) HideRow(i);
                if (rows == 0)
                {
                    PlaceText(txtEmpty, y, ROW_H);
                    UIFactory.SetTextRaw(txtEmpty, I18n.Tr("No games together yet"));
                    SetActive(txtEmpty, true);
                    y += ROW_H;
                }
                else SetActive(txtEmpty, false);

                // Footer: last meeting, ranked series streak, net rating.
                y += 6f;
                string f1 = "", f2 = "", f3 = "";
                if (d.lastMode != null)
                    f1 = I18n.TrF("Last met: {0}  -  {1}  -  {2}", DateOf(d.lastAt), ModeName(d.lastMode), ResultName(d.lastResult));
                if (d.streakHolder != null)
                    f2 = d.streakHolder == "viewer"
                        ? "<color=#66DD77>" + I18n.TrF("Series streak: you x{0}", d.streakN) + "</color>"
                        : "<color=#FF8A8A>" + I18n.TrF("Series streak: them x{0}", d.streakN) + "</color>";
                if (d.seriesW + d.seriesL > 0)
                    f3 = I18n.TrF("Net rating vs them: {0}", (d.netRating > 0 ? "+" : "") + d.netRating);
                y = PlaceFoot(txtFoot1, f1, y);
                y = PlaceFoot(txtFoot2, f2, y);
                y = PlaceFoot(txtFoot3, f3, y);
                cardH = y + PAD_BOTTOM;

                panel.SetBackdrop(C_BG);
                panel.SetBackdropRaycast(pinned);
                openFor = steamId;
                panel.Show();
            }
            catch (Exception ex)
            {
                openFor = null;
                if (panel != null) panel.Hide();
                VanillaFixSupport.DiagLimited("ProfileCard", "render failed: " + ex.Message, 5);
            }
        }

        private static int FillRow(int i, ref float y, string label, int w, int l)
        {
            if (w + l <= 0 || i >= MaxRows) return i;
            PlaceText(rowLabel[i], y, ROW_H);
            UIFactory.SetTextRaw(rowLabel[i], label);
            PlaceText(rowNums[i], y, ROW_H);
            UIFactory.SetTextRaw(rowNums[i], w + " - " + l);
            float barY = y + (ROW_H - BAR_H) * 0.5f;
            float left = Mathf.Round(BAR_W * (float)w / (w + l));
            PlaceGO(rowBarBg[i], BAR_X, barY, BAR_W, BAR_H);
            PlaceGO(rowBarL[i], BAR_X, barY, left, BAR_H);
            PlaceGO(rowBarR[i], BAR_X + left, barY, BAR_W - left, BAR_H);
            SetActive(rowLabel[i], true); SetActive(rowNums[i], true);
            SetActiveGO(rowBarBg[i], true); SetActiveGO(rowBarL[i], left > 0f); SetActiveGO(rowBarR[i], BAR_W - left > 0f);
            y += ROW_H;
            return i + 1;
        }

        private static void HideRow(int i)
        {
            SetActive(rowLabel[i], false); SetActive(rowNums[i], false);
            SetActiveGO(rowBarBg[i], false); SetActiveGO(rowBarL[i], false); SetActiveGO(rowBarR[i], false);
        }

        private static float PlaceFoot(object tmp, string text, float y)
        {
            if (string.IsNullOrEmpty(text)) { SetActive(tmp, false); return y; }
            PlaceText(tmp, y, FOOT_H);
            UIFactory.SetTextRaw(tmp, text);
            SetActive(tmp, true);
            return y + FOOT_H;
        }

        private static void PlaceText(object tmp, float yTop, float h)
        {
            var comp = tmp as Component;
            if (comp == null) return;
            var rt = comp.GetComponent<RectTransform>();
            if (rt != null) TmpOverlayPanel.PlaceTopLeft(rt, rt.anchoredPosition.x, yTop, rt.sizeDelta.x, h);
        }

        private static void PlaceGO(GameObject go, float x, float yTop, float w, float h)
        {
            if (go == null) return;
            var rt = go.GetComponent<RectTransform>();
            if (rt != null) TmpOverlayPanel.PlaceTopLeft(rt, x, yTop, Mathf.Max(0f, w), h);
        }

        private static void SetActive(object tmp, bool on)
        {
            var comp = tmp as Component;
            if (comp != null && comp.gameObject.activeSelf != on) comp.gameObject.SetActive(on);
        }

        private static void SetActiveGO(GameObject go, bool on)
        {
            if (go != null && go.activeSelf != on) go.SetActive(on);
        }

        /// <summary>Beside the name, never under the pointer: to the right of
        /// the name's rect when that fits on screen, else to its left, else
        /// below (or above) it; clamped to the screen. Re-run every frame while
        /// unpinned, so the card follows a scrolling row (the rect is live).</summary>
        private static void Position(Rect a, Vector3 mp)
        {
            float W = CardW, H = cardH;
            float sw = Screen.width, sh = Screen.height;
            float x, y;
            if (a.width < 1f)
            {
                x = mp.x + 18f;
                y = mp.y - H - 12f;
            }
            else
            {
                x = a.xMax + 10f;
                y = a.center.y - H * 0.5f;
                if (x + W > sw - 4f) x = a.xMin - W - 10f;
                if (x < 4f)
                {
                    x = Mathf.Clamp(mp.x - W * 0.5f, 4f, Mathf.Max(4f, sw - W - 4f));
                    y = a.yMin - H - 8f;
                    if (y < 4f) y = a.yMax + 8f;
                }
            }
            x = Mathf.Clamp(x, 4f, Mathf.Max(4f, sw - W - 4f));
            y = Mathf.Clamp(y, 4f, Mathf.Max(4f, sh - H - 4f));
            cardRect = new Rect(x, y, W, H);
            panel.SetRect(x, y, W, H);
        }

        private static void Pin()
        {
            if (pinned || openFor == null || panel == null || !panel.Visible) return;
            pinned = true;
            panel.SetBackdropRaycast(true);
        }

        private static void CloseCard()
        {
            pinned = false;
            if (panel != null) panel.SetBackdropRaycast(false);
            HideCard();
        }

        private static void HideCard()
        {
            openFor = null;
            cardRect = Offscreen;
            if (panel != null) panel.Hide();
        }

        // ── text helpers ──

        internal static string Ago(int seconds)
        {
            if (seconds < 60) return I18n.Tr("just now");
            if (seconds < 3600) return I18n.TrF("{0} min ago", seconds / 60);
            if (seconds < 86400) return I18n.TrF("{0} h ago", seconds / 3600);
            return I18n.TrF("{0} d ago", seconds / 86400);
        }

        private static string ModeName(string mode)
        {
            switch (mode)
            {
                case "ranked_1v1": return I18n.Tr("Ranked 1v1");
                case "casual_1v1": return I18n.Tr("Casual 1v1");
                case "team_2v2": return I18n.Tr("2v2");
                case "ffa": return I18n.Tr("FFA");
                case "ovt": return I18n.Tr("1v2");
                default: return mode ?? "";
            }
        }

        private static string ResultName(string r)
        {
            switch (r)
            {
                case "W": return I18n.Tr("Win");
                case "L": return I18n.Tr("Loss");
                case "T": return I18n.Tr("Tie");
                default: return r ?? "";
            }
        }

        /// <summary>The meeting's DATE, as the history rows render theirs — a
        /// server timestamp is never subtracted from this clock.</summary>
        private static string DateOf(string iso)
        {
            try { if (!string.IsNullOrEmpty(iso) && iso.Length >= 10) return DateFmt.Short(DateTime.Parse(iso)); } catch { }
            return "";
        }

        private static string TruncSafe(string s, int max)
        {
            if (string.IsNullOrEmpty(s) || s.Length <= max) return s ?? "";
            return s.Substring(0, TmpOverlayPanel.SafeCut(s, max)).TrimEnd() + "...";
        }

        private static string HexOr(string hex, string fallback)
        {
            Color c;
            return !string.IsNullOrEmpty(hex) && hex.Length <= 9 && ColorUtility.TryParseHtmlString(hex, out c) ? hex : fallback;
        }

        private static Color ParseHex(string hex, Color fallback)
        {
            Color c;
            return !string.IsNullOrEmpty(hex) && hex.Length <= 9 && ColorUtility.TryParseHtmlString(hex, out c) ? c : fallback;
        }
    }
}
