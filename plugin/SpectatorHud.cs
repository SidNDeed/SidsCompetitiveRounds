using System;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 13 (spectator mode), PHASE 3 — the spectator's own screen.
    ///
    /// IMGUI, drawn from near the top of CompetitiveUI.DrawUI (#255: state
    /// this overlay owns must not be released only from deep in the draw
    /// chain — being early also means the blackout paints before, and is
    /// painted over by, nothing that matters).
    ///
    /// Three responsibilities:
    ///   1. BLACKOUT until activation — the §5.3 contract is "admit the
    ///      actor, render nothing until a clean boundary". The blackout IS
    ///      the failure containment: every sync failure degrades to this.
    ///   2. A minimal live HUD while Active (score, names, leave hint).
    ///   3. The Esc leave menu. Vanilla's EscapeMenuHandler is suppressed
    ///      for the whole session (SpectatorPatches), so Esc is ours; the
    ///      menu's open state joins ClickHandler.ModalBlockInput through
    ///      CompetitiveUI's single-writer assignment (#200).
    /// </summary>
    internal static class SpectatorHud
    {
        /// <summary>True while the leave-confirm menu is open. OR'd into
        /// ClickHandler.ModalBlockInput by CompetitiveUI.DrawUI — never
        /// assigned to the static here (#200: one writer).</summary>
        internal static bool MenuOpen { get; private set; }

        private static Texture2D _black;
        private static GUIStyle _title, _sub, _score;
        private static readonly StringBuilder _sb = new StringBuilder(128);
        private static string _cachedNamesLine = "";
        private static float _namesCachedAt = -999f;

        internal static void Draw()
        {
            if (!SpectatorSession.IsLocalSpectator)
            {
                MenuOpen = false;
                return;
            }
            try
            {
                EnsureStyles();
                var e = Event.current;

                // Esc: toggle the leave menu. KeyDown only, consumed so no
                // other IMGUI consumer sees it.
                if (e != null && e.type == EventType.KeyDown && e.keyCode == KeyCode.Escape)
                {
                    MenuOpen = !MenuOpen;
                    e.Use();
                }

                var stage = SpectatorSync.CurrentStage;
                bool active = stage == SpectatorSync.Stage.Active;

                if (!active)
                    DrawBlackout(stage);
                else
                    DrawLiveBar();

                if (MenuOpen)
                    DrawLeaveMenu();
            }
            catch { }
        }

        private static void DrawBlackout(SpectatorSync.Stage stage)
        {
            int w = Screen.width, h = Screen.height;
            // IMGUI paints OVER the uGUI overlay canvas, so a fullscreen
            // blackout would hide (but not disable!) an open F5 menu — an
            // invisible click-trap. With the menu open, drop to the slim bar
            // instead; the menu's own panels cover most of the arena anyway.
            if (NativeUI.IsOpen)
            {
                DrawLiveBar();
                return;
            }
            GUI.color = Color.white;
            GUI.DrawTexture(new Rect(0, 0, w, h), BlackTex());

            string headline = I18n.Tr("SPECTATOR");
            string status;
            if (!Photon.Pun.PhotonNetwork.InRoom)
                status = I18n.Tr("Connecting to the game...");
            else
                status = I18n.Tr("Synchronizing - viewing begins next battle");

            GUI.Label(new Rect(0, h * 0.38f, w, 40), headline, _title);
            GUI.Label(new Rect(0, h * 0.38f + 44, w, 30), status, _sub);

            string names = NamesLine();
            if (names.Length > 0)
                GUI.Label(new Rect(0, h * 0.38f + 78, w, 30), names, _sub);
            if (SpectatorViewState.HasScore)
                GUI.Label(new Rect(0, h * 0.38f + 108, w, 30), SpectatorViewState.ScoreLine(), _score);

            GUI.Label(new Rect(0, h - 60, w, 24), I18n.Tr("Press Esc to leave"), _sub);
        }

        private static void DrawLiveBar()
        {
            int w = Screen.width;
            // Slim top-center bar: SPECTATING | names | series | game score.
            // Cached strings only on Repaint-heavy path (#162): names line
            // refreshes at 2s, series line at 5s.
            string names = NamesLine();
            _sb.Length = 0;
            _sb.Append(I18n.Tr("SPECTATING"));
            if (names.Length > 0) _sb.Append("  |  ").Append(names);
            string series = SeriesLine();
            if (series.Length > 0) _sb.Append("  |  ").Append(series);
            if (SpectatorViewState.HasScore) _sb.Append("  |  ").Append(SpectatorViewState.ScoreLine());
            string line = _sb.ToString();

            var rect = new Rect(0, 6, w, 26);
            GUI.color = new Color(0f, 0f, 0f, 0.55f);
            // Wider backdrop: titles + ratings joined the line (playtest #2b).
            GUI.DrawTexture(new Rect(w * 0.5f - 480, 4, 960, 28), BlackTex());
            GUI.color = Color.white;
            GUI.Label(rect, line, _sub);
        }

        private static void DrawLeaveMenu()
        {
            int w = Screen.width, h = Screen.height;
            float bw = 380f, bh = 150f;
            var box = new Rect(w * 0.5f - bw / 2, h * 0.5f - bh / 2, bw, bh);
            GUI.color = new Color(0f, 0f, 0f, 0.92f);
            GUI.DrawTexture(box, BlackTex());
            GUI.color = Color.white;
            GUI.Label(new Rect(box.x, box.y + 18, bw, 30), I18n.Tr("Stop spectating?"), _title);

            var yes = new Rect(box.x + 40, box.y + 80, 130, 40);
            var no = new Rect(box.x + bw - 170, box.y + 80, 130, 40);
            if (GUI.Button(yes, I18n.Tr("Leave")))
            {
                MenuOpen = false;
                SpectatorSync.LeaveToMenu("user leave");
            }
            if (GUI.Button(no, I18n.Tr("Keep watching")))
            {
                MenuOpen = false;
            }
        }

        // Series tally from the live-series feeds (playtest #169d), matched
        // by fighter steam ids. 5s cache; the feeds refresh on the
        // spectator's own maintenance loop.
        private static string _cachedSeriesLine = "";
        private static float _seriesCachedAt = -999f;

        private static string SeriesLine()
        {
            if (Time.unscaledTime - _seriesCachedAt < 5f) return _cachedSeriesLine;
            _seriesCachedAt = Time.unscaledTime;
            _cachedSeriesLine = "";
            try
            {
                var sids = SpectatorSync.FighterSteamIds;
                if (sids == null || sids.Length < 2) return "";
                if (SpectatorSync.WatchedMode == "1v1")
                {
                    var list = ApiClient.CachedActiveSeries;
                    if (list != null)
                    {
                        foreach (var s in list)
                        {
                            if (s == null) continue;
                            bool a = false, b = false;
                            foreach (var sid in sids)
                            {
                                if (sid == s.p1_steam_id) a = true;
                                else if (sid == s.p2_steam_id) b = true;
                            }
                            if (a && b)
                            {
                                // Render in FighterNames order (p1 may be
                                // either fighter): flip when our first
                                // fighter is the feed's p2.
                                bool flipped = sids.Length > 0 && sids[0] == s.p2_steam_id;
                                int w1 = flipped ? s.p2_wins : s.p1_wins;
                                int w2 = flipped ? s.p1_wins : s.p2_wins;
                                _cachedSeriesLine = I18n.TrF("Series {0}-{1}", w1, w2);
                                break;
                            }
                        }
                    }
                }
                else if (SpectatorSync.WatchedMode == "2v2")
                {
                    var list = ApiClient.CachedActiveTeamSeries;
                    if (list != null)
                    {
                        foreach (var s in list)
                        {
                            if (s == null) continue;
                            int hits = 0;
                            foreach (var sid in sids)
                                if (sid == s.t1a_steam || sid == s.t1b_steam
                                    || sid == s.t2a_steam || sid == s.t2b_steam) hits++;
                            if (hits >= 3)
                            {
                                _cachedSeriesLine = I18n.TrF("Series {0}-{1}", s.t1_wins, s.t2_wins);
                                break;
                            }
                        }
                    }
                }
            }
            catch { _cachedSeriesLine = ""; }
            return _cachedSeriesLine;
        }

        // Playtest #2b: fighter NickNames arrive fully nametag-styled.
        // IMGUI renders <b>/<i>/<color>/<size> but NOT <u> (shown literally),
        // and <size> made styled names huge in a fixed-height bar. Keep only
        // the basic styling; everything else — size, u, voffset, cspace,
        // sprite, whatever future styles add — is stripped.
        private static readonly System.Text.RegularExpressions.Regex _tagStrip =
            new System.Text.RegularExpressions.Regex(
                @"<(?!/?(?:b|i)>)(?!/?color\b)[^>]*>",
                System.Text.RegularExpressions.RegexOptions.Compiled);

        private static readonly System.Text.RegularExpressions.Regex _allTagStrip =
            new System.Text.RegularExpressions.Regex("<[^>]*>",
                System.Text.RegularExpressions.RegexOptions.Compiled);

        private static string SanitizeStyled(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            try
            {
                var kept = _tagStrip.Replace(s, "");
                // Codex r5 find 7: an UNBALANCED surviving tag (a crafted
                // `<color=#00000000>` with no closer) would bleed into every
                // element after it in the same label. Unbalanced -> plain.
                int opens = 0, closes = 0, bOpens = 0, bCloses = 0, iOpens = 0, iCloses = 0;
                foreach (System.Text.RegularExpressions.Match m in _allTagStrip.Matches(kept))
                {
                    string t = m.Value;
                    if (t.StartsWith("<color", StringComparison.OrdinalIgnoreCase)) opens++;
                    else if (t.StartsWith("</color", StringComparison.OrdinalIgnoreCase)) closes++;
                    else if (t == "<b>") bOpens++;
                    else if (t == "</b>") bCloses++;
                    else if (t == "<i>") iOpens++;
                    else if (t == "</i>") iCloses++;
                }
                if (opens != closes || bOpens != bCloses || iOpens != iCloses)
                    return _allTagStrip.Replace(kept, "");
                return kept;
            }
            catch { return _allTagStrip.Replace(s, ""); }
        }

        /// <summary>Title + elo decoration for a fighter, matched through the
        /// grant-time games-list metadata (roster-aligned arrays).</summary>
        private static string DecorFor(int fighterIndex)
        {
            try
            {
                var sids = SpectatorSync.FighterSteamIds;
                var roster = SpectatorSession.WatchedRoster;
                if (sids == null || fighterIndex >= sids.Length || roster == null) return "";
                int m = -1;
                for (int r = 0; r < roster.Length; r++)
                    if (roster[r] == sids[fighterIndex]) { m = r; break; }
                if (m < 0) return "";
                var titles = SpectatorSession.WatchedTitles;
                var ratings = SpectatorSession.WatchedRatings;
                string title = titles != null && m < titles.Length ? titles[m] : "";
                string rating = ratings != null && m < ratings.Length ? ratings[m] : "";
                _decorSb.Length = 0;
                if (!string.IsNullOrEmpty(title))
                    _decorSb.Append(" <color=#BBAA66>").Append(SanitizeStyled(title)).Append("</color>");
                if (!string.IsNullOrEmpty(rating))
                    _decorSb.Append(" <color=#999999>(").Append(rating).Append(")</color>");
                return _decorSb.ToString();
            }
            catch { return ""; }
        }
        private static readonly StringBuilder _decorSb = new StringBuilder(64);

        private static void AppendFighter(int i)
        {
            var names = SpectatorSync.FighterNames;
            _sb.Append(SanitizeStyled(names[i])).Append(DecorFor(i));
        }

        private static string NamesLine()
        {
            // 2s cache — the underlying arrays only change on snapshots.
            if (Time.unscaledTime - _namesCachedAt < 2f) return _cachedNamesLine;
            _namesCachedAt = Time.unscaledTime;
            try
            {
                var names = SpectatorSync.FighterNames;
                var teams = SpectatorSync.FighterTeams;
                if (names == null || names.Length == 0) { _cachedNamesLine = ""; return ""; }
                _sb.Length = 0;
                if (teams != null && teams.Length == names.Length && SpectatorSync.WatchedMode != "ffa")
                {
                    // Group by team: "A + B vs C + D".
                    bool first0 = true, any1 = false;
                    for (int i = 0; i < names.Length; i++)
                    {
                        if (teams[i] == 0)
                        {
                            if (!first0) _sb.Append(" + ");
                            AppendFighter(i); first0 = false;
                        }
                        else any1 = true;
                    }
                    if (any1)
                    {
                        _sb.Append(" vs ");
                        bool first1 = true;
                        for (int i = 0; i < names.Length; i++)
                        {
                            if (teams[i] != 0 && teams[i] >= 0)
                            {
                                if (!first1) _sb.Append(" + ");
                                AppendFighter(i); first1 = false;
                            }
                        }
                    }
                }
                else
                {
                    for (int i = 0; i < names.Length; i++)
                    {
                        if (i > 0) _sb.Append(", ");
                        AppendFighter(i);
                    }
                }
                _cachedNamesLine = _sb.ToString();
            }
            catch { _cachedNamesLine = ""; }
            return _cachedNamesLine;
        }

        private static Texture2D BlackTex()
        {
            if (_black == null)
            {
                _black = new Texture2D(1, 1, TextureFormat.RGBA32, false);
                _black.SetPixel(0, 0, Color.black);
                _black.Apply();
                _black.hideFlags = HideFlags.HideAndDontSave;
            }
            return _black;
        }

        private static void EnsureStyles()
        {
            if (_title != null) return;
            _title = new GUIStyle(GUI.skin.label)
            {
                alignment = TextAnchor.MiddleCenter,
                fontSize = 26,
                fontStyle = FontStyle.Bold,
                clipping = TextClipping.Overflow,   // #143: ROUNDS' IMGUI skin clips tall glyphs
            };
            _title.normal.textColor = Color.white;
            _sub = new GUIStyle(GUI.skin.label)
            {
                alignment = TextAnchor.MiddleCenter,
                fontSize = 15,
                fontStyle = FontStyle.Bold,
                clipping = TextClipping.Overflow,
            };
            _sub.normal.textColor = new Color(0.85f, 0.85f, 0.85f);
            _score = new GUIStyle(_sub) { fontSize = 20 };
            _score.normal.textColor = Color.white;
        }
    }
}
