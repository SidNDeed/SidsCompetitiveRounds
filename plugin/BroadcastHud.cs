using System;
using System.Collections.Generic;
using System.Text;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// SCR Broadcast §4 — the per-fighter stat/action panels the stream
    /// shows. IMGUI, drawn from CompetitiveUI.DrawUI directly after
    /// SpectatorHud (the codebase's overlay pattern).
    ///
    /// Gate: BroadcastMode active (identity + config) AND the spectator
    /// session has activated AND no leave is requested. Everything is a
    /// no-op on every other install.
    ///
    /// Data sources:
    ///  - Stats: TabStatsOverlay's shared 8 Hz snapshot via the read-only
    ///    Broadcast* accessors (#162: cached strings, no per-frame reads).
    ///  - Watched-game metadata (ratings, tournament flag): BroadcastMode's
    ///    stored /broadcast/target response — deliberately NOT the public
    ///    games-list cache (§4).
    ///  - Action display (§4b, VERIFIED against
    ///    logs-snapshot/decompiled/SyncPlayerMovement.cs): replicas apply the
    ///    owner's ACTUAL input each stream drain — data.input.direction /
    ///    jumpIsPressed are genuine held state; RPCAO_DoBlock fires ONLY for
    ///    BlockTriggerType.Default (real key presses; card auto-blocks travel
    ///    RPCA_DoBlock with their type attached); SyncPlayerMovement.Shoot
    ///    fires per owner-side gun attack whatever initiated it, so SHOT is
    ///    labeled an ACTIVATION, not a click.
    ///
    /// L10n: DELIBERATELY English-only with NO I18n.Tr anywhere in this file.
    /// The broadcast seat is our own bot; running these literals through Tr
    /// would put stream-only strings into the translation catalogue and hand
    /// translators keys no player can ever see (#295 extractor harvests at
    /// call sites).
    /// </summary>
    internal static class BroadcastHud
    {
        private static GUIStyle stName, stStat, stStatLabel, stKey, stTag;

        private const float FLASH_SECONDS = 0.15f;

        // Action-display edge state, keyed by Photon actor number. Cleared on
        // any boundary/session generation move (covers rematch + session
        // change) — a 150ms flash cannot meaningfully outlive either, but the
        // reset rule keeps stale latches structurally impossible (§4 edge
        // resets; death is handled per-draw by skipping dead bodies).
        private static readonly Dictionary<int, float> _blockFlashUntil = new Dictionary<int, float>();
        private static readonly Dictionary<int, float> _shotFlashUntil = new Dictionary<int, float>();
        private static int _edgeBoundaryGen = int.MinValue;
        private static int _edgeAttemptGen = int.MinValue;

        // Cached derived strings (header name+rating, cards line, FFA strip
        // lines) — rebuilt ONLY when TabStatsOverlay's snapshot generation
        // moves (8 Hz, r1 F8), so Repaint never allocates (#162). The caches
        // are additionally invalidated on boundary/session generation change
        // (r1 F9) via ResetEdgesIfMoved, which also forces the next snapshot
        // refresh so a rematch's deck reset cannot show stale for 0.5s.
        private static readonly List<string> _headerCache = new List<string>();
        private static readonly List<string> _nameCache = new List<string>();
        private static readonly List<string> _cardsCache = new List<string>();
        private static readonly List<string> _ffaLine1Cache = new List<string>();
        private static readonly List<string> _ffaLine2Cache = new List<string>();
        // Bug 239: one-line name fit state, per fighter per surface (FFA
        // strip cell / corner panel). GUI.skin.label word-wraps by default,
        // so a long "Name (elo)" wrapped to two lines inside the strip's
        // 18px-tall rect and rendered clipped top AND bottom. The fit picks
        // the largest font 14..10 that keeps ONE line inside the cell,
        // drops the rating before shrinking below readability, and only
        // then hard-trims the bare name. Cached per (text, width) so
        // CalcSize runs only when the header or the cell width changes.
        private struct NameFit { public string src; public float w; public string text; public int size; }
        private static NameFit[] _ffaNameFit = new NameFit[0];
        private static NameFit[] _panelNameFit = new NameFit[0];
        private static readonly GUIContent _measure = new GUIContent();
        // FFA mini card bar (Stan, Aug 18): five 2-letter slots per fighter,
        // rebuilt at snapshot cadence like every other derived string.
        private const int FFA_CARD_SLOTS = 5;
        private static readonly List<string[]> _ffaCardAbbrevCache = new List<string[]>();
        private static int _cachesSnapshotGen = int.MinValue;
        private static readonly List<string> _sortScratch = new List<string>(10);
        private static readonly StringBuilder _sb = new StringBuilder(64);

        internal static void Draw()
        {
            try
            {
                if (Event.current == null || Event.current.type != EventType.Repaint) return;
                if (!BroadcastMode.DirectorActive) return;
                ResetEdgesIfMoved();
                if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) return;
                if (!SpectatorSync.HasEverActivated) return;

                int n = TabStatsOverlay.BroadcastEnsureFresh();
                if (n <= 0) return;
                EnsureStyles();
                RefreshCaches(n);

                DrawTournamentTag();

                string mode = SpectatorSync.WatchedMode;
                if (mode == "ffa") DrawFfaStrip(n);
                else if (n == 2) Draw1v1Panels();
                else DrawTeamPanels(n);
            }
            catch { /* overlay must never break the seat */ }
        }

        // ── patch feed (called from the postfixes below) ─────────────────

        internal static void NoteBlockPress(Photon.Pun.SyncPlayerMovement smp)
        {
            // Cheap early-out on every non-broadcast seat: two static reads.
            if (!BroadcastMode.IsBroadcastIdentity || !RoomActors.LocalIsSpectator) return;
            try
            {
                int actor = ActorOf(smp);
                if (actor > 0) _blockFlashUntil[actor] = Time.realtimeSinceStartup + FLASH_SECONDS;
            }
            catch { }
        }

        internal static void NoteShot(Photon.Pun.SyncPlayerMovement smp)
        {
            if (!BroadcastMode.IsBroadcastIdentity || !RoomActors.LocalIsSpectator) return;
            try
            {
                int actor = ActorOf(smp);
                if (actor > 0) _shotFlashUntil[actor] = Time.realtimeSinceStartup + FLASH_SECONDS;
            }
            catch { }
        }

        private static int ActorOf(Photon.Pun.SyncPlayerMovement smp)
        {
            if (smp == null) return -1;
            try
            {
                var view = smp.photonView != null ? smp.photonView : smp.GetComponent<Photon.Pun.PhotonView>();
                return view != null ? view.OwnerActorNr : -1;
            }
            catch { return -1; }
        }

        private static void ResetEdgesIfMoved()
        {
            try
            {
                int bg = SpectatorSync.BoundaryGeneration;
                int ag = SpectatorSync.BoundaryAttemptGeneration;
                if (bg != _edgeBoundaryGen || ag != _edgeAttemptGen)
                {
                    _edgeBoundaryGen = bg;
                    _edgeAttemptGen = ag;
                    _blockFlashUntil.Clear();
                    _shotFlashUntil.Clear();
                    // r1 F9: a boundary reconcile resets/replays fighter decks
                    // — the derived-string caches AND the underlying snapshot
                    // must both refresh now, not up to 0.5s later.
                    _cachesSnapshotGen = int.MinValue;
                    try { TabStatsOverlay.BroadcastForceNextRefresh(); } catch { }
                }
            }
            catch { }
        }

        // ── caches ───────────────────────────────────────────────────────

        private static void RefreshCaches(int n)
        {
            // Rebuild exactly when the shared snapshot moved (r1 F8/F9) —
            // never per-Repaint, never on a wall-clock TTL.
            int snapGen = TabStatsOverlay.BroadcastSnapshotGeneration;
            if (snapGen == _cachesSnapshotGen
                && _headerCache.Count == n && _cardsCache.Count == n) return;
            _cachesSnapshotGen = snapGen;
            SizeCache(_headerCache, n);
            SizeCache(_nameCache, n);
            SizeCache(_cardsCache, n);
            SizeCache(_ffaLine1Cache, n);
            SizeCache(_ffaLine2Cache, n);
            if (_ffaNameFit.Length < n)
            {
                _ffaNameFit = new NameFit[n];
                _panelNameFit = new NameFit[n];
            }
            while (_ffaCardAbbrevCache.Count < n) _ffaCardAbbrevCache.Add(new string[FFA_CARD_SLOTS]);
            while (_ffaCardAbbrevCache.Count > n) _ffaCardAbbrevCache.RemoveAt(_ffaCardAbbrevCache.Count - 1);

            // Ratings from the stored target response (§4): roster-aligned to
            // the server's SORTED-ordinal steam-id roster — the same order
            // GameStateWatcher's attest builds (sids.Sort(StringComparer.
            // Ordinal)), so sorting the live fighters' ids reproduces it.
            var meta = BroadcastMode.CurrentTargetMeta;
            bool haveRatings = false;
            _sortScratch.Clear();
            if (meta != null && meta.ratings != null && meta.ratings.Count == n)
            {
                haveRatings = true;
                for (int i = 0; i < n; i++)
                {
                    string sid = SteamIdOfFighter(i);
                    // Any unresolved id makes the positional mapping garbage —
                    // drop ratings entirely rather than pin one fighter's elo
                    // on another (the SetWatchedMeta length rule, same logic).
                    if (string.IsNullOrEmpty(sid)) { haveRatings = false; break; }
                    _sortScratch.Add(sid);
                }
                if (haveRatings) _sortScratch.Sort(StringComparer.Ordinal);
            }

            bool ffa = false;
            try { ffa = SpectatorSync.WatchedMode == "ffa"; } catch { }
            for (int i = 0; i < n; i++)
            {
                _sb.Length = 0;
                _sb.Append(TabStatsOverlay.BroadcastFighterName(i));
                _nameCache[i] = _sb.ToString();
                if (haveRatings)
                {
                    int at = _sortScratch.IndexOf(SteamIdOfFighter(i));
                    if (at >= 0 && at < meta.ratings.Count)
                        _sb.Append("  (").Append(((int)Math.Round(meta.ratings[at])).ToString(
                            System.Globalization.CultureInfo.InvariantCulture)).Append(')');
                }
                _headerCache[i] = _sb.ToString();
                _cardsCache[i] = "Cards: " + TabStatsOverlay.BroadcastFighterCardCount(i).ToString(
                    System.Globalization.CultureInfo.InvariantCulture);
                // r1 F8: the FFA strip's composite lines are built HERE, at
                // snapshot cadence — DrawFfaStrip only reads. Curated
                // indices: 0=HP, 1=Damage (validated map). Stan's Aug 18
                // stream notes (Sid agreed): Lives + card-count dropped
                // (they read "1" and "5" virtually always in FFA), HP and
                // Dmg share one line, and the freed line carries a mini
                // card bar — up to five two-letter squares in vanilla
                // CardBar's own abbreviation style, from the snapshot's
                // canonical card names.
                if (ffa)
                {
                    _sb.Length = 0;
                    _sb.Append("HP ").Append(TabStatsOverlay.BroadcastStatValue(i, 0))
                       .Append("   Dmg ").Append(TabStatsOverlay.BroadcastStatValue(i, 1));
                    _ffaLine1Cache[i] = _sb.ToString();
                    var abbrevs = _ffaCardAbbrevCache[i];
                    for (int c = 0; c < FFA_CARD_SLOTS; c++)
                        abbrevs[c] = CardAbbrev(TabStatsOverlay.BroadcastFighterCardName(i, c));
                    _ffaLine2Cache[i] = "";
                }
                else
                {
                    _ffaLine1Cache[i] = "";
                    _ffaLine2Cache[i] = "";
                }
            }
        }

        private static void SizeCache(List<string> cache, int n)
        {
            while (cache.Count < n) cache.Add("");
            while (cache.Count > n) cache.RemoveAt(cache.Count - 1);
        }

        /// <summary>Vanilla CardBar's own abbreviation: the first two
        /// letters, first upper + second lower ("BombsAway" -> "Bo") —
        /// exactly what CardBar.AddCard renders in its squares, so the
        /// strip's mini bar reads like the real one. "" for an empty slot.</summary>
        private static string CardAbbrev(string canonicalName)
        {
            if (string.IsNullOrEmpty(canonicalName)) return "";
            char a = char.ToUpperInvariant(canonicalName[0]);
            if (canonicalName.Length < 2) return a.ToString();
            char b = char.ToLowerInvariant(canonicalName[1]);
            return new string(new[] { a, b });
        }

        /// <summary>Bug 239: fit one fighter header into availW as a SINGLE
        /// line. Preference order: full "Name (elo)" at 14..10pt, then the
        /// bare name at 14..10pt (the rating is the first thing to go —
        /// the name is what the stream needs), then the bare name
        /// hard-trimmed with ".." at the 10pt floor. Measures with the
        /// style's own CalcSize, so the result never overflows the cell;
        /// cached per (header, width) — recomputes only when the snapshot
        /// text or the cell width actually changes.</summary>
        private static void FitNameLine(ref NameFit fit, string header, string bare, float availW, GUIStyle style)
        {
            if (fit.text != null && fit.src == header && Math.Abs(fit.w - availW) < 0.5f) return;
            fit.src = header;
            fit.w = availW;
            int prevSize = style.fontSize;
            try
            {
                // Priority (review r1 F4): a READABLE name beats a shrunken
                // name+rating. The full header only wins at comfortable
                // sizes (14..12); below that the rating is dropped and the
                // bare name gets the whole 14..10 range before any header
                // retry at the floor sizes.
                for (int s = 14; s >= 12; s--)
                {
                    style.fontSize = s;
                    _measure.text = header;
                    if (style.CalcSize(_measure).x <= availW) { fit.text = header; fit.size = s; return; }
                }
                if (!string.IsNullOrEmpty(bare) && bare != header)
                {
                    for (int s = 14; s >= 10; s--)
                    {
                        style.fontSize = s;
                        _measure.text = bare;
                        if (style.CalcSize(_measure).x <= availW) { fit.text = bare; fit.size = s; return; }
                    }
                }
                else
                {
                    // No separate bare form: let the header use the floor
                    // sizes too before hard-trimming.
                    for (int s = 11; s >= 10; s--)
                    {
                        style.fontSize = s;
                        _measure.text = header;
                        if (style.CalcSize(_measure).x <= availW) { fit.text = header; fit.size = s; return; }
                    }
                }
                style.fontSize = 10;
                string basis = string.IsNullOrEmpty(bare) ? header : bare;
                for (int len = basis.Length - 1; len >= 1; len--)
                {
                    _measure.text = basis.Substring(0, len) + "..";
                    if (style.CalcSize(_measure).x <= availW) { fit.text = _measure.text; fit.size = 10; return; }
                }
                fit.text = basis;
                fit.size = 10;
            }
            finally { style.fontSize = prevSize; }
        }

        private static string SteamIdOfFighter(int i)
        {
            try
            {
                var body = TabStatsOverlay.BroadcastFighterBody(i);
                var owner = body?.data?.view != null ? body.data.view.Owner : null;
                return owner != null ? (RoomActors.SteamIdOf(owner) ?? "") : "";
            }
            catch { return ""; }
        }

        // ── layouts ──────────────────────────────────────────────────────

        private static void DrawTournamentTag()
        {
            var meta = BroadcastMode.CurrentTargetMeta;
            if (meta == null || !meta.is_tournament) return;
            // Just under SpectatorHud's top bar (bar: y 4..32).
            float w = 220f;
            var r = new Rect((Screen.width - w) / 2f, 34f, w, 20f);
            GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0.28f, 0.21f, 0.02f, 0.85f), 0, 0);
            var prev = GUI.contentColor;
            GUI.contentColor = new Color(1f, 0.85f, 0.3f);
            GUI.Label(r, "TOURNAMENT MATCH", stTag);
            GUI.contentColor = prev;
        }

        private const float PANEL_W = 232f;
        private const float PANEL_MARGIN_X = 10f;

        private static float PanelHeight(bool withActions)
        {
            int stats = TabStatsOverlay.BroadcastStatCount;
            return 26f + stats * 17f + 16f + (withActions ? 46f : 0f) + 10f;
        }

        // ── top anchor: measured just under the vanilla card bars ─────────
        // (Sid, Aug 18: the mid/low panels sat over the arena — "move them to
        // the top corners, under the cards".) The bars are uGUI rows under
        // ROUNDS' ScreenSpaceCamera canvas, so their screen rect must go
        // through the canvas camera (#6); measured live rather than
        // hardcoded because the rows' height depends on resolution and the
        // bars only exist once a game is assembled. 1s cache (#162);
        // fallback sits below the spectator top bar + tournament tag.
        private static float _anchorYCache = 90f;
        private static float _anchorYAt = -999f;
        private static readonly Vector3[] _cornerScratch = new Vector3[4];
        private static Type _tCanvasCached;
        private static System.Reflection.PropertyInfo _piRenderMode, _piWorldCamera;

        /// <summary>The canvas camera for a uGUI element, by reflection (#15:
        /// no UIModule reference in this assembly). Same walk NativeUI's
        /// hover-region code uses: nearest Canvas ancestor; renderMode 0
        /// (ScreenSpaceOverlay) means world corners already ARE screen
        /// points; otherwise worldCamera (Camera.main fallback), per #6.</summary>
        private static Camera ResolveUiCamera(Component element, out bool overlay, out bool resolved)
        {
            overlay = false;
            resolved = false;
            try
            {
                if (_tCanvasCached == null)
                {
                    _tCanvasCached = UIFactory.tCanvas
                        ?? Type.GetType("UnityEngine.Canvas, UnityEngine.UIModule");
                    if (_tCanvasCached != null)
                    {
                        var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
                        _piRenderMode = _tCanvasCached.GetProperty("renderMode", bf);
                        _piWorldCamera = _tCanvasCached.GetProperty("worldCamera", bf);
                    }
                }
                if (_tCanvasCached == null) return null;
                var t = element.transform;
                while (t != null)
                {
                    var cc = t.GetComponent(_tCanvasCached);
                    if (cc != null)
                    {
                        resolved = true;
                        int rm = _piRenderMode != null ? (int)_piRenderMode.GetValue(cc) : 0;
                        if (rm == 0) { overlay = true; return null; }
                        var cam = _piWorldCamera != null ? _piWorldCamera.GetValue(cc) as Camera : null;
                        return cam != null ? cam : Camera.main;
                    }
                    t = t.parent;
                }
            }
            catch { }
            return null;
        }

        private static float TopAnchorY()
        {
            if (Time.realtimeSinceStartup - _anchorYAt < 1f) return _anchorYCache;
            _anchorYAt = Time.realtimeSinceStartup;
            float bottom = 58f;
            try
            {
                var handler = CardBarHandler.instance;
                var bars = handler != null ? handler.cardBars : null;
                if (bars != null)
                {
                    Camera uiCam = null;
                    bool overlay = false, camResolved = false;
                    for (int i = 0; i < bars.Length; i++)
                    {
                        var bar = bars[i];
                        if (bar == null || !bar.gameObject.activeInHierarchy) continue;
                        var rt = bar.transform as RectTransform;
                        if (rt == null) continue;
                        if (!camResolved)
                        {
                            uiCam = ResolveUiCamera(bar, out overlay, out camResolved);
                            if (!camResolved) break;   // no canvas found: keep the fallback anchor
                        }
                        rt.GetWorldCorners(_cornerScratch);
                        float minScreenY = float.MaxValue;
                        for (int c = 0; c < 4; c++)
                        {
                            Vector3 world = _cornerScratch[c];
                            float sy = overlay || uiCam == null ? world.y : uiCam.WorldToScreenPoint(world).y;
                            if (sy < minScreenY) minScreenY = sy;
                        }
                        // IMGUI y runs downward; screen y upward.
                        float guiBottom = Screen.height - minScreenY;
                        if (guiBottom > bottom) bottom = guiBottom;
                    }
                }
            }
            catch { }
            _anchorYCache = Mathf.Clamp(bottom + 6f, 58f, Screen.height * 0.35f);
            return _anchorYCache;
        }

        /// <summary>1v1: panels in the TOP corners, directly under the card
        /// bars (measured — TopAnchorY), team 0 left / team 1 right — the
        /// same left/right convention the spectator top bar uses. Action
        /// rows on (1v1 first, §4). Replaces the original bottom-side
        /// placement that floated over the arena (Sid, Aug 18); the old
        /// BroadcastHudOffsetX/Y config pair is retired with it.</summary>
        private static void Draw1v1Panels()
        {
            float h = PanelHeight(withActions: true);
            float y = TopAnchorY();
            DrawPanel(0, new Rect(PANEL_MARGIN_X, y, PANEL_W, h), withActions: true);
            DrawPanel(1, new Rect(Screen.width - PANEL_MARGIN_X - PANEL_W, y, PANEL_W, h), withActions: true);
        }

        /// <summary>2v2 / 1v2: compact panels in the top corners under the
        /// card bars (same measured anchor as 1v1), stacked per team.
        /// Snapshot order is team-major (TabStatsOverlay sorts TeamID then
        /// PlayerID), so a simple split by TeamID lands teammates on the
        /// same side. No action rows (§4: action display is 1v1-first).</summary>
        private static void DrawTeamPanels(int n)
        {
            float h = PanelHeight(withActions: false);
            float leftY = TopAnchorY(), rightY = leftY;
            for (int i = 0; i < n; i++)
            {
                var body = TabStatsOverlay.BroadcastFighterBody(i);
                int team = 0;
                try { team = body != null ? body.TeamID : 0; } catch { }
                bool left = team == 0;
                var r = left
                    ? new Rect(10f, leftY, PANEL_W, h)
                    : new Rect(Screen.width - 10f - PANEL_W, rightY, PANEL_W, h);
                DrawPanel(i, r, withActions: false);
                if (left) leftY += h + 8f; else rightY += h + 8f;
            }
        }

        /// <summary>FFA: one compact strip across the top (below the bar) —
        /// name, then HP + Damage on one line, then the mini card bar: five
        /// two-letter squares (Stan's Aug 18 stream notes, Sid agreed —
        /// Lives and the card COUNT are gone; in FFA they read "1" and "5"
        /// virtually always, and what people actually want is WHICH cards).</summary>
        private static void DrawFfaStrip(int n)
        {
            float cellW = Mathf.Min(180f, (Screen.width - 40f) / Mathf.Max(1, n));
            float x = (Screen.width - cellW * n) / 2f;
            float y = 58f;   // below the spectator bar + tournament tag
            for (int i = 0; i < n; i++)
            {
                var r = new Rect(x + i * cellW, y, cellW - 4f, 58f);
                GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                    new Color(0f, 0f, 0f, 0.62f), 0, 0);
                var prev = GUI.contentColor;
                GUI.contentColor = TabStatsOverlay.BroadcastFighterColor(i);
                // Bug 239: fitted single line — long names used to word-wrap
                // inside this 18px rect and clip top+bottom on stream.
                string hdr = _headerCache.Count > i ? _headerCache[i] : "";
                string bare = _nameCache.Count > i ? _nameCache[i] : hdr;
                FitNameLine(ref _ffaNameFit[i], hdr, bare, r.width - 12f, stName);
                stName.fontSize = _ffaNameFit[i].size;
                GUI.Label(new Rect(r.x + 6, r.y + 2, r.width - 12, 18), _ffaNameFit[i].text, stName);
                GUI.contentColor = prev;
                // r1 F8: composite lines come pre-built from RefreshCaches
                // (snapshot cadence) — zero string work per Repaint.
                GUI.Label(new Rect(r.x + 6, r.y + 20, r.width - 12, 17),
                    _ffaLine1Cache.Count > i ? _ffaLine1Cache[i] : "", stStat);
                if (i < _ffaCardAbbrevCache.Count)
                {
                    var abbrevs = _ffaCardAbbrevCache[i];
                    float slotGap = 3f;
                    float slotW = (r.width - 12f - slotGap * (FFA_CARD_SLOTS - 1)) / FFA_CARD_SLOTS;
                    float sy = r.y + 39f;
                    for (int c = 0; c < FFA_CARD_SLOTS; c++)
                    {
                        var sr = new Rect(r.x + 6 + c * (slotW + slotGap), sy, slotW, 16f);
                        bool filled = !string.IsNullOrEmpty(abbrevs[c]);
                        GUI.DrawTexture(sr, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                            filled ? new Color(0.16f, 0.16f, 0.22f, 0.95f)
                                   : new Color(0.08f, 0.08f, 0.10f, 0.55f), 0, 0);
                        GUI.DrawTexture(new Rect(sr.x, sr.y, sr.width, 1), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(1f, 1f, 1f, filled ? 0.35f : 0.12f), 0, 0);
                        if (filled) GUI.Label(sr, abbrevs[c], stKey);
                    }
                }
            }
        }

        private static void DrawPanel(int i, Rect r, bool withActions)
        {
            var body = TabStatsOverlay.BroadcastFighterBody(i);
            if (body == null) return;

            GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0f, 0f, 0f, 0.66f), 0, 0);

            float y = r.y + 4f;
            var prev = GUI.contentColor;
            GUI.contentColor = TabStatsOverlay.BroadcastFighterColor(i);
            // Bug 239 sibling: the 20px panel header word-wrapped the same way.
            string hdr = _headerCache.Count > i ? _headerCache[i] : "";
            string bare = _nameCache.Count > i ? _nameCache[i] : hdr;
            if (i < _panelNameFit.Length)
            {
                FitNameLine(ref _panelNameFit[i], hdr, bare, r.width - 16f, stName);
                stName.fontSize = _panelNameFit[i].size;
                hdr = _panelNameFit[i].text;
            }
            GUI.Label(new Rect(r.x + 8, y, r.width - 16, 20), hdr, stName);
            GUI.contentColor = prev;
            y += 22f;

            int stats = TabStatsOverlay.BroadcastStatCount;
            for (int s = 0; s < stats; s++)
            {
                if ((s & 1) == 0)
                    GUI.DrawTexture(new Rect(r.x + 4, y, r.width - 8, 17), Texture2D.whiteTexture,
                        ScaleMode.StretchToFill, true, 0, new Color(1f, 1f, 1f, 0.04f), 0, 0);
                GUI.Label(new Rect(r.x + 8, y, 92, 17), TabStatsOverlay.BroadcastStatLabel(s), stStatLabel);
                GUI.Label(new Rect(r.x + 100, y, r.width - 108, 17), TabStatsOverlay.BroadcastStatValue(i, s), stStat);
                y += 17f;
            }
            GUI.Label(new Rect(r.x + 8, y, r.width - 16, 16), _cardsCache.Count > i ? _cardsCache[i] : "", stStatLabel);
            y += 18f;

            if (withActions) DrawActionRow(body, new Rect(r.x + 8, y, r.width - 16, 42));
        }

        // ── action display (§4b) ─────────────────────────────────────────

        private static void DrawActionRow(Player body, Rect area)
        {
            bool left = false, right = false, jump = false, dead = false;
            float aimX = 0f, aimY = 0f;
            try
            {
                dead = body.data.dead;
                if (!dead)
                {
                    var input = body.data.input;
                    if (input != null)
                    {
                        // Replica-applied owner input (decompiled
                        // SyncPlayerMovement.cs:69-71) — genuine held state.
                        left = input.direction.x < -0.3f;
                        right = input.direction.x > 0.3f;
                        jump = input.jumpIsPressed;
                        aimX = input.aimDirection.x;
                        aimY = input.aimDirection.y;
                    }
                }
            }
            catch { }

            int actor = -1;
            try { actor = body.data.view != null ? body.data.view.OwnerActorNr : -1; } catch { }
            float now = Time.realtimeSinceStartup;
            float until;
            // Death edge-reset (§4): a dead body shows nothing pressed.
            bool shot = !dead && actor > 0 && _shotFlashUntil.TryGetValue(actor, out until) && until > now;
            bool block = !dead && actor > 0 && _blockFlashUntil.TryGetValue(actor, out until) && until > now;

            // Row budget (r1 F10): 24+3 + 24+3 + 40+3 + 40+3 + 46+3 + 26 =
            // 215 px, inside the 216 px panel interior (PANEL_W 232 - 2*8) —
            // the aim box can no longer clip past the panel edge.
            float keyH = 26f;
            float x = area.x;
            DrawKey(new Rect(x, area.y, 24, keyH), "<", left); x += 27;
            DrawKey(new Rect(x, area.y, 24, keyH), ">", right); x += 27;
            DrawKey(new Rect(x, area.y, 40, keyH), "JUMP", jump); x += 43;
            // SHOT is an ACTIVATION indicator (owner gun attack whatever
            // initiated it — §4b decompile note), not a raw click.
            DrawKey(new Rect(x, area.y, 40, keyH), "SHOT", shot); x += 43;
            DrawKey(new Rect(x, area.y, 46, keyH), "BLOCK", block); x += 49;
            DrawAim(new Rect(x, area.y, keyH, keyH), aimX, aimY, dead);
        }

        /// <summary>Same visual language as CompetitiveUI.DrawKeyBox (pressed
        /// = red fill + bright edge, idle = dim slate). Local copy — the
        /// original is private and carries its own style pair.</summary>
        private static void DrawKey(Rect r, string label, bool pressed)
        {
            Color fill = pressed
                ? new Color(0.85f, 0.18f, 0.18f, 0.92f)
                : new Color(0.10f, 0.10f, 0.13f, 0.78f);
            Color edge = pressed
                ? new Color(1f, 0.5f, 0.5f, 0.9f)
                : new Color(1f, 1f, 1f, 0.35f);
            GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, fill, 0, 0);
            GUI.DrawTexture(new Rect(r.x, r.y, r.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            GUI.DrawTexture(new Rect(r.x, r.y + r.height - 1, r.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            GUI.DrawTexture(new Rect(r.x, r.y, 1, r.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            GUI.DrawTexture(new Rect(r.x + r.width - 1, r.y, 1, r.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, edge, 0, 0);
            var prev = GUI.contentColor;
            GUI.contentColor = Color.white;
            GUI.Label(r, label, stKey);
            GUI.contentColor = prev;
        }

        /// <summary>Optional aim arrow (§4): a thin bar rotated to the
        /// replica's aim direction inside a small box.</summary>
        private static void DrawAim(Rect r, float ax, float ay, bool dead)
        {
            GUI.DrawTexture(r, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(0.10f, 0.10f, 0.13f, 0.78f), 0, 0);
            if (dead || (ax * ax + ay * ay) < 0.01f) return;
            // Screen y grows downward; game aim y grows upward.
            float angle = Mathf.Atan2(-ay, ax) * Mathf.Rad2Deg;
            var pivot = new Vector2(r.x + r.width / 2f, r.y + r.height / 2f);
            var saved = GUI.matrix;
            GUIUtility.RotateAroundPivot(angle, pivot);
            GUI.DrawTexture(new Rect(pivot.x - 2f, pivot.y - 1.5f, r.width / 2f - 3f, 3f),
                Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                new Color(1f, 0.85f, 0.3f, 0.95f), 0, 0);
            GUI.matrix = saved;
        }

        private static void EnsureStyles()
        {
            if (stName != null) return;
            // Bug 239: names are single-line by contract — GUI.skin.label
            // defaults wordWrap ON, which is what wrapped long names into
            // the 18px strip rect. Overflow clipping keeps tall glyph
            // metrics from shaving letter tops (#143); horizontal overflow
            // cannot happen because FitNameLine measures with this style.
            stName = new GUIStyle(GUI.skin.label) { fontSize = 14, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft, wordWrap = false, clipping = TextClipping.Overflow };
            stStat = new GUIStyle(GUI.skin.label) { fontSize = 12, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft };
            stStatLabel = new GUIStyle(GUI.skin.label) { fontSize = 12, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft };
            stStatLabel.normal.textColor = new Color(0.72f, 0.76f, 0.84f);
            stKey = new GUIStyle(GUI.skin.label) { fontSize = 11, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
            stTag = new GUIStyle(GUI.skin.label) { fontSize = 12, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
        }
    }

    // ── §4b Harmony feeds ────────────────────────────────────────────────
    //
    // Both targets are concrete public methods on Photon.Pun.
    // SyncPlayerMovement, verified against the decompile at
    // logs-snapshot/decompiled/SyncPlayerMovement.cs. Per-class registration
    // (Plugin bootstrap) logs "[HARMONY] Failed to patch <name>" if either
    // ever stops resolving, so a dead feed is loud (#83) — grep the startup
    // log before trusting the action display.

    /// <summary>RPCAO_DoBlock is sent ONLY for BlockTriggerType.Default —
    /// the owner's real block key press (SendBlock, decompile :80-104). Card
    /// auto-blocks travel RPCA_DoBlock with their trigger type and never
    /// reach this method, so this postfix is a true press feed.</summary>
    [HarmonyPatch(typeof(Photon.Pun.SyncPlayerMovement), "RPCAO_DoBlock")]
    internal static class Broadcast_BlockPress_Patch
    {
        static void Postfix(Photon.Pun.SyncPlayerMovement __instance)
        {
            try { BroadcastHud.NoteBlockPress(__instance); } catch { }
        }
    }

    /// <summary>Shoot fires once per owner-side gun attack, whatever caused
    /// it (decompile :118-126) — labeled an ACTIVATION on the HUD.</summary>
    [HarmonyPatch(typeof(Photon.Pun.SyncPlayerMovement), "Shoot")]
    internal static class Broadcast_ShotActivation_Patch
    {
        static void Postfix(Photon.Pun.SyncPlayerMovement __instance)
        {
            try { BroadcastHud.NoteShot(__instance); } catch { }
        }
    }
}
