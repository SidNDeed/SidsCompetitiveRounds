using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Ask 14: the player report form's rules, Unity-free so the client
    /// harness runs them (suite "playerreport"). The closed lists the server
    /// also holds, the table from each answer of the server to what the form
    /// says and what it closes, the labels of a game and a player, and the
    /// request's body are all decided here; PlayerReportUI only draws the
    /// answer and ApiClient only carries it.
    ///
    /// AFTER A REFUSAL THE FORM NEVER ASKS AGAIN FOR THE SAME THING. A refused
    /// request is counted for the player's address at the edge, so every
    /// refusal closes something: the same player of the same game (409), the
    /// game, the sign-in the server refused (401), the rest of this run of the
    /// game (429, 503), or at least the identical request. Nothing here sends
    /// by itself: Send is a press, and Check says whether a press may send.</summary>
    internal static partial class PlayerReportRules
    {
        // ---- the closed lists, equal to the server's player_report_rules.py ----

        internal static readonly string[] ReasonCodes =
            { "cheating", "harassment", "griefing", "leaving", "name", "other" };
        internal const string ReasonNeedsDetails = "other";
        internal static readonly string[] GameKinds = { "1v1", "2v2", "1v2", "ffa" };
        internal static readonly string[] Verdicts = { "dismissed", "actioned" };
        internal const int DetailsMax = 1000;        // characters the server keeps
        internal const int NoteMax = 500;
        internal const int LogMaxChars = 3500000;    // the tail the server keeps of a log
        internal const string ActionList = "player_reports";
        internal const string ActionLog = "player_reports_log";
        internal const string ActionClose = "player_reports_close";
        internal const string TargetList = "list";

        private const char Q = '"';
        private const char Bs = (char)92;            // a backslash

        /// <summary>The reason's text in the player's language, by its place in ReasonCodes.</summary>
        internal static string ReasonText(int i)
        {
            switch (i)
            {
                case 0: return I18n.Tr("Cheating or exploiting");
                case 1: return I18n.Tr("Harassment or abuse");
                case 2: return I18n.Tr("Griefing or throwing");
                case 3: return I18n.Tr("Leaving games");
                case 4: return I18n.Tr("Offensive name");
                case 5: return I18n.Tr("Other");
                default: return "";
            }
        }

        internal static string ReasonTextOf(string code)
        {
            int i = Array.IndexOf(ReasonCodes, code ?? "");
            return i < 0 ? Plain(code) : ReasonText(i);
        }

        // ---- what the server lists ----------------------------------------------

        /// <summary>A player of a listed game other than the caller.</summary>
        internal sealed class Other
        {
            internal readonly string SteamId;
            internal readonly string Name;
            internal readonly bool Reported;      // already reported by the caller for this game
            internal Other(string steamId, string name, bool reported)
            { SteamId = steamId ?? ""; Name = name ?? ""; Reported = reported; }
        }

        internal sealed class Game
        {
            internal readonly string Kind;
            internal readonly string Id;
            internal readonly string EndedAt;     // the server's UTC stamp, as sent
            internal readonly Other[] Others;
            internal Game(string kind, string id, string endedAt, Other[] others)
            { Kind = kind ?? ""; Id = id ?? ""; EndedAt = endedAt ?? ""; Others = others ?? new Other[0]; }
        }

        /// <summary>The server's stamp ("2026-11-09T03:00:00Z") as UTC; false when it is not one.</summary>
        internal static bool TryParseUtc(string stamp, out DateTime utc)
        {
            return DateTime.TryParseExact(stamp ?? "", "yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out utc);
        }

        // ---- labels: names are another player's text, never markup -----------------

        /// <summary>The mod's rule for user-written text in an IMGUI rich-text
        /// style (CompetitiveUI.SanitizeForImgui), restated here so a label is
        /// plain by construction.</summary>
        internal static string Plain(string s)
        {
            return string.IsNullOrEmpty(s) ? "" : s.Replace("<", "(").Replace(">", ")");
        }

        internal static string Cut(string s, int max)
        {
            s = (s ?? "").Trim();
            return s.Length <= max ? s : s.Substring(0, Math.Max(0, max - 3)) + "...";
        }

        internal static string KindLabel(string kind)
        {
            return kind == "ffa" ? I18n.Tr("FFA") : Plain(kind);
        }

        /// <summary>The other players of a game on one line: the first `show`
        /// names, then how many more.</summary>
        internal static string NamesLine(Other[] others, int show, int nameMax)
        {
            var sb = new StringBuilder();
            int n = others == null ? 0 : others.Length;
            for (int i = 0; i < n && i < show; i++)
            {
                if (i > 0) sb.Append(", ");
                sb.Append(Plain(Cut(others[i].Name, nameMax)));
            }
            return n > show ? I18n.TrF("{0} and {1} more", sb.ToString(), n - show) : sb.ToString();
        }

        /// <summary>One row of the game selector: the mode, when it ended (the
        /// caller formats the local time, by the player's date setting) and
        /// who else played.</summary>
        internal static string GameLabel(Game g, string when)
        {
            if (g == null) return "";
            return KindLabel(g.Kind) + "   " + Plain(when) + "   " + NamesLine(g.Others, 2, 12);
        }

        /// <summary>One row of the player selector.</summary>
        internal static string OtherLabel(Other o)
        {
            if (o == null) return "";
            string name = Plain(Cut(o.Name, 32));
            return o.Reported ? I18n.TrF("{0} (already reported)", name) : name;
        }

        /// <summary>The same row, knowing what this run of the game already sent.</summary>
        internal static string OtherLabel(FormState st, Game g, Other o)
        {
            if (o == null) return "";
            Outcome closed;
            bool sent = st != null && st.Choices.TryGetValue(ChoiceKey(g, o), out closed) && closed == Outcome.AlreadyReported;
            return sent && !o.Reported ? I18n.TrF("{0} (already reported)", Plain(Cut(o.Name, 32))) : OtherLabel(o);
        }

        // ---- the answers --------------------------------------------------------

        /// <summary>What the form says after an answer.</summary>
        internal enum Outcome
        {
            Sent, SentWithoutLog, AlreadyReported, DailyLimit, SignIn, TurnedOff,
            Unavailable, GameGone, NotInGame, TooLarge, NeedsUpdate, NotAccepted, NotSent
        }

        /// <summary>What an answer closes Send for. Same = this exact request
        /// (any edit reopens); Choice = this player of this game; Game = every
        /// player of this game; Auth = the sign-in that was refused (a new one
        /// reopens); Run = until the game is restarted. A 403 does not depend
        /// on what was chosen, so it closes the run, not one request.</summary>
        internal enum Closes { Nothing, Same, Choice, Game, Auth, Run }

        internal sealed class AnswerRow
        {
            internal readonly int Status;     // the HTTP status; 0 = no answer at all
            internal readonly string Code;    // the server's error code; "" = any other code of that status
            internal readonly Outcome Outcome;
            internal readonly Closes Closes;
            internal AnswerRow(int status, string code, Outcome outcome, Closes closes)
            { Status = status; Code = code; Outcome = outcome; Closes = closes; }
        }

        /// <summary>One row per answer the submit can get. A status with no row
        /// (a 500, a 502) is NoAnswerRow: the request was not judged, so
        /// nothing closes and nothing is sent again without a press.</summary>
        internal static readonly AnswerRow[] Answers =
        {
            new AnswerRow(200, "",                   Outcome.Sent,            Closes.Choice),
            new AnswerRow(400, "",                   Outcome.NotAccepted,     Closes.Same),
            new AnswerRow(401, "",                   Outcome.SignIn,          Closes.Auth),
            new AnswerRow(403, "",                   Outcome.NotAccepted,     Closes.Run),
            new AnswerRow(404, "game_not_found",     Outcome.GameGone,        Closes.Game),
            new AnswerRow(404, "",                   Outcome.Unavailable,     Closes.Run),
            new AnswerRow(409, "",                   Outcome.AlreadyReported, Closes.Choice),
            new AnswerRow(413, "",                   Outcome.TooLarge,        Closes.Same),
            new AnswerRow(422, "player_not_in_game", Outcome.NotInGame,       Closes.Choice),
            new AnswerRow(422, "",                   Outcome.NotAccepted,     Closes.Same),
            new AnswerRow(426, "",                   Outcome.NeedsUpdate,     Closes.Run),
            new AnswerRow(429, "report_limit",       Outcome.DailyLimit,      Closes.Run),
            new AnswerRow(429, "",                   Outcome.Unavailable,     Closes.Run),
            new AnswerRow(503, "player_reports_off", Outcome.TurnedOff,       Closes.Run),
            new AnswerRow(503, "",                   Outcome.Unavailable,     Closes.Run),
        };
        internal static readonly AnswerRow NoAnswerRow = new AnswerRow(0, "", Outcome.NotSent, Closes.Nothing);
        /// <summary>A 4xx the table does not name (a proxy's own refusal): the
        /// identical request is not sent again, and the form says it was not
        /// accepted. No answer is dropped without a line on screen.</summary>
        internal static readonly AnswerRow OtherRefusalRow = new AnswerRow(0, "", Outcome.NotAccepted, Closes.Same);

        internal static AnswerRow FindAnswer(int status, string code)
        {
            AnswerRow any = null;
            foreach (AnswerRow row in Answers)
            {
                if (row.Status != status) continue;
                if (row.Code.Length > 0 && row.Code == (code ?? "")) return row;
                if (row.Code.Length == 0) any = row;
            }
            if (any != null) return any;
            return status >= 400 && status < 500 ? OtherRefusalRow : NoAnswerRow;
        }

        internal static string AnswerText(Outcome o)
        {
            switch (o)
            {
                case Outcome.Sent: return I18n.Tr("Report sent. Thank you.");
                case Outcome.SentWithoutLog: return I18n.Tr("Report sent. The log could not be attached.");
                case Outcome.AlreadyReported: return I18n.Tr("You already reported this player for this game.");
                case Outcome.DailyLimit: return I18n.Tr("You have reached today's limit of reports.");
                case Outcome.SignIn: return I18n.Tr("Reports need a verified Steam sign-in.");
                case Outcome.TurnedOff: return I18n.Tr("Player reports are turned off right now.");
                case Outcome.Unavailable: return I18n.Tr("Player reports are unavailable right now.");
                case Outcome.GameGone: return I18n.Tr("That game can no longer be reported.");
                case Outcome.NotInGame: return I18n.Tr("That player was not in that game.");
                case Outcome.TooLarge: return I18n.Tr("The report is too large. Send it without the log.");
                case Outcome.NeedsUpdate: return I18n.Tr("Update the mod to use player reports.");
                case Outcome.NotAccepted: return I18n.Tr("The report was not accepted.");
                default: return I18n.Tr("The report could not be sent. Try again later.");
            }
        }

        /// <summary>The status out of ApiClient's failure text ("HTTP 409: ...");
        /// 200 for a success; 426 for "outdated", the transport's word for the
        /// version answer the server gave; 0 when there was no answer at all,
        /// "no-consent" included (that request was never sent).</summary>
        internal static int StatusOf(bool ok, string text)
        {
            if (ok) return 200;
            if (text == "outdated") return 426;
            if (string.IsNullOrEmpty(text) || !text.StartsWith("HTTP ", StringComparison.Ordinal)) return 0;
            int colon = text.IndexOf(':', 5);
            int code;
            if (colon > 5 && int.TryParse(text.Substring(5, colon - 5).Trim(), NumberStyles.None,
                                          CultureInfo.InvariantCulture, out code) && code >= 100 && code <= 599)
                return code;
            return 0;
        }

        /// <summary>The server's error code ({"detail":{"error":"..."}}): lower
        /// case letters and underscores, or "" for anything else.</summary>
        internal static string ErrorCode(string text)
        {
            if (string.IsNullOrEmpty(text)) return "";
            string key = Q + "error" + Q;
            int at = text.IndexOf(key, StringComparison.Ordinal);
            if (at < 0) return "";
            int i = at + key.Length;
            while (i < text.Length && (text[i] == ' ' || text[i] == ':')) i++;
            if (i >= text.Length || text[i] != Q) return "";
            int end = i + 1;
            while (end < text.Length && ((text[end] >= 'a' && text[end] <= 'z') || text[end] == '_')) end++;
            if (end >= text.Length || text[end] != Q || end - i - 1 > 40) return "";
            return text.Substring(i + 1, end - i - 1);
        }

        /// <summary>Whether a success says the attached log was stored.</summary>
        internal static bool LogStored(string body)
        {
            if (string.IsNullOrEmpty(body)) return false;
            string key = Q + "log_stored" + Q;
            int at = body.IndexOf(key, StringComparison.Ordinal);
            if (at < 0) return false;
            int i = at + key.Length;
            while (i < body.Length && (body[i] == ' ' || body[i] == ':')) i++;
            return string.CompareOrdinal(body, i, "true", 0, 4) == 0;
        }

        // ---- what a press may send -----------------------------------------------

        /// <summary>What the form remembers for this run of the game: what each
        /// answer closed, with what the form says about it. It is never
        /// cleared: closing and reopening the form reopens nothing.</summary>
        internal sealed class FormState
        {
            internal readonly Dictionary<string, Outcome> Choices = new Dictionary<string, Outcome>(StringComparer.Ordinal);
            internal readonly Dictionary<string, Outcome> Games = new Dictionary<string, Outcome>(StringComparer.Ordinal);
            internal readonly Dictionary<string, Outcome> Refused = new Dictionary<string, Outcome>(StringComparer.Ordinal);
            internal string RefusedSignIn = "";       // SessionKey of the sign-in the server refused
            internal bool RunClosed;
            internal Outcome RunOutcome = Outcome.NotSent;
            internal int Remaining = -1;        // left of today's limit as the server last said; -1 = not known
        }

        /// <summary>Why Send is closed. None = a press sends one request.</summary>
        internal enum Block
        {
            None, Sending, RunClosed, SignIn, NoneLeft, NoGame, GameClosed, NoPlayer,
            ChoiceClosed, NoReason, NeedsDetails, Refused
        }

        /// <summary>A fingerprint of the sign-in a request goes out with ("" =
        /// none). The state keeps this, never the token itself.</summary>
        internal static string SessionKey(string token)
        {
            if (string.IsNullOrEmpty(token)) return "";
            ulong h = 14695981039346656037UL;
            unchecked
            {
                foreach (char c in token) { h ^= c; h *= 1099511628211UL; }
            }
            return h.ToString("x16", CultureInfo.InvariantCulture);
        }

        internal static string GameKey(Game g)
        {
            return g == null ? "" : g.Kind + ":" + g.Id;
        }

        internal static string ChoiceKey(Game g, Other o)
        {
            return GameKey(g) + ":" + (o == null ? "" : o.SteamId);
        }

        /// <summary>The identical request: the details go last because they
        /// are the only part that may hold a colon.</summary>
        internal static string SameKey(Game g, Other o, string reason, string details, bool withLog)
        {
            return ChoiceKey(g, o) + ":" + (reason ?? "") + ":" + (withLog ? "1" : "0") + ":" + (details ?? "").Trim();
        }

        /// <summary>Whether a press on Send may send, decided without asking
        /// the server; `why` is what the form says when it may not. The order
        /// is the order the form explains itself in: what closes everything,
        /// then what is still to choose, then what this choice was already
        /// answered with.</summary>
        internal static Block Check(FormState st, Game game, Other other, string reason, string details,
                                    bool withLog, bool sending, string sessionKey, out Outcome why)
        {
            why = Outcome.NotSent;
            Outcome closed;
            if (sending) return Block.Sending;
            if (st.RunClosed) { why = st.RunOutcome; return Block.RunClosed; }
            if (string.IsNullOrEmpty(sessionKey) || sessionKey == st.RefusedSignIn) { why = Outcome.SignIn; return Block.SignIn; }
            if (st.Remaining == 0) { why = Outcome.DailyLimit; return Block.NoneLeft; }
            if (game == null) return Block.NoGame;
            if (st.Games.TryGetValue(GameKey(game), out closed)) { why = closed; return Block.GameClosed; }
            if (other == null) return Block.NoPlayer;
            if (other.Reported) { why = Outcome.AlreadyReported; return Block.ChoiceClosed; }
            if (st.Choices.TryGetValue(ChoiceKey(game, other), out closed)) { why = closed; return Block.ChoiceClosed; }
            if (Array.IndexOf(ReasonCodes, reason ?? "") < 0) return Block.NoReason;
            string d = (details ?? "").Trim();
            if (reason == ReasonNeedsDetails && d.Length == 0) return Block.NeedsDetails;
            // Longer details than the server keeps are cut by BuildBody, not refused.
            if (st.Refused.TryGetValue(SameKey(game, other, reason, d, withLog), out closed)) { why = closed; return Block.Refused; }
            return Block.None;
        }

        /// <summary>Takes the server's answer to a submit into the state and
        /// says what the form shows. Every row but NoAnswerRow closes
        /// something, so the request that was just answered is never sent a
        /// second time: Check returns a Block for it from now on.</summary>
        internal static Outcome Apply(FormState st, int status, string code, bool logStored, Game game, Other other,
                                      string reason, string details, bool withLog, string sessionKey)
        {
            AnswerRow row = FindAnswer(status, code);
            Outcome o = row.Outcome;
            switch (row.Closes)
            {
                case Closes.Same: st.Refused[SameKey(game, other, reason, details, withLog)] = o; break;
                // A player already reported reads the same whether this run sent the report or the server said so.
                case Closes.Choice: st.Choices[ChoiceKey(game, other)] = o == Outcome.Sent ? Outcome.AlreadyReported : o; break;
                case Closes.Game: st.Games[GameKey(game)] = o; break;
                case Closes.Auth: st.RefusedSignIn = sessionKey ?? ""; break;
                case Closes.Run: st.RunClosed = true; st.RunOutcome = o; break;
            }
            if (status == 200)
            {
                if (st.Remaining > 0) st.Remaining--;
                if (withLog && !logStored) o = Outcome.SentWithoutLog;
            }
            return o;
        }

        /// <summary>What the form says while Send is closed. The blocks that
        /// only mean "still to choose" say nothing: the selector reads "Choose".</summary>
        internal static string BlockText(Block b, Outcome why)
        {
            switch (b)
            {
                case Block.Sending: return I18n.Tr("Sending...");
                case Block.RunClosed:
                case Block.SignIn:
                case Block.NoneLeft:
                case Block.GameClosed:
                case Block.ChoiceClosed:
                case Block.Refused: return AnswerText(why);
                default: return "";
            }
        }

        // ---- the games list of one opening of the form ---------------------------

        internal enum ListState { Loading, Loaded, SignIn, Closed, Failed }

        /// <summary>Whether opening the form may ask for the games: Loading =
        /// it may, and the caller sends the one GET of this opening.</summary>
        internal static ListState BeforeList(FormState st, string sessionKey)
        {
            if (st.RunClosed) return ListState.Closed;
            if (string.IsNullOrEmpty(sessionKey) || sessionKey == st.RefusedSignIn) return ListState.SignIn;
            return ListState.Loading;
        }

        /// <summary>The answer to that GET. A refusal closes as a refused
        /// submit does (the sign-in after 401, the run after any other 4xx or
        /// a 503); no answer or a 5xx closes nothing, and only a new opening
        /// of the form asks again.</summary>
        internal static ListState ApplyList(FormState st, int status, string code, string sessionKey)
        {
            if (status == 200) return ListState.Loaded;
            if (status == 401) { st.RefusedSignIn = sessionKey ?? ""; return ListState.SignIn; }
            if ((status >= 400 && status < 500) || status == 503)
            {
                st.RunClosed = true;
                st.RunOutcome = status == 426 ? Outcome.NeedsUpdate
                              : code == "player_reports_off" ? Outcome.TurnedOff : Outcome.Unavailable;
                return ListState.Closed;
            }
            return ListState.Failed;
        }

        internal static string ListText(ListState s, FormState st, int games)
        {
            switch (s)
            {
                case ListState.Loading: return I18n.Tr("Loading...");
                case ListState.SignIn: return AnswerText(Outcome.SignIn);
                case ListState.Closed: return AnswerText(st.RunOutcome);
                case ListState.Failed: return I18n.Tr("Your games could not be loaded. Try again later.");
                default: return games == 0 ? I18n.Tr("You have no recent games to report.") : "";
            }
        }

        // ---- the request's body --------------------------------------------------

        internal const int BodyMax = 8 * 1024 * 1024;    // bytes the server reads of one request

        /// <summary>A JSON string literal, quotes included. Names, details and
        /// log lines are text the mod did not write, so every control
        /// character is escaped (a raw TAB or NUL makes a strict parser refuse
        /// the whole body): the table of ApiClient.JsonEscapeFull.</summary>
        internal static string JsonText(string s)
        {
            var sb = new StringBuilder((s == null ? 0 : s.Length) + 16);
            AppendJsonText(sb, s);
            return sb.ToString();
        }

        private static void AppendJsonText(StringBuilder sb, string s)
        {
            sb.Append(Q);
            if (s != null)
            {
                foreach (char c in s)
                {
                    if (c == Q || c == Bs) sb.Append(Bs).Append(c);
                    else if (c == '\n') sb.Append(Bs).Append('n');
                    else if (c == '\r') sb.Append(Bs).Append('r');
                    else if (c == '\t') sb.Append(Bs).Append('t');
                    else if (c < 0x20 || c == 0x7F)
                        sb.Append(Bs).Append('u').Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    else sb.Append(c);
                }
            }
            sb.Append(Q);
        }

        /// <summary>The last `max` characters, never starting inside a
        /// surrogate pair.</summary>
        internal static string Tail(string s, int max)
        {
            if (s == null || s.Length <= max) return s ?? "";
            int from = s.Length - max;
            if (char.IsLowSurrogate(s[from])) from++;
            return s.Substring(from);
        }

        /// <summary>The submit's body. It names the game, the reported player
        /// and the reason; it has NO field for who reports: the server takes
        /// the reporter from the session the request carries and from nothing
        /// else. logText null = no log attached.</summary>
        internal static string BuildBody(string kind, string gameId, string reportedSteamId, string reason,
                                         string details, string logText)
        {
            var sb = new StringBuilder(256 + (logText == null ? 0 : Math.Min(logText.Length, LogMaxChars)));
            sb.Append('{');
            Field(sb, "game_kind", kind).Append(',');
            Field(sb, "game_id", gameId).Append(',');
            Field(sb, "reported_steam_id", reportedSteamId).Append(',');
            Field(sb, "reason", reason).Append(',');
            Field(sb, "details", Clip(details, DetailsMax));
            if (logText != null)
            {
                sb.Append(',');
                Field(sb, "log_text", Tail(logText, LogMaxChars));
            }
            sb.Append('}');
            return sb.ToString();
        }

        private static StringBuilder Field(StringBuilder sb, string key, string value)
        {
            sb.Append(Q).Append(key).Append(Q).Append(':');
            AppendJsonText(sb, value ?? "");
            return sb;
        }

        private static string Clip(string s, int max)
        {
            s = (s ?? "").Trim();
            if (s.Length <= max) return s;
            int end = char.IsHighSurrogate(s[max - 1]) ? max - 1 : max;
            return s.Substring(0, end);
        }

        // ---- the admin's view ----------------------------------------------------

        /// <summary>One report of the admin list, as the server's list_row sends it.</summary>
        internal sealed class Report
        {
            internal string Id = "", CreatedAt = "", Status = "", Reason = "", Details = "";
            internal string GameKind = "", GameId = "", GameEndedAt = "";
            internal string ReporterSteamId = "", ReporterName = "";
            internal string ReportedSteamId = "", ReportedName = "";
            internal int Reporters30d;        // distinct accounts that reported this player in 30 days
            internal bool HasLog;
            internal string ClosedAt = "", ClosedBy = "", CloseNote = "";
        }

        /// <summary>The text an admin request is signed over: the tree's one
        /// form (admin:steam:action:target) with this lane's own action word,
        /// so a signature made for one route verifies for no other.</summary>
        internal static string AdminCanonical(string adminSteamId, string action, string target)
        {
            return "admin:" + adminSteamId + ":" + action + ":" + target;
        }

        /// <summary>The close signature names the report AND the verdict it closes with.</summary>
        internal static string CloseTarget(string reportId, string verdict)
        {
            return reportId + ":" + verdict;
        }

        /// <summary>A report's id as the server writes it: 36 characters, lower
        /// case hex in the 8-4-4-4-12 form. Nothing else is put into a URL.</summary>
        internal static bool IsReportId(string id)
        {
            if (id == null || id.Length != 36) return false;
            for (int i = 0; i < 36; i++)
            {
                char c = id[i];
                bool dash = i == 8 || i == 13 || i == 18 || i == 23;
                if (dash ? c != '-' : !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
            }
            return true;
        }

        internal static bool IsVerdict(string verdict)
        {
            return Array.IndexOf(Verdicts, verdict ?? "") >= 0;
        }

        internal static string StatusText(string status)
        {
            switch (status)
            {
                case "open": return I18n.Tr("Pending");
                case "dismissed": return I18n.Tr("Dismissed");
                case "actioned": return I18n.Tr("Actioned");
                default: return Plain(status);
            }
        }

        internal static string VerdictQuestion(string verdict)
        {
            return verdict == "actioned" ? I18n.Tr("Mark this report as actioned?") : I18n.Tr("Dismiss this report?");
        }

        /// <summary>One row of the admin list: when, why, who reported whom.</summary>
        internal static string ReportLine(Report r, string when)
        {
            if (r == null) return "";
            return Plain(when) + "   " + ReasonTextOf(r.Reason) + "   "
                 + I18n.TrF("{0} reported {1}", Plain(Cut(r.ReporterName, 18)), Plain(Cut(r.ReportedName, 18)));
        }

        /// <summary>What the viewer says after an admin request that did not succeed.</summary>
        internal static string AdminAnswerText(int status, string code)
        {
            if (status == 200) return "";
            if (code == "already_closed") return I18n.Tr("That report is already closed.");
            if (code == "report_not_found") return I18n.Tr("That report no longer exists.");
            if (code == "no_log") return I18n.Tr("No log is stored for this report.");
            if (status == 426) return I18n.Tr("Update the mod to use player reports.");
            if (status == 401 || status == 403) return I18n.Tr("Not allowed.");
            return I18n.Tr("The request failed. Try again later.");
        }

        /// <summary>The admin viewer after a refusal: 401, 403, 426, 429 and 503 do
        /// not depend on the report that was asked for, so the viewer sends
        /// nothing more for this run of the game.</summary>
        internal static bool AdminCloses(int status)
        {
            return status == 401 || status == 403 || status == 426 || status == 429 || status == 503;
        }

        /// <summary>The badge on the Queues launcher: the count of open
        /// reports as digits (no word, so no translation), "" for none.
        /// The badge sits on the launcher's corner and takes no width, so
        /// the count never moves a row the menu rule packed.</summary>
        internal const int CountMax = 99;

        internal static string CountText(int open)
        {
            if (open <= 0) return "";
            return open > CountMax ? CountMax.ToString(CultureInfo.InvariantCulture) + "+"
                                   : open.ToString(CultureInfo.InvariantCulture);
        }

        /// <summary>Whether the admin tab may ask for that count now: admins
        /// only, once per opening of the menu, never twice inside
        /// CountEverySeconds, and never after a refusal ended the viewer's
        /// requests for the run.</summary>
        internal const float CountEverySeconds = 60f;

        internal static bool MayAskCount(bool isAdmin, bool closedForRun, bool askedThisOpening, float now, float lastAskedAt)
        {
            return isAdmin && !closedForRun && !askedThisOpening && now - lastAskedAt >= CountEverySeconds;
        }
    }
}
