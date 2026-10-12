using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>
    /// Verified reads, the client half (requirements 30-35): every decision
    /// the mod makes about the server's read gate, kept free of Unity,
    /// Photon, BepInEx and I18n so it runs under a plain compiler.
    /// ApiClient asks these functions and acts on the answer; it decides
    /// nothing about the gate itself.
    ///
    /// The server advertises its stage on the OPEN GET /api/v1/mod-version as
    /// `read_gate` ("off", "log", "enforce" or "unknown") and the GET
    /// templates it never refuses for want of a read credential as
    /// `read_gate_open`. That advert is the ONE signal deciding OPEN versus
    /// gated (requirement 32): no list of open routes is compiled in here.
    /// Before any advert has arrived nothing is held, because the stage is
    /// taken as "off" -- so stages 0 and 1 change nothing for the player.
    ///
    /// EXECUTED, not asserted about (#391): tools/client-rules-harness
    /// compiles this file beside ReadGateRulesSelfTest.cs (suite `readgate`).
    /// The cases live there so the shipped DLL carries no fixture.
    ///
    /// No catalogue string lives here: the one notice is translated at its
    /// I18n.Tr call site in ApiClient (#464). The words returned below
    /// (read_session_pending, secure_route_required) are identity strings
    /// handed to callbacks as failure text, never displayed.
    /// </summary>
    internal sealed partial class ReadGateRules
    {
        internal const string ModeOff = "off";
        internal const string ModeLog = "log";
        internal const string ModeEnforce = "enforce";
        internal const string ModeUnknown = "unknown";

        /// <summary>The failure text of a gated GET that waited the whole
        /// hold without a session (requirement 33).</summary>
        internal const string FailPendingWord = "read_session_pending";
        /// <summary>The failure text of a gated GET on a transport that
        /// cannot carry the session (the plaintext fallback).</summary>
        internal const string FailSecureRouteWord = "secure_route_required";

        /// <summary>Hold polling interval and bound (requirement 33).</summary>
        internal const double HoldPollSeconds = 0.5;
        internal const double HoldLimitSeconds = 20.0;
        /// <summary>Mode poll cadence while running (requirement 35).</summary>
        internal const double ModePollSeconds = 300.0;
        /// <summary>Replication-pending retry delays (requirement 34).</summary>
        internal static readonly double[] ReplicationRetryDelays = { 1.0, 2.0, 4.0, 8.0 };
        /// <summary>The single retry after read_gate_unavailable.</summary>
        internal const double UnavailableRetrySeconds = 5.0;

        /// <summary>The process-wide instance ApiClient uses. The harness
        /// builds its own instances, one per case.</summary>
        internal static readonly ReadGateRules Current = new ReadGateRules();

        private string _advertised = ModeOff;
        private bool _enforceLatched;
        private List<string[]> _open;            // null until an advert carried the list
        private bool _fallbackNoticeTaken;
        private bool _pollRequested;

        internal string AdvertisedMode { get { return _advertised; } }
        internal bool EnforceLatched { get { return _enforceLatched; } }
        internal bool HasOpenList { get { return _open != null; } }

        /// <summary>Whether gated GETs are held now: the advert said
        /// enforce, or a refusal latched it (a client that booted under `log`
        /// learns the flip from its first refusal).</summary>
        internal bool Enforcing { get { return _enforceLatched; } }

        // -- the advert (requirement 35) -------------------------------------

        /// <summary>Feed one /mod-version answer's `read_gate` word and its
        /// raw body (for `read_gate_open`). `enforce` latches; `log` and
        /// `off` clear the latch; `unknown`, an absent field and any other
        /// word leave it as it was. A body without the list leaves the last
        /// list in place. Returns the mode word to log.</summary>
        internal string OnModeAdvert(string mode, string body)
        {
            string m = string.IsNullOrEmpty(mode) ? null : mode.Trim();
            if (m == ModeEnforce) _enforceLatched = true;
            else if (m == ModeLog || m == ModeOff) _enforceLatched = false;
            if (m == ModeOff || m == ModeLog || m == ModeEnforce || m == ModeUnknown) _advertised = m;
            List<string> list = ParseOpenList(body);
            if (list != null) SetOpenTemplates(list);
            return m ?? "(absent)";
        }

        internal void SetOpenTemplates(IEnumerable<string> templates)
        {
            var parsed = new List<string[]>();
            foreach (string t in templates)
                if (!string.IsNullOrEmpty(t) && t.StartsWith("/", StringComparison.Ordinal))
                    parsed.Add(t.Split('/'));
            _open = parsed;
        }

        /// <summary>`read_gate_open` out of a /mod-version body, by hand: Unity's
        /// JsonUtility silently fails on arrays inside objects, so the codebase
        /// splits strings (CLAUDE.md). Null when the field is absent or
        /// malformed; an empty list when it is present and empty.</summary>
        internal static List<string> ParseOpenList(string body)
        {
            if (string.IsNullOrEmpty(body)) return null;
            int k = body.IndexOf("\"read_gate_open\"", StringComparison.Ordinal);
            if (k < 0) return null;
            int open = body.IndexOf('[', k);
            if (open < 0) return null;
            int close = body.IndexOf(']', open);
            if (close < 0) return null;
            var list = new List<string>();
            int i = open + 1;
            while (i < close)
            {
                int q1 = body.IndexOf('"', i);
                if (q1 < 0 || q1 > close) break;
                int q2 = body.IndexOf('"', q1 + 1);
                if (q2 < 0 || q2 > close) return null;
                list.Add(body.Substring(q1 + 1, q2 - q1 - 1));
                i = q2 + 1;
            }
            return list;
        }

        // -- OPEN versus gated (requirement 32) ------------------------------

        /// <summary>Whether a GET to `url` is one the gate can refuse for want
        /// of a read credential. Only /api/v1/ paths are considered; a path
        /// that matches an advertised OPEN template is not gated. With no list
        /// yet (a latch from a refusal before any advert) every /api/v1/ path
        /// but /mod-version counts as gated, and the refusal also asks for an
        /// immediate mode poll, which brings the list.</summary>
        internal bool IsGated(string url)
        {
            string path = PathOf(url);
            if (path == null || !path.StartsWith("/api/v1/", StringComparison.Ordinal)) return false;
            if (path == "/api/v1/mod-version") return false;
            if (_open == null) return true;
            string[] segs = path.Split('/');
            foreach (string[] t in _open)
                if (TemplateMatches(t, segs)) return false;
            return true;
        }

        /// <summary>The path of an absolute or root-relative URL, without its
        /// query or fragment.</summary>
        internal static string PathOf(string url)
        {
            if (string.IsNullOrEmpty(url)) return null;
            string s = url;
            int scheme = s.IndexOf("://", StringComparison.Ordinal);
            if (scheme >= 0)
            {
                int slash = s.IndexOf('/', scheme + 3);
                s = slash < 0 ? "/" : s.Substring(slash);
            }
            int cut = s.IndexOfAny(new[] { '?', '#' });
            if (cut >= 0) s = s.Substring(0, cut);
            return s;
        }

        /// <summary>One template against one path, segment by segment. A
        /// segment holding `{name}` matches any non-empty text in that
        /// place, with the literal text around it (`{size}.png`) required
        /// verbatim, as Starlette's default path convertor does.</summary>
        internal static bool TemplateMatches(string[] template, string[] path)
        {
            if (template.Length != path.Length) return false;
            for (int i = 0; i < template.Length; i++)
            {
                string t = template[i], p = path[i];
                int b = t.IndexOf('{');
                if (b < 0) { if (!string.Equals(t, p, StringComparison.Ordinal)) return false; continue; }
                int e = t.IndexOf('}', b);
                if (e < 0) { if (!string.Equals(t, p, StringComparison.Ordinal)) return false; continue; }
                string pre = t.Substring(0, b), post = t.Substring(e + 1);
                if (p.Length <= pre.Length + post.Length) return false;
                if (!p.StartsWith(pre, StringComparison.Ordinal) || !p.EndsWith(post, StringComparison.Ordinal)) return false;
            }
            return true;
        }

        // -- the hold (requirement 33) ---------------------------------------

        internal enum Hold { Send, Wait, FailPending, FailSecureRoute }

        /// <summary>What a GET does now. Keyed on enforce only, so in `off`
        /// and `log` every GET is sent exactly as before. Under enforce an
        /// OPEN GET is sent at once; a gated GET on a transport that cannot
        /// carry the session fails locally (it is never sent without the
        /// token); a gated GET with a fresh session is sent; otherwise it
        /// waits, polling every HoldPollSeconds, until HoldLimitSeconds have
        /// passed, then fails locally.</summary>
        internal Hold ShouldHold(string url, bool secureTransport, bool hasFreshSession, double waitedSeconds)
        {
            if (!Enforcing || !IsGated(url)) return Hold.Send;
            if (!secureTransport) return Hold.FailSecureRoute;
            if (hasFreshSession) return Hold.Send;
            if (waitedSeconds >= HoldLimitSeconds) return Hold.FailPending;
            return Hold.Wait;
        }

        /// <summary>The fallback notice, once per process: true exactly the
        /// first time it is asked after a FailSecureRoute.</summary>
        internal bool TakeFallbackNotice()
        {
            if (_fallbackNoticeTaken) return false;
            _fallbackNoticeTaken = true;
            return true;
        }

        // -- refusal and retry (requirement 34) ------------------------------

        internal enum Next { Deliver, ResessionRetry, DelayRetry }

        /// <summary>Per-request retry bookkeeping, one per GET.</summary>
        internal sealed class Attempts
        {
            internal int Resession;
            internal int Replication;
            internal int Unavailable;
        }

        internal struct Verdict
        {
            internal Next Next;
            /// <summary>Seconds to wait before the retry (DelayRetry).</summary>
            internal double Delay;
            /// <summary>Hand the response to HandleSessionReject first.</summary>
            internal bool PassToSessionReject;
            /// <summary>The 1-based number of this replication retry, for the log.</summary>
            internal int ReplicationRetry;
            /// <summary>Which gate refusal this was ("" when none).</summary>
            internal string Refusal;
        }

        /// <summary>The gate's refusal word a 401 carries, or null.
        /// `read_credential_required` and `player_session_required` are the
        /// gate's alone. `session_required` is ALSO what the server's
        /// session-checked handlers answer, in every stage; it counts as the
        /// gate's only when the answer carries the gate's
        /// `Cache-Control: no-store` mark (every gate refusal carries it, and
        /// in `off` and `log` no handler 401 does). Without that test a
        /// handler's 401 in stage 0 would latch enforce and start holding
        /// reads that the server still answers.</summary>
        internal static string GateRefusal401(string body, string cacheControl)
        {
            if (string.IsNullOrEmpty(body)) return null;
            if (body.IndexOf("read_credential_required", StringComparison.Ordinal) >= 0) return "read_credential_required";
            if (body.IndexOf("player_session_required", StringComparison.Ordinal) >= 0) return "player_session_required";
            if (body.IndexOf("session_required", StringComparison.Ordinal) >= 0
                && cacheControl != null && cacheControl.IndexOf("no-store", StringComparison.OrdinalIgnoreCase) >= 0)
                return "session_required";
            return null;
        }

        /// <summary>What to do with one answer to a GET. A 401 carrying a
        /// gate refusal word latches enforce, goes through
        /// HandleSessionReject, and is retried ONCE after a fresh session (the
        /// caller holds as in ShouldHold); a second is delivered as an
        /// ordinary failure. A 503 session_replication_pending keeps the
        /// token, skips HandleSessionReject, and is retried after 1, 2, 4 and
        /// 8 s, then delivered. A 503 read_gate_unavailable is retried once
        /// after 5 s. Every gate refusal asks for one mode poll. Anything else
        /// is delivered untouched (a handler's own 401 keeps today's path).</summary>
        internal Verdict OnRefusal(long code, string body, string cacheControl, Attempts attempts)
        {
            var v = new Verdict { Next = Next.Deliver, Refusal = "" };
            if (code == 401)
            {
                string word = GateRefusal401(body, cacheControl);
                if (word == null) return v;
                v.Refusal = word;
                v.PassToSessionReject = true;
                _enforceLatched = true;
                _pollRequested = true;
                if (attempts.Resession < 1) { attempts.Resession++; v.Next = Next.ResessionRetry; }
                return v;
            }
            if (code == 503 && body != null)
            {
                if (body.IndexOf("session_replication_pending", StringComparison.Ordinal) >= 0)
                {
                    v.Refusal = "session_replication_pending";
                    _pollRequested = true;
                    if (attempts.Replication < ReplicationRetryDelays.Length)
                    {
                        v.Delay = ReplicationRetryDelays[attempts.Replication];
                        attempts.Replication++;
                        v.ReplicationRetry = attempts.Replication;
                        v.Next = Next.DelayRetry;
                    }
                    return v;
                }
                if (body.IndexOf("read_gate_unavailable", StringComparison.Ordinal) >= 0)
                {
                    v.Refusal = "read_gate_unavailable";
                    _pollRequested = true;
                    if (attempts.Unavailable < 1)
                    {
                        attempts.Unavailable++;
                        v.Delay = UnavailableRetrySeconds;
                        v.Next = Next.DelayRetry;
                    }
                    return v;
                }
            }
            return v;
        }

        /// <summary>True once per gate refusal since the last call: the mode
        /// poll runs one extra read when it sees it.</summary>
        internal bool TakePollRequest()
        {
            bool r = _pollRequested;
            _pollRequested = false;
            return r;
        }
    }
}
