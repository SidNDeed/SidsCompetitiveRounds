using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The harness's half of SecureRouteRules (board row 27). It lives HERE,
    /// under tools/, so the shipped DLL carries no fixture: the plugin build
    /// compiles the rules half of this partial class, the harness compiles
    /// both, plus plugin/SecureRouteText.cs and plugin/I18nCatalogues.cs
    /// against the stand-in I18n beside this file. Every sentence checked below
    /// is therefore the one the shipped code produces, and the L cases look it
    /// up in the shipped catalogues.
    ///
    /// The clock and the transport are fakes: time moves only when a case
    /// moves it, and a held probe answers only when a case releases it. The
    /// timer is driven exactly as ApiClient.SecureRouteTick drives it: once a
    /// second, only while on the backup, AutoDue then Begin(Timer).
    ///
    /// Each decision has a case AND a control that moves only the input
    /// deciding it (#391); the control's name says "control".
    /// </summary>
    internal static partial class SecureRouteRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private const string TSecure = "https://competitive-rounds.duckdns.org:8444";
        private const string TBackup = "http://competitive-rounds.duckdns.org:8443";
        private const string THostPort = "competitive-rounds.duckdns.org:8444";
        private const string TLanOverride = "http://192.168.72.102:8443";
        private const int TOwner = 7;
        private const double TRetry = 300.0;

        /// <summary>A transport that records every GET and answers either at
        /// once (AutoAnswer) or when a case releases it, oldest first.</summary>
        private sealed class FakeTransport : ITransport
        {
            internal readonly List<string> Urls = new List<string>();
            internal readonly List<int> Timeouts = new List<int>();
            private readonly Queue<Action<Reading>> _held = new Queue<Action<Reading>>();
            internal bool AutoAnswer;
            internal Reading AutoReading;

            public void Get(string url, int timeoutSeconds, Action<Reading> done)
            {
                Urls.Add(url);
                Timeouts.Add(timeoutSeconds);
                if (AutoAnswer) { done(AutoReading); return; }
                _held.Enqueue(done);
            }

            internal int Held { get { return _held.Count; } }

            internal void Release(Reading r)
            {
                _held.Dequeue()(r);
            }
        }

        private sealed class FakeClock
        {
            internal double Now;
            internal double Read() { return Now; }
        }

        private sealed class RunLog
        {
            internal readonly List<Attempt> Attempts = new List<Attempt>();
            internal readonly List<Conclusion> Done = new List<Conclusion>();
            internal Conclusion Last { get { return Done.Count == 0 ? null : Done[Done.Count - 1]; } }
        }

        private static Reading ROk()
        {
            return new Reading { Result = Transport.Success, ResultName = "Success", HttpCode = 200, VersionParsed = true, ElapsedSeconds = 0.2 };
        }

        private static Reading RTimeout()
        {
            return new Reading { Result = Transport.ConnectionError, ResultName = "ConnectionError", Error = "Request timeout", ElapsedSeconds = 8.0 };
        }

        private static Reading RRefused()
        {
            return new Reading { Result = Transport.ConnectionError, ResultName = "ConnectionError", Error = "Cannot connect to destination host", ElapsedSeconds = 0.1 };
        }

        private static void Drive(Route route, int gen, FakeTransport t, FakeClock clock, RunLog log, double retry)
        {
            route.Run(gen, t, clock.Read, () => retry, a => log.Attempts.Add(a), c => log.Done.Add(c));
        }

        /// <summary>A route whose boot check failed at clock.Now: both
        /// attempts timed out, so the session is on the backup.</summary>
        private static Route BackupRoute(FakeClock clock, double retry)
        {
            var route = new Route(TSecure, TBackup);
            var t = new FakeTransport { AutoAnswer = true, AutoReading = RTimeout() };
            int g = route.Begin(Trigger.Boot, TSecure, clock.Now, TOwner, retry);
            Drive(route, g, t, clock, new RunLog(), retry);
            return route;
        }

        /// <summary>ApiClient.SecureRouteTick, once per fake second from
        /// `from` to `to` inclusive. Returns the seconds a check began.</summary>
        private static List<double> TickTimer(Route route, FakeClock clock, FakeTransport t, double from, double to,
                                              double retry, RunLog log)
        {
            var begun = new List<double>();
            for (double s = from; s <= to; s += 1.0)
            {
                clock.Now = s;
                if (!route.OnFallback || !route.AutoDue(s, TOwner)) continue;
                int g = route.Begin(Trigger.Timer, TSecure, s, TOwner, retry);
                if (g == 0) continue;
                begun.Add(s);
                Drive(route, g, t, clock, log, retry);
            }
            return begun;
        }

        /// <summary>The harness's stand-in for ApiClient.CredentialedTransportAllowed
        /// on the addresses these cases use: the secure address carries the
        /// token, the public plaintext backup does not.</summary>
        private static bool OutboxModelCarries(string url)
        {
            return url.StartsWith("https://", StringComparison.OrdinalIgnoreCase);
        }

        private sealed class OutboxRun
        {
            internal int SecureSendsBeforeSession, SecureSendsAfterSession, CarriedSends, TokenlessSecureSends, Settled;
            internal int Rows, RowsAtRestore, TokenlessOkAnswers, TokenlessOkBeforeRestore, SettledTokenless;
            internal int AttemptsAtSession = -1;
            internal bool QueuedAtSession, QueuedAtEnd, QueuedAtRestore, Dropped;
            internal readonly List<string> Events = new List<string>();
            internal string Describe()
            {
                return "secureBefore=" + SecureSendsBeforeSession + " secureAfter=" + SecureSendsAfterSession
                       + " carried=" + CarriedSends + " tokenlessSecure=" + TokenlessSecureSends
                       + " attemptsAtSession=" + AttemptsAtSession + " queuedAtSession=" + QueuedAtSession
                       + " settled=" + Settled + " settledTokenless=" + SettledTokenless + " rows=" + Rows
                       + " tokenless2xx=" + TokenlessOkAnswers + " (before restore " + TokenlessOkBeforeRestore + ")"
                       + " queuedAtRestore=" + QueuedAtRestore + " rowsAtRestore=" + RowsAtRestore
                       + " queuedAtEnd=" + QueuedAtEnd + " dropped=" + Dropped
                       + " | " + string.Join("; ", Events.ToArray());
            }
        }

        /// <summary>What the sink answers a request that did NOT carry the
        /// session token. Enforcing: 401 session_required (a request with the
        /// token is answered 200 and records its row). Tokenless200: 200
        /// WITHOUT recording a row (Codex round 3 HIGH 1's falsifier: a server
        /// that does not enforce, or anything answering in its place on the
        /// plaintext backup).</summary>
        private enum Sink { Enforcing, Tokenless200 }

        /// <summary>ApiClient.OutboxPass over one queued report, a lap every
        /// ten fake seconds for thirty minutes: resolve the address
        /// (OutboxTarget), ask the gate (OutboxSendGate) with the session as
        /// it is at that lap, send, and ask the answer rule (OutboxAnswerFor)
        /// with the answer's status AND what the request CARRIED. The sink
        /// answers a request with the token 200 and records one row; a
        /// tokenless one per `sink`. Settlement is what the RULE decides (the
        /// entry removed), and rows are what the sink recorded, counted apart,
        /// so a removal without a row shows. The route starts on the backup and
        /// is restored at 300 s (as OnSecureRouteRestored does, the entry falls
        /// due within 20 s); the session lands `sessionAfterRestore` seconds
        /// after that. `dropBeforeStamp`: the first send after the session
        /// lands goes out without the token although the gate saw it.</summary>
        private static OutboxRun OutboxComposition(int seededAttempts, double sessionAfterRestore, bool dropBeforeStamp)
        {
            return OutboxComposition(seededAttempts, sessionAfterRestore, dropBeforeStamp, Sink.Enforcing);
        }

        private static OutboxRun OutboxComposition(int seededAttempts, double sessionAfterRestore, bool dropBeforeStamp, Sink sink)
        {
            const string path = "/api/v1/matches";
            const double restoreAt = 300.0;
            var run = new OutboxRun();
            var clock = new FakeClock();
            var rt = BackupRoute(clock, TRetry);
            string url = rt.CurrentBase + path;
            int attempts = seededAttempts;
            double nextAt = 30.0;
            bool queued = true, restored = false, dropUsed = false;
            double sessionAt = restoreAt + sessionAfterRestore;
            for (double now = 0; now <= 1800.0 && queued; now += 10.0)
            {
                if (!restored && now >= restoreAt)
                {
                    var tt = new FakeTransport { AutoAnswer = true, AutoReading = ROk() };
                    TickTimer(rt, clock, tt, now, now, TRetry, new RunLog());
                    restored = rt.Restored;
                    if (nextAt > now + 20.0) nextAt = now + 20.0;
                    run.QueuedAtRestore = queued;
                    run.RowsAtRestore = run.Rows;
                    run.Events.Add("restored@" + now);
                }
                bool session = now >= sessionAt && restored;
                if (session && run.AttemptsAtSession < 0)
                {
                    run.AttemptsAtSession = attempts;
                    run.QueuedAtSession = queued;
                }
                if (now < nextAt) continue;
                string target = OutboxTarget(url, rt.CurrentBase, rt.Bases(TSecure));
                url = target;
                bool transport = OutboxModelCarries(target);
                if (OutboxSendGate(transport, session) == OutboxGate.WaitForSession)
                {
                    nextAt = now + OutboxSessionPollSeconds;
                    continue;
                }
                attempts++;
                nextAt = now + 60.0 * Math.Min(4.0, attempts);
                bool carried = transport && session;
                if (carried && dropBeforeStamp && !dropUsed) { carried = false; dropUsed = true; }
                if (transport)
                {
                    if (session) run.SecureSendsAfterSession++; else run.SecureSendsBeforeSession++;
                    if (!carried) run.TokenlessSecureSends++;
                }
                if (carried) run.CarriedSends++;
                bool ok = carried || sink == Sink.Tokenless200;
                if (ok && carried) run.Rows++;
                if (ok && !carried)
                {
                    run.TokenlessOkAnswers++;
                    if (!restored) run.TokenlessOkBeforeRestore++;
                }
                var answer = OutboxAnswerFor(ok, carried);
                if (answer == OutboxAnswer.Settle)
                {
                    run.Settled++;
                    if (!carried) run.SettledTokenless++;
                    queued = false;
                    run.Events.Add("settled@" + now + (carried ? " with the token" : " WITHOUT the token"));
                    break;
                }
                if (answer == OutboxAnswer.GiveBack)
                {
                    attempts--;
                    nextAt = now + 60.0 * 4.0;
                    continue;
                }
                if (attempts >= 94)
                {
                    queued = false;
                    run.Dropped = true;
                    run.Events.Add("dropped@" + now + " attempt " + attempts);
                }
            }
            if (run.AttemptsAtSession < 0) { run.AttemptsAtSession = attempts; run.QueuedAtSession = queued; }
            run.QueuedAtEnd = queued;
            return run;
        }

        private static string Times(List<double> ts)
        {
            var parts = new List<string>();
            foreach (double d in ts) parts.Add(d.ToString("0.##", CultureInfo.InvariantCulture));
            return parts.Count == 0 ? "(none)" : string.Join(",", parts);
        }

        private static string Show(Route route, Conclusion c)
        {
            string s = "base=" + route.CurrentBase + " onBackup=" + route.OnFallback + " restored=" + route.Restored
                       + " next=" + (route.NextAutoAt == double.MaxValue ? "none" : route.NextAutoAt.ToString("0.##", CultureInfo.InvariantCulture));
            if (c != null)
                s += " | stale=" + c.Stale + " usable=" + c.Usable + " outcome=" + c.Outcome + " flipped=" + c.Flipped
                     + " open=" + c.OpenPortal + " report=" + c.ReportFailure + " n=" + c.AttemptsSinceFallback;
            return s;
        }

        private static List<KeyValuePair<string, string>> Sentences()
        {
            var l = new List<KeyValuePair<string, string>>();
            l.Add(new KeyValuePair<string, string>("checking", SecureRouteText.Checking()));
            l.Add(new KeyValuePair<string, string>("restored", SecureRouteText.RestoredOpeningPortal()));
            l.Add(new KeyValuePair<string, string>("plaintext", SecureRouteText.PlaintextOverride(TLanOverride)));
            foreach (Outcome o in Enum.GetValues(typeof(Outcome)))
                if (o != Outcome.Usable)
                    l.Add(new KeyValuePair<string, string>(o.ToString(), SecureRouteText.Failure(o, THostPort, ProbeTimeoutSeconds, 502)));
            return l;
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // -- C: what one probe reading means --------------------------------
            {
                var ok = ROk();
                Check(r, "C1 a 200 carrying a mod-version payload is usable",
                      Classify(ok, 8) == Outcome.Usable, Classify(ok, 8).ToString());
                var html = ROk();
                html.VersionParsed = false;
                Check(r, "C1c control: the same 200 without the payload is not the SCR server",
                      Classify(html, 8) == Outcome.NotTheServer, Classify(html, 8).ToString());
                var e502 = new Reading { Result = Transport.HttpError, ResultName = "ProtocolError", HttpCode = 502, ElapsedSeconds = 0.1 };
                Check(r, "C2 an HTTP error status is a server error",
                      Classify(e502, 8) == Outcome.ServerError, Classify(e502, 8).ToString());
                Check(r, "C3 an engine timeout reads as timed out",
                      Classify(RTimeout(), 8) == Outcome.TimedOut, Classify(RTimeout(), 8).ToString());
                var dns = new Reading { Result = Transport.ConnectionError, Error = "Cannot resolve destination host", ElapsedSeconds = 0.05 };
                Check(r, "C4 a failed name lookup reads as name not found",
                      Classify(dns, 8) == Outcome.NameNotFound, Classify(dns, 8).ToString());
                var tls = new Reading { Result = Transport.ConnectionError, Error = "Unable to complete SSL connection", ElapsedSeconds = 0.3 };
                Check(r, "C5 a TLS failure reads as a failed security check",
                      Classify(tls, 8) == Outcome.SecurityCheckFailed, Classify(tls, 8).ToString());
                Check(r, "C6 a fast connect failure reads as refused",
                      Classify(RRefused(), 8) == Outcome.Refused, Classify(RRefused(), 8).ToString());
                var slow = RRefused();
                slow.ElapsedSeconds = 8.0;
                Check(r, "C6c control: the same error after the whole timeout reads as timed out",
                      Classify(slow, 8) == Outcome.TimedOut, Classify(slow, 8).ToString());
                var odd = new Reading { Result = Transport.ConnectionError, Error = "Unknown Error", ElapsedSeconds = 1.0 };
                Check(r, "C7 an unrecognised connection error reads as unreachable",
                      Classify(odd, 8) == Outcome.Unreachable, Classify(odd, 8).ToString());
                var never = new Reading { Result = Transport.NotStarted, Error = "the probe could not start (no active host)" };
                Check(r, "C8 a probe that never started reads as unreachable",
                      Classify(never, 8) == Outcome.Unreachable, Classify(never, 8).ToString());
            }

            // -- A: addresses and the interval ----------------------------------
            {
                Check(r, "A1 host:port names the probed address and its port",
                      HostPort(TSecure + "/") == THostPort, HostPort(TSecure + "/"));
                Check(r, "A2 host:port supplies the scheme's default port",
                      HostPort("https://example.org") == "example.org:443", HostPort("https://example.org"));
                bool sec = IsSecure(TSecure), plain = IsSecure(TBackup), userinfo = IsSecure("https://u:p@example.org");
                Check(r, "A3 only an https address without user info counts as secure",
                      sec && !plain && !userinfo, "secure=" + sec + " plaintext=" + plain + " userinfo=" + userinfo);
                double m5 = RetrySecondsFromMinutes(5), m0 = RetrySecondsFromMinutes(0),
                       mNaN = RetrySecondsFromMinutes(double.NaN), mBig = RetrySecondsFromMinutes(1000);
                Check(r, "A4 the retry interval is the cfg minutes, clamped to 15 s .. 60 min, 5 min by default",
                      m5 == 300 && m0 == 15 && mNaN == 300 && mBig == 3600 && DefaultRetryMinutes == 5.0,
                      "5->" + m5 + " 0->" + m0 + " NaN->" + mNaN + " 1000->" + mBig);
            }

            // -- B: the boot check ----------------------------------------------
            {
                var clock = new FakeClock();
                var route = new Route(TSecure, TBackup);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = ROk() };
                var log = new RunLog();
                int g = route.Begin(Trigger.Boot, TSecure, 0, TOwner, TRetry);
                Drive(route, g, t, clock, log, TRetry);
                var c = log.Last;
                Check(r, "B1 a usable boot answer keeps the secure base and schedules no check",
                      g != 0 && c != null && c.Usable && !c.EnteredFallback && route.CurrentBase == TSecure
                      && !route.OnFallback && route.NextAutoAt == double.MaxValue && t.Urls.Count == 1,
                      Show(route, c) + " probes=" + t.Urls.Count);
                int again = route.Begin(Trigger.Boot, TSecure, 1, TOwner, TRetry);
                Check(r, "B4 the boot check cannot be begun twice", again == 0, "generation=" + again);
            }
            {
                var clock = new FakeClock();
                var route = new Route(TSecure, TBackup);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = RTimeout() };
                var log = new RunLog();
                int g = route.Begin(Trigger.Boot, TSecure, 0, TOwner, TRetry);
                Drive(route, g, t, clock, log, TRetry);
                var c = log.Last;
                bool urls = t.Urls.Count == 2 && t.Urls[0] == TSecure + ProbePath && t.Urls[1] == TSecure + ProbePath
                            && t.Timeouts[0] == 8 && t.Timeouts[1] == 8;
                Check(r, "B2 two failed boot attempts move the session to the backup and schedule the timer",
                      c != null && !c.Usable && c.EnteredFallback && route.OnFallback && route.CurrentBase == TBackup
                      && route.NextAutoAt == 300 && urls && log.Attempts.Count == 2,
                      Show(route, c) + " probes=" + string.Join(" ", t.Urls));
            }
            {
                var clock = new FakeClock();
                var route = new Route(TSecure, TBackup);
                var t = new FakeTransport();
                var log = new RunLog();
                int g = route.Begin(Trigger.Boot, TSecure, 0, TOwner, TRetry);
                Drive(route, g, t, clock, log, TRetry);
                t.Release(RTimeout());
                clock.Now = 8;
                t.Release(ROk());
                var c = log.Last;
                Check(r, "B3 a second boot attempt that answers rescues the session",
                      c != null && c.Usable && !route.OnFallback && route.CurrentBase == TSecure && t.Urls.Count == 2,
                      Show(route, c) + " probes=" + t.Urls.Count);
            }

            // -- P: the portal button -------------------------------------------
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                clock.Now = 42;
                var t = new FakeTransport();
                var log = new RunLog();
                int gen;
                var press = route.PressPortal(TSecure, 42, TOwner, TRetry, out gen);
                if (press == Press.Checking) Drive(route, gen, t, clock, log, TRetry);
                Check(r, "P1 on the backup a press begins ONE check of the secure address with the 8 s timeout",
                      press == Press.Checking && gen != 0 && t.Urls.Count == 1 && t.Urls[0] == TSecure + ProbePath
                      && t.Timeouts[0] == 8 && ProbeTimeoutSeconds == 8,
                      "press=" + press + " probes=" + string.Join(" ", t.Urls));
                int gen2;
                var again = route.PressPortal(TSecure, 43, TOwner, TRetry, out gen2);
                Check(r, "P9 a second press while the check runs joins it and starts nothing",
                      again == Press.Joined && gen2 == 0 && t.Urls.Count == 1,
                      "press=" + again + " probes=" + t.Urls.Count);
                clock.Now = 42.3;
                t.Release(ROk());
                var c = log.Last;
                Check(r, "P2 the check answers: the session flips to the secure base and the portal opens in the same press",
                      c != null && c.Flipped && c.OpenPortal && !c.ReportFailure && route.CurrentBase == TSecure
                      && !route.OnFallback && route.Restored && c.AttemptsSinceFallback == 1,
                      Show(route, c));
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                clock.Now = 42;
                var t = new FakeTransport { AutoAnswer = true, AutoReading = RTimeout() };
                var log = new RunLog();
                int gen;
                var press = route.PressPortal(TSecure, 42, TOwner, TRetry, out gen);
                if (press == Press.Checking) Drive(route, gen, t, clock, log, TRetry);
                var c = log.Last;
                Check(r, "P3 control: the check times out: the session stays on the backup and the press reports it",
                      c != null && !c.Flipped && !c.OpenPortal && c.ReportFailure && route.OnFallback
                      && route.CurrentBase == TBackup,
                      Show(route, c));
                string toast = c == null ? null : SecureRouteText.Failure(c.Outcome, c.HostPort, c.TimeoutSeconds, c.HttpCode);
                const string want = "The secure connection to competitive-rounds.duckdns.org:8444 timed out after 8 s. "
                                    + "The portal needs it; the game keeps working on the backup connection.";
                Check(r, "P4 the failure toast names the host:port and the 8 s timeout, word for word",
                      toast == want, toast);
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = RRefused() };
                var log = new RunLog();
                int gen;
                var press = route.PressPortal(TSecure, 42, TOwner, TRetry, out gen);
                if (press == Press.Checking) Drive(route, gen, t, clock, log, TRetry);
                var c = log.Last;
                string toast = c == null ? null : SecureRouteText.Failure(c.Outcome, c.HostPort, c.TimeoutSeconds, c.HttpCode);
                const string want = "The secure connection to competitive-rounds.duckdns.org:8444 was refused. "
                                    + "The portal needs it; the game keeps working on the backup connection.";
                Check(r, "P5 a refused check names the refusal instead", c != null && c.ReportFailure && toast == want, toast);
            }
            {
                var all = Sentences();
                string bad = null;
                var failures = new HashSet<string>(StringComparer.Ordinal);
                foreach (var kv in all)
                {
                    string s = kv.Value;
                    if (s == null || s.IndexOf("restart", StringComparison.OrdinalIgnoreCase) >= 0 || s.IndexOf('{') >= 0)
                    {
                        bad = kv.Key + ": " + (s ?? "(null)");
                        break;
                    }
                    if (kv.Key != "checking" && kv.Key != "restored" && kv.Key != "plaintext") failures.Add(s);
                }
                Check(r, "P6 no sentence tells the player to restart, and every hole is filled",
                      bad == null && all.Count == 10, bad ?? ("sentences=" + all.Count));
                Check(r, "P6b each failure outcome names its own failure",
                      failures.Count == 7, "distinct failure sentences=" + failures.Count);
            }
            {
                var clock = new FakeClock();
                var route = new Route(TSecure, TBackup);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = ROk() };
                int g = route.Begin(Trigger.Boot, TSecure, 0, TOwner, TRetry);
                Drive(route, g, t, clock, new RunLog(), TRetry);
                int gen;
                var press = route.PressPortal(TSecure, 5, TOwner, TRetry, out gen);
                Check(r, "P7 on the secure base a press opens at once and begins nothing",
                      press == Press.OpenNow && gen == 0 && t.Urls.Count == 1, "press=" + press + " probes=" + t.Urls.Count);
            }
            {
                var route = new Route(TLanOverride, TBackup);
                int gen;
                var press = route.PressPortal(TSecure, 5, TOwner, TRetry, out gen);
                Check(r, "P8 control: a plaintext base that is not the backup refuses and begins nothing",
                      press == Press.Refused && gen == 0 && !route.OnFallback, "press=" + press);
            }

            // -- T: the timer (fake clock) ----------------------------------------
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = RTimeout() };
                var log = new RunLog();
                var begun = TickTimer(route, clock, t, 0, 1000, TRetry, log);
                Check(r, "T1 on the backup the timer checks at the 5-minute marks and at no other second",
                      Times(begun) == "300,600,900" && t.Urls.Count == 3 && route.OnFallback,
                      "begun=" + Times(begun));
                bool counted = log.Attempts.Count == 3 && log.Attempts[0].Of == 1
                               && log.Attempts[0].AttemptsSinceFallback == 1 && log.Attempts[2].AttemptsSinceFallback == 3;
                Check(r, "T1b each timer check is one attempt and carries its count since the fall-back",
                      counted, "attempts=" + log.Attempts.Count);
            }
            {
                var clock = new FakeClock();
                var route = new Route(TSecure, TBackup);
                var boot = new FakeTransport { AutoAnswer = true, AutoReading = ROk() };
                int g = route.Begin(Trigger.Boot, TSecure, 0, TOwner, TRetry);
                Drive(route, g, boot, clock, new RunLog(), TRetry);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = RTimeout() };
                var begun = TickTimer(route, clock, t, 0, 1000, TRetry, new RunLog());
                Check(r, "T2 control: a session that never left the secure base never checks",
                      begun.Count == 0 && t.Urls.Count == 0, "begun=" + Times(begun));
            }
            {
                double retry = RetrySecondsFromMinutes(0.25);
                var clock = new FakeClock();
                var route = BackupRoute(clock, retry);
                var t = new FakeTransport();
                var log = new RunLog();
                var begun = TickTimer(route, clock, t, 0, 33, retry, log);
                Check(r, "T3 a live check holds the timer past its mark: never a second check beside it",
                      retry == 15 && Times(begun) == "15" && t.Held == 1 && ClaimLifetimeSeconds(Trigger.Timer) == 18,
                      "begun=" + Times(begun) + " held=" + t.Held);
            }
            {
                double retry = RetrySecondsFromMinutes(0.25);
                var clock = new FakeClock();
                var route = BackupRoute(clock, retry);
                var t = new FakeTransport();
                var log = new RunLog();
                var begun = TickTimer(route, clock, t, 0, 20, retry, log);
                clock.Now = 20;
                t.Release(RTimeout());
                begun.AddRange(TickTimer(route, clock, t, 21, 33, retry, log));
                Check(r, "T3c control: once the check has answered, the mark alone decides",
                      Times(begun) == "15,30", "begun=" + Times(begun));
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = RTimeout() };
                var log = new RunLog();
                var begun = TickTimer(route, clock, t, 0, 99, TRetry, log);
                clock.Now = 100;
                int gen;
                var press = route.PressPortal(TSecure, 100, TOwner, TRetry, out gen);
                if (press == Press.Checking) Drive(route, gen, t, clock, log, TRetry);
                begun.AddRange(TickTimer(route, clock, t, 101, 1000, TRetry, log));
                Check(r, "T4 a press moves the next mark: checks stay five minutes apart whoever starts them",
                      press == Press.Checking && Times(begun) == "400,700,1000", "begun=" + Times(begun));
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport { AutoAnswer = true, AutoReading = RTimeout() };
                var log = new RunLog();
                var begun = TickTimer(route, clock, t, 0, 300, TRetry, log);
                t.AutoReading = ROk();
                begun.AddRange(TickTimer(route, clock, t, 301, 3600, TRetry, log));
                var flip = log.Last;
                Check(r, "T5 the timer stops at the first answer and the session is back on the secure base",
                      Times(begun) == "300,600" && flip != null && flip.Flipped && !flip.OpenPortal && route.Restored
                      && !route.OnFallback && route.CurrentBase == TSecure && route.NextAutoAt == double.MaxValue
                      && flip.AttemptsSinceFallback == 2,
                      "begun=" + Times(begun) + " | " + Show(route, flip));
                int g1 = route.Begin(Trigger.Timer, TSecure, 4000, TOwner, TRetry);
                int g2 = route.Begin(Trigger.Button, TSecure, 4000, TOwner, TRetry);
                int gen;
                var press = route.PressPortal(TSecure, 4000, TOwner, TRetry, out gen);
                Check(r, "T6 off the backup no check of any trigger begins, and a press opens at once",
                      g1 == 0 && g2 == 0 && press == Press.OpenNow && gen == 0,
                      "timer=" + g1 + " button=" + g2 + " press=" + press);
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport();
                var log = new RunLog();
                var begun = TickTimer(route, clock, t, 0, 300, TRetry, log);
                clock.Now = 319;
                int gen;
                var press = route.PressPortal(TSecure, 319, TOwner, TRetry, out gen);
                if (press == Press.Checking) Drive(route, gen, t, clock, log, TRetry);
                t.Release(ROk());
                bool lateIgnored = log.Attempts.Count == 1 && !log.Attempts[0].Current && log.Done.Count == 0
                                   && route.OnFallback;
                t.Release(RTimeout());
                var c = log.Last;
                Check(r, "T7 a check whose host died is taken over after its lifetime, and its late answer changes nothing",
                      Times(begun) == "300" && press == Press.Checking && lateIgnored && c != null && c.ReportFailure
                      && route.OnFallback,
                      "press=" + press + " lateIgnored=" + lateIgnored + " | " + Show(route, c));
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport();
                var log = new RunLog();
                TickTimer(route, clock, t, 0, 300, TRetry, log);
                int gen;
                var press = route.PressPortal(TSecure, 310, TOwner, TRetry, out gen);
                Check(r, "T7c control: a press inside the check's lifetime joins it",
                      press == Press.Joined && gen == 0 && t.Urls.Count == 1, "press=" + press + " probes=" + t.Urls.Count);
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport();
                var log = new RunLog();
                TickTimer(route, clock, t, 0, 300, TRetry, log);
                int gen;
                route.PressPortal(TSecure, 305, TOwner, TRetry, out gen);
                var begun = TickTimer(route, clock, t, 301, 600, TRetry, log);
                t.Release(RTimeout());
                t.Release(ROk());
                var c = log.Last;
                Check(r, "T8 a press that waited on a check that died is not answered by a later timer check",
                      Times(begun) == "600" && c != null && c.Flipped && !c.OpenPortal,
                      "begun=" + Times(begun) + " | " + Show(route, c));
            }
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                var t = new FakeTransport();
                var log = new RunLog();
                TickTimer(route, clock, t, 0, 300, TRetry, log);
                clock.Now = 301;
                t.Release(RTimeout());
                var begun = TickTimer(route, clock, t, 302, 600, TRetry, log);
                int gen;
                var press = route.PressPortal(TSecure, 605, TOwner, TRetry, out gen);
                t.Release(ROk());
                var c = log.Last;
                Check(r, "T8c control: a press that joins the live timer check is answered by it",
                      Times(begun) == "600" && press == Press.Joined && c != null && c.Flipped && c.OpenPortal,
                      "press=" + press + " | " + Show(route, c));
            }

            // -- F: the flip mid-flight -------------------------------------------
            // ApiClient builds every request from its base-url field at the
            // moment it builds it; the flip writes the field once and rewrites
            // nothing already built or in flight. Modelled here as URLs built
            // from CurrentBase. The outbox resolves a queued report's address
            // at each send instead (the O cases below).
            {
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                clock.Now = 299;
                string queued = route.CurrentBase + "/api/v1/matches/report";
                var t = new FakeTransport { AutoAnswer = true, AutoReading = ROk() };
                var log = new RunLog();
                var begun = TickTimer(route, clock, t, 300, 300, TRetry, log);
                string after = route.CurrentBase + "/api/v1/matches/report";
                bool flipped = log.Last != null && log.Last.Flipped;
                Check(r, "F1 a request queued on the backup before the flip completes against the backup",
                      Times(begun) == "300" && flipped && queued == TBackup + "/api/v1/matches/report",
                      "queued=" + queued);
                Check(r, "F2 control: a request built after the flip goes to the secure base",
                      flipped && after == TSecure + "/api/v1/matches/report", "after=" + after);
            }

            // -- J: the probe's body (Codex round 1 MEDIUM 1) ---------------------
            // The verdict a 200 body earns, through the same reading and the
            // same Classify the transport's answer goes through, and then
            // through a timer check on the backup: only a whole mod-version
            // object restores the secure route.
            {
                const string compact = "{\"version\":\"1.41.0\",\"min_version\":\"1.38.7\",\"server_accepts_involuntary_ffa_cause\":true}";
                const string spaced = "{ \"version\" : \"1.41.0\" ,\n  \"min_version\": \"1.38.7\",\t\"server_accepts_involuntary_ffa_cause\": false }\n";
                const string wrong = "{\"latest\":\"1.41.0\",\"min_version\":\"1.38.7\"}";
                const string truncated = "{\"version\":\"1.41.0";
                Func<string, Outcome> verdict = body => Classify(new Reading
                {
                    Result = Transport.Success, ResultName = "Success", HttpCode = 200,
                    VersionParsed = IsModVersionBody(body), ElapsedSeconds = 0.1,
                }, ProbeTimeoutSeconds);
                Func<string, bool> flips = body =>
                {
                    var clock = new FakeClock();
                    var route = BackupRoute(clock, TRetry);
                    var t = new FakeTransport { AutoAnswer = true, AutoReading = new Reading
                    {
                        Result = Transport.Success, ResultName = "Success", HttpCode = 200,
                        VersionParsed = IsModVersionBody(body), ElapsedSeconds = 0.1,
                    } };
                    var log = new RunLog();
                    TickTimer(route, clock, t, 300, 300, TRetry, log);
                    return log.Last != null && log.Last.Flipped && !route.OnFallback;
                };
                Check(r, "J1 a compact mod-version body is usable and restores the secure route",
                      verdict(compact) == Outcome.Usable && flips(compact), "outcome=" + verdict(compact) + " flips=" + flips(compact));
                Check(r, "J2 a mod-version body with whitespace between its tokens is usable and restores the secure route",
                      verdict(spaced) == Outcome.Usable && flips(spaced), "outcome=" + verdict(spaced) + " flips=" + flips(spaced));
                Check(r, "J3 control: a JSON body without the version member is not the SCR server and keeps the backup",
                      verdict(wrong) == Outcome.NotTheServer && !flips(wrong), "outcome=" + verdict(wrong) + " flips=" + flips(wrong));
                Check(r, "J4 control: a body cut off inside the version string is not the SCR server and keeps the backup",
                      verdict(truncated) == Outcome.NotTheServer && !flips(truncated),
                      "outcome=" + verdict(truncated) + " flips=" + flips(truncated));
                var malformed = new[]
                {
                    "{\"version\":\"1.41.0\"", "{\"version\":\"1.41.0\"} x", "x {\"version\":\"1.41.0\"}",
                    "{\"version\":\"1.41.0\",}", "{\"version\":\"1.41.0\" \"a\":1}", "{\"version\":1.41}",
                    "{\"version\":\"latest\"}", "{\"version\":\"1.41\"}", "{\"version\":\"1.41.0 \"}",
                    "{\"version\":\"1.41.0\",\"version\":\"1.41.0\"}", "[{\"version\":\"1.41.0\"}]",
                    "{\"a\":{\"version\":\"1.41.0\"}}", "<html>{\"version\":\"1.41.0\"}</html>", "", "   ",
                    "{\"version\":\"1.41.0\",\"a\":[1,2}", "{\"version\":\"1.41.0\",\"a\":\"x\\q\"}",
                    "{\"version\":\"1.41.0\",\"a\":01}", "{\"version\":\"1.41.0\",\"a\":tru}",
                    "{\"version\":\"1.41.0\",\"a\":\"line\nbreak\"}", "{'version':'1.41.0'}", "{\"version\":\"1.41.0-\"}",
                };
                string accepted = null;
                foreach (string m in malformed)
                    if (IsModVersionBody(m)) { accepted = m; break; }
                Check(r, "J5 every malformed or foreign body is refused (unclosed, trailing or leading text, trailing comma, "
                         + "missing comma, a number or a non-release version, two version members, an array, a nested version, "
                         + "HTML, empty, a broken nested value, a bad escape, a raw control character, single quotes)",
                      accepted == null, accepted == null ? "refused=" + malformed.Length : "accepted=" + accepted);
                var wellFormed = new[]
                {
                    "{\"version\":\"1.41.0-beta2\",\"caps\":{\"a\":[1,-2.5e3,0,null,true,false,\"\\u0041\\\"\"]},\"x\":[]}",
                    "\r\n{\"min_version\":\"1.38.7\",\"version\":\"1.40.3\"}\r\n",
                    "{\"version\":\"1\\u002e41.0\"}",
                };
                string refused = null;
                foreach (string w in wellFormed)
                    if (!IsModVersionBody(w)) { refused = w; break; }
                Check(r, "J6 control: well-formed bodies with nested members, escapes, suffixes and any member order are accepted",
                      refused == null, refused == null ? "accepted=" + wellFormed.Length : "refused=" + refused);
            }

            // -- O: the report outbox follows the route (Codex round 1 HIGH 1) ------
            // ApiClient.OutboxPass resolves each queued report's address with
            // OutboxTarget at every send, over the route's own bases, and asks
            // OutboxAnswerFor after every answer. Modelled with the real
            // route and the real rules; the send is the fake.
            {
                const string path = "/api/v1/matches";
                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                string queued = route.CurrentBase + path;
                string before = OutboxTarget(queued, route.CurrentBase, route.Bases(TSecure));
                var t = new FakeTransport { AutoAnswer = true, AutoReading = ROk() };
                var log = new RunLog();
                TickTimer(route, clock, t, 300, 300, TRetry, log);
                bool flipped = log.Last != null && log.Last.Flipped;
                string after = OutboxTarget(queued, route.CurrentBase, route.Bases(TSecure));
                Check(r, "O1 a report queued on the backup is sent to the secure base from the first send after the flip",
                      flipped && queued == TBackup + path && after == TSecure + path, "queued=" + queued + " after=" + after);
                Check(r, "O1c control: before the flip the same report is sent to the backup",
                      before == TBackup + path, "before=" + before);

                var boot = new FakeClock();
                var backupNow = BackupRoute(boot, TRetry);
                string earlier = TSecure + path;
                string other = OutboxTarget(earlier, backupNow.CurrentBase, backupNow.Bases(TSecure));
                Check(r, "O2 the other direction: a report queued on the secure base goes to the backup while the session is on it",
                      other == TBackup + path, "sent=" + other);
                string lan = TLanOverride + path;
                string keptLan = OutboxTarget(lan, route.CurrentBase, route.Bases(TSecure));
                string lookalike = "https://competitive-rounds.duckdns.org:84440" + path;
                string keptLook = OutboxTarget(lookalike, backupNow.CurrentBase, backupNow.Bases(TSecure));
                string upper = OutboxTarget("HTTP://Competitive-Rounds.DuckDNS.org:8443" + path, route.CurrentBase, route.Bases(TSecure));
                Check(r, "O2b the scheme and host are matched without regard to case",
                      upper == TSecure + path, "upper=" + upper);
                Check(r, "O3 control: an address that is not one of the route's bases is kept as queued, a longer port included",
                      keptLan == lan && keptLook == lookalike,
                      "lan=" + keptLan + " lookalike=" + keptLook);

                var failTokenless = OutboxAnswerFor(false, false);
                var failCarried = OutboxAnswerFor(false, true);
                Check(r, "O4 a failed retry that did not carry the session token spends no attempt",
                      failTokenless == OutboxAnswer.GiveBack, "answer=" + failTokenless);
                Check(r, "O4c control: a failed retry that carried the token spends one",
                      failCarried == OutboxAnswer.Spend, "answer=" + failCarried);
                var okTokenless = OutboxAnswerFor(true, false);
                var okCarried = OutboxAnswerFor(true, true);
                Check(r, "O4d a 2xx to a retry that did not carry the session token removes nothing and spends nothing",
                      okTokenless == OutboxAnswer.GiveBack, "answer=" + okTokenless);
                Check(r, "O4dc control: a 2xx to a retry that carried the token settles the report",
                      okCarried == OutboxAnswer.Settle, "answer=" + okCarried);
                var waitNoSession = OutboxSendGate(true, false);
                var sendWithSession = OutboxSendGate(true, true);
                var sendBackup = OutboxSendGate(false, false);
                Check(r, "O4b over a transport that carries the token, a report without a fresh session waits and is not sent",
                      waitNoSession == OutboxGate.WaitForSession, "gate=" + waitNoSession);
                Check(r, "O4bc control: with a fresh session it is sent; over the plaintext backup (no token either way) it is sent",
                      sendWithSession == OutboxGate.Send && sendBackup == OutboxGate.Send,
                      "session=" + sendWithSession + " backup=" + sendBackup);

                // The outbox's ladder against a server that answers 401 to any
                // request without the token (enforcement armed): 94 counted
                // attempts delete a report. "Carried" is what the request
                // carried: a session held at the send AND a transport that
                // stamps it (Codex round 2: the round-2 model read "https" as
                // carried, so it could not tell a restored route without a
                // session from one with).
                Func<bool, bool, string> ladder = (followRoute, restoreAt10) =>
                {
                    var c = new FakeClock();
                    var rt = BackupRoute(c, TRetry);
                    string url = rt.CurrentBase + path;
                    int attempts = 0, sends = 0;
                    bool session = false;
                    for (int i = 1; i <= 400; i++)
                    {
                        if (restoreAt10 && i == 10)
                        {
                            var tt = new FakeTransport { AutoAnswer = true, AutoReading = ROk() };
                            TickTimer(rt, c, tt, 300, 300, TRetry, new RunLog());
                            session = true;
                        }
                        string target = followRoute ? OutboxTarget(url, rt.CurrentBase, rt.Bases(TSecure)) : url;
                        url = target;
                        bool transport = OutboxModelCarries(target);
                        if (OutboxSendGate(transport, session) == OutboxGate.WaitForSession) continue;
                        attempts++;
                        sends++;
                        bool carried = transport && session;
                        // The enforcing sink: 200 only to a request with the token.
                        var answer = OutboxAnswerFor(carried, carried);
                        if (answer == OutboxAnswer.Settle) return "delivered at send " + sends + " to " + target;
                        if (answer == OutboxAnswer.GiveBack) attempts--;
                        if (attempts >= 94) return "deleted at send " + sends + " (attempt " + attempts + ")";
                    }
                    return "still queued after 400 sends, attempt " + attempts;
                };
                string fixedRun = ladder(true, true);
                string oldRun = ladder(false, true);
                string neverRun = ladder(true, false);
                Check(r, "O5 with enforcement armed a report queued on the backup is delivered once, with the token, after the restore",
                      fixedRun == "delivered at send 10 to " + TSecure + path, fixedRun);
                Check(r, "O5c control: the queued URL kept, as in round 1, never reaches the secure base and is never delivered",
                      oldRun == "still queued after 400 sends, attempt 0", oldRun);
                Check(r, "O6 a session that never leaves the backup keeps the report queued instead of deleting it at 94",
                      neverRun == "still queued after 400 sends, attempt 0", neverRun);

                // O7, Codex round 2 HIGH 1's falsifier as a composition: the
                // report is queued on the backup with NO session and 93 of 94
                // attempts already spent, the route is restored while the
                // Steam exchange stays unavailable for two minutes, then a
                // session lands. Every pass is modelled on ApiClient.OutboxPass
                // (resolve, gate, spend) against an enforcing server.
                var o7 = OutboxComposition(93, 120.0, false);
                Check(r, "O7 restored without a session for 2 min: no send to the secure base, no attempt spent, the entry kept",
                      o7.SecureSendsBeforeSession == 0 && o7.AttemptsAtSession == 93 && o7.QueuedAtSession,
                      o7.Describe());
                Check(r, "O7b then the session lands: exactly one send, with the token, one settlement, an empty outbox",
                      o7.SecureSendsAfterSession == 1 && o7.CarriedSends == 1 && o7.Settled == 1 && o7.Rows == 1
                          && !o7.QueuedAtEnd && !o7.Dropped,
                      o7.Describe());
                var o7c = OutboxComposition(93, 0.0, false);
                Check(r, "O7c control: with the session already held at the restore, the first pass after it delivers",
                      o7c.Settled == 1 && o7c.SecureSendsBeforeSession == 0 && o7c.SecureSendsAfterSession == 1, o7c.Describe());
                // O8: the gate saw a session, but it was dropped before the
                // stamp, so the request went out without the token.
                // O9 (Codex round 2 LOW 1's falsifier): a tokenless retry on
                // the backup is in flight at 290 s; the route is restored at
                // 300 s (the entry is promised a look by 320 s); the held 401
                // is released at 305 s. The give-back must not move the entry
                // past the promise.
                {
                    double sendAt = 290.0, restoreAt = 300.0, answerAt = 305.0;
                    double nextAtSend = sendAt + 60.0 * Math.Min(4.0, 1);
                    double promise = restoreAt + 20.0;
                    double nextAfterRestore = Math.Min(nextAtSend, promise);
                    double proposed = answerAt + 60.0 * 4.0;
                    double giveBack = OutboxGiveBackDue(proposed, promise);
                    double giveBackNoRestore = OutboxGiveBackDue(proposed, -1.0);
                    Check(r, "O9 a backup 401 that lands after a restore keeps the entry due by the restore's promise (20 s)",
                          giveBack <= promise && nextAfterRestore <= promise,
                          "promise=" + promise + " giveBack=" + giveBack + " proposed=" + proposed);
                    Check(r, "O9c control: with no restore while it was in flight, the give-back waits the capped interval",
                          giveBackNoRestore == proposed, "giveBack=" + giveBackNoRestore);
                }
                var o8 = OutboxComposition(93, 120.0, true);
                Check(r, "O8 a request sent without the token after the gate passed spends nothing and removes nothing",
                      !o8.Dropped && o8.Settled == 1 && o8.SettledTokenless == 0 && o8.Rows == 1 && o8.TokenlessSecureSends == 1,
                      o8.Describe());
                // O10, Codex round 3 HIGH 1's falsifier: the sink answers a
                // tokenless POST 200 WITHOUT recording a row (a server that does
                // not enforce, or anything answering in its place on the
                // backup). The report is queued on the backup with 93 of 94
                // spent; every backup send is answered that way; the route is
                // restored at 300 s with the session held.
                var o10 = OutboxComposition(93, 0.0, false, Sink.Tokenless200);
                Check(r, "O10 a tokenless 2xx without a row leaves the entry queued: nothing removed, no attempt spent, 0 rows",
                      o10.TokenlessOkBeforeRestore >= 1 && o10.QueuedAtRestore && o10.RowsAtRestore == 0
                          && o10.AttemptsAtSession == 93 && o10.SettledTokenless == 0,
                      o10.Describe());
                Check(r, "O10b then the restore and the session: exactly one token-bearing settlement, one row, an empty outbox",
                      o10.Settled == 1 && o10.SettledTokenless == 0 && o10.CarriedSends == 1 && o10.Rows == 1
                          && !o10.QueuedAtEnd && !o10.Dropped,
                      o10.Describe());
                var o10c = OutboxComposition(93, 0.0, false, Sink.Enforcing);
                Check(r, "O10c control: the same run against the enforcing sink (401 without the token) settles the same way",
                      o10c.TokenlessOkAnswers == 0 && o10c.QueuedAtRestore && o10c.Settled == 1 && o10c.Rows == 1
                          && !o10c.QueuedAtEnd,
                      o10c.Describe());
            }

            // -- R and K: the portal press (Codex round 1 LOW 1 and LOW 2) --------
            {
                bool a = IsSessionRefusal("HTTP 401: {\"detail\":\"steam session required\"}");
                bool b = IsSessionRefusal("HTTP 401: {\"detail\":\"session_required\"}");
                bool n1 = IsSessionRefusal("HTTP 401: {\"detail\":\"ticket_verification_failed\"}");
                bool n2 = IsSessionRefusal("HTTP 403: {\"detail\":\"banned\"}");
                Check(r, "R1 both refusal wordings (the portal mint's and the enforced writes') read as a session refusal",
                      a && b, "portal=" + a + " writes=" + b);
                Check(r, "R1c control: other refusals are not session refusals",
                      !n1 && !n2, "ticket=" + n1 + " banned=" + n2);
                const string refusedPortal = "HTTP 401: {\"detail\":\"steam session required\"}";
                var first = PortalMintAction(false, null, refusedPortal, true);
                var second = PortalMintAction(false, null, refusedPortal, false);
                var opened = PortalMintAction(true, "tok", "{\"token\":\"tok\"}", true);
                var banned = PortalMintAction(false, null, "HTTP 403: {\"detail\":\"banned\"}", true);
                var noTok = PortalMintAction(true, null, "{}", true);
                Check(r, "R2 a mint refused for its session re-mints once, and the second refusal is reported, never looped",
                      first == MintAction.RemintOnce && second == MintAction.Fail && opened == MintAction.Open,
                      "first=" + first + " second=" + second + " token=" + opened);
                Check(r, "R2c control: a refusal that is not about the session, and an answer without a token, are reported",
                      banned == MintAction.Fail && noTok == MintAction.Fail, "banned=" + banned + " noToken=" + noTok);

                var clock = new FakeClock();
                var route = BackupRoute(clock, TRetry);
                int g;
                var press = route.PressPortal(TSecure, clock.Now, TOwner, TRetry, out g);
                var k1 = PortalPressAction(press, false, route.Restored, false);
                Check(r, "K1 a press on the backup while the local identity is unknown still starts the check and shows it",
                      press == Press.Checking && g != 0 && k1 == PressAction.ShowChecking, "press=" + press + " action=" + k1);
                var k2 = PortalPressAction(null, false, false, false);
                Check(r, "K2 a press on an explicit plaintext address while the identity is unknown still names the address",
                      k2 == PressAction.RefusePlaintext, "action=" + k2);
                var k3 = PortalPressAction(Press.OpenNow, true, false, false);
                var k3c = PortalPressAction(Press.OpenNow, true, false, true);
                var k4 = PortalPressAction(Press.OpenNow, true, true, true);
                Check(r, "K3 on the secure base with the identity unknown the press waits for it and mints, never a silent no-op",
                      k3 == PressAction.WaitThenMint, "action=" + k3);
                Check(r, "K3c control: with the identity known the press mints at once; after a restore it waits for the session",
                      k3c == PressAction.MintNow && k4 == PressAction.WaitThenMint, "known=" + k3c + " restored=" + k4);
            }

            // -- W: the portal's readiness wait outlasts its own auth exchange ------
            // (Codex round 2 LOW 2.) A press restores the route at t = 0 and the
            // ticket goes out at once; the exchange answers after d seconds,
            // anywhere inside its own timeout. The wait polls every 0.5 s as
            // ApiClient's two waits do, then mints once, with or without it.
            {
                double lastEnd = 0;
                Func<double, bool> mintCarriesSession = d =>
                {
                    double t = 0;
                    while (KeepWaitingForSession(0, t, t >= d, null)) t += 0.5;
                    lastEnd = t;
                    return t >= d;
                };
                var got = new StringBuilder();
                bool all = true;
                foreach (double d in new[] { 16.0, 17.0, 18.0, 19.0, 19.9 })
                {
                    bool ok = mintCarriesSession(d);
                    all &= ok;
                    got.Append("d=").Append(d).Append(ok ? ":session@" : ":none@").Append(lastEnd).Append(' ');
                }
                Check(r, "W1 a session the exchange lands 16-19.9 s after the press is waited for: the one mint carries it",
                      all && PortalSessionWaitSeconds >= SteamAuthExchangeTimeoutSeconds + SessionWaitMarginSeconds
                          && SessionWaitMarginSeconds > 0,
                      got.ToString().Trim() + " wait=" + PortalSessionWaitSeconds + " exchange=" + SteamAuthExchangeTimeoutSeconds);
                bool never = mintCarriesSession(1000.0);
                double ended = lastEnd;
                bool at5 = mintCarriesSession(5.0);
                Check(r, "W1c control: a session that never lands ends the wait at the bound; an early one ends it at once",
                      !never && ended >= PortalSessionWaitSeconds && ended < PortalSessionWaitSeconds + 0.5
                          && at5 && lastEnd == 5.0,
                      "never ended@" + ended + " early ended@" + lastEnd);

                // W1d (Codex round 3 LOW 1's falsifier): the wait's first poll at
                // or after `reqAt` requests the ticket (SteamAuth.MaybeRefresh, as
                // the wait calls it every 0.5 s; later than 0 when the latch or
                // the refresh backoff was busy at the press); Steam's callback
                // arrives `cb` seconds after the request and the exchange answers
                // `ex` seconds after that, inside its own 20 s timeout. The wait
                // then mints once. `fail`: the exchange FAILS then (no session).
                int mints = 0;
                Func<double, double, double, bool, bool> press = (reqAt, cbDelay, ex, fail) =>
                {
                    var latch = new TicketLatch();
                    Func<bool> cancelOk = () => true;
                    bool session = false, requested = false;
                    double t = 0, cb = double.MaxValue;
                    mints = 0;
                    while (true)
                    {
                        if (latch.IsHeld && latch.CallbackAt < 0 && t >= cb) latch.CallbackArrived(latch.Serial, cb);
                        if (latch.IsHeld && latch.CallbackAt >= 0 && t >= cb + ex)
                        {
                            bool f0;
                            session = !fail;
                            latch.End(latch.Serial, fail ? "failed" : "answered", cancelOk, out f0);
                        }
                        if (!KeepWaitingForSession(0, t, session, latch)) break;
                        bool f1;
                        latch.Tick(t, cancelOk, out f1);
                        if (!session && !requested && t >= reqAt && latch.MayRequest)
                        {
                            latch.Took(t);
                            requested = true;
                            cb = t + cbDelay;
                        }
                        t += 0.5;
                    }
                    mints++;
                    lastEnd = t;
                    return session;
                };
                var gotD = new StringBuilder();
                bool allD = true;
                foreach (var ce in new[] { new[] { 0, 6.5, 19.5 }, new[] { 0, 10.0, 19.9 }, new[] { 0, 24.0, 19.9 },
                                           new[] { 10.0, 20.0, 15.0 } })
                {
                    bool ok = press(ce[0], ce[1], ce[2], false);
                    allD &= ok && mints == 1;
                    gotD.Append("request=").Append(ce[0]).Append(" callback+").Append(ce[1]).Append(" exchange=").Append(ce[2])
                        .Append(ok ? ":session@" : ":none@").Append(lastEnd).Append(" mints=").Append(mints).Append(' ');
                }
                Check(r, "W1d a ticket callback later than 5 s and an exchange inside its 20 s: one press mints once, with the session",
                      allD && TicketCallbackBoundSeconds >= 24.0,
                      gotD.ToString().Trim() + " callbackBound=" + TicketCallbackBoundSeconds);
                bool noCb = press(0, 1000.0, 1.0, false);
                double noCbEnd = lastEnd;
                bool lateCb = press(0, 30.0, 1.0, false);
                double lateEnd = lastEnd;
                bool failed = press(0, 10.0, 19.0, true);
                double failEnd = lastEnd;
                Check(r, "W1dc control: an outstanding callback is waited for only within its bound, and a failed exchange ends the wait",
                      !noCb && noCbEnd >= TicketCallbackBoundSeconds && noCbEnd < TicketCallbackBoundSeconds + 0.5
                          && !lateCb && lateEnd < 30.0
                          && !failed && failEnd >= 29.0 && failEnd < 29.5,
                      "no callback ended@" + noCbEnd + " callback at 30 ended@" + lateEnd + " failed at 29 ended@" + failEnd);
            }

            // -- N: the plaintext refusal's log line (Codex round 2 LOW 3) --------
            {
                string withCreds = PlaintextRefusalLine("http://ops:hunter2@example.org:8080/api/v1?key=sentinel-7781#frag");
                string lan = PlaintextRefusalLine("http://192.168.72.102:8443/");
                string junk = PlaintextRefusalLine("not a url sentinel-7781");
                bool clean = withCreds.Contains("http://example.org:8080 ")
                             && withCreds.IndexOf("hunter2", StringComparison.Ordinal) < 0
                             && withCreds.IndexOf("ops", StringComparison.Ordinal) < 0
                             && withCreds.IndexOf("sentinel-7781", StringComparison.Ordinal) < 0
                             && withCreds.IndexOf("/api", StringComparison.Ordinal) < 0
                             && withCreds.IndexOf("frag", StringComparison.Ordinal) < 0
                             && withCreds.Contains("plaintext") && withCreds.Contains("https")
                             && withCreds.IndexOf('\n') < 0 && withCreds.IndexOf('\r') < 0;
                Check(r, "N1 the plaintext refusal's log line names the base as scheme://host:port and the reason, with no credential",
                      clean, withCreds);
                Check(r, "N1c control: a plain LAN base is named as it is, and an address that does not parse is not echoed",
                      lan.Contains("http://192.168.72.102:8443 ") && junk.IndexOf("sentinel-7781", StringComparison.Ordinal) < 0,
                      lan + " || " + junk);

                // N1d (Codex round 3 LOW 2's falsifier): a valid 253-character
                // DNS name of four legal labels (63.63.63.61).
                string host253 = new string('a', 63) + "." + new string('b', 63) + "." + new string('c', 63) + "." + new string('d', 61);
                string longLine = PlaintextRefusalLine("http://" + host253 + ":8443/api");
                bool longOk = host253.Length == 253
                              && longLine.Length <= PlaintextRefusalLineMax && PlaintextRefusalLineMax < 160
                              && longLine.StartsWith("[SCR] portal button: not opened; the server address http://aaaa", StringComparison.Ordinal)
                              && longLine.Contains("...:8443 is plaintext")
                              && longLine.EndsWith(" is plaintext, and the portal token is only sent over https", StringComparison.Ordinal)
                              && longLine.IndexOf('\n') < 0 && longLine.IndexOf('\r') < 0;
                Check(r, "N1d a valid 253-character host: the whole line stays within its declared maximum, the host cut with a marker",
                      longOk, "len=" + longLine.Length + "/" + PlaintextRefusalLineMax + " line=" + longLine);
                Check(r, "N1dc control: an address that fits is not cut, and its line is within the maximum too",
                      lan.IndexOf("...", StringComparison.Ordinal) < 0 && lan.Length <= PlaintextRefusalLineMax
                          && PlaintextRefusalLine("http://competitive-rounds.duckdns.org:8443").Contains("http://competitive-rounds.duckdns.org:8443 "),
                      "len=" + lan.Length + " line=" + lan);
            }

            // -- M: the mint failure line is bounded and token-safe (Codex round 2 LOW 4)
            {
                const string sentinel = "SENTINELtok9f8e7d6c5b4a39281706f5e4d3c2b1a0";
                string body = "HTTP 502: {\"detail\":\"upstream\",\"token\":\"" + sentinel + "\"}\r\n<html>"
                              + new string('x', 200) + "\r\n</html>";
                string line = PortalMintFailureLine("https://scr.example.org:8443", false, body, true);
                bool bounded = line.Length <= MintFailureLineMax && line.EndsWith("... (after the one re-mint)", StringComparison.Ordinal);
                bool oneLine = line.IndexOf('\r') < 0 && line.IndexOf('\n') < 0;
                bool scrubbed = line.IndexOf("SENTINEL", StringComparison.Ordinal) < 0 && line.Contains("[redacted]");
                Check(r, "M1 a 161+ character failure body with a token: the whole line is bounded, one line, and scrubbed",
                      body.Length > 161 && bounded && oneLine && scrubbed
                          && line.StartsWith("[I18N] portal mint failed over https://scr.example.org:8443: HTTP 502", StringComparison.Ordinal),
                      "len=" + line.Length + "/" + MintFailureLineMax + " oneLine=" + oneLine + " scrubbed=" + scrubbed + " line=" + line);
                string bare = PortalMintFailureLine("https://scr.example.org:8443", false,
                    "HTTP 401: session " + sentinel + " X-Session-Token: abcDEF0123 ?portal_token=zz99 Session Ticket: " + new string('A', 40), false);
                bool bareClean = bare.IndexOf("SENTINEL", StringComparison.Ordinal) < 0 && bare.IndexOf("abcDEF0123", StringComparison.Ordinal) < 0
                                 && bare.IndexOf("zz99", StringComparison.Ordinal) < 0 && bare.IndexOf("AAAAAAAAAA", StringComparison.Ordinal) < 0;
                Check(r, "M2 a bare token-shaped value, a session header, a token pair and a Steam ticket are all redacted",
                      bareClean, bare);
                string plain = PortalMintFailureLine("https://scr.example.org:8443", false, "HTTP 403: {\"detail\":\"banned\"}", false);
                string noTok = PortalMintFailureLine("https://scr.example.org:8443", true, "{\"token\":\"" + sentinel + "\"}", true);
                Check(r, "M1c control: a short answer with no credential is logged whole, and a success is named, never printed",
                      plain == "[I18N] portal mint failed over https://scr.example.org:8443: HTTP 403: {\"detail\":\"banned\"}"
                          && noTok == "[I18N] portal mint failed over https://scr.example.org:8443: answered without a token (after the one re-mint)",
                      plain + " || " + noTok);
            }

            // -- MT: the one-ticket latch (Codex round 2 LOW 5) ---------------------
            // A refresh tick is modelled as SteamAuth.MaybeRefresh runs it: the
            // latch's Tick first, then a successor only when MayRequest.
            {
                int cancels = 0, requested = 0, throwsLeft = 0;
                var requestedAtCancel = new List<int>();
                var freeDuringCancel = new List<bool>();
                var lines = new List<string>();
                TicketLatch latch = null;
                Func<bool> cancel = () =>
                {
                    cancels++;
                    requestedAtCancel.Add(requested);
                    // While a handle's cancel is running the latch is not free:
                    // nothing reached from inside the cancel may request beside it.
                    freeDuringCancel.Add(latch.MayRequest);
                    if (throwsLeft > 0) { throwsLeft--; throw new InvalidOperationException("steam cancel unavailable"); }
                    return true;
                };
                Action<double> refreshTick = now =>
                {
                    bool f;
                    string n = latch.Tick(now, cancel, out f);
                    if (n != null) lines.Add(n);
                    if (latch.MayRequest) { requested++; latch.Took(now); }
                };
                Action<int> reset = t => { latch = new TicketLatch(); cancels = 0; requested = 0; throwsLeft = t; requestedAtCancel.Clear(); freeDuringCancel.Clear(); lines.Clear(); };

                // MT6: the cancel throws once while ticket creation stays available.
                reset(1);
                refreshTick(0.0);                                   // ticket 1
                bool failed6;
                string end6 = latch.End(1, "answered", cancel, out failed6);
                bool heldAfterFail = !latch.MayRequest && latch.State == TicketState.CancelFailed;
                int requestedBeforeRetry = requested;
                refreshTick(3.0);                                   // retry succeeds, then ticket 2
                refreshTick(6.0);
                Check(r, "MT6 a cancel that throws once keeps the handle; the next tick cancels it, and no successor is requested before that",
                      failed6 && heldAfterFail && requestedBeforeRetry == 1 && cancels == 2 && requestedAtCancel[1] == 1
                          && !freeDuringCancel.Contains(true)
                          && requested == 2 && latch.Serial == 2 && latch.IsHeld
                          && lines.Count == 1 && lines[0].Contains("cancelled with Steam on the retry"),
                      "end=" + end6 + " | heldAfterFail=" + heldAfterFail + " cancels=" + cancels + " requested=" + requested
                          + " requestedAtRetry=" + (requestedAtCancel.Count > 1 ? requestedAtCancel[1] : -1)
                          + " freeDuringCancel=" + string.Join(",", freeDuringCancel) + " lines=" + string.Join(" / ", lines));

                // MT6b: the cancel throws twice: retired with a line, never a third attempt.
                reset(2);
                refreshTick(0.0);
                bool failed6b;
                latch.End(1, "failed", cancel, out failed6b);
                refreshTick(3.0);                                   // retry fails: retired, then ticket 2
                int cancelsAfterRetire = cancels;
                refreshTick(6.0); refreshTick(9.0);
                Check(r, "MT6b a cancel that throws twice is retired with a log line on the next tick, never tried a third time",
                      failed6b && cancelsAfterRetire == 2 && cancels == 2 && requestedAtCancel[1] == 1 && requested == 2
                          && lines.Count == 1 && lines[0].Contains("retired uncancelled") && latch.Serial == 2,
                      "cancels=" + cancels + " requested=" + requested + " lines=" + string.Join(" / ", lines));

                // MT6c control: a cancel that succeeds frees the latch at once.
                reset(0);
                refreshTick(0.0);
                bool failed6c;
                string end6c = latch.End(1, "answered", cancel, out failed6c);
                bool freeAtOnce = latch.MayRequest;
                refreshTick(3.0);
                Check(r, "MT6c control: a cancel that succeeds frees the latch at once, and the next tick may request",
                      !failed6c && freeAtOnce && end6c.EndsWith("cancelled with Steam", StringComparison.Ordinal) && requested == 2 && cancels == 1,
                      "end=" + end6c + " requested=" + requested);

                // MT7: a late or repeated end changes nothing.
                reset(1);
                refreshTick(0.0);
                bool fx;
                latch.End(1, "failed", cancel, out fx);             // CancelFailed
                string again = latch.End(1, "failed", cancel, out fx);
                bool stillFailed = latch.State == TicketState.CancelFailed && cancels == 1;
                refreshTick(3.0);                                   // retry ok, ticket 2
                string stale = latch.End(1, "late", cancel, out fx);
                Check(r, "MT7 a repeated end of a failed handle, and a late end of an old serial, change nothing",
                      again == null && stillFailed && stale == null && latch.IsHeld && latch.Serial == 2 && cancels == 2,
                      "again=" + (again ?? "null") + " stale=" + (stale ?? "null") + " state=" + latch.State + " cancels=" + cancels);

                // MT8: a held ticket whose end never arrives is abandoned past the exchange's timeout.
                reset(0);
                refreshTick(0.0);
                refreshTick(TicketAbandonSeconds - 1);
                int before = requested;
                refreshTick(TicketAbandonSeconds + 1);
                Check(r, "MT8 a held ticket whose end never arrives is abandoned (cancelled) past the exchange's timeout, then superseded",
                      before == 1 && requested == 2 && cancels == 1 && TicketAbandonSeconds > SteamAuthExchangeTimeoutSeconds + 10
                          && lines.Count == 1 && lines[0].Contains("abandoned after 45 s") && lines[0].EndsWith("cancelled with Steam", StringComparison.Ordinal),
                      "requested=" + requested + " lines=" + string.Join(" / ", lines));
            }

            // -- H: the local witness harness's route ------------------------------
            {
                const string loop = "http://127.0.0.1:18555";
                var player = new Route(TSecure, TBackup);
                int gp = player.Begin(Trigger.Boot, loop, 0, TOwner, TRetry);
                var harness = new Route(loop, "http://[::1]:18555", acceptLoopbackPlaintext: true);
                int gh = harness.Begin(Trigger.Boot, loop, 0, TOwner, TRetry);
                var harness2 = new Route(loop, "http://[::1]:18555", acceptLoopbackPlaintext: true);
                int gl = harness2.Begin(Trigger.Boot, "http://192.168.72.102:8443", 0, TOwner, TRetry);
                Check(r, "H1 a player's route never checks a plaintext address, loopback included",
                      gp == 0, "generation=" + gp);
                Check(r, "H1c control: the witness harness's route checks plaintext loopback and nothing else plaintext",
                      gh != 0 && gl == 0, "loopback=" + gh + " lan=" + gl);
            }

            // -- L: every catalogue, executed ---------------------------------------
            {
                I18nCatalogues.Install();
                I18n.HarnessLocale = "en";
                var en = Sentences();
                foreach (string loc in new[] { "es", "ru", "uk", "sv" })
                {
                    I18n.HarnessLocale = loc;
                    var tr = Sentences();
                    string bad = null;
                    for (int i = 0; i < en.Count && bad == null; i++)
                    {
                        string e = en[i].Value, x = tr[i].Value;
                        bool ok = x != null && x != e && x.IndexOf('{') < 0
                                  && (e.IndexOf(THostPort, StringComparison.Ordinal) < 0 || x.IndexOf(THostPort, StringComparison.Ordinal) >= 0)
                                  && (e.IndexOf(TLanOverride, StringComparison.Ordinal) < 0 || x.IndexOf(TLanOverride, StringComparison.Ordinal) >= 0)
                                  && (e.IndexOf("HTTP 502", StringComparison.Ordinal) < 0 || x.IndexOf("HTTP 502", StringComparison.Ordinal) >= 0)
                                  && (e.IndexOf(" 8 s", StringComparison.Ordinal) < 0 || x.IndexOf("8", StringComparison.Ordinal) >= 0);
                        if (!ok) bad = en[i].Key + " -> " + (x ?? "(null)");
                    }
                    Check(r, "L-" + loc + " every secure-route sentence is translated in the " + loc + " catalogue, holes filled",
                          I18n.HasCatalogue(loc) && bad == null && tr.Count == 10, bad ?? ("sentences=" + tr.Count));
                }
                I18n.HarnessLocale = "en";
            }

            return r;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
