using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Ask 14: the player report form's rules executed by the client
    /// harness as suite "playerreport". Every case prints its measurement in
    /// got=, so a wrong row of the answer table, a request sent twice, an
    /// unescaped character or a missing translation is red by its value. The
    /// cases named "after ..." are the form's state table: one per answer the
    /// server can give, each showing what a press is told afterwards.</summary>
    internal static partial class PlayerReportRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private static readonly string[] Locales = { "es", "ru", "uk", "sv" };

        private const string Key1 = "0123456789abcdef";   // one sign-in's fingerprint
        private const string Key2 = "fedcba9876543210";   // another's

        // A small fixed world: an FFA with three other players (the third one
        // already reported) and a 1v1.
        private static Game G1()
        {
            return new Game("ffa", "g-1", "2026-11-08T21:14:00Z", new[]
                { new Other("S_ANN", "Ann", false), new Other("S_BO", "Bo", false), new Other("S_CY", "Cy", true) });
        }

        private static Game G2()
        {
            return new Game("1v1", "g-2", "2026-11-07T10:00:00Z", new[] { new Other("S_DEE", "Dee", false) });
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            I18nCatalogues.Install();
            string savedLocale = I18n.HarnessLocale;
            try
            {
                I18n.HarnessLocale = "en";
                ListsCase(r);
                AnswerCases(r);
                StateCases(r);
                PressCases(r);
                ListCases(r);
                ParseCases(r);
                LabelCases(r);
                BodyCases(r);
                AdminCases(r);
                CatalogueCase(r);
            }
            finally { I18n.HarnessLocale = savedLocale; }
            return r;
        }

        private static void Case(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name).Append(" | got=").Append(got).Append('\n');
        }

        // ---- the closed lists (pytest compares this line with the server's module) ----

        private static void ListsCase(SelfTestResult r)
        {
            string got = "reasons=" + string.Join(",", ReasonCodes) + " needs=" + ReasonNeedsDetails
                       + " kinds=" + string.Join(",", GameKinds) + " verdicts=" + string.Join(",", Verdicts)
                       + " details=" + DetailsMax + " note=" + NoteMax + " log=" + LogMaxChars + " body=" + BodyMax
                       + " actions=" + ActionList + "," + ActionLog + "," + ActionClose + " target=" + TargetList;
            Case(r, "closed lists and caps",
                 got == "reasons=cheating,harassment,griefing,leaving,name,other needs=other"
                      + " kinds=1v1,2v2,1v2,ffa verdicts=dismissed,actioned details=1000 note=500 log=3500000 body=8388608"
                      + " actions=player_reports,player_reports_log,player_reports_close target=list", got);
        }

        // ---- the answer table ------------------------------------------------------

        /// <summary>Every answer the server's rules give a submit ("status
        /// code"), then the answers that are not the rules' own: the route's
        /// 503 on the standby (read_replica), a 503 whose detail names no code
        /// (the identity locks' queue_contended), the version gate's 426, a
        /// proxy's own 4xx, the limiter's 429, a missing route's 404, a failing
        /// server, no answer.</summary>
        private static readonly string[] ServerAnswers =
        {
            "401 session_required", "503 player_reports_off", "400 bad_length", "413 body_too_large",
            "403 no_player", "404 game_not_found", "422 player_not_in_game", "409 already_reported",
            "429 report_limit", "422 bad_body", "422 bad_game_kind", "422 bad_game_id", "422 bad_player",
            "422 bad_reason", "422 bad_details", "422 details_too_long", "422 details_required", "422 bad_log",
            "503 read_replica", "503 ", "426 ", "418 ", "429 ", "404 ", "500 ", "502 ", "0 ",
        };

        private static void AnswerCases(SelfTestResult r)
        {
            var sb = new StringBuilder();
            int open = 0;
            foreach (AnswerRow a in Answers)
            {
                if (sb.Length > 0) sb.Append(';');
                sb.Append(a.Status).Append('/').Append(a.Code).Append('=').Append(a.Outcome).Append('>').Append(a.Closes);
                if (a.Closes == Closes.Nothing) open++;
            }
            string got = sb.ToString();
            Case(r, "the answer table",
                 got == "200/=Sent>Choice;400/=NotAccepted>Same;401/=SignIn>Auth;403/=NotAccepted>Run;"
                      + "404/game_not_found=GameGone>Game;404/=Unavailable>Run;409/=AlreadyReported>Choice;"
                      + "413/=TooLarge>Same;422/player_not_in_game=NotInGame>Choice;422/=NotAccepted>Same;426/=NeedsUpdate>Run;"
                      + "429/report_limit=DailyLimit>Run;429/=Unavailable>Run;503/player_reports_off=TurnedOff>Run;"
                      + "503/=Unavailable>Run", got);
            AnswerRow other = FindAnswer(418, "teapot"), none = FindAnswer(500, "");
            Case(r, "every row of the table closes something",
                 Answers.Length == 15 && open == 0 && other.Closes == Closes.Same && none.Closes == Closes.Nothing,
                 "rows=" + Answers.Length + " closing_nothing=" + open + " unnamed_4xx=" + other.Outcome + ">" + other.Closes
                 + " no_answer_or_5xx=" + none.Outcome + ">" + none.Closes);

            // No answer is dropped without a line on screen: every outcome has
            // a text, no two share one, and the two answers the table had no
            // word for before read as below.
            var said = new List<string>();
            int blank = 0;
            foreach (Outcome o in Enum.GetValues(typeof(Outcome)))
            {
                string t = AnswerText(o);
                if (string.IsNullOrEmpty(t)) blank++;
                if (!said.Contains(t)) said.Add(t);
            }
            got = "outcomes=" + Enum.GetValues(typeof(Outcome)).Length + " lines=" + said.Count + " blank=" + blank
                + " version=" + AnswerText(FindAnswer(426, "").Outcome) + " unnamed=" + AnswerText(FindAnswer(418, "").Outcome);
            Case(r, "each outcome has a line of its own",
                 got == "outcomes=13 lines=13 blank=0 version=Update the mod to use player reports. unnamed=The report was not accepted.", got);

            sb.Length = 0;
            foreach (string c in ServerAnswers)
            {
                int sp = c.IndexOf(' ');
                AnswerRow a = FindAnswer(int.Parse(c.Substring(0, sp), CultureInfo.InvariantCulture), c.Substring(sp + 1));
                if (sb.Length > 0) sb.Append(';');
                sb.Append(c.Trim().Replace(' ', '/')).Append('=').Append(a.Outcome).Append('>').Append(a.Closes);
            }
            got = sb.ToString();
            Case(r, "each server answer finds its row",
                 got == "401/session_required=SignIn>Auth;503/player_reports_off=TurnedOff>Run;400/bad_length=NotAccepted>Same;"
                      + "413/body_too_large=TooLarge>Same;403/no_player=NotAccepted>Run;404/game_not_found=GameGone>Game;"
                      + "422/player_not_in_game=NotInGame>Choice;409/already_reported=AlreadyReported>Choice;"
                      + "429/report_limit=DailyLimit>Run;422/bad_body=NotAccepted>Same;422/bad_game_kind=NotAccepted>Same;"
                      + "422/bad_game_id=NotAccepted>Same;422/bad_player=NotAccepted>Same;422/bad_reason=NotAccepted>Same;"
                      + "422/bad_details=NotAccepted>Same;422/details_too_long=NotAccepted>Same;"
                      + "422/details_required=NotAccepted>Same;422/bad_log=NotAccepted>Same;"
                      + "503/read_replica=Unavailable>Run;503=Unavailable>Run;426=NeedsUpdate>Run;"
                      + "418=NotAccepted>Same;429=Unavailable>Run;"
                      + "404=Unavailable>Run;500=NotSent>Nothing;502=NotSent>Nothing;0=NotSent>Nothing", got);
        }

        // ---- the state table: what a press is told after each answer -----------------

        private static string Told(FormState st, Game g, Other o, string reason, string details, bool withLog, string key)
        {
            Outcome why;
            Block b = Check(st, g, o, reason, details, withLog, false, key, out why);
            return b == Block.None ? "None" : b + "(" + why + ")";
        }

        /// <summary>One answer to (the FFA, Ann, cheating, no details, with the
        /// log) on a fresh state, then what a press is told for: the same
        /// request; the same choice with another reason; the same without the
        /// log; another player of that game; another game; and the same request
        /// after a new sign-in.</summary>
        private static void After(SelfTestResult r, int status, string code, string expected)
        {
            var st = new FormState();
            Game g1 = G1(), g2 = G2();
            string before = Told(st, g1, g1.Others[0], "cheating", "", true, Key1);
            Outcome said = Apply(st, status, code, true, g1, g1.Others[0], "cheating", "", true, Key1);
            string got = "before=" + before + " said=" + said
                       + " same=" + Told(st, g1, g1.Others[0], "cheating", "", true, Key1)
                       + " reason=" + Told(st, g1, g1.Others[0], "griefing", "", true, Key1)
                       + " nolog=" + Told(st, g1, g1.Others[0], "cheating", "", false, Key1)
                       + " player=" + Told(st, g1, g1.Others[1], "cheating", "", true, Key1)
                       + " game=" + Told(st, g2, g2.Others[0], "cheating", "", true, Key1)
                       + " signin=" + Told(st, g1, g1.Others[0], "cheating", "", true, Key2);
            Case(r, "after " + status + (code.Length == 0 ? "" : " " + code), got == expected, got);
        }

        private static string Exp(string said, string same, string reason, string nolog, string player, string game, string signin)
        {
            return "before=None said=" + said + " same=" + same + " reason=" + reason + " nolog=" + nolog
                 + " player=" + player + " game=" + game + " signin=" + signin;
        }

        private static string ExpAll(string said, string all) { return Exp(said, all, all, all, all, all, all); }

        private static void StateCases(SelfTestResult r)
        {
            const string AR = "ChoiceClosed(AlreadyReported)", NIG = "ChoiceClosed(NotInGame)", GG = "GameClosed(GameGone)";
            const string RNA = "Refused(NotAccepted)", RTL = "Refused(TooLarge)", SI = "SignIn(SignIn)", N = "None";
            After(r, 200, "", Exp("Sent", AR, AR, AR, N, N, AR));
            After(r, 400, "bad_length", Exp("NotAccepted", RNA, N, N, N, N, RNA));
            After(r, 401, "session_required", Exp("SignIn", SI, SI, SI, SI, SI, N));
            After(r, 403, "no_player", ExpAll("NotAccepted", "RunClosed(NotAccepted)"));
            After(r, 404, "game_not_found", Exp("GameGone", GG, GG, GG, GG, N, GG));
            After(r, 404, "", ExpAll("Unavailable", "RunClosed(Unavailable)"));
            After(r, 409, "already_reported", Exp("AlreadyReported", AR, AR, AR, N, N, AR));
            After(r, 413, "body_too_large", Exp("TooLarge", RTL, N, N, N, N, RTL));
            After(r, 422, "player_not_in_game", Exp("NotInGame", NIG, NIG, NIG, N, N, NIG));
            After(r, 422, "bad_reason", Exp("NotAccepted", RNA, N, N, N, N, RNA));
            After(r, 426, "", ExpAll("NeedsUpdate", "RunClosed(NeedsUpdate)"));  // the version answer
            After(r, 418, "", Exp("NotAccepted", RNA, N, N, N, N, RNA));       // a 4xx the table does not name
            After(r, 429, "report_limit", ExpAll("DailyLimit", "RunClosed(DailyLimit)"));
            After(r, 429, "", ExpAll("Unavailable", "RunClosed(Unavailable)"));
            After(r, 503, "player_reports_off", ExpAll("TurnedOff", "RunClosed(TurnedOff)"));
            After(r, 503, "", ExpAll("Unavailable", "RunClosed(Unavailable)"));
            After(r, 500, "", ExpAll("NotSent", N));
            After(r, 0, "", ExpAll("NotSent", N));

            // The sweep behind the table: whatever the server answers a
            // submit with, the request it answered is closed afterwards. The
            // answers swept are exactly those the table judges (FindAnswer
            // gives a row other than NoAnswerRow), and every row of the table
            // but the success's is reached by one of them.
            int resend = 0, swept = 0, judged = 0;
            var open = new StringBuilder();
            var reached = new List<AnswerRow>();
            foreach (string c in ServerAnswers)
            {
                int sp = c.IndexOf(' ');
                int status = int.Parse(c.Substring(0, sp), CultureInfo.InvariantCulture);
                string code = c.Substring(sp + 1);
                AnswerRow row = FindAnswer(status, code);
                if (!ReferenceEquals(row, NoAnswerRow)) { judged++; if (!reached.Contains(row)) reached.Add(row); }
                if (status == 0 || (status >= 500 && status != 503)) continue;   // not judged: nothing closes, and nothing is sent again without a press
                var st = new FormState();
                Game g1 = G1();
                Apply(st, status, code, true, g1, g1.Others[0], "other", " he left ", true, Key1);
                swept++;
                if (Told(st, g1, g1.Others[0], "other", "he left", true, Key1) == "None") { resend++; open.Append(c).Append(';'); }
            }
            var unswept = new StringBuilder();
            foreach (AnswerRow row in Answers)
                if (row.Status != 200 && !reached.Contains(row)) unswept.Append(row.Status).Append('/').Append(row.Code).Append(';');
            Case(r, "a refused request is never sent again",
                 swept > 0 && swept == judged && resend == 0 && unswept.Length == 0,
                 "answers=" + swept + " judged=" + judged + " open_again=" + resend
                 + " rows_unswept=" + (unswept.Length > 0 ? unswept.ToString() : "0") + (open.Length > 0 ? " " + open : ""));
        }

        // ---- before a press ----------------------------------------------------------

        private static void PressCases(SelfTestResult r)
        {
            Game g1 = G1();
            var st = new FormState();
            Outcome why;
            var sb = new StringBuilder();
            sb.Append(Check(st, null, null, "", "", true, false, "", out why)).Append(',');           // no sign-in comes first
            sb.Append(Check(st, null, null, "", "", true, false, Key1, out why)).Append(',');         // then the game
            sb.Append(Check(st, g1, null, "", "", true, false, Key1, out why)).Append(',');           // the player
            sb.Append(Check(st, g1, g1.Others[2], "", "", true, false, Key1, out why)).Append(',');   // listed as reported
            sb.Append(Check(st, g1, g1.Others[0], "", "", true, false, Key1, out why)).Append(',');   // the reason
            sb.Append(Check(st, g1, g1.Others[0], "rude", "", true, false, Key1, out why)).Append(',');
            sb.Append(Check(st, g1, g1.Others[0], "other", "  ", true, false, Key1, out why)).Append(',');
            sb.Append(Check(st, g1, g1.Others[0], "other", "x", true, false, Key1, out why)).Append(',');
            sb.Append(Check(st, g1, g1.Others[0], "other", "x", true, true, Key1, out why));          // a request in flight
            string got = sb.ToString();
            Case(r, "what is still to choose, in order",
                 got == "SignIn,NoGame,NoPlayer,ChoiceClosed,NoReason,NoReason,NeedsDetails,None,Sending", got);

            st = new FormState();
            st.Remaining = 2;
            Apply(st, 200, "", true, g1, g1.Others[0], "cheating", "", false, Key1);
            int one = st.Remaining;
            Apply(st, 200, "", true, g1, g1.Others[1], "cheating", "", false, Key1);
            int none = st.Remaining;
            Game g2 = G2();
            string third = Told(st, g2, g2.Others[0], "cheating", "", false, Key1);
            var unknown = new FormState();
            Apply(unknown, 200, "", true, g1, g1.Others[0], "cheating", "", false, Key1);
            got = "left=2>" + one + ">" + none + " third=" + third + " unknown=" + unknown.Remaining;
            Case(r, "the day's limit closes Send without asking", got == "left=2>1>0 third=NoneLeft(DailyLimit) unknown=-1", got);

            got = "stored=" + Apply(new FormState(), 200, "", true, g1, g1.Others[0], "cheating", "", true, Key1)
                + " not_stored=" + Apply(new FormState(), 200, "", false, g1, g1.Others[0], "cheating", "", true, Key1)
                + " no_log=" + Apply(new FormState(), 200, "", false, g1, g1.Others[0], "cheating", "", false, Key1);
            Case(r, "a report sent without its log says so", got == "stored=Sent not_stored=SentWithoutLog no_log=Sent", got);

            st = new FormState();
            Apply(st, 503, "player_reports_off", true, g1, g1.Others[0], "cheating", "", true, Key1);
            got = Check(st, g1, g1.Others[0], "cheating", "", true, true, Key1, out why) + ",";
            got += Check(st, null, null, "", "", true, false, "", out why) + "(" + why + ")";
            Case(r, "a request in flight, then the closed run, come before anything else",
                 got == "Sending,RunClosed(TurnedOff)", got);

            // The sign-in the server refused closes Send; the next sign-in
            // (SteamAuth.MaybeRefresh mints another token) opens it again.
            string refused = SessionKey("the token the server refused"), minted = SessionKey("the token minted afterwards");
            st = new FormState();
            Apply(st, 401, "session_required", false, g1, g1.Others[0], "cheating", "", true, refused);
            got = "press_before_refresh=" + Told(st, g1, g1.Others[0], "cheating", "", true, refused)
                + " list_before=" + BeforeList(st, refused)
                + " press_after_refresh=" + Told(st, g1, g1.Others[0], "cheating", "", true, minted)
                + " list_after=" + BeforeList(st, minted)
                + " no_sign_in=" + Told(st, g1, g1.Others[0], "cheating", "", true, "")
                + " state_holds_the_token=" + (st.RefusedSignIn.Length != 16 || st.RefusedSignIn.Contains("token"));
            Case(r, "after 401 a press stays closed until the next sign-in, then goes out",
                 got == "press_before_refresh=SignIn(SignIn) list_before=SignIn press_after_refresh=None list_after=Loading"
                      + " no_sign_in=SignIn(SignIn) state_holds_the_token=False", got);

            st = new FormState();
            Apply(st, 200, "", true, g1, g1.Others[0], "cheating", "", false, Key1);
            Apply(st, 422, "player_not_in_game", false, g1, g1.Others[1], "cheating", "", false, Key1);
            got = OtherLabel(st, g1, g1.Others[0]) + "|" + OtherLabel(st, g1, g1.Others[1]) + "|" + OtherLabel(st, g1, g1.Others[2])
                + "|" + OtherLabel(st, g2, g2.Others[0]) + "|" + OtherLabel(null, g1, g1.Others[0]) + "|" + OtherLabel(st, g1, null);
            Case(r, "the player row marks what this run already sent", got == "Ann (already reported)|Bo|Cy (already reported)|Dee|Ann|", got);

            got = BlockText(Block.Sending, Outcome.NotSent) + "|" + BlockText(Block.NoGame, Outcome.NotSent)
                + "|" + BlockText(Block.NeedsDetails, Outcome.NotSent) + "|" + BlockText(Block.ChoiceClosed, Outcome.NotInGame)
                + "|" + BlockText(Block.Refused, Outcome.TooLarge) + "|" + BlockText(Block.RunClosed, Outcome.TurnedOff);
            Case(r, "what the form says while Send is closed",
                 got == "Sending...|||That player was not in that game.|The report is too large. Send it without the log."
                      + "|Player reports are turned off right now.", got);
        }

        // ---- the games list ----------------------------------------------------------

        private static void ListCases(SelfTestResult r)
        {
            var st = new FormState();
            string got = "fresh=" + BeforeList(st, Key1) + " none=" + BeforeList(st, "");
            st.RefusedSignIn = Key1;
            got += " refused=" + BeforeList(st, Key1) + " renewed=" + BeforeList(st, Key2);
            st.RunClosed = true;
            got += " closed=" + BeforeList(st, Key2);
            Case(r, "whether opening the form may ask for the games",
                 got == "fresh=Loading none=SignIn refused=SignIn renewed=Loading closed=Closed", got);

            var sb = new StringBuilder();
            string[] answers = { "200 ", "401 session_required", "403 ", "404 ", "426 ", "429 ", "503 player_reports_off", "503 ", "500 ", "0 " };
            foreach (string a in answers)
            {
                int sp = a.IndexOf(' ');
                var s2 = new FormState();
                ListState ls = ApplyList(s2, int.Parse(a.Substring(0, sp), CultureInfo.InvariantCulture), a.Substring(sp + 1), Key1);
                if (sb.Length > 0) sb.Append(';');
                sb.Append(a.Substring(0, sp)).Append('=').Append(ls);
                if (s2.RunClosed) sb.Append("/run:").Append(s2.RunOutcome);
                if (s2.RefusedSignIn.Length > 0) sb.Append("/signin");
                sb.Append('>').Append(BeforeList(s2, Key1));     // what the next opening does
            }
            got = sb.ToString();
            Case(r, "each answer to the games read and the next opening",
                 got == "200=Loaded>Loading;401=SignIn/signin>SignIn;403=Closed/run:Unavailable>Closed;"
                      + "404=Closed/run:Unavailable>Closed;426=Closed/run:NeedsUpdate>Closed;"
                      + "429=Closed/run:Unavailable>Closed;"
                      + "503=Closed/run:TurnedOff>Closed;503=Closed/run:Unavailable>Closed;500=Failed>Loading;0=Failed>Loading", got);

            st = new FormState();
            st.RunOutcome = Outcome.TurnedOff;
            got = ListText(ListState.Loading, st, 0) + "|" + ListText(ListState.Loaded, st, 3) + "|" + ListText(ListState.Loaded, st, 0)
                + "|" + ListText(ListState.SignIn, st, 0) + "|" + ListText(ListState.Closed, st, 0) + "|" + ListText(ListState.Failed, st, 0);
            Case(r, "what the form says about its list",
                 got == "Loading...||You have no recent games to report.|Reports need a verified Steam sign-in."
                      + "|Player reports are turned off right now.|Your games could not be loaded. Try again later.", got);
        }

        // ---- reading an answer -------------------------------------------------------

        /// <summary>Test text written without escapes: an apostrophe stands for
        /// a quote and a caret for a backslash.</summary>
        private static string J(string s) { return s.Replace((char)39, Q).Replace('^', Bs); }

        /// <summary>Non-ASCII as a u-escape, so a log line reads the same on any console.</summary>
        private static string Ascii(string s)
        {
            var sb = new StringBuilder();
            foreach (char c in s ?? "")
            {
                if (c >= 32 && c < 127) sb.Append(c);
                else sb.Append(Bs).Append('u').Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
            }
            return sb.ToString();
        }

        private static void ParseCases(SelfTestResult r)
        {
            string refused = "HTTP 409: " + J("{'detail':{'error':'already_reported'}}");
            string got = StatusOf(true, "{}") + "," + StatusOf(false, refused) + ","
                       + StatusOf(false, "HTTP 429: slow down\nRetry-After: 5") + "," + StatusOf(false, "") + ","
                       + StatusOf(false, null) + "," + StatusOf(false, "Cannot connect to destination host") + ","
                       + StatusOf(false, "HTTP abc: x") + "," + StatusOf(false, "HTTP 99: x") + "," + StatusOf(false, "HTTP 503")
                       + "," + StatusOf(false, "outdated") + "," + StatusOf(false, "no-consent");
            Case(r, "the status out of the transport's text", got == "200,409,429,0,0,0,0,0,0,426,0", got);

            got = "a=" + ErrorCode(refused)
                + " b=" + ErrorCode(J("HTTP 429: {'detail': {'error': 'report_limit'}}"))
                + " c=" + ErrorCode(J("{'error':'Bad_Code'}"))
                + " d=" + ErrorCode(J("{'error':'") + new string('a', 41) + J("'}"))
                + " e=" + ErrorCode("HTTP 500: Internal Server Error")
                + " f=" + ErrorCode(J("{'error':12}"))
                + " g=" + ErrorCode(null)
                + " h=" + ErrorCode(J("{'error':'") + new string('a', 40) + J("'}")).Length;
            Case(r, "the error code out of a refusal", got == "a=already_reported b=report_limit c= d= e= f= g= h=40", got);

            got = LogStored(J("{'ok':true,'log_stored':true}")) + "," + LogStored(J("{'ok':true,'log_stored':false}")) + ","
                + LogStored(J("{'ok':true}")) + "," + LogStored("") + "," + LogStored(J("{'log_stored': true}"));
            Case(r, "whether the log was stored", got == "True,False,False,False,True", got);

            DateTime utc;
            bool ok = TryParseUtc("2026-11-08T21:14:00Z", out utc);
            got = ok + ":" + utc.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture) + ":" + utc.Kind;
            got += "," + TryParseUtc("2026-11-08 21:14:00", out utc) + "," + TryParseUtc("", out utc) + "," + TryParseUtc(null, out utc);
            Case(r, "the server's stamp as UTC", got == "True:2026-11-08 21:14:Utc,False,False,False", got);
        }

        // ---- labels ------------------------------------------------------------------

        private static Game Crowd()
        {
            return new Game("ffa", "g-3", "", new[]
                { new Other("a", "Ann", false), new Other("b", "Bo", false), new Other("c", "Cy", false), new Other("d", "Dee", false) });
        }

        private static void LabelCases(SelfTestResult r)
        {
            Game g1 = G1(), g2 = G2();
            string got = GameLabel(g1, "8 Nov 21:14") + "|" + GameLabel(g2, "7 Nov 10:00") + "|" + GameLabel(Crowd(), "now")
                       + "|" + OtherLabel(g1.Others[0]) + "|" + OtherLabel(g1.Others[2]) + "|" + GameLabel(null, "x") + OtherLabel(null);
            Case(r, "the game and player rows in English",
                 got == "FFA   8 Nov 21:14   Ann, Bo and 1 more|1v1   7 Nov 10:00   Dee|FFA   now   Ann, Bo and 2 more"
                      + "|Ann|Cy (already reported)|", got);

            var odd = new Other("x", "<b>Very long name of a player</b>", false);
            got = OtherLabel(odd) + "|" + NamesLine(new[] { odd }, 2, 14) + "|" + Plain("<color=red>a</color>")
                + "|" + KindLabel("<i>") + "|" + ReasonTextOf("<x>") + "|" + ReasonTextOf("name") + "|" + GameLabel(g2, "<size=40>");
            Case(r, "another player's text is never markup",
                 got == "(b)Very long name of a player...|(b)Very lon...|(color=red)a(/color)|(i)|(x)|Offensive name"
                      + "|1v1   (size=40)   Dee", got);

            string enGame = GameLabel(Crowd(), "t"), enOther = OtherLabel(g1.Others[2]), enReason = ReasonText(0);
            var sb = new StringBuilder();
            bool all = true;
            foreach (string loc in Locales)
            {
                I18n.HarnessLocale = loc;
                string lg = GameLabel(Crowd(), "t"), lo = OtherLabel(g1.Others[2]), lr = ReasonText(0);
                bool ok = lg != enGame && lg.Contains("Ann, Bo") && lg.Contains("2") && lg.IndexOf('{') < 0
                       && lo != enOther && lo.Contains("Cy") && lo.IndexOf('{') < 0
                       && lr != enReason && lr.Length > 0;
                all = all && ok;
                sb.Append(loc).Append(ok ? ":ok " : ":BAD ").Append(Ascii(lg)).Append(" / ").Append(Ascii(lo)).Append(" / ").Append(Ascii(lr)).Append("; ");
            }
            I18n.HarnessLocale = "en";
            Case(r, "the rows in the four locales", all, sb.ToString().TrimEnd());
        }

        // ---- the request's body --------------------------------------------------------

        /// <summary>The body's keys in order: every string that is followed by a colon.</summary>
        private static string Keys(string json)
        {
            var keys = new List<string>();
            bool inStr = false;
            int start = 0;
            for (int i = 0; i < json.Length; i++)
            {
                char c = json[i];
                if (!inStr) { if (c == Q) { inStr = true; start = i + 1; } continue; }
                if (c == Bs) { i++; continue; }
                if (c != Q) continue;
                inStr = false;
                if (i + 1 < json.Length && json[i + 1] == ':') keys.Add(json.Substring(start, i - start));
            }
            return string.Join(",", keys);
        }

        /// <summary>The characters of one string field of a body built by BuildBody (the last field).</summary>
        private static int LastFieldChars(string body, string key)
        {
            string marker = Q + key + Q + ":" + Q;
            int at = body.IndexOf(marker, StringComparison.Ordinal);
            return at < 0 ? -1 : body.Length - (at + marker.Length) - 2;   // the closing quote and brace
        }

        private static void BodyCases(SelfTestResult r)
        {
            char hi = (char)0xD83D, lo = (char)0xDE00;
            string details = "  he said " + Q + "x" + Q + "\tand\nleft " + (char)1 + Bs + " ";
            string plain = BuildBody("ffa", "g-1", "S_ANN", "other", details, null);
            Case(r, "the body, with quotes and control characters",
                 plain == J("{'game_kind':'ffa','game_id':'g-1','reported_steam_id':'S_ANN','reason':'other',"
                          + "'details':'he said ^'x^'^tand^nleft ^u0001^^'}"), plain);

            string with = BuildBody("1v1", "g-2", "S_DEE", "cheating", null, "line one\nline two");
            string got = "keys=" + Keys(plain) + " with_log=" + Keys(with)
                       + " names_a_reporter=" + ((plain + with).IndexOf("reporter", StringComparison.OrdinalIgnoreCase) >= 0);
            Case(r, "the body names no reporter",
                 got == "keys=game_kind,game_id,reported_steam_id,reason,details"
                      + " with_log=game_kind,game_id,reported_steam_id,reason,details,log_text names_a_reporter=False", got);

            string big = BuildBody("ffa", "g-1", "S_ANN", "cheating", "", new string('a', 10) + new string('z', LogMaxChars));
            int logAt = big.Length - 2 - LogMaxChars;
            got = "log_chars=" + LastFieldChars(big, "log_text") + " first=" + big[logAt]
                + " pair=" + Ascii(Tail("a" + hi + lo + "bc", 3)) + " short=" + Tail("abc", 5) + " null=[" + Tail(null, 5) + "]";
            Case(r, "the log's tail", got == "log_chars=3500000 first=z pair=bc short=abc null=[]", got);

            var every = new StringBuilder();
            for (int c = 0; c < 128; c++) every.Append((char)c);
            string esc = JsonText(every.ToString());
            int raw = 0;
            for (int i = 1; i < esc.Length - 1; i++) if (esc[i] < 0x20 || esc[i] == 0x7F) raw++;
            got = "len=" + esc.Length + " raw_control=" + raw
                + " sample=" + JsonText("a" + Q + "b" + Bs + "c\n\r\t" + (char)0 + (char)0x1f + (char)0x7f) + " null=" + JsonText(null);
            Case(r, "every control character is escaped",
                 got == "len=285 raw_control=0 sample=" + J("'a^'b^^c^n^r^t^u0000^u001f^u007f'") + " null=" + J("''"), got);

            string split = BuildBody("ffa", "g-1", "S_ANN", "other", new string('d', DetailsMax - 1) + hi + lo + "tail", null);
            string whole = BuildBody("ffa", "g-1", "S_ANN", "other", new string('d', DetailsMax + 5), null);
            got = "pair_at_the_cut=" + LastFieldChars(split, "details") + " plain=" + LastFieldChars(whole, "details");
            Case(r, "details are cut to what the server keeps", got == "pair_at_the_cut=999 plain=1000", got);

            got = "empty=[" + SessionKey("") + "] null=[" + SessionKey(null) + "] abc=" + SessionKey("abc")
                + " differs=" + (SessionKey("abc") != SessionKey("abd"))
                + " holds_the_token=" + SessionKey("a-long-session-token-value").Contains("token");
            Case(r, "a sign-in's fingerprint", got == "empty=[] null=[] abc=e71fa2190541574b differs=True holds_the_token=False", got);
        }

        // ---- the admin's view ----------------------------------------------------------

        private static void AdminCases(SelfTestResult r)
        {
            string got = AdminCanonical("S_ADM", ActionList, TargetList) + "|" + AdminCanonical("S_ADM", ActionLog, "r-1")
                       + "|" + AdminCanonical("S_ADM", ActionClose, CloseTarget("r-1", "actioned"));
            Case(r, "what each admin request signs",
                 got == "admin:S_ADM:player_reports:list|admin:S_ADM:player_reports_log:r-1"
                      + "|admin:S_ADM:player_reports_close:r-1:actioned", got);

            got = IsVerdict("dismissed") + "," + IsVerdict("actioned") + "," + IsVerdict("open") + "," + IsVerdict("") + "," + IsVerdict(null);
            Case(r, "the two verdicts", got == "True,True,False,False,False", got);

            got = IsReportId("0f8fad5b-d9cb-469f-a165-70867728950e") + "," + IsReportId("0F8FAD5B-D9CB-469F-A165-70867728950E")
                + "," + IsReportId("0f8fad5b-d9cb-469f-a165-70867728950") + "," + IsReportId("0f8fad5bd9cb-469f-a165-70867728950e0")
                + "," + IsReportId("0f8fad5b-d9cb-469f-a165-7086772895/e") + "," + IsReportId("") + "," + IsReportId(null);
            Case(r, "a report id is the 36 characters the server writes", got == "True,False,False,False,False,False,False", got);

            got = AdminAnswerText(200, "") + "|" + AdminAnswerText(409, "already_closed") + "|" + AdminAnswerText(404, "report_not_found")
                + "|" + AdminAnswerText(404, "no_log") + "|" + AdminAnswerText(403, "") + "|" + AdminAnswerText(401, "")
                + "|" + AdminAnswerText(500, "") + "|" + AdminAnswerText(0, "") + "|" + AdminAnswerText(426, "");
            Case(r, "what the viewer says after each answer",
                 got == "|That report is already closed.|That report no longer exists.|No log is stored for this report."
                      + "|Not allowed.|Not allowed.|The request failed. Try again later.|The request failed. Try again later."
                      + "|Update the mod to use player reports.", got);

            var sb = new StringBuilder();
            foreach (int s in new[] { 401, 403, 426, 429, 503, 404, 409, 422, 500, 0 }) sb.Append(s).Append(AdminCloses(s) ? "=closes " : "=open ");
            got = sb.ToString().TrimEnd();
            Case(r, "which answers end the viewer's requests for the run",
                 got == "401=closes 403=closes 426=closes 429=closes 503=closes 404=open 409=open 422=open 500=open 0=open", got);

            var rep = new Report();
            rep.Reason = "griefing"; rep.ReporterName = "Ann"; rep.ReportedName = "<b>Bo</b>";
            got = StatusText("open") + "," + StatusText("dismissed") + "," + StatusText("actioned") + "," + StatusText("<x>")
                + "|" + VerdictQuestion("dismissed") + "|" + VerdictQuestion("actioned")
                + "|" + ReportLine(rep, "8 Nov 21:14") + "|" + ReportLine(null, "x");
            Case(r, "the admin list's texts",
                 got == "Pending,Dismissed,Actioned,(x)|Dismiss this report?|Mark this report as actioned?"
                      + "|8 Nov 21:14   Griefing or throwing   Ann reported (b)Bo(/b)|", got);

            got = "[" + CountText(0) + "][" + CountText(-1) + "][" + CountText(3) + "][" + CountText(99) + "][" + CountText(100) + "]";
            Case(r, "the open count on the launcher", got == "[][][3][99][99+]", got);

            got = "first=" + MayAskCount(true, false, false, 5f, -1000f)
                + " same_opening=" + MayAskCount(true, false, true, 500f, 5f)
                + " next_opening_at_59s=" + MayAskCount(true, false, false, 64f, 5f)
                + " next_opening_at_60s=" + MayAskCount(true, false, false, 65f, 5f)
                + " after_a_refusal=" + MayAskCount(true, true, false, 500f, 5f)
                + " not_an_admin=" + MayAskCount(false, false, false, 500f, -1000f);
            Case(r, "when the admin tab asks for the open count",
                 got == "first=True same_opening=False next_opening_at_59s=False next_opening_at_60s=True"
                      + " after_a_refusal=False not_an_admin=False", got);
        }

        // ---- the catalogues ------------------------------------------------------------

        /// <summary>Every text this lane's rules file translates and the tree
        /// did not have before (pytest holds this list against the file's own
        /// I18n.Tr literals).</summary>
        internal static readonly string[] NewKeys =
        {
            "Cheating or exploiting", "Harassment or abuse", "Griefing or throwing", "Leaving games", "Offensive name",
            "{0} (already reported)",
            "Report sent. Thank you.", "Report sent. The log could not be attached.",
            "You already reported this player for this game.", "You have reached today's limit of reports.",
            "Reports need a verified Steam sign-in.", "Player reports are turned off right now.",
            "Player reports are unavailable right now.", "That game can no longer be reported.",
            "That player was not in that game.", "The report is too large. Send it without the log.",
            "The report was not accepted.", "The report could not be sent. Try again later.",
            "Your games could not be loaded. Try again later.", "You have no recent games to report.",
            "Pending", "Dismissed", "Actioned", "Mark this report as actioned?", "Dismiss this report?", "{0} reported {1}",
            "That report is already closed.", "That report no longer exists.", "No log is stored for this report.",
            "The request failed. Try again later.", "Update the mod to use player reports.",
        };

        /// <summary>Texts the rules file uses that other lanes already translated.</summary>
        internal static readonly string[] SharedKeys =
            { "Other", "FFA", "{0} and {1} more", "Sending...", "Loading...", "Not allowed." };

        private static void CatalogueCase(SelfTestResult r)
        {
            var bad = new StringBuilder();
            int same = 0;
            foreach (string loc in Locales)
            {
                I18n.HarnessLocale = loc;
                foreach (string key in NewKeys)
                {
                    string t = I18n.Tr(key);
                    if (string.IsNullOrEmpty(t) || t.Trim().Length == 0) { bad.Append(loc).Append(" empty: ").Append(key).Append("; "); continue; }
                    if (t == key) { same++; bad.Append(loc).Append(" untranslated: ").Append(key).Append("; "); continue; }
                    for (int n = 0; n < 2; n++)
                    {
                        string slot = "{" + n + "}";
                        if (key.Contains(slot) != t.Contains(slot)) bad.Append(loc).Append(" slot ").Append(slot).Append(": ").Append(key).Append("; ");
                    }
                    if (t.IndexOf('<') >= 0 || t.IndexOf('>') >= 0) bad.Append(loc).Append(" markup: ").Append(key).Append("; ");
                }
                foreach (string key in SharedKeys)
                    if (string.IsNullOrEmpty(I18n.Tr(key))) bad.Append(loc).Append(" empty: ").Append(key).Append("; ");
            }
            I18n.HarnessLocale = "en";
            Case(r, "31 new keys in four catalogues", NewKeys.Length == 31 && bad.Length == 0,
                 bad.Length == 0 ? "keys=" + NewKeys.Length + " shared=" + SharedKeys.Length + " same_as_english=" + same
                                 : Ascii(bad.ToString().TrimEnd()));
        }
    }
}
