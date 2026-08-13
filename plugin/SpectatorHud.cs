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

                // Esc: toggle the leave menu — but YIELD to higher-priority
                // consumers (bug 191 + Aug 10 review find 13): an open chat
                // box closes on Esc later in this same DrawUI pass, and the
                // F5 menu already consumed this frame's Esc in Update
                // (NativeUI.IsOpen is false by OnGUI time — the frame stamp
                // is the only reliable signal).
                if (e != null && e.type == EventType.KeyDown && e.keyCode == KeyCode.Escape)
                {
                    bool yield = false;
                    try
                    {
                        yield = CompetitiveUI.AnyChatTyping
                                || NativeUI.IsOpen
                                || NativeUI.EscConsumedFrame == Time.frameCount;
                    }
                    catch { }
                    if (!yield)
                    {
                        MenuOpen = !MenuOpen;
                        e.Use();
                    }
                }

                var stage = SpectatorSync.CurrentStage;

                // Item 2 (seizure-inducing black flashes): the fullscreen
                // cover exists ONLY before the first activation. Every later
                // reconcile keeps the live scene visible — vanilla's own
                // point sequence plays between points, and the top bar grows
                // a "Syncing" note while a reconcile is in flight.
                if (!SpectatorSync.HasEverActivated)
                    DrawBlackout(stage);
                else
                    DrawLiveBar();

                if (MenuOpen)
                    DrawLeaveMenu();
            }
            catch { }
        }

        /// <summary>Fully de-styled name for plain-text surfaces
        /// (notifications, the game-over toast).</summary>
        internal static string PlainName(string styled)
        {
            if (string.IsNullOrEmpty(styled)) return "";
            try { return _allTagStrip.Replace(styled, ""); }
            catch { return styled; }
        }

        // ── item 8: the connect state, made COHERENT ─────────────────────
        //
        // WHAT THE COVER IS ACTUALLY FOR (established before changing it —
        // design §5.3): a spectator that has not yet reached a battle
        // boundary is not looking at a correct rendering of the match. It
        // holds no snapshot, so the score, both decks and every applied card
        // effect are unknown; the map under the bodies may still be the
        // previous one; and the join-replay quarantine is still burying the
        // hundreds of cached objects the room replayed into this client at
        // join (#312). Vanilla never reconstructs mid-round health, deaths,
        // projectiles or effects for a late joiner and neither do we — so
        // what renders pre-activation is a partially-correct scene that would
        // be read as the real state. The cover is also the failure
        // containment: every sync failure path degrades back to it.
        //
        // Sid's report is NOT that the cover is wrong — it is that it reads
        // as arbitrary, because with F5 open the arena is plainly visible
        // behind the menu and the black then looks like it is hiding
        // something that works. That exception cannot simply be removed:
        // IMGUI paints OVER the uGUI overlay canvas, so covering an open menu
        // hides it without disabling it, i.e. an invisible click trap.
        //
        // So the fix is on the legibility axis (#250 — the axis is
        // visible-and-announced, not hide-vs-show). The cover now states that
        // the match is already running and why the picture is held, and ticks
        // a live wait counter so it can never read as hung; and the bar drawn
        // in the F5 case carries the SAME "not live yet" statement. The two
        // states still differ in coverage, but they no longer disagree about
        // what is happening.
        private static void DrawBlackout(SpectatorSync.Stage stage)
        {
            int w = Screen.width, h = Screen.height;
            if (NativeUI.IsOpen)
            {
                DrawLiveBar();
                return;
            }
            GUI.color = Color.white;
            GUI.DrawTexture(new Rect(0, 0, w, h), BlackTex());

            float y = h * 0.34f;
            GUI.Label(new Rect(0, y, w, 40), I18n.Tr("SPECTATOR"), _title);
            y += 46;
            GUI.Label(new Rect(0, y, w, 30), ConnectStatusLine(), _score);
            y += 38;

            // Why the screen is held. Two short lines rather than one long
            // one: this box is full screen width but the text is centred, and
            // a single sentence at 15pt reads as a caption nobody finishes.
            GUI.Label(new Rect(0, y, w, 26), I18n.Tr("The match is already running."), _sub);
            y += 26;
            GUI.Label(new Rect(0, y, w, 26),
                      I18n.Tr("Your view starts at the next round - that is the first moment the score, cards and health can be shown correctly."),
                      _sub);
            y += 36;

            string names = NamesLine();
            if (names.Length > 0) { GUI.Label(new Rect(0, y, w, 30), names, _sub); y += 32; }
            if (SpectatorViewState.HasScore)
                GUI.Label(new Rect(0, y, w, 30), SpectatorViewState.ScoreLine(), _score);

            GUI.Label(new Rect(0, h - 60, w, 24), I18n.Tr("Press Esc to leave"), _sub);
        }

        // Composed at 4 Hz: the dot cycle and the wait counter are the only
        // moving parts and this runs on every IMGUI event (#162).
        private static string _cachedConnectLine = "";
        private static float _connectCachedAt = -999f;

        /// <summary>The pre-activation state in one line, plus a ticking wait
        /// counter — a point transition is what triggers activation, so
        /// joining just after a point means a full round of waiting and the
        /// screen has to prove it is still working.
        ///
        /// Both status literals are carried forward BYTE-FOR-BYTE from before
        /// this pass (#289: the key is derived from the English source, so
        /// editing a string retires its translations — these two already have
        /// es/ru/uk/sv entries and their meaning has not changed). The motion
        /// is the counter, not an animated ellipsis, precisely so neither
        /// string had to be reworded.</summary>
        private static string ConnectStatusLine()
        {
            if (Time.unscaledTime - _connectCachedAt < 0.25f) return _cachedConnectLine;
            _connectCachedAt = Time.unscaledTime;
            try
            {
                bool inRoom = false;
                try { inRoom = Photon.Pun.PhotonNetwork.InRoom; } catch { }
                string s = inRoom
                    ? I18n.Tr("Synchronizing - viewing begins next battle")
                    : I18n.Tr("Connecting to the game...");
                // Its OWN builder, not the shared _decorSb: that one is
                // borrowed by DecorFor/TeamScoreInline from inside the same
                // draw pass, and a shared builder is exactly how a future
                // caller order silently corrupts one of the two lines.
                _connectSb.Length = 0;
                _connectSb.Append(s);
                int secs = (int)(Time.unscaledTime - SpectatorSession.SessionStartedAt);
                // Only past the point where a wait is worth counting — a
                // counter that appears instantly reads as a stopwatch on a
                // failure rather than as reassurance.
                if (SpectatorSession.SessionStartedAt > 0f && secs >= 5)
                    _connectSb.Append("   <color=#888888>")
                              .Append(I18n.TrF("waiting {0}s", secs))
                              .Append("</color>");
                _cachedConnectLine = _connectSb.ToString();
            }
            catch { _cachedConnectLine = ""; }
            return _cachedConnectLine;
        }

        // ROUNDS team hues for the score line (ASCII hex only, #47).
        private const string ORANGE_HEX = "#FF8124";
        private const string BLUE_HEX = "#33B5FF";

        private static string _cachedBarLine = "";
        private static float _barCachedAt = -999f;
        private static float _cachedBarWidth = 960f;

        private static void DrawLiveBar()
        {
            int w = Screen.width;
            // Slim top-center bar (0.5s composite cache, #162):
            //   SPECTATING | <orange>A</> 2.5 - 3 <blue>B</> | Series 1-0 | Session 2-1 [| Syncing...]
            // The colored score segment REPLACES the plain names segment when
            // a score exists (Aug 10 review find 11 — never both).
            if (Time.unscaledTime - _barCachedAt > 0.5f)
            {
                _barCachedAt = Time.unscaledTime;
                // Segments FIRST — NamesLine() clears the shared _sb builder
                // internally, so it must never run mid-composition.
                bool live = SpectatorSync.HasEverActivated;
                string score = TeamScoreInline();
                string names = score.Length > 0 ? "" : NamesLine();
                string series = SeriesLine();
                string session = SessionLine();
                _sb.Length = 0;
                _sb.Append(live ? I18n.Tr("SPECTATING") : I18n.Tr("SPECTATOR"));
                if (score.Length > 0) _sb.Append("  |  ").Append(score);
                else if (names.Length > 0) _sb.Append("  |  ").Append(names);
                if (series.Length > 0) _sb.Append("  |  ").Append(series);
                if (session.Length > 0) _sb.Append("  |  ").Append(session);
                if (!live)
                {
                    // Item 8: this is the bar the F5 case shows INSTEAD of the
                    // cover, with the live arena visible behind the menu. It
                    // has to say the same thing the cover says, or the two
                    // states contradict each other and the cover reads as an
                    // arbitrary blindfold. "Syncing..." did not say it.
                    _sb.Append("  |  <color=#FFD94D>")
                       .Append(I18n.Tr("NOT LIVE YET - your view starts at the next round"))
                       .Append("</color>");
                }
                else if (SpectatorSync.CurrentStage != SpectatorSync.Stage.Active)
                {
                    _sb.Append("  |  ").Append(I18n.Tr("Syncing..."));
                }
                _cachedBarLine = _sb.ToString();
                // Measure, never guess (#237): the line already carries names,
                // titles and ratings, and the pre-activation note is longer
                // still — a fixed 960 backdrop leaves text hanging off both
                // ends. Recomputed only with the line, so CalcSize never runs
                // per IMGUI event (#162).
                try
                {
                    float need = _sub.CalcSize(new GUIContent(_cachedBarLine)).x + 48f;
                    _cachedBarWidth = Mathf.Min(w, Mathf.Max(320f, need));
                }
                catch { _cachedBarWidth = Mathf.Min(w, 960f); }
            }

            var rect = new Rect(0, 6, w, 26);
            GUI.color = new Color(0f, 0f, 0f, 0.55f);
            GUI.DrawTexture(new Rect(w * 0.5f - _cachedBarWidth * 0.5f, 4, _cachedBarWidth, 28), BlackTex());
            GUI.color = Color.white;
            GUI.Label(rect, _cachedBarLine, _sub);
        }

        /// <summary>Item 3: the game score with sides attached and half
        /// points — "NameA 2.5 - 3 NameB", each side in its ROUNDS team
        /// color, so who leads is one glance. Empty when no score yet or in
        /// FFA (which has its own score HUD).</summary>
        private static string TeamScoreInline()
        {
            try
            {
                if (!SpectatorViewState.HasScore) return "";
                if (SpectatorSync.WatchedMode == "ffa") return "";
                var names = SpectatorSync.FighterNames;
                var teams = SpectatorSync.FighterTeams;
                if (names == null || teams == null || names.Length != teams.Length || names.Length == 0)
                    return "";
                string t0 = TeamNamesInline(0), t1 = TeamNamesInline(1);
                if (t0.Length == 0 || t1.Length == 0) return "";
                // Aug 11 playtest item 3: follow the equipped team-colour
                // identity (Midnight team must not read as "blue") — the
                // resolver works on a spectator seat because it consumes the
                // replicated cr_tcol room prop / player props; classic
                // orange/blue is the unresolved fallback. The bar's 0.5s
                // composite cache is fine — the resolver has its own TTL.
                string hex0 = TeamColorIdentity.DisplayHexForTeam(0, ORANGE_HEX);
                string hex1 = TeamColorIdentity.DisplayHexForTeam(1, BLUE_HEX);
                _decorSb.Length = 0;
                _decorSb.Append("<color=").Append(hex0).Append(">").Append(t0).Append("  ")
                        .Append(SpectatorViewState.TeamScoreText(0)).Append("</color>")
                        .Append("  -  ")
                        .Append("<color=").Append(hex1).Append(">")
                        .Append(SpectatorViewState.TeamScoreText(1)).Append("  ").Append(t1).Append("</color>");
                return _decorSb.ToString();
            }
            catch { return ""; }
        }

        private static string TeamNamesInline(int team)
        {
            var names = SpectatorSync.FighterNames;
            var teams = SpectatorSync.FighterTeams;
            var sb = new StringBuilder(48);
            for (int i = 0; i < names.Length; i++)
            {
                if (teams[i] != team) continue;
                if (sb.Length > 0) sb.Append(" + ");
                // Plain names inside the colored segment: nested nametag
                // color styling would fight the team color mid-string.
                sb.Append(PlainName(names[i])).Append(DecorPlain(i));
            }
            return sb.ToString();
        }

        /// <summary>Rating-only decor (no color tags) for the team-colored
        /// score segment.</summary>
        private static string DecorPlain(int fighterIndex)
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
                var ratings = SpectatorSession.WatchedRatings;
                string rating = ratings != null && m < ratings.Length ? ratings[m] : "";
                return string.IsNullOrEmpty(rating) ? "" : " (" + rating + ")";
            }
            catch { return ""; }
        }

        /// <summary>Item 3: series won per side THIS SITTING (snapshot slots
        /// 16/17, fighter-array order mapped to team order). Hidden unless a
        /// well-formed 1v1 tally arrived.</summary>
        private static string SessionLine()
        {
            try
            {
                int s0 = SpectatorViewState.SessionSeries0;
                int s1 = SpectatorViewState.SessionSeries1;
                if (s0 < 0 || s1 < 0) return "";
                var teams = SpectatorSync.FighterTeams;
                if (teams == null || teams.Length != 2) return "";
                // Fighter-array order -> team order (team 0 renders left).
                int left = teams[0] == 0 ? s0 : s1;
                int right = teams[0] == 0 ? s1 : s0;
                return I18n.TrF("Session {0}-{1}", left, right);
            }
            catch { return ""; }
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

        /// <summary>Aug 12 item 9b: THE one place a spectator surface renders a
        /// title, in the same shape every other title surface in the mod uses —
        /// a bold bracketed span in the title's OWN colour (NativeUI's Home,
        /// leaderboard, chat and FFA scoreboard sites all build exactly this).
        /// It cannot literally call one of those: they are private to NativeUI,
        /// each takes a different entry type, and they emit for TMP while this
        /// bar is IMGUI (where SanitizeStyled keeps only b/i/color). Every
        /// spectator title goes through here so the shape can never drift
        /// again.
        ///
        /// The colour is validated, not trusted: it arrives as free text in a
        /// pipe-joined server field, and an unvalidated value inside a
        /// `&lt;color=...&gt;` tag is a rich-text injection into a label that
        /// also renders player names.</summary>
        private static string TitleSpan(string title, string hex)
        {
            if (string.IsNullOrEmpty(title)) return "";
            string safe = SanitizeStyled(title);
            if (safe.Length == 0) return "";
            return " <b><color=" + SafeHex(hex) + ">[" + safe + "]</color></b>";
        }

        /// <summary>#RGB / #RRGGBB / #RRGGBBAA only; anything else falls back.
        /// The fallback matches the mod's other title surfaces that have no
        /// colour to work with (chat, recent-series rows).</summary>
        private const string TITLE_FALLBACK_HEX = "#CCCCCC";
        private static string SafeHex(string hex)
        {
            if (string.IsNullOrEmpty(hex)) return TITLE_FALLBACK_HEX;
            if (hex[0] != '#') return TITLE_FALLBACK_HEX;
            if (hex.Length != 4 && hex.Length != 7 && hex.Length != 9) return TITLE_FALLBACK_HEX;
            for (int i = 1; i < hex.Length; i++)
            {
                char c = hex[i];
                bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
                if (!ok) return TITLE_FALLBACK_HEX;
            }
            return hex;
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
                var colors = SpectatorSession.WatchedTitleColors;
                var ratings = SpectatorSession.WatchedRatings;
                string title = titles != null && m < titles.Length ? titles[m] : "";
                string tcol = colors != null && m < colors.Length ? colors[m] : "";
                string rating = ratings != null && m < ratings.Length ? ratings[m] : "";
                _decorSb.Length = 0;
                _decorSb.Append(TitleSpan(title, tcol));
                if (!string.IsNullOrEmpty(rating))
                    _decorSb.Append(" <color=#999999>(").Append(rating).Append(")</color>");
                return _decorSb.ToString();
            }
            catch { return ""; }
        }
        private static readonly StringBuilder _decorSb = new StringBuilder(64);
        private static readonly StringBuilder _connectSb = new StringBuilder(96);

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
