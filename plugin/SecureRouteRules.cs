using System;

namespace CompetitiveRounds
{
    /// <summary>
    /// Which API base a session uses while the secure default is in doubt
    /// (board row 27): the boot check, the portal button's on-demand check and
    /// the automatic retry on the plaintext backup all go through ONE probe
    /// run (Route.Run), and Classify says what each probe reading means.
    ///
    /// Why: from inside the LAN the router's hairpin to the public address
    /// answers the first connection and hangs the second (#223), so the
    /// two-attempt boot check fails on a LAN desktop. The session then stayed
    /// on the plaintext backup until the game was restarted, and the portal,
    /// which never opens over plaintext, refused every press. Now the button
    /// checks on demand and a timer checks every few minutes while on the
    /// backup; the first usable answer returns the session to the address that
    /// gave it, for every request built after that moment.
    ///
    /// Kept free of Unity, Photon, BepInEx and I18n so tools/client-rules-harness
    /// can drive it with a fake transport and a fake clock (#391). ApiClient
    /// owns the transport (UnityWebRequest), the clock (realtime seconds), the
    /// log lines and its base-url field, which it copies from CurrentBase after
    /// every conclusion; SecureRouteText owns every sentence a player reads.
    /// </summary>
    internal static partial class SecureRouteRules
    {
        internal const string ProbePath = "/api/v1/mod-version";
        internal const int ProbeTimeoutSeconds = 8;
        internal const int BootAttempts = 2;
        internal const int OnDemandAttempts = 1;
        /// <summary>Added to a run's worst case (attempts x timeout) before its
        /// claim is presumed dead. A host destroyed mid-probe stops the
        /// coroutine without running anything, so no path clears the claim
        /// (#508); expiry is the bound that covers every such way of stopping.</summary>
        internal const double ClaimSlackSeconds = 10.0;
        internal const double DefaultRetryMinutes = 5.0;
        internal const double MinRetryMinutes = 0.25;
        internal const double MaxRetryMinutes = 60.0;

        internal enum Trigger { Boot, Button, Timer }

        /// <summary>What the transport reports, reduced to the cases the rules
        /// read. NotStarted: the request never went out (no active host).</summary>
        internal enum Transport { NotStarted, Success, HttpError, ConnectionError, DataError }

        internal enum Outcome
        {
            Usable, TimedOut, Refused, NameNotFound, SecurityCheckFailed, ServerError, NotTheServer, Unreachable,
        }

        /// <summary>One probe attempt as plain values.</summary>
        internal struct Reading
        {
            public Transport Result;
            /// <summary>The engine's own name for the result, kept for the boot
            /// log line players send us (it prints result=...).</summary>
            public string ResultName;
            public long HttpCode;
            public string Error;
            /// <summary>The body carried a parseable mod-version payload.
            /// "Reachable" must mean USABLE: a captive portal answers an HTML
            /// 200 and nginx with the api down answers 502.</summary>
            public bool VersionParsed;
            public double ElapsedSeconds;
        }

        internal interface ITransport
        {
            /// <summary>Send one GET and call `done` exactly once with what it
            /// saw, possibly synchronously.</summary>
            void Get(string url, int timeoutSeconds, Action<Reading> done);
        }

        /// <summary>One attempt of a run, for the caller's log line.
        /// Current is false when the run was superseded before this attempt
        /// answered; such an attempt changes nothing.</summary>
        internal struct Attempt
        {
            public Trigger Trigger;
            public int Number;
            public int Of;
            public int Generation;
            public string Base;
            public Outcome Outcome;
            public Reading Reading;
            public bool Current;
            /// <summary>Probes begun since the session entered the backup,
            /// this one included; 0 for the boot run.</summary>
            public int AttemptsSinceFallback;
        }

        /// <summary>What a finished run decided, and what the caller must do.</summary>
        internal sealed class Conclusion
        {
            public int Generation;
            /// <summary>Superseded before it answered: nothing changed and
            /// nothing is to be shown.</summary>
            public bool Stale;
            public Trigger Trigger;
            public bool Usable;
            public Outcome Outcome;
            public long HttpCode;
            /// <summary>The address this run probed.</summary>
            public string Base;
            public string HostPort;
            public int TimeoutSeconds;
            /// <summary>The boot run failed and the session is now on the backup.</summary>
            public bool EnteredFallback;
            /// <summary>A run begun on the backup answered: the session is back
            /// on the address this run probed, for good.</summary>
            public bool Flipped;
            public int AttemptsSinceFallback;
            /// <summary>A portal press was waiting on this run and it answered.</summary>
            public bool OpenPortal;
            /// <summary>A portal press was waiting on this run and it did not answer.</summary>
            public bool ReportFailure;
        }

        internal enum Press
        {
            /// <summary>The session is on a secure base and no check is running.</summary>
            OpenNow,
            /// <summary>On the backup: a button check was begun (use the generation).</summary>
            Checking,
            /// <summary>A check is already running; the press waits for its verdict.</summary>
            Joined,
            /// <summary>Not on the backup and not on a secure base; the caller's gate refuses.</summary>
            Refused,
        }

        internal static int AttemptsFor(Trigger t) => t == Trigger.Boot ? BootAttempts : OnDemandAttempts;

        internal static double ClaimLifetimeSeconds(Trigger t) => AttemptsFor(t) * ProbeTimeoutSeconds + ClaimSlackSeconds;

        /// <summary>The retry interval from the cfg's minutes, clamped; a value
        /// that is not a finite number reads as the default.</summary>
        internal static double RetrySecondsFromMinutes(double minutes)
        {
            if (double.IsNaN(minutes) || double.IsInfinity(minutes)) minutes = DefaultRetryMinutes;
            if (minutes < MinRetryMinutes) minutes = MinRetryMinutes;
            if (minutes > MaxRetryMinutes) minutes = MaxRetryMinutes;
            return minutes * 60.0;
        }

        internal static string TrimBase(string url) => (url ?? "").Trim().TrimEnd('/');

        internal static bool IsSecure(string url)
        {
            string u = TrimBase(url);
            if (!u.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) return false;
            Uri parsed;
            return Uri.TryCreate(u, UriKind.Absolute, out parsed) && string.IsNullOrEmpty(parsed.UserInfo);
        }

        /// <summary>"host:port" for a toast or a log line; the scheme's default
        /// port when the address names none.</summary>
        internal static string HostPort(string url)
        {
            Uri parsed;
            if (!Uri.TryCreate(TrimBase(url), UriKind.Absolute, out parsed)) return TrimBase(url);
            return parsed.Host + ":" + parsed.Port;
        }

        internal static Outcome Classify(Reading r, int timeoutSeconds)
        {
            switch (r.Result)
            {
                case Transport.Success:
                    return r.VersionParsed ? Outcome.Usable : Outcome.NotTheServer;
                case Transport.HttpError:
                    return Outcome.ServerError;
                case Transport.ConnectionError:
                {
                    string e = (r.Error ?? "").ToLowerInvariant();
                    if (e.Contains("timeout") || e.Contains("timed out")) return Outcome.TimedOut;
                    if (e.Contains("resolve")) return Outcome.NameNotFound;
                    if (e.Contains("ssl") || e.Contains("tls") || e.Contains("certificate") || e.Contains("cert ")
                        || e.Contains("curl error 60") || e.Contains("curl error 35") || e.Contains("handshake"))
                        return Outcome.SecurityCheckFailed;
                    // Whatever the engine called it, a connection that used the
                    // whole timeout timed out.
                    if (timeoutSeconds > 0 && r.ElapsedSeconds >= timeoutSeconds - 0.25) return Outcome.TimedOut;
                    if (e.Contains("connect")) return Outcome.Refused;
                    return Outcome.Unreachable;
                }
                default:
                    return Outcome.Unreachable;
            }
        }

        /// <summary>The outcome in words for a LOG line (English, never shown
        /// to a player; the toast sentences live in SecureRouteText).</summary>
        internal static string Describe(Outcome o, long httpCode, int timeoutSeconds)
        {
            switch (o)
            {
                case Outcome.Usable: return "usable";
                case Outcome.TimedOut: return "timed out after " + timeoutSeconds + " s";
                case Outcome.Refused: return "refused";
                case Outcome.NameNotFound: return "name not found";
                case Outcome.SecurityCheckFailed: return "failed the security check";
                case Outcome.ServerError: return "HTTP " + httpCode;
                case Outcome.NotTheServer: return "answered, but not as the SCR server";
                default: return "could not be opened";
            }
        }

        // -- The probe's body (Codex round 1, MEDIUM 1) ------------------------

        /// <summary>Whether a probe's 200 body is a mod-version answer: ONE JSON
        /// object, whitespace allowed between tokens, every string and the
        /// object closed, nothing after it, and a member "version" (exactly
        /// once) whose string value is a release number, digits.digits.digits
        /// with an optional suffix. Anything else is not the SCR server and
        /// keeps the session where it is. The previous reading looked for the
        /// compact text "version":" anywhere, so a body with a space after the
        /// colon was refused and a body cut off inside the string was accepted,
        /// and an accepted body ends the backup for the session.
        ///
        /// A strict parser for the whole JSON grammar (nested members are
        /// walked and must be well formed too, so a later field of any shape
        /// neither breaks the check nor slips a broken body past it).</summary>
        internal static bool IsModVersionBody(string body)
        {
            if (body == null) return false;
            var p = new StrictJson(body);
            string version;
            if (!p.ReadTopObject(out version)) return false;
            p.SkipWs();
            if (!p.AtEnd) return false;
            return version != null && IsReleaseNumber(version);
        }

        /// <summary>digits.digits.digits, then optionally one of - + . and a
        /// suffix of letters, digits and - + . (for example 1.41.0, 1.41.0-beta2).</summary>
        internal static bool IsReleaseNumber(string v)
        {
            if (string.IsNullOrEmpty(v)) return false;
            int i = 0;
            for (int part = 0; part < 3; part++)
            {
                int start = i;
                while (i < v.Length && v[i] >= '0' && v[i] <= '9') i++;
                if (i == start) return false;
                if (part < 2)
                {
                    if (i >= v.Length || v[i] != '.') return false;
                    i++;
                }
            }
            if (i == v.Length) return true;
            char sep = v[i];
            if (sep != '-' && sep != '+' && sep != '.') return false;
            i++;
            if (i >= v.Length) return false;
            for (; i < v.Length; i++)
            {
                char c = v[i];
                bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                          || c == '-' || c == '+' || c == '.';
                if (!ok) return false;
            }
            return true;
        }

        /// <summary>A reader for RFC 8259 JSON that answers only "well formed or
        /// not" and, for the top-level object, the string value of "version".</summary>
        private sealed class StrictJson
        {
            private readonly string _s;
            private int _i;
            private int _depth;
            private const int MaxDepth = 32;

            internal StrictJson(string s) { _s = s; _i = 0; }

            internal bool AtEnd { get { return _i >= _s.Length; } }

            internal void SkipWs()
            {
                while (_i < _s.Length && (_s[_i] == ' ' || _s[_i] == '\t' || _s[_i] == '\n' || _s[_i] == '\r')) _i++;
            }

            /// <summary>The top level must be an object. `version` is the
            /// string value of its "version" member, or null when the member is
            /// absent, is not a string, or appears more than once.</summary>
            internal bool ReadTopObject(out string version)
            {
                version = null;
                SkipWs();
                if (_i >= _s.Length || _s[_i] != '{') return false;
                int seen = 0;
                string found = null;
                bool ok = ReadObject((key, isString, value) =>
                {
                    if (key != "version") return;
                    seen++;
                    found = isString ? value : null;
                });
                if (!ok) return false;
                version = seen == 1 ? found : null;
                return true;
            }

            private bool ReadObject(Action<string, bool, string> onTopMember)
            {
                if (++_depth > MaxDepth) return false;
                _i++;   // '{'
                SkipWs();
                if (_i < _s.Length && _s[_i] == '}') { _i++; _depth--; return true; }
                while (true)
                {
                    SkipWs();
                    string key;
                    if (!ReadString(out key)) return false;
                    SkipWs();
                    if (_i >= _s.Length || _s[_i] != ':') return false;
                    _i++;
                    SkipWs();
                    bool isString = _i < _s.Length && _s[_i] == '"';
                    string sval = null;
                    if (isString) { if (!ReadString(out sval)) return false; }
                    else if (!ReadValue()) return false;
                    if (onTopMember != null) onTopMember(key, isString, sval);
                    SkipWs();
                    if (_i >= _s.Length) return false;
                    if (_s[_i] == ',') { _i++; continue; }
                    if (_s[_i] == '}') { _i++; _depth--; return true; }
                    return false;
                }
            }

            private bool ReadArray()
            {
                if (++_depth > MaxDepth) return false;
                _i++;   // '['
                SkipWs();
                if (_i < _s.Length && _s[_i] == ']') { _i++; _depth--; return true; }
                while (true)
                {
                    SkipWs();
                    if (!ReadValue()) return false;
                    SkipWs();
                    if (_i >= _s.Length) return false;
                    if (_s[_i] == ',') { _i++; continue; }
                    if (_s[_i] == ']') { _i++; _depth--; return true; }
                    return false;
                }
            }

            private bool ReadValue()
            {
                SkipWs();
                if (_i >= _s.Length) return false;
                char c = _s[_i];
                if (c == '{') return ReadObject(null);
                if (c == '[') return ReadArray();
                if (c == '"') { string ignored; return ReadString(out ignored); }
                if (c == 't') return ReadWord("true");
                if (c == 'f') return ReadWord("false");
                if (c == 'n') return ReadWord("null");
                return ReadNumber();
            }

            private bool ReadWord(string w)
            {
                if (_i + w.Length > _s.Length || string.CompareOrdinal(_s, _i, w, 0, w.Length) != 0) return false;
                _i += w.Length;
                return true;
            }

            private bool ReadNumber()
            {
                int start = _i;
                if (_i < _s.Length && _s[_i] == '-') _i++;
                if (_i >= _s.Length) return false;
                if (_s[_i] == '0') _i++;
                else if (_s[_i] >= '1' && _s[_i] <= '9') { while (_i < _s.Length && _s[_i] >= '0' && _s[_i] <= '9') _i++; }
                else return false;
                if (_i < _s.Length && _s[_i] == '.')
                {
                    _i++;
                    int d = _i;
                    while (_i < _s.Length && _s[_i] >= '0' && _s[_i] <= '9') _i++;
                    if (_i == d) return false;
                }
                if (_i < _s.Length && (_s[_i] == 'e' || _s[_i] == 'E'))
                {
                    _i++;
                    if (_i < _s.Length && (_s[_i] == '+' || _s[_i] == '-')) _i++;
                    int d = _i;
                    while (_i < _s.Length && _s[_i] >= '0' && _s[_i] <= '9') _i++;
                    if (_i == d) return false;
                }
                return _i > start;
            }

            /// <summary>A closed string with legal escapes and no raw control
            /// character; `value` is the decoded text.</summary>
            private bool ReadString(out string value)
            {
                value = null;
                if (_i >= _s.Length || _s[_i] != '"') return false;
                _i++;
                var sb = new System.Text.StringBuilder();
                while (_i < _s.Length)
                {
                    char c = _s[_i++];
                    if (c == '"') { value = sb.ToString(); return true; }
                    if (c < 0x20) return false;
                    if (c != '\\') { sb.Append(c); continue; }
                    if (_i >= _s.Length) return false;
                    char e = _s[_i++];
                    switch (e)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'u':
                        {
                            if (_i + 4 > _s.Length) return false;
                            int code = 0;
                            for (int k = 0; k < 4; k++)
                            {
                                char h = _s[_i++];
                                int v = h >= '0' && h <= '9' ? h - '0'
                                      : h >= 'a' && h <= 'f' ? h - 'a' + 10
                                      : h >= 'A' && h <= 'F' ? h - 'A' + 10 : -1;
                                if (v < 0) return false;
                                code = code * 16 + v;
                            }
                            sb.Append((char)code);
                            break;
                        }
                        default: return false;
                    }
                }
                return false;   // end of input inside the string
            }
        }

        // -- The report outbox and the route (Codex round 1, HIGH 1) -----------

        /// <summary>The address a queued report is sent to NOW. A report is
        /// queued with the base the session used at the time; when that base is
        /// one of this route's own (the secure address, the backup, a witness
        /// lever's), the report follows the route and goes to the base the
        /// session uses at the moment of the send, in either direction. A
        /// report queued on the backup therefore goes to the secure base with
        /// the session token once the route is restored, instead of repeating
        /// an unauthenticated post the server refuses until the budget deletes
        /// it. Any other address (an explicit override from an earlier launch)
        /// is kept as it was. The caller resolves once per send and keeps the
        /// result for that send: a request already in flight keeps its URL.</summary>
        internal static string OutboxTarget(string storedUrl, string currentBase, string[] routeBases)
        {
            if (string.IsNullOrEmpty(storedUrl) || routeBases == null) return storedUrl;
            string cur = TrimBase(currentBase);
            if (cur.Length == 0) return storedUrl;
            foreach (string b in routeBases)
            {
                string t = TrimBase(b);
                if (t.Length == 0) continue;
                if (storedUrl.Length > t.Length
                    && storedUrl.StartsWith(t, StringComparison.OrdinalIgnoreCase)
                    && storedUrl[t.Length] == '/')
                    return cur + storedUrl.Substring(t.Length);
            }
            return storedUrl;
        }

        /// <summary>What the outbox does with a due report (Codex round 2,
        /// HIGH 1). WaitForSession: the send would go over a transport that
        /// carries the session token (the secure base, or a private-network or
        /// loopback address) but no fresh session is held, so nothing is sent
        /// and no attempt is spent; the entry is looked at again after
        /// OutboxSessionPollSeconds. A report is therefore sent to such an
        /// address only with the token, and an enforcing server never sees it
        /// unauthenticated there. Send: a session is held, or the transport
        /// cannot carry one anyway (the plaintext backup to a public host,
        /// where the token is withheld by rule and an unarmed server may still
        /// take the report).</summary>
        internal enum OutboxGate { Send, WaitForSession }

        internal static OutboxGate OutboxSendGate(bool transportCarriesSession, bool freshSession)
        {
            return transportCarriesSession && !freshSession ? OutboxGate.WaitForSession : OutboxGate.Send;
        }

        /// <summary>How often a report waiting for a session is looked at
        /// again. Bounded polling, never a send: the supervisor's own lap is
        /// ten seconds, so in practice this means "every lap".</summary>
        internal const double OutboxSessionPollSeconds = 5.0;

        /// <summary>What an outbox attempt's answer does to the queued report.
        /// Settle: the entry is removed as delivered. GiveBack: the attempt is
        /// returned and the entry stays queued. Spend: the attempt counts, and
        /// the drop rule (the attempt cap, a permanent refusal) is asked.</summary>
        internal enum OutboxAnswer { Settle, GiveBack, Spend }

        /// <summary>The whole outbox answer rule. Whether the request CARRIED
        /// the session token (read from the header actually stamped on it,
        /// never from its address or scheme) decides removal as well as spend,
        /// and it is asked BEFORE the answer's status (Codex round 3 HIGH 1).
        /// A request without the token was never judged on the report by an
        /// enforcing server, so its answer, a failure or a 2xx alike, neither
        /// removes the entry nor counts toward the budget that deletes one: a
        /// 2xx can come from a server that does not enforce, or from anything
        /// answering in its place on the plaintext backup, and says nothing
        /// about whether the report was recorded (#98: a retry budget must not
        /// tick while its precondition is unmet). Such an entry is delivered
        /// later by one send that carries the token; a server that did record
        /// the tokenless copy answers that send as a duplicate. Only a 2xx to a
        /// request that carried the token settles; only a failure of one
        /// spends.</summary>
        internal static OutboxAnswer OutboxAnswerFor(bool answered2xx, bool requestCarriedToken)
        {
            if (!requestCarriedToken) return OutboxAnswer.GiveBack;
            return answered2xx ? OutboxAnswer.Settle : OutboxAnswer.Spend;
        }

        /// <summary>When a given-back entry falls due again (Codex round 2
        /// LOW 1). A retry sent on the backup can still be in flight when the
        /// route is restored and the entry is promised a look within 20 s
        /// (`restoreDue`, negative when no promise stands); its 401 then arrives
        /// after the flip, and overwriting the due time with the capped
        /// interval cancelled that promise for four minutes. The give-back
        /// takes the EARLIER of the two, so it never moves the entry later
        /// than the restoration promised.</summary>
        internal static double OutboxGiveBackDue(double proposed, double restoreDue)
        {
            return restoreDue >= 0 && restoreDue < proposed ? restoreDue : proposed;
        }

        /// <summary>Whether a 401 body is the server refusing the session the
        /// request carried. Two routes word it differently: the enforced
        /// writes answer "session_required", the portal mint answers "steam
        /// session required".</summary>
        internal static bool IsSessionRefusal(string body)
        {
            if (string.IsNullOrEmpty(body)) return false;
            return body.IndexOf("session_required", StringComparison.Ordinal) >= 0
                || body.IndexOf("steam session required", StringComparison.Ordinal) >= 0;
        }

        // -- The portal press (Codex round 1, LOW 1 and LOW 2) -----------------

        /// <summary>The Steam session exchange's own request timeout
        /// (PostSteamAuth passes it to its POST). A session that the exchange
        /// lands can arrive up to this long after the ticket goes out.</summary>
        internal const int SteamAuthExchangeTimeoutSeconds = 20;

        /// <summary>Slack over the exchange's timeout for the poll interval and
        /// the frame between the ticket callback and the exchange's POST.</summary>
        internal const float SessionWaitMarginSeconds = 5f;

        /// <summary>The base of a portal press's wait for a session (Codex
        /// round 2 LOW 2): derived from the exchange's own timeout. Both waits
        /// (the press after a restore and the re-mint after a refused session)
        /// read it through KeepWaitingForSession, which extends it while a
        /// sign-in the wait depends on is still inside its own bounds.</summary>
        internal const float PortalSessionWaitSeconds = SteamAuthExchangeTimeoutSeconds + SessionWaitMarginSeconds;

        /// <summary>Whether a portal readiness wait begun at `started` keeps
        /// polling at `now` (Codex round 3 LOW 1). Never once the session is
        /// ready. Otherwise for PortalSessionWaitSeconds, and past that for as
        /// long as a Steam ticket requested inside that window is still inside
        /// its own bounds (TicketLatch.ExchangeRunning): its asynchronous
        /// callback within TicketCallbackBoundSeconds of the request, then its
        /// exchange within the exchange's timeout plus the margin of the
        /// callback. The deadline used to start before the ticket was even
        /// requested while the exchange's 20 s started only at the callback, so
        /// a callback at 6 s plus a valid 19 s exchange landed after the wait
        /// had minted without the session. Composed bound: a ticket requested
        /// at the press is waited for until at most 25 + 25 = 50 s after it,
        /// and no wait outlives PortalSessionWaitSeconds +
        /// TicketCallbackBoundSeconds + SteamAuthExchangeTimeoutSeconds +
        /// SessionWaitMarginSeconds = 75 s (a ticket requested at the very end
        /// of the base window). `latch` null reads as no ticket.</summary>
        internal static bool KeepWaitingForSession(double started, double now, bool ready, TicketLatch latch)
        {
            if (ready) return false;
            if (now - started < PortalSessionWaitSeconds) return true;
            return latch != null && latch.ExchangeRunning(now, started + PortalSessionWaitSeconds);
        }

        // -- The one-ticket latch (board row 27 round 2; Codex round 2 LOW 5) --

        /// <summary>How long a held ticket may wait for its exchange's end
        /// before it is abandoned (cancelled) on a refresh tick: past the
        /// exchange's own timeout plus the ticket callback, so only a ticket
        /// whose end never arrived is abandoned.</summary>
        internal const double TicketAbandonSeconds = SteamAuthExchangeTimeoutSeconds + 25;

        /// <summary>The bound on Steam's asynchronous ticket callback: the
        /// part of TicketAbandonSeconds that is not the exchange's timeout, so
        /// a callback inside it leaves the exchange its whole timeout before
        /// the ticket could be abandoned. A portal wait does not wait for an
        /// outstanding callback past it.</summary>
        internal const double TicketCallbackBoundSeconds = TicketAbandonSeconds - SteamAuthExchangeTimeoutSeconds;

        internal enum TicketState { Free, Held, CancelFailed }

        /// <summary>
        /// One Steam web-API ticket at a time. A ticket is held from its request
        /// until its exchange ends, and the latch is released only AFTER the
        /// ticket's cancel returns. A cancel that throws keeps the handle
        /// held-but-failed (CancelFailed); the next refresh tick retries the
        /// cancel once, and then the handle is retired either way, with a log
        /// line. No successor ticket may be requested while a handle is held or
        /// unretired (MayRequest). SteamAuth owns the handle and passes the
        /// cancel in: it returns false when there is no handle to cancel and
        /// throws when the cancel fails.
        /// </summary>
        internal sealed class TicketLatch
        {
            internal TicketState State { get; private set; } = TicketState.Free;
            internal int Serial { get; private set; }
            internal double Since { get; private set; } = -999;

            internal bool MayRequest => State == TicketState.Free;
            internal bool IsHeld => State == TicketState.Held;

            /// <summary>When the held ticket's callback arrived; negative until
            /// it has.</summary>
            internal double CallbackAt { get; private set; } = -1;

            /// <summary>A ticket was requested (after the request returned).</summary>
            internal int Took(double now)
            {
                State = TicketState.Held;
                Serial++;
                Since = now;
                CallbackAt = -1;
                return Serial;
            }

            /// <summary>The held ticket's callback arrived and its exchange is
            /// about to be posted. Only the held serial's first callback counts.</summary>
            internal void CallbackArrived(int serial, double now)
            {
                if (State == TicketState.Held && serial == Serial && CallbackAt < 0) CallbackAt = now;
            }

            /// <summary>Whether a sign-in a portal wait depends on is still inside
            /// its own bounds at `now` (Codex round 3 LOW 1): a ticket is held
            /// that was requested no later than `requestedBy`, and either its
            /// callback is outstanding within TicketCallbackBoundSeconds of the
            /// request, or its exchange started at the callback and is within
            /// the exchange's timeout plus SessionWaitMarginSeconds.</summary>
            internal bool ExchangeRunning(double now, double requestedBy)
            {
                if (State != TicketState.Held || Since > requestedBy) return false;
                if (CallbackAt < 0) return now - Since < TicketCallbackBoundSeconds;
                return now - CallbackAt < SteamAuthExchangeTimeoutSeconds + SessionWaitMarginSeconds;
            }

            /// <summary>The held ticket's exchange ended (`outcome` names how).
            /// Cancels first; Free only once the cancel has returned. A serial
            /// that is not the held ticket's, or a handle already failed,
            /// changes nothing (null). The line to log is returned; `failed`
            /// says it is a warning.</summary>
            internal string End(int serial, string outcome, Func<bool> cancel, out bool failed)
            {
                failed = false;
                if (State != TicketState.Held || serial != Serial) return null;
                bool had;
                try { had = cancel(); }
                catch (Exception ex)
                {
                    State = TicketState.CancelFailed;
                    failed = true;
                    return "[STEAM-AUTH] ticket " + Serial + " ended (" + outcome + "); cancel failed: " + ex.Message
                         + "; kept held, the cancel is retried once on the next refresh tick";
                }
                State = TicketState.Free;
                return "[STEAM-AUTH] ticket " + Serial + " ended (" + outcome + "); "
                     + (had ? "cancelled with Steam" : "no ticket handle to cancel");
            }

            /// <summary>Run at the top of every refresh tick, before the request
            /// gate. A failed cancel is retried exactly once and the handle is
            /// then retired either way; a held ticket past TicketAbandonSeconds
            /// is ended as abandoned (which cancels it).</summary>
            internal string Tick(double now, Func<bool> cancel, out bool failed)
            {
                failed = false;
                if (State == TicketState.CancelFailed)
                {
                    try { cancel(); }
                    catch (Exception ex)
                    {
                        State = TicketState.Free;   // retired: one retry, never a third attempt
                        failed = true;
                        return "[STEAM-AUTH] ticket " + Serial + " retired uncancelled: the retry failed too (" + ex.Message + ")";
                    }
                    State = TicketState.Free;
                    return "[STEAM-AUTH] ticket " + Serial + " cancelled with Steam on the retry";
                }
                if (State == TicketState.Held && now - Since > TicketAbandonSeconds)
                    return End(Serial, "abandoned after " + (int)TicketAbandonSeconds + " s", cancel, out failed);
                return null;
            }
        }

        internal enum PressAction
        {
            /// <summary>A check was begun or joined: show "Checking...".</summary>
            ShowChecking,
            /// <summary>No route and a plaintext base: name the address.</summary>
            RefusePlaintext,
            /// <summary>Wait (bounded) for a known identity and a fresh session, then mint.</summary>
            WaitThenMint,
            MintNow,
        }

        /// <summary>What a Translate press does. `routePress` is the route's
        /// answer, or null with no route. The identity is asked LAST: the
        /// check and the plaintext refusal need none, and a press during the
        /// startup identity race must still start the check or show the
        /// refusal (LOW 2). After a restore, or before the identity is known,
        /// the press waits for both before it mints.</summary>
        internal static PressAction PortalPressAction(Press? routePress, bool baseIsHttps, bool restored, bool identityKnown)
        {
            if (routePress == Press.Checking || routePress == Press.Joined) return PressAction.ShowChecking;
            if (!baseIsHttps) return PressAction.RefusePlaintext;
            if (restored || !identityKnown) return PressAction.WaitThenMint;
            return PressAction.MintNow;
        }

        /// <summary>The one log line a portal press refused for a plaintext
        /// base writes (Codex round 2 LOW 3): the base as scheme://host:port
        /// (CredentialFreeBase) and the reason. The address may carry user
        /// info, a path or a query; none of them reaches the log.</summary>
        internal static string PlaintextRefusalLine(string baseUrl)
        {
            return "[SCR] portal button: not opened; the server address " + CredentialFreeBase(baseUrl)
                 + " is plaintext, and the portal token is only sent over https";
        }

        /// <summary>An address reduced to scheme://host:port: no user info,
        /// path, query or fragment. An address that does not parse is not
        /// echoed at all.</summary>
        internal static string CredentialFreeBase(string url)
        {
            Uri parsed;
            if (!Uri.TryCreate(TrimBase(url), UriKind.Absolute, out parsed)) return "(an address that does not parse)";
            return parsed.Scheme + "://" + parsed.Host + ":" + parsed.Port;
        }

        /// <summary>The declared bound on the portal mint's failure line, the
        /// whole line (Codex round 2 LOW 4).</summary>
        internal const int MintFailureLineMax = 240;

        /// <summary>The one log line a failed portal mint writes: the base as
        /// scheme://host:port, the failure's own answer (never a token: a
        /// success without one is named, not printed), and whether this was
        /// the mint after the one re-mint. Built whole, then CR/LF become
        /// spaces, then LogScrub.RedactCredentials runs over it, and only
        /// then is it cut to MintFailureLineMax including the "..." marker,
        /// so a cut can never split a credential out of the scrub's
        /// sight.</summary>
        internal static string PortalMintFailureLine(string portalBase, bool success, string response, bool afterRemint)
        {
            string why = success ? "answered without a token"
                       : string.IsNullOrEmpty(response) ? "no answer" : response.Trim();
            string tail = afterRemint ? " (after the one re-mint)" : "";
            string line = "[I18N] portal mint failed over " + CredentialFreeBase(portalBase) + ": " + why;
            line = line.Replace("\r", " ").Replace("\n", " ");
            line = LogScrub.RedactCredentials(line);
            // The fixed tail survives the cut; the answer is what is shortened.
            return line.Length + tail.Length <= MintFailureLineMax
                ? line + tail
                : line.Substring(0, MintFailureLineMax - 3 - tail.Length) + "..." + tail;
        }

        internal enum MintAction { Open, RemintOnce, Fail }

        /// <summary>What the portal mint's answer means. A token opens the
        /// portal. A 401 refusing the session the request carried re-mints
        /// ONCE when the press may (the first mint of a press), so a token the
        /// server has dropped costs no second press (LOW 1); anything else,
        /// and a second refusal, is reported.</summary>
        internal static MintAction PortalMintAction(bool success, string token, string response, bool mayRemint)
        {
            if (success && !string.IsNullOrEmpty(token)) return MintAction.Open;
            if (!success && mayRemint && response != null
                && response.StartsWith("HTTP 401", StringComparison.Ordinal) && IsSessionRefusal(response))
                return MintAction.RemintOnce;
            return MintAction.Fail;
        }

        /// <summary>The local witness harness's stand-in for the secure route:
        /// plaintext to loopback only (127.0.0.1 or localhost), no user info.
        /// A Route accepts it only when built for that harness.</summary>
        internal static bool IsLoopbackPlaintext(string url)
        {
            string u = TrimBase(url);
            if (!u.StartsWith("http://", StringComparison.OrdinalIgnoreCase)) return false;
            Uri parsed;
            if (!Uri.TryCreate(u, UriKind.Absolute, out parsed) || !string.IsNullOrEmpty(parsed.UserInfo)) return false;
            return parsed.Host == "127.0.0.1" || string.Equals(parsed.Host, "localhost", StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>
        /// One session's route state. ApiClient builds one per Initialize, and
        /// only for the compiled secure default: an explicit BaseUrl override
        /// gets no Route, so no probe, no backup and no timer ever run for it.
        ///
        /// The probe claim (#508) is a generation, an owner (the host's
        /// instance id) and a time bound. A run whose host died is simply never
        /// heard from again; the next Begin after its lifetime (or from a new
        /// host) takes a fresh generation, and anything the old run might
        /// still report is dropped by the generation check.
        /// </summary>
        internal sealed class Route
        {
            /// <param name="acceptLoopbackPlaintext">The local witness harness
            /// only (ApiClient passes true on the broadcast identity with the
            /// TestBackupUrl lever set): a check may also probe a plaintext
            /// loopback address, which stands in for the secure route there.
            /// False for every player, so every check probes https only.</param>
            internal Route(string configuredBase, string fallbackBase, bool acceptLoopbackPlaintext = false)
            {
                CurrentBase = TrimBase(configuredBase);
                _configuredBase = CurrentBase;
                FallbackBase = TrimBase(fallbackBase);
                NextAutoAt = double.MaxValue;
                AcceptsLoopbackPlaintext = acceptLoopbackPlaintext;
            }

            private readonly string _configuredBase;

            internal bool AcceptsLoopbackPlaintext { get; }

            /// <summary>An address a check may probe: https, or (harness
            /// routes only) plaintext loopback.</summary>
            internal bool Probeable(string url)
            {
                return IsSecure(url) || (AcceptsLoopbackPlaintext && IsLoopbackPlaintext(url));
            }

            /// <summary>The bases a queued report may have been queued under on
            /// this route (OutboxTarget): the configured one, the backup, the
            /// current one and the address the last check probed.</summary>
            internal string[] Bases(string probeBase)
            {
                return new[] { _configuredBase, FallbackBase, CurrentBase, TrimBase(probeBase) };
            }

            /// <summary>The base every request built from now on uses.</summary>
            internal string CurrentBase { get; private set; }
            internal string FallbackBase { get; }
            internal bool OnFallback { get; private set; }
            /// <summary>Back on a secure base after the backup. Terminal for
            /// this Route: no timer and no button check runs again.</summary>
            internal bool Restored { get; private set; }
            internal int AttemptsSinceFallback { get; private set; }
            /// <summary>Realtime second at which the timer's next check is due
            /// (MaxValue when no check is scheduled).</summary>
            internal double NextAutoAt { get; private set; }
            internal bool PortalWaiting { get; private set; }
            internal int Generation => _gen;

            private bool _claimed;
            private int _gen;
            private int _owner;
            private double _claimedAt;
            private Trigger _claimTrigger;
            private string _claimBase = "";
            private bool _bootBegun;

            /// <summary>A run is in flight on this host and inside its lifetime.</summary>
            internal bool ProbeLive(double now, int owner)
            {
                return _claimed && owner == _owner && now - _claimedAt <= ClaimLifetimeSeconds(_claimTrigger);
            }

            /// <summary>The timer's question, asked on a tick: only on the
            /// backup, never beside a live run, never before the next mark.</summary>
            internal bool AutoDue(double now, int owner)
            {
                return OnFallback && !Restored && !ProbeLive(now, owner) && now >= NextAutoAt;
            }

            /// <summary>Claim a run. Returns its generation, or 0 when refused:
            /// a live run exists, the address is not a secure one, the boot run
            /// already began, or (Button, Timer) the session is not on the
            /// backup. A Button or Timer begin moves the next timer mark to
            /// now + the interval, so the checks are an interval apart whoever
            /// started them.</summary>
            internal int Begin(Trigger trigger, string probeBase, double now, int owner, double retrySeconds)
            {
                if (!Probeable(probeBase)) return 0;
                if (ProbeLive(now, owner)) return 0;
                if (trigger == Trigger.Boot)
                {
                    if (_bootBegun || OnFallback || Restored) return 0;
                    _bootBegun = true;
                }
                else if (!OnFallback || Restored) return 0;
                // A press waiting on a run that died is abandoned with it; a
                // verdict minutes later from some other run is not its answer.
                if (_claimed) PortalWaiting = false;
                _claimed = true;
                _gen++;
                _owner = owner;
                _claimedAt = now;
                _claimTrigger = trigger;
                _claimBase = TrimBase(probeBase);
                if (trigger != Trigger.Boot)
                {
                    AttemptsSinceFallback++;
                    NextAutoAt = now + retrySeconds;
                }
                return _gen;
            }

            /// <summary>The portal button. Joins a live run rather than
            /// starting a second one; on the backup with none running it begins
            /// a Button run (the caller then Runs `generation`).</summary>
            internal Press PressPortal(string probeBase, double now, int owner, double retrySeconds, out int generation)
            {
                generation = 0;
                if (ProbeLive(now, owner))
                {
                    PortalWaiting = true;
                    return Press.Joined;
                }
                if (!OnFallback) return IsSecure(CurrentBase) ? Press.OpenNow : Press.Refused;
                generation = Begin(Trigger.Button, probeBase, now, owner, retrySeconds);
                if (generation == 0) return Press.Refused;
                PortalWaiting = true;
                return Press.Checking;
            }

            /// <summary>Record a run's verdict. Only the current generation
            /// changes anything. The session only ever moves to an address a
            /// run has just shown usable, or (boot failure) to the backup.</summary>
            internal Conclusion Conclude(int generation, Outcome outcome, long httpCode, double now, double retrySeconds)
            {
                var c = new Conclusion
                {
                    Generation = generation, Outcome = outcome, HttpCode = httpCode, TimeoutSeconds = ProbeTimeoutSeconds,
                };
                if (!_claimed || generation != _gen)
                {
                    c.Stale = true;
                    return c;
                }
                _claimed = false;
                c.Trigger = _claimTrigger;
                c.Base = _claimBase;
                c.HostPort = HostPort(_claimBase);
                c.Usable = outcome == Outcome.Usable;
                if (_claimTrigger == Trigger.Boot)
                {
                    if (c.Usable) CurrentBase = _claimBase;
                    else
                    {
                        OnFallback = true;
                        CurrentBase = FallbackBase;
                        AttemptsSinceFallback = 0;
                        NextAutoAt = now + retrySeconds;
                        c.EnteredFallback = true;
                    }
                }
                else if (c.Usable && OnFallback)
                {
                    OnFallback = false;
                    Restored = true;
                    CurrentBase = _claimBase;
                    NextAutoAt = double.MaxValue;
                    c.Flipped = true;
                }
                c.AttemptsSinceFallback = AttemptsSinceFallback;
                if (PortalWaiting)
                {
                    PortalWaiting = false;
                    c.OpenPortal = c.Usable;
                    c.ReportFailure = !c.Usable;
                }
                return c;
            }

            /// <summary>Drive the claimed run: its attempts one after another
            /// through `transport`, each reported to `onAttempt`, the verdict to
            /// `onDone`. Every attempt of every trigger probes the same path
            /// with the same timeout and the same usability rule. A run that is
            /// superseded mid-way reports the late attempt as not Current and
            /// stops; its verdict is never delivered.</summary>
            internal void Run(int generation, ITransport transport, Func<double> clock, Func<double> retrySeconds,
                              Action<Attempt> onAttempt, Action<Conclusion> onDone)
            {
                if (transport == null || clock == null || generation == 0 || generation != _gen || !_claimed) return;
                Step(1, AttemptsFor(_claimTrigger), generation, _claimTrigger, _claimBase,
                     transport, clock, retrySeconds, onAttempt, onDone);
            }

            private void Step(int number, int of, int generation, Trigger trigger, string probeBase,
                              ITransport transport, Func<double> clock, Func<double> retrySeconds,
                              Action<Attempt> onAttempt, Action<Conclusion> onDone)
            {
                transport.Get(probeBase + ProbePath, ProbeTimeoutSeconds, reading =>
                {
                    Outcome outcome = Classify(reading, ProbeTimeoutSeconds);
                    bool current = _claimed && generation == _gen;
                    if (onAttempt != null)
                        onAttempt(new Attempt
                        {
                            Trigger = trigger, Number = number, Of = of, Generation = generation, Base = probeBase,
                            Outcome = outcome, Reading = reading, Current = current,
                            AttemptsSinceFallback = trigger == Trigger.Boot ? 0 : AttemptsSinceFallback,
                        });
                    if (!current) return;
                    if (outcome == Outcome.Usable || number >= of)
                    {
                        double retry = retrySeconds != null ? retrySeconds() : RetrySecondsFromMinutes(DefaultRetryMinutes);
                        var c = Conclude(generation, outcome, reading.HttpCode, clock(), retry);
                        if (onDone != null) onDone(c);
                        return;
                    }
                    Step(number + 1, of, generation, trigger, probeBase, transport, clock, retrySeconds, onAttempt, onDone);
                });
            }
        }
    }
}
