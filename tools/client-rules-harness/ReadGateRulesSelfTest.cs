using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The harness's half of ReadGateRules (verified reads, requirements
    /// 30-35), suite `readgate`. It lives here, not in plugin/, so the
    /// shipped DLL carries no fixture. Every case prints its name whatever
    /// its verdict, and each decision has a control that moves exactly the
    /// input deciding it (#391). URLs are synthetic.
    /// </summary>
    internal sealed partial class ReadGateRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private const string Base = "https://example.test:8444";
        private const string GatedUrl = Base + "/api/v1/players/s1/stats?season=3";
        private const string OpenUrl = Base + "/api/v1/alerts";
        private const string AtlasUrl = Base + "/api/v1/pc-face/motion/p1/r2/en/card.png";

        private static string Advert(string mode, params string[] open)
        {
            var sb = new StringBuilder("{\"version\":\"1.41.0\",\"read_gate\":\"").Append(mode).Append("\",\"read_gate_open\":[");
            for (int i = 0; i < open.Length; i++)
                sb.Append(i == 0 ? "" : ",").Append('"').Append(open[i]).Append('"');
            return sb.Append("],\"min_version\":\"1.40.0\"}").ToString();
        }

        private static readonly string[] OpenSet =
        {
            "/api/v1/alerts", "/api/v1/i18n/pack/{locale}", "/api/v1/mod-version",
            "/api/v1/release-notes", "/api/v1/health",
        };

        private static ReadGateRules Enforced()
        {
            var r = new ReadGateRules();
            r.OnModeAdvert(ModeEnforce, Advert(ModeEnforce, OpenSet));
            return r;
        }

        internal static SelfTestResult SelfTest()
        {
            var res = new SelfTestResult();

            // -- stages 0 and 1 change nothing (bar 13) ----------------------
            {
                var r = new ReadGateRules();
                var h = r.ShouldHold(GatedUrl, false, false, 0);
                Check(res, "no advert yet: a gated GET with no session is sent, on the fallback too", h == Hold.Send, h.ToString());
                r.OnModeAdvert(ModeOff, Advert(ModeOff, OpenSet));
                h = r.ShouldHold(GatedUrl, true, false, 0);
                Check(res, "off: a gated GET with no session is sent", h == Hold.Send, h.ToString());
                r.OnModeAdvert(ModeLog, Advert(ModeLog, OpenSet));
                h = r.ShouldHold(GatedUrl, false, false, 0);
                Check(res, "log: a gated GET with no session is sent, on the fallback too", h == Hold.Send, h.ToString());
                var v = r.OnRefusal(401, "{\"detail\":\"session_required\"}", null, new Attempts());
                Check(res, "log: a handler's own 401 session_required (no gate mark) is delivered and latches nothing",
                      v.Next == Next.Deliver && !v.PassToSessionReject && !r.Enforcing && v.Refusal.Length == 0,
                      v.Next + " latched=" + r.Enforcing);
                v = r.OnRefusal(401, "{\"detail\":\"session_required\"}", "no-store, private", new Attempts());
                Check(res, "control: the same 401 carrying the gate's no-store mark is the gate's and latches",
                      v.Next == Next.ResessionRetry && r.Enforcing, v.Next + " latched=" + r.Enforcing);
            }

            // -- the hold under enforce (requirement 33) ---------------------
            {
                var r = Enforced();
                var h = r.ShouldHold(OpenUrl, true, false, 0);
                Check(res, "enforce: an OPEN GET with no session is sent", h == Hold.Send, h.ToString());
                h = r.ShouldHold(OpenUrl, false, false, 0);
                Check(res, "enforce: an OPEN GET on the fallback is sent", h == Hold.Send, h.ToString());
                h = r.ShouldHold(GatedUrl, true, false, 0);
                Check(res, "enforce: a gated GET with no session waits", h == Hold.Wait, h.ToString());
                h = r.ShouldHold(GatedUrl, true, false, 19.5);
                Check(res, "enforce: still waiting at 19.5 s", h == Hold.Wait, h.ToString());
                h = r.ShouldHold(GatedUrl, true, false, 20.0);
                Check(res, "enforce: at 20 s it fails locally (read_session_pending)", h == Hold.FailPending && FailPendingWord == "read_session_pending", h.ToString());
                h = r.ShouldHold(GatedUrl, true, true, 3.0);
                Check(res, "enforce: a gated GET with a fresh session is sent", h == Hold.Send, h.ToString());
                h = r.ShouldHold(GatedUrl, false, true, 0);
                Check(res, "enforce: a gated GET on the fallback fails locally (secure_route_required), session or not",
                      h == Hold.FailSecureRoute && FailSecureRouteWord == "secure_route_required", h.ToString());
                h = r.ShouldHold(AtlasUrl, true, false, 0);
                Check(res, "enforce: a face atlas (not advertised OPEN) waits like any gated GET", h == Hold.Wait, h.ToString());
                bool first = r.TakeFallbackNotice(), second = r.TakeFallbackNotice();
                Check(res, "the fallback notice is given once per process", first && !second, first + "," + second);
            }

            // -- the one OPEN/gated signal (requirement 32) ------------------
            {
                var r = Enforced();
                Check(res, "a template with a parameter matches one segment", !r.IsGated(Base + "/api/v1/i18n/pack/es"), "es");
                Check(res, "control: an extra segment is not that template", r.IsGated(Base + "/api/v1/i18n/pack/es/x"), "es/x");
                Check(res, "the query string does not decide", !r.IsGated(Base + "/api/v1/alerts?since=5"), "alerts?since");
                Check(res, "a non-/api/v1 path is never gated", !r.IsGated("https://api.github.com/repos/x/y/releases"), "github");
                var t = "/api/v1/pc-face/motion/{print_id}/{motion_rev}/{locale}/{size}.png".Split('/');
                Check(res, "a parameter with literal text around it ({size}.png) needs that text",
                      TemplateMatches(t, "/api/v1/pc-face/motion/a/b/en/card.png".Split('/'))
                      && !TemplateMatches(t, "/api/v1/pc-face/motion/a/b/en/card.gif".Split('/')), "png vs gif");
                var bare = new ReadGateRules();
                bare.OnRefusal(401, "{\"detail\":\"read_credential_required\"}", "no-store, private", new Attempts());
                Check(res, "latched with no list yet: every /api/v1 path is gated but /mod-version",
                      bare.IsGated(OpenUrl) && !bare.IsGated(Base + "/api/v1/mod-version"), "alerts gated, mod-version open");
                var parsed = ParseOpenList(Advert(ModeLog, "/a", "/b/{c}"));
                Check(res, "the advert's list is read by hand", parsed != null && parsed.Count == 2 && parsed[1] == "/b/{c}",
                      parsed == null ? "null" : string.Join(";", parsed));
                Check(res, "an advert without the list leaves it absent (null), an empty one is empty",
                      ParseOpenList("{\"read_gate\":\"off\"}") == null && ParseOpenList(Advert(ModeOff)).Count == 0, "null / 0");
                var keep = Enforced();
                keep.OnModeAdvert(ModeEnforce, "{\"read_gate\":\"enforce\"}");
                Check(res, "an advert without the list keeps the last list", !keep.IsGated(OpenUrl), "alerts open");
            }

            // -- refusal and retry (requirement 34) --------------------------
            foreach (string word in new[] { "read_credential_required", "player_session_required" })
            {
                var r = new ReadGateRules();
                r.OnModeAdvert(ModeLog, Advert(ModeLog, OpenSet));
                var a = new Attempts();
                var v1 = r.OnRefusal(401, "{\"detail\":\"" + word + "\"}", null, a);
                var v2 = r.OnRefusal(401, "{\"detail\":\"" + word + "\"}", null, a);
                Check(res, "401 " + word + ": latches enforce, passes to the session reject, retries once, then delivers",
                      v1.Next == Next.ResessionRetry && v1.PassToSessionReject && r.Enforcing && v1.Refusal == word
                      && v2.Next == Next.Deliver && v2.PassToSessionReject,
                      v1.Next + "/" + v2.Next + " latched=" + r.Enforcing);
                Check(res, "401 " + word + ": asks for one mode poll", r.TakePollRequest() && !r.TakePollRequest(), "once");
            }
            {
                var r = new ReadGateRules();
                var a = new Attempts();
                var delays = new List<string>();
                Verdict v;
                bool anyReject = false;
                do
                {
                    v = r.OnRefusal(503, "{\"detail\":\"session_replication_pending\"}", "no-store, private", a);
                    anyReject |= v.PassToSessionReject;
                    if (v.Next == Next.DelayRetry) delays.Add(v.Delay + "@" + v.ReplicationRetry);
                } while (v.Next == Next.DelayRetry && delays.Count < 10);
                string got = string.Join(",", delays);
                Check(res, "503 session_replication_pending: retried after 1, 2, 4 and 8 s, then delivered",
                      got == "1@1,2@2,4@3,8@4" && v.Next == Next.Deliver, got + " then " + v.Next);
                Check(res, "503 session_replication_pending: keeps the token (no session reject) and latches nothing",
                      !anyReject && !r.Enforcing, "reject=" + anyReject + " latched=" + r.Enforcing);
            }
            {
                var r = new ReadGateRules();
                var a = new Attempts();
                var v1 = r.OnRefusal(503, "{\"detail\":\"read_gate_unavailable\"}", "no-store, private", a);
                var v2 = r.OnRefusal(503, "{\"detail\":\"read_gate_unavailable\"}", "no-store, private", a);
                Check(res, "503 read_gate_unavailable: retried once after 5 s, then delivered",
                      v1.Next == Next.DelayRetry && v1.Delay == 5.0 && v2.Next == Next.Deliver && !v1.PassToSessionReject,
                      v1.Next + "@" + v1.Delay + "/" + v2.Next);
                var c = new ReadGateRules();
                var v3 = c.OnRefusal(503, "{\"detail\":\"maintenance\"}", null, new Attempts());
                var v4 = c.OnRefusal(500, "{\"detail\":\"read_credential_required\"}", null, new Attempts());
                Check(res, "control: another 503, and a 500 carrying a gate word, are delivered untouched and ask no poll",
                      v3.Next == Next.Deliver && v4.Next == Next.Deliver && !c.Enforcing && !c.TakePollRequest(),
                      v3.Next + "/" + v4.Next);
            }

            // -- prolonged_mint_failure_zero_gated_sends (requirement 33) -----
            {
                var sim = Simulate(Enforced(), secure: true, sessionAt: -1);
                Check(res, "prolonged_mint_failure_zero_gated_sends: 120 s without a session, zero gated sends, every OPEN GET sent",
                      sim.GatedSent == 0 && sim.OpenSent == sim.OpenStarted && sim.OpenStarted > 0 && sim.GatedFailed > 0,
                      sim.ToString());
                var fb = Simulate(Enforced(), secure: false, sessionAt: -1);
                Check(res, "prolonged_mint_failure_zero_gated_sends: the same on the fallback",
                      fb.GatedSent == 0 && fb.OpenSent == fb.OpenStarted && fb.OpenStarted > 0, fb.ToString());
                var ctl = Simulate(Enforced(), secure: true, sessionAt: 60.0);
                Check(res, "control: a session minted at 60 s sends the gated GETs still waiting and every later one",
                      ctl.GatedSent > 0 && ctl.GatedSent < ctl.GatedStarted, ctl.ToString());
            }

            // -- enforce_to_log_unchanged_process (requirement 35) ------------
            foreach (string back in new[] { ModeLog, ModeOff })
            {
                var r = new ReadGateRules();
                r.OnModeAdvert(ModeLog, Advert(ModeLog, OpenSet));
                r.OnRefusal(401, "{\"detail\":\"read_credential_required\"}", "no-store, private", new Attempts());
                var held = r.ShouldHold(GatedUrl, true, false, 0);
                var fbHeld = r.ShouldHold(GatedUrl, false, false, 0);
                r.OnModeAdvert(ModeUnknown, Advert(ModeUnknown, OpenSet));
                var stillHeld = r.ShouldHold(GatedUrl, true, false, 0);
                r.OnModeAdvert(back, Advert(back, OpenSet));
                var after = r.ShouldHold(GatedUrl, true, false, 0);
                var fbAfter = r.ShouldHold(GatedUrl, false, false, 0);
                Check(res, "enforce_to_log_unchanged_process: latched, then '" + back + "' resumes gated sends in the same instance, on the fallback too",
                      held == Hold.Wait && fbHeld == Hold.FailSecureRoute && after == Hold.Send && fbAfter == Hold.Send,
                      held + "," + fbHeld + " -> " + after + "," + fbAfter);
                Check(res, "enforce_to_log_unchanged_process: 'unknown' leaves the latch as it was (before '" + back + "')",
                      stillHeld == Hold.Wait, stillHeld.ToString());
            }

            // -- latched before any advert (merged hold 3, Codex client merged
            // round 1 HIGH 2) ---------------------------------------------------
            // A process whose first word from the gate was a refusal latched
            // enforce with no OPEN list. Its next periodic /mod-version read is
            // stamped with X-Mod-Version, so the answer carries the mode and the
            // list: a log or off advert clears the latch and the list arrives,
            // in the same process. The control is the answer an unstamped read
            // gets (the server omits both fields; ExtractJsonString reads ""):
            // nothing changes.
            foreach (string back in new[] { ModeLog, ModeOff })
            {
                var r = new ReadGateRules();
                r.OnRefusal(401, "{\"detail\":\"read_credential_required\"}", "no-store, private", new Attempts());
                bool latchedBare = r.Enforcing && !r.HasOpenList && r.IsGated(OpenUrl);
                var held = r.ShouldHold(GatedUrl, true, false, 0);
                string word = r.OnModeAdvert(back, Advert(back, OpenSet));
                var after = r.ShouldHold(GatedUrl, true, false, 0);
                Check(res, "latched_before_any_advert: the next periodic read's '" + back + "' advert clears the latch and brings the OPEN list",
                      latchedBare && held == Hold.Wait && word == back && !r.Enforcing && r.HasOpenList
                      && !r.IsGated(OpenUrl) && r.IsGated(GatedUrl) && after == Hold.Send && r.AdvertisedMode == back,
                      "before latched=" + latchedBare + " " + held + "; after word=" + word + " latched=" + r.Enforcing
                      + " list=" + r.HasOpenList + " " + after);
            }
            {
                var r = new ReadGateRules();
                r.OnRefusal(401, "{\"detail\":\"read_credential_required\"}", "no-store, private", new Attempts());
                string word = r.OnModeAdvert("", "{\"version\":\"1.41.0\",\"min_version\":\"1.40.0\"}");
                var after = r.ShouldHold(GatedUrl, true, false, 0);
                Check(res, "control: latched_before_any_advert, a periodic answer without the advert fields keeps the latch and no list",
                      word == "(absent)" && r.Enforcing && !r.HasOpenList && r.IsGated(OpenUrl) && after == Hold.Wait,
                      "word=" + word + " latched=" + r.Enforcing + " list=" + r.HasOpenList + " " + after);
            }

            return res;
        }

        private sealed class SimResult
        {
            internal int GatedStarted, GatedSent, GatedFailed, OpenStarted, OpenSent;
            public override string ToString()
            {
                return "gated started=" + GatedStarted + " sent=" + GatedSent + " failed=" + GatedFailed
                       + " open started=" + OpenStarted + " sent=" + OpenSent;
            }
        }

        /// <summary>120 simulated seconds on a 0.5 s tick: every 3 s one gated
        /// and one OPEN GET start, and each is stepped through ShouldHold the
        /// way ApiClient.ReadGateHold steps it, until it sends or fails. A
        /// session appears at `sessionAt` (never when negative).</summary>
        private static SimResult Simulate(ReadGateRules r, bool secure, double sessionAt)
        {
            var s = new SimResult();
            var waiting = new List<KeyValuePair<string, double>>();
            for (int tick = 0; tick <= 240; tick++)
            {
                double now = tick * HoldPollSeconds;
                if (tick % 6 == 0)
                {
                    waiting.Add(new KeyValuePair<string, double>(GatedUrl, now)); s.GatedStarted++;
                    waiting.Add(new KeyValuePair<string, double>(OpenUrl, now)); s.OpenStarted++;
                }
                bool session = sessionAt >= 0 && now >= sessionAt;
                for (int i = waiting.Count - 1; i >= 0; i--)
                {
                    var req = waiting[i];
                    var h = r.ShouldHold(req.Key, secure, session, now - req.Value);
                    if (h == Hold.Wait) continue;
                    bool gated = req.Key == GatedUrl;
                    if (h == Hold.Send) { if (gated) s.GatedSent++; else s.OpenSent++; }
                    else if (gated) s.GatedFailed++;
                    waiting.RemoveAt(i);
                }
            }
            // Still waiting at the end counts as neither sent nor failed.
            return s;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
