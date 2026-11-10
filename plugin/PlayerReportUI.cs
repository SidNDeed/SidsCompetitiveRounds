using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Ask 14: the player report form (the flag icon of the utility
    /// strip) and the admins' viewer (Admin > Queues > Player Reports...).
    /// IMGUI, on the bug form's pattern. This file draws and carries; what a
    /// press may send and what each answer closes are PlayerReportRules',
    /// which the client-rules harness executes.
    ///
    /// Three things hold in every draw: a name, a detail or a log line is
    /// another person's text and is drawn through PlayerReportRules.Plain or a
    /// style without rich text; every word the mod writes goes through
    /// I18n.Tr; and nothing is sent except by a press that
    /// PlayerReportRules.Check allowed.</summary>
    internal static class PlayerReportUI
    {
        // ---- the form ------------------------------------------------------------

        private static bool _open;
        /// <summary>What answers closed, for this run of the game (never cleared).</summary>
        private static readonly PlayerReportRules.FormState _state = new PlayerReportRules.FormState();
        private static PlayerReportRules.ListState _list = PlayerReportRules.ListState.Loading;
        private static List<PlayerReportRules.Game> _games = new List<PlayerReportRules.Game>();
        private static int _opening;                 // counts the form's openings
        private static PlayerReportRules.Game _game;
        private static PlayerReportRules.Other _other;
        private static string _reason = "";
        private static string _details = "";
        private static bool _withLog = true;         // ticked at first, as the bug form's box is
        private static bool _sending;
        private static string _status = "";          // what the last answer said, translated
        private static bool _statusGood;
        private static Vector2 _detailsScroll;
        private static GUIStyle _titleStyle, _labelStyle, _noteStyle, _plainStyle, _areaStyle, _fieldStyle, _buttonStyle,
                                _pickedStyle, _selectStyle, _tickStyle, _rowStyle, _rowDimStyle, _logStyle;

        internal static bool AnyOpen { get { return _open || _adminOpen; } }

        private static string SessionKeyNow()
        {
            return MarkOf(SteamAuth.SessionToken);
        }

        /// <summary>The mark of a token ("" = none), the one place the form
        /// makes it: from the token held now (SessionKeyNow), and from the one
        /// a request carried as its transport stamped it, which a refresh while
        /// the body was built or the read was held makes newer (ask 14 R1 H1).</summary>
        private static string MarkOf(string token)
        {
            return PlayerReportRules.SessionKey(token);
        }

        /// <summary>Opens the form and asks once for the caller's games, when
        /// the rules allow the question. A later answer to an earlier opening
        /// still closes what it closes, and is otherwise dropped.</summary>
        internal static void Open()
        {
            _open = true;
            if (!_sending)
            {
                _game = null; _other = null; _reason = ""; _details = ""; _status = "";
            }
            _games = new List<PlayerReportRules.Game>();
            string key = SessionKeyNow();
            _list = PlayerReportRules.BeforeList(_state, key);
            int mine = ++_opening;
            if (_list != PlayerReportRules.ListState.Loading) return;
            ApiClient.FetchReportableGames((status, code, games, remaining, carried) =>
            {
                // A refusal closes the sign-in the GET carried; key stands in
                // only when nothing went out, and such an answer closes none.
                PlayerReportRules.ListState answered = PlayerReportRules.ApplyList(_state, status, code,
                                                                                   carried == null ? key : MarkOf(carried));
                if (status == 200 && remaining >= 0) _state.Remaining = remaining;
                if (mine != _opening) return;
                _list = answered;
                if (answered == PlayerReportRules.ListState.Loaded && games != null) _games = games;
            });
        }

        private static void EnsureStyles()
        {
            if (_titleStyle != null) return;
            _titleStyle = new GUIStyle(GUI.skin.label)
            { fontSize = 19, fontStyle = FontStyle.Bold, richText = true, alignment = TextAnchor.MiddleLeft };
            _labelStyle = new GUIStyle(GUI.skin.label) { fontSize = 13, richText = true };
            _plainStyle = new GUIStyle(GUI.skin.label) { fontSize = 13, richText = false, wordWrap = true, alignment = TextAnchor.UpperLeft };
            _areaStyle = new GUIStyle(GUI.skin.textArea) { fontSize = 13, wordWrap = true, richText = false };
            _buttonStyle = new GUIStyle(GUI.skin.button) { fontSize = 13 };
            _selectStyle = new GUIStyle(GUI.skin.button) { fontSize = 13, richText = false, alignment = TextAnchor.MiddleLeft };
            _noteStyle = new GUIStyle(_labelStyle) { wordWrap = true, alignment = TextAnchor.UpperLeft };
            _fieldStyle = new GUIStyle(GUI.skin.textField) { fontSize = 13, richText = false };
            _tickStyle = new GUIStyle(GUI.skin.label)
            { fontSize = 16, fontStyle = FontStyle.Bold, richText = false, alignment = TextAnchor.MiddleCenter };
            _rowStyle = new GUIStyle(GUI.skin.label) { fontSize = 13, richText = false, wordWrap = false };
            _rowDimStyle = new GUIStyle(_rowStyle) { fontSize = 12 };
            _rowDimStyle.normal.textColor = new Color(0.7f, 0.72f, 0.76f);
            _logStyle = new GUIStyle(GUI.skin.label)
            { fontSize = 12, richText = false, wordWrap = false, alignment = TextAnchor.UpperLeft };
            _pickedStyle = new GUIStyle(GUI.skin.button) { fontSize = 13, fontStyle = FontStyle.Bold };
            _pickedStyle.normal.background = Texture2D.whiteTexture; _pickedStyle.normal.textColor = Color.black;
            _pickedStyle.hover.background = Texture2D.whiteTexture; _pickedStyle.hover.textColor = Color.black;
            _pickedStyle.active.background = Texture2D.whiteTexture; _pickedStyle.active.textColor = Color.black;
        }

        /// <summary>A game's end in the player's own time and date order.</summary>
        private static string When(string stamp)
        {
            DateTime utc;
            if (!PlayerReportRules.TryParseUtc(stamp, out utc)) return "";
            DateTime local = utc.ToLocalTime();
            return DateFmt.Short(local) + " " + local.ToString("HH:mm", CultureInfo.InvariantCulture);
        }

        // Each selector is a wide button showing the current choice; a press
        // opens the mod's list picker. The picker draws after this form, so it
        // is on top, and Draw leaves Escape and every control to it meanwhile.

        private static void PickGame()
        {
            int n = _games.Count;
            if (n == 0) return;
            var names = new string[n];
            var ids = new string[n];
            for (int i = 0; i < n; i++)
            {
                names[i] = PlayerReportRules.GameLabel(_games[i], When(_games[i].EndedAt));
                ids[i] = PlayerReportRules.GameKey(_games[i]);
            }
            CompetitiveUI.OpenArtistPicker(I18n.Tr("Choose a game"), names, ids, picked =>
            {
                foreach (PlayerReportRules.Game g in _games)
                {
                    if (PlayerReportRules.GameKey(g) != picked) continue;
                    if (!ReferenceEquals(g, _game))
                    {
                        _game = g;
                        _other = g.Others.Length == 1 ? g.Others[0] : null;   // one other player: nothing to choose
                        _status = "";
                    }
                    break;
                }
            }, actionLabel: I18n.Tr("Select"), showClear: false, itemNoun: "",
               selectedId: _game == null ? null : PlayerReportRules.GameKey(_game), showIds: false);
        }

        private static void PickPlayer()
        {
            PlayerReportRules.Game g = _game;
            if (g == null || g.Others.Length == 0) return;
            var names = new string[g.Others.Length];
            var ids = new string[g.Others.Length];
            for (int i = 0; i < g.Others.Length; i++)
            {
                names[i] = PlayerReportRules.OtherLabel(_state, g, g.Others[i]);
                ids[i] = g.Others[i].SteamId;
            }
            CompetitiveUI.OpenArtistPicker(I18n.Tr("Choose a player"), names, ids, picked =>
            {
                if (!ReferenceEquals(g, _game)) return;
                foreach (PlayerReportRules.Other o in g.Others)
                    if (o.SteamId == picked) { _other = o; _status = ""; break; }
            }, actionLabel: I18n.Tr("Select"), showClear: false, itemNoun: "",
               selectedId: _other == null ? null : _other.SteamId, showIds: false);
        }

        private static void PickReason()
        {
            int n = PlayerReportRules.ReasonCodes.Length;
            var names = new string[n];
            for (int i = 0; i < n; i++) names[i] = PlayerReportRules.ReasonText(i);
            CompetitiveUI.OpenArtistPicker(I18n.Tr("Choose a reason"), names, PlayerReportRules.ReasonCodes, picked =>
            {
                if (Array.IndexOf(PlayerReportRules.ReasonCodes, picked) >= 0) { _reason = picked; _status = ""; }
            }, actionLabel: I18n.Tr("Select"), showClear: false, itemNoun: "",
               selectedId: _reason.Length == 0 ? null : _reason, showIds: false);
        }

        private static void Frame(float x, float y, float w, float h, float dim)
        {
            GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, dim), 0, 0);
            GUI.DrawTexture(new Rect(x - 10, y - 10, w + 20, h + 20), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(0.07f, 0.08f, 0.11f, 0.97f), 0, 0);
            GUI.DrawTexture(new Rect(x - 10, y - 10, w + 20, 1), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(1f, 1f, 1f, 0.4f), 0, 0);
        }

        /// <summary>The bug form's hand-drawn tick box: a filled square, its
        /// four edges and an X.</summary>
        private static void TickBox(Rect box, bool on)
        {
            Color fill = on ? new Color(0.25f, 0.7f, 0.3f, 0.95f) : new Color(0.18f, 0.18f, 0.22f, 0.95f);
            GUI.DrawTexture(box, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, fill, 0, 0);
            GUI.DrawTexture(new Rect(box.x, box.y, box.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            GUI.DrawTexture(new Rect(box.x, box.y + box.height - 1, box.width, 1), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            GUI.DrawTexture(new Rect(box.x, box.y, 1, box.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            GUI.DrawTexture(new Rect(box.x + box.width - 1, box.y, 1, box.height), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, Color.white, 0, 0);
            if (on) GUI.Label(box, "X", _tickStyle);
        }

        /// <summary>The form. Called from CompetitiveUI.DrawUI ahead of the
        /// list picker and the log preview, which therefore draw on top.</summary>
        internal static void Draw()
        {
            if (!_open) return;
            if (!NativeUI.IsOpen) { _open = false; return; }
            EnsureStyles();

            // A picker or the log preview is up: it owns Escape and the mouse.
            bool covered = CompetitiveUI.ArtistPromptOpen || CompetitiveUI.LogViewerOpen;
            var ev = Event.current;
            if (!covered && ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            { _open = false; ev.Use(); return; }

            float w = 680, h = 470;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            Frame(x, y, w, h, 0.45f);

            GUI.Label(new Rect(x, y, w, 28), "<color=#FFE580>" + I18n.Tr("Report a Player") + "</color>", _titleStyle);
            GUI.Label(new Rect(x, y + 30, w, 22),
                      "<color=#AAAAAA>" + I18n.Tr("Reports go to the mod team. Pick the game, the player and a reason.") + "</color>",
                      _noteStyle);

            string key = SessionKeyNow();
            bool loaded = _list == PlayerReportRules.ListState.Loaded;
            bool free = !covered && !_sending;
            const float fieldX = 110f;

            GUI.Label(new Rect(x, y + 62, fieldX, 22), "<b>" + I18n.Tr("Game:") + "</b>", _labelStyle);
            GUI.enabled = free && loaded && _games.Count > 0;
            if (GUI.Button(new Rect(x + fieldX, y + 58, w - fieldX, 28),
                           _game == null ? I18n.Tr("Choose a game") : PlayerReportRules.GameLabel(_game, When(_game.EndedAt)),
                           _selectStyle))
                PickGame();

            GUI.enabled = true;
            GUI.Label(new Rect(x, y + 98, fieldX, 22), "<b>" + I18n.Tr("Player:") + "</b>", _labelStyle);
            GUI.enabled = free && loaded && _game != null;
            if (GUI.Button(new Rect(x + fieldX, y + 94, w - fieldX, 28),
                           _other == null ? I18n.Tr("Choose a player") : PlayerReportRules.OtherLabel(_state, _game, _other),
                           _selectStyle))
                PickPlayer();

            GUI.enabled = true;
            GUI.Label(new Rect(x, y + 134, fieldX, 22), "<b>" + I18n.Tr("Reason:") + "</b>", _labelStyle);
            GUI.enabled = free;
            if (GUI.Button(new Rect(x + fieldX, y + 130, w - fieldX, 28),
                           _reason.Length == 0 ? I18n.Tr("Choose a reason") : PlayerReportRules.ReasonTextOf(_reason),
                           _selectStyle))
                PickReason();

            GUI.enabled = true;
            GUI.Label(new Rect(x, y + 170, w, 18),
                      _reason == PlayerReportRules.ReasonNeedsDetails
                          ? I18n.Tr("<b>What happened?</b> <color=#FF9966>(required)</color>")
                          : I18n.Tr("<b>What happened?</b> <color=#888>(optional)</color>"),
                      _labelStyle);
            float areaH = Mathf.Max(120, (_details == null ? 0 : _details.Length) / 4);
            _detailsScroll = GUI.BeginScrollView(new Rect(x, y + 190, w, 120), _detailsScroll, new Rect(0, 0, w - 20, areaH));
            GUI.enabled = free;
            _details = GUI.TextArea(new Rect(0, 0, w - 20, areaH), _details ?? "", PlayerReportRules.DetailsMax, _areaStyle);
            GUI.enabled = true;
            GUI.EndScrollView();

            // The log row: tick box and label on the left (their own hit
            // area), the preview button on the right, as the bug form has it.
            GUI.enabled = free;
            if (GUI.Button(new Rect(x, y + 322, 300, 26), GUIContent.none, GUIStyle.none)) _withLog = !_withLog;
            TickBox(new Rect(x + 2, y + 324, 20, 20), _withLog);
            GUI.Label(new Rect(x + 28, y + 322, 268, 26), I18n.Tr("Attach game logs (recommended)"), _labelStyle);
            GUI.enabled = !covered;
            if (GUI.Button(new Rect(x + 316, y + 322, 140, 24), I18n.Tr("Preview logs"), _buttonStyle))
                CompetitiveUI.OpenLogViewer();
            GUI.enabled = true;

            // One line: the list's state while there is no list, then what the
            // last answer said, then why Send is closed.
            PlayerReportRules.Outcome why;
            PlayerReportRules.Block block = PlayerReportRules.Check(_state, _game, _other, _reason, _details, _withLog,
                                                                    _sending, key, out why);
            string line;
            bool good = false;
            if (!loaded || _games.Count == 0) line = PlayerReportRules.ListText(_list, _state, _games.Count);
            else if (_status.Length > 0) { line = _status; good = _statusGood; }
            else line = PlayerReportRules.BlockText(block, why);
            if (line.Length > 0)
                GUI.Label(new Rect(x, y + 356, w, 40), "<color=" + (good ? "#88FF88" : "#FFCC66") + ">" + line + "</color>", _noteStyle);

            GUI.enabled = !covered;
            if (GUI.Button(new Rect(x, y + h - 44, 120, 30), I18n.Tr("Close"), _buttonStyle))
            { _open = false; GUI.enabled = true; return; }
            GUI.enabled = !covered && loaded && block == PlayerReportRules.Block.None;
            if (GUI.Button(new Rect(x + w - 160, y + h - 44, 160, 30),
                           _sending ? I18n.Tr("Submitting...") : I18n.Tr("Submit Report"), _buttonStyle))
                Send();
            GUI.enabled = true;
        }

        // ---- the send --------------------------------------------------------------
        //
        // The bug form's split (CompetitiveUI.SubmitBugReportNow): nothing
        // proportional to the logs runs on the game thread.
        //   MAIN THREAD, on the press: Check, the fields, CaptureLogBundleInputs
        //   and starting the worker.
        //   WORKER: the capped reads, the scrub, the JSON body and its bytes.
        //   MAIN THREAD, from Plugin's persistent tick (Pump): the one POST.
        // The pump does not depend on the form being open, so a report whose
        // form is closed while it builds is still sent, once.

        /// <summary>What one press chose, kept until its answer arrives.</summary>
        private sealed class Pending
        {
            internal PlayerReportRules.Game Game;
            internal PlayerReportRules.Other Other;
            internal string Reason, Details, Key;
            internal bool WithLog;
        }

        /// <summary>What the worker hands back. Not changed once published.</summary>
        private sealed class Bundle
        {
            internal byte[] Body;
            internal string Probe;
            internal int Scrubbed;
            internal string Diagnostic;
            internal string Failure;
        }

        private static Pending _pending;
        private static readonly LogBundleCore.OffMainJob<Bundle> _job = new LogBundleCore.OffMainJob<Bundle>();

        private static void Send()
        {
            string key = SessionKeyNow();
            PlayerReportRules.Outcome why;
            if (PlayerReportRules.Check(_state, _game, _other, _reason, _details, _withLog, _sending, key, out why)
                != PlayerReportRules.Block.None)
                return;
            if (_job.Busy || _pending != null) return;
            PlayerReportRules.Game game = _game;
            PlayerReportRules.Other other = _other;
            string reason = _reason;
            string details = (_details ?? "").Trim();
            bool withLog = _withLog;
            CompetitiveUI.LogBundleInputs inputs = withLog ? CompetitiveUI.CaptureLogBundleInputs() : null;
            _pending = new Pending { Game = game, Other = other, Reason = reason, Details = details, Key = key, WithLog = withLog };
            _sending = true;
            _status = "";
            bool started = _job.Start("SCR-PlayerReportBundle", () =>
            {
                var r = new Bundle();
                string log = null;
                if (inputs != null)
                {
                    var info = new LogBundleCore.ComposeInfo();
                    log = CompetitiveUI.ComposeLogBundle(inputs, info);
                    r.Scrubbed = info.Scrubbed;
                    r.Diagnostic = info.Diagnostic;
                }
                string body = PlayerReportRules.BuildBody(game.Kind, game.Id, other.SteamId, reason, details, log);
                r.Body = System.Text.Encoding.UTF8.GetBytes(body);
                r.Probe = ApiClient.SensitiveBodyProbe(body);
                return r;
            },
            // The type name only: an exception message from a file read can
            // carry the path that produced it.
            ex => new Bundle { Failure = ex.GetType().Name });
            if (!started) Finish(0, "", false);
        }

        /// <summary>MAIN THREAD, once a frame from Plugin's persistent tick:
        /// hands a finished body to the one request of its press.</summary>
        internal static void Pump()
        {
            if (_countAsked && !NativeUI.IsOpen) _countAsked = false;     // the next opening of the menu may ask again
            PumpAdminLog();
            int workerId;
            Bundle r = _job.TakeFinished(out workerId);
            if (r == null)
            {
                if (workerId != 0) Finish(0, "", false);     // the worker ended without a body
                return;
            }
            if (r.Failure != null || r.Body == null)
            {
                Plugin.Log.LogWarning("[PLAYER-REPORT] the report could not be built (" + (r.Failure ?? "no body") + ")");
                Finish(0, "", false);
                return;
            }
            if (!string.IsNullOrEmpty(r.Diagnostic))
            {
                if (r.Scrubbed < 0) Plugin.Log.LogError(r.Diagnostic); else Plugin.Log.LogInfo(r.Diagnostic);
            }
            if (r.Body.Length > PlayerReportRules.BodyMax)
            {
                // The server reads no more than this: refused here, by the
                // same row of the table, instead of sent to be refused.
                Finish(413, "body_too_large", false);
                return;
            }
            ApiClient.SubmitPlayerReportBody(r.Body, r.Probe, Finish);
        }

        /// <summary>The answer to a press (or the reason there was none): into
        /// the state by the rules' table, then onto the status line. A 401
        /// closes the sign-in the request carried (<paramref name="carried"/>,
        /// stamped at dispatch, after the worker built the body); the press's
        /// mark stands in only when nothing went out, and such an answer closes
        /// no sign-in.</summary>
        private static void Finish(int status, string code, bool logStored, string carried = null)
        {
            Pending p = _pending;
            _pending = null;
            _sending = false;
            if (p == null) return;
            PlayerReportRules.Outcome said = PlayerReportRules.Apply(_state, status, code, logStored, p.Game, p.Other,
                                                                      p.Reason, p.Details, p.WithLog,
                                                                      carried == null ? p.Key : MarkOf(carried));
            _status = PlayerReportRules.AnswerText(said);
            _statusGood = said == PlayerReportRules.Outcome.Sent || said == PlayerReportRules.Outcome.SentWithoutLog;
            if (!_statusGood) return;
            if (ReferenceEquals(_other, p.Other)) { _other = null; _details = ""; }
            CompetitiveUI.ShowNotification(_status, new Color(0.5f, 1f, 0.5f), 5f);
        }

        // ---- the admins' viewer ------------------------------------------------------
        //
        // A list on the left, the chosen report on the right. Closing a report
        // records a verdict and an optional note and does nothing else: no
        // sanction is applied and nobody is told. Each of the viewer's three
        // requests is signed with its own action word (ApiClient), and after
        // an answer that does not depend on the report asked for (401, 403,
        // 426, 429, 503) the viewer sends nothing more for this run of the game.

        private sealed class LogLines
        {
            internal string ReportId;
            internal string[] Lines;
        }

        private const int LogTailChars = 400000;     // what the viewer shows of a stored log
        private const int LogLineChars = 1000;
        private const float LogLineH = 14f;
        private const float LabelW = 170f;           // the detail pane's label column (the longest label is Swedish)
        private const float NoteLabelW = 190f;

        private static bool _adminOpen;
        private static bool _adminClosed;            // a refusal ended the viewer's requests for this run
        private static bool _adminLoading, _closing, _logLoading;
        private static int _adminLoad;
        private static string _adminFilter = "open";
        private static List<PlayerReportRules.Report> _reports = new List<PlayerReportRules.Report>();
        private static string _selectedId;
        private static string _adminStatus = "";
        private static string _confirm = "";         // the verdict that waits for Yes
        private static string _note = "";
        private static string _logFor;               // the report whose log is shown or being read
        private static string[] _logLines;
        private static Vector2 _listScroll, _detailScroll, _logScroll;
        private static float _countAskedAt = -1000f;
        private static bool _countAsked;             // for this opening of the menu (Pump clears it when the menu closes)
        private static readonly LogBundleCore.OffMainJob<LogLines> _logJob = new LogBundleCore.OffMainJob<LogLines>();

        internal static void OpenAdmin()
        {
            _adminOpen = true;
            _selectedId = null; _confirm = ""; _note = ""; _adminStatus = "";
            _logFor = null; _logLines = null;
            LoadAdmin();
        }

        /// <summary>What every admin answer does first: a refusal that does not
        /// depend on the report closes the viewer's requests for the run.</summary>
        private static void AdminAnswered(int status, string code)
        {
            if (PlayerReportRules.AdminCloses(status)) _adminClosed = true;
            _adminStatus = PlayerReportRules.AdminAnswerText(status, code);
        }

        /// <summary>Reads the list. <paramref name="said"/> is what the press
        /// that asked for it has to say once the list is in ("" for nothing).</summary>
        private static void LoadAdmin(string said = "")
        {
            if (_adminClosed || _adminLoading) return;
            if (!ApiClient.IsAdmin) { _adminStatus = I18n.Tr("Not allowed."); return; }
            _adminLoading = true;
            int mine = ++_adminLoad;
            ApiClient.FetchPlayerReports(MatchTracker.LocalSteamId, _adminFilter, 100, (status, code, reports, openTotal) =>
            {
                _adminLoading = false;
                AdminAnswered(status, code);
                if (status != 200 || mine != _adminLoad) return;
                _adminStatus = said;
                _reports = reports ?? new List<PlayerReportRules.Report>();
                NativeUI.SetPlayerReportBadge(openTotal);
            });
        }

        /// <summary>One admin read for the launcher's badge when the admin tab
        /// is shown, by PlayerReportRules.MayAskCount: admins only, once per
        /// opening of the menu, never twice inside a minute, and never after
        /// a refusal closed the viewer's requests.</summary>
        internal static void RefreshOpenCount()
        {
            float now = Time.realtimeSinceStartup;
            if (!PlayerReportRules.MayAskCount(ApiClient.IsAdmin, _adminClosed, _countAsked, now, _countAskedAt)) return;
            _countAsked = true;
            _countAskedAt = now;
            ApiClient.FetchPlayerReports(MatchTracker.LocalSteamId, "open", 1, (status, code, reports, openTotal) =>
            {
                if (PlayerReportRules.AdminCloses(status)) _adminClosed = true;
                if (status == 200) NativeUI.SetPlayerReportBadge(openTotal);
            });
        }

        private static PlayerReportRules.Report Selected()
        {
            if (_selectedId == null) return null;
            foreach (PlayerReportRules.Report r in _reports)
                if (r.Id == _selectedId) return r;
            return null;
        }

        private static void CloseReport(PlayerReportRules.Report r, string verdict)
        {
            if (_adminClosed || _closing || r == null) return;
            _closing = true;
            ApiClient.ClosePlayerReport(MatchTracker.LocalSteamId, r.Id, verdict, (_note ?? "").Trim(), (status, code) =>
            {
                _closing = false;
                _confirm = "";
                AdminAnswered(status, code);
                if (status != 200) return;        // a refusal is shown; the admin presses Refresh
                _note = "";
                _adminStatus = I18n.Tr("Report closed.");
                LoadAdmin(_adminStatus);
            });
        }

        private static void ViewLog(PlayerReportRules.Report r)
        {
            if (_adminClosed || _logLoading || r == null || !r.HasLog) return;
            string id = r.Id;
            _logFor = id; _logLines = null; _logLoading = true;
            ApiClient.FetchPlayerReportLog(MatchTracker.LocalSteamId, id, (status, code, text) =>
            {
                AdminAnswered(status, code);
                bool started = status == 200 && _logFor == id
                    && _logJob.Start("SCR-PlayerReportLog",
                                     () => new LogLines { ReportId = id, Lines = SplitLines(text) },
                                     ex => new LogLines { ReportId = id, Lines = new string[0] });
                if (started) return;
                _logLoading = false;
                if (_logFor == id) _logFor = null;
            });
        }

        /// <summary>WORKER THREAD: the tail of a stored log as lines, each cut
        /// to what a row shows.</summary>
        private static string[] SplitLines(string text)
        {
            string tail = PlayerReportRules.Tail(text ?? "", LogTailChars);
            string[] lines = tail.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string l = lines[i];
                if (l.Length > 0 && l[l.Length - 1] == '\r') l = l.Substring(0, l.Length - 1);
                if (l.Length > LogLineChars) l = l.Substring(0, LogLineChars) + " ...";
                lines[i] = l;
            }
            return lines;
        }

        private static void PumpAdminLog()
        {
            int workerId;
            LogLines r = _logJob.TakeFinished(out workerId);
            if (r == null)
            {
                if (workerId != 0) { _logLoading = false; _logFor = null; }
                return;
            }
            _logLoading = false;
            if (r.ReportId != _logFor) return;
            _logLines = r.Lines;
            _logScroll = Vector2.zero;
        }

        /// <summary>The viewer. Called from CompetitiveUI.DrawUI beside the form.</summary>
        internal static void DrawAdmin()
        {
            if (!_adminOpen) return;
            if (!NativeUI.IsOpen) { _adminOpen = false; return; }
            EnsureStyles();

            var ev = Event.current;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape)
            {
                // Escape steps back once: the log, then the question, then the viewer.
                if (_logFor != null) { _logFor = null; _logLines = null; }
                else if (_confirm.Length > 0) _confirm = "";
                else _adminOpen = false;
                ev.Use();
                return;
            }

            float w = Mathf.Min(Screen.width - 40, 1180);
            float h = Mathf.Min(Screen.height - 60, 700);
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            Frame(x, y, w, h, 0.55f);

            bool can = !_adminClosed && !_adminLoading && !_closing;
            GUI.Label(new Rect(x, y, 300, 26), "<color=#FFE580>" + I18n.Tr("Player Reports") + "</color>", _titleStyle);
            GUI.enabled = can;
            if (GUI.Button(new Rect(x + 320, y, 110, 26), I18n.Tr("Pending"), _adminFilter == "open" ? _pickedStyle : _buttonStyle)
                && _adminFilter != "open")
            { _adminFilter = "open"; LoadAdmin(); }
            if (GUI.Button(new Rect(x + 436, y, 110, 26), I18n.Tr("All"), _adminFilter.Length == 0 ? _pickedStyle : _buttonStyle)
                && _adminFilter.Length != 0)
            { _adminFilter = ""; LoadAdmin(); }
            if (GUI.Button(new Rect(x + w - 216, y, 106, 26), I18n.Tr("Refresh"), _buttonStyle)) LoadAdmin();
            GUI.enabled = true;
            if (GUI.Button(new Rect(x + w - 104, y, 104, 26), I18n.Tr("Close"), _buttonStyle)) { _adminOpen = false; return; }

            string note = _adminLoading ? I18n.Tr("Loading...") : _adminStatus;
            if (note.Length > 0) GUI.Label(new Rect(x, y + 30, w, 20), "<color=#FFCC66>" + note + "</color>", _labelStyle);

            // The list: two lines a row, drawn without rich text because both
            // names are players' own text.
            float listW = Mathf.Min(520, w * 0.45f);
            float bodyY = y + 56, bodyH = h - 56;
            const float rowH = 46f, rowGap = 4f;
            float contentW = listW - 20;
            float contentH = Mathf.Max(bodyH - 4, _reports.Count * (rowH + rowGap) + 4);
            _listScroll = GUI.BeginScrollView(new Rect(x, bodyY, listW, bodyH), _listScroll, new Rect(0, 0, contentW, contentH));
            for (int i = 0; i < _reports.Count; i++)
            {
                PlayerReportRules.Report r = _reports[i];
                var rect = new Rect(0, i * (rowH + rowGap), contentW, rowH);
                bool selected = r.Id == _selectedId;
                GUI.DrawTexture(rect, Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0,
                                selected ? new Color(0.20f, 0.30f, 0.45f, 0.95f) : new Color(0.13f, 0.15f, 0.19f, 0.95f), 0, 0);
                GUI.Label(new Rect(8, rect.y + 4, contentW - 16, 20), PlayerReportRules.ReportLine(r, When(r.CreatedAt)), _rowStyle);
                GUI.Label(new Rect(8, rect.y + 24, contentW - 16, 20),
                          PlayerReportRules.StatusText(r.Status) + (r.HasLog ? "   " + I18n.Tr("Log attached") : ""), _rowDimStyle);
                if (GUI.Button(rect, GUIContent.none, GUIStyle.none) && !selected)
                {
                    _selectedId = r.Id;
                    _confirm = ""; _note = ""; _logFor = null; _logLines = null;
                    _detailScroll = Vector2.zero;
                }
            }
            if (_reports.Count == 0 && !_adminLoading)
                GUI.Label(new Rect(8, 8, contentW - 16, 24), I18n.Tr("No reports."), _rowDimStyle);
            GUI.EndScrollView();

            PlayerReportRules.Report sel = Selected();
            if (sel == null) return;
            float dx = x + listW + 14, dw = w - listW - 14;
            if (_logFor == sel.Id) DrawLog(dx, bodyY, dw, bodyH);
            else DrawDetail(sel, dx, bodyY, dw, bodyH, can);
        }

        /// <summary>One labelled line of the detail pane: the label is the
        /// mod's (rich text), the value a player's (plain).</summary>
        private static float Line(float x, float y, float w, string label, string value)
        {
            GUI.Label(new Rect(x, y, LabelW, 20), "<b>" + label + "</b>", _labelStyle);
            GUI.Label(new Rect(x + LabelW + 4, y, w - LabelW - 4, 20), value ?? "", _rowStyle);
            return y + 22;
        }

        private static void DrawDetail(PlayerReportRules.Report r, float x, float y, float w, float h, bool can)
        {
            float cy = y;
            cy = Line(x, cy, w, I18n.Tr("Reporter:"), r.ReporterName + "   " + r.ReporterSteamId);
            cy = Line(x, cy, w, I18n.Tr("Reported player:"), r.ReportedName + "   " + r.ReportedSteamId);
            cy = Line(x, cy, w, "", I18n.TrF("Reporters in the last 30 days: {0}", r.Reporters30d));
            cy = Line(x, cy, w, I18n.Tr("Game:"), PlayerReportRules.KindLabel(r.GameKind) + "   " + When(r.GameEndedAt));
            cy = Line(x, cy, w, I18n.Tr("Reason:"), PlayerReportRules.ReasonTextOf(r.Reason));
            string status = PlayerReportRules.StatusText(r.Status);
            if (r.ClosedBy.Length > 0) status += "   " + I18n.TrF("Closed by {0}", r.ClosedBy);
            if (r.ClosedAt.Length > 0) status += "   " + When(r.ClosedAt);
            cy = Line(x, cy, w, I18n.Tr("Status:"), status);
            if (r.CloseNote.Length > 0) cy = Line(x, cy, w, I18n.Tr("Note:"), r.CloseNote);

            GUI.Label(new Rect(x, cy, w, 20), "<b>" + I18n.Tr("Details:") + "</b>", _labelStyle);
            cy += 22;
            float areaH = Mathf.Max(60, y + h - cy - 84);
            string details = r.Details.Length == 0 ? "-" : r.Details;
            float textH = Mathf.Max(areaH, _plainStyle.CalcHeight(new GUIContent(details), w - 24));
            _detailScroll = GUI.BeginScrollView(new Rect(x, cy, w, areaH), _detailScroll, new Rect(0, 0, w - 20, textH));
            GUI.Label(new Rect(0, 0, w - 24, textH), details, _plainStyle);
            GUI.EndScrollView();
            cy += areaH + 8;

            if (_confirm.Length == 0)
            {
                GUI.enabled = can && r.HasLog && !_logLoading;
                if (GUI.Button(new Rect(x, cy, 130, 28), I18n.Tr("View Log"), _buttonStyle)) ViewLog(r);
                GUI.enabled = can && r.Status == "open";
                if (GUI.Button(new Rect(x + w - 300, cy, 140, 28), I18n.Tr("Dismiss"), _buttonStyle)) _confirm = "dismissed";
                if (GUI.Button(new Rect(x + w - 150, cy, 150, 28), I18n.Tr("Mark Actioned"), _buttonStyle)) _confirm = "actioned";
                GUI.enabled = true;
                return;
            }

            // The question, an optional note, then Yes or Cancel: a verdict is
            // never one press.
            GUI.Label(new Rect(x, cy, w, 20), "<color=#FFCC66>" + PlayerReportRules.VerdictQuestion(_confirm) + "</color>", _labelStyle);
            cy += 24;
            GUI.Label(new Rect(x, cy + 3, NoteLabelW, 20), I18n.Tr("Note (optional):"), _labelStyle);
            GUI.enabled = can;
            _note = GUI.TextField(new Rect(x + NoteLabelW + 4, cy, w - NoteLabelW - 4 - 230, 24), _note ?? "",
                                  PlayerReportRules.NoteMax, _fieldStyle);
            if (GUI.Button(new Rect(x + w - 220, cy, 100, 26), I18n.Tr("Yes"), _buttonStyle)) CloseReport(r, _confirm);
            GUI.enabled = !_closing;
            if (GUI.Button(new Rect(x + w - 110, cy, 110, 26), I18n.Tr("Cancel"), _buttonStyle)) _confirm = "";
            GUI.enabled = true;
        }

        /// <summary>A stored log, read-only: only the lines inside the scroll
        /// window are drawn, each without rich text.</summary>
        private static void DrawLog(float x, float y, float w, float h)
        {
            if (GUI.Button(new Rect(x + w - 110, y, 110, 26), I18n.Tr("Close"), _buttonStyle))
            { _logFor = null; _logLines = null; return; }
            string[] lines = _logLines;
            if (lines == null)
            {
                GUI.Label(new Rect(x, y + 3, w - 120, 22), I18n.Tr("Loading..."), _labelStyle);
                return;
            }
            float viewY = y + 32, viewH = h - 32;
            const float contentW = 7200f;
            float contentH = Mathf.Max(viewH, lines.Length * LogLineH + 8);
            _logScroll = GUI.BeginScrollView(new Rect(x, viewY, w, viewH), _logScroll, new Rect(0, 0, contentW, contentH), true, true);
            int first = Mathf.Max(0, (int)(_logScroll.y / LogLineH) - 2);
            int last = Mathf.Min(lines.Length - 1, first + (int)(viewH / LogLineH) + 4);
            for (int i = first; i <= last; i++)
                GUI.Label(new Rect(0, i * LogLineH, contentW, LogLineH + 4), lines[i], _logStyle);
            GUI.EndScrollView();
        }
    }
}
