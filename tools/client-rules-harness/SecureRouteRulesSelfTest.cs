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
            // moment it builds it, and the outbox keeps each queued report's
            // URL; the flip writes the field once and rewrites nothing already
            // built. Modelled here as URLs built from CurrentBase.
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
