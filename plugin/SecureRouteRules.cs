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
            internal Route(string configuredBase, string fallbackBase)
            {
                CurrentBase = TrimBase(configuredBase);
                FallbackBase = TrimBase(fallbackBase);
                NextAutoAt = double.MaxValue;
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
                if (!IsSecure(probeBase)) return 0;
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
