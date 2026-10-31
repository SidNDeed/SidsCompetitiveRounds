using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;

namespace CompetitiveRounds
{
    /// <summary>
    /// The harness's half of ServerTextRules (v1.41.0 late i18n, round 3). It
    /// lives HERE, under tools/, so the shipped DLL carries no fixture: the
    /// plugin build compiles only the rules half of this partial class.
    ///
    /// Every recognition rule has a case and a control. The H1 controls
    /// (wrong field, code in another field, unknown object) each show the
    /// round-2 substring rule answering YES on the same fixture, so the case
    /// measures the structural reading and not an easy input (#391). The
    /// English cases assert the server's own text comes back unchanged; the
    /// "es" cases assert the catalogue row is reached.
    /// </summary>
    internal static partial class ServerTextRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private static string Env(int status, string body) { return "HTTP " + status + ": " + body; }
        private static string Q(string s) { return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\""; }
        private static string DetailBody(string d) { return "{\"detail\":" + Q(d) + "}"; }

        // Every RefusalTemplate rule in ServerTextRules.cs as "status|N or T|template"
        // (N: numeric holes, T: text holes); the coverage test checks this table
        // against the calls in the source.
        private static readonly string[] TEMPLATES = {
            "402|N|" + "Insufficient gold: have {0}, need {1}",
            "429|N|" + "{0} submissions already awaiting review — wait for those first",
            "400|N|" + "PNG missing or too large ({0} MB, 1,600,000 base64 characters max)",
            "409|N|" + "missing frames: have {0} of {1}",
            "400|N|" + "GIF is {0} KB — the limit is {1} KB. Reduce the frame size or the number of colours and re-export.",
            "400|N|" + "GIF frames are {0}x{1} — the limit is 2048x2048",
            "400|N|" + "GIF has {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).",
            "400|N|" + "GIF has more than {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).",
            "400|N|" + "GIF has {0} frame(s) — an animation needs at least 2. Upload a PNG instead for static art.",
            "400|N|" + "GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at least {5} ms and re-export; the server will not change the speed for you.",
            "400|N|" + "GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at most {5} ms and re-export; the server will not change the speed for you.",
            "400|N|" + "converted frame {0} is {1} KB — the per-image limit is {2} KB. Simplify the art or reduce its colour count.",
            "400|N|" + "GIF decoded inconsistently ({0} of {1} frames) — re-export it and try again.",
            "400|N|" + "must be exactly 512x512 (got {0}x{1})",
            "400|N|" + "PNG has {0} stray byte(s) after IEND",
            "400|T|" + "bad frame PNG: {0}",
            "400|T|" + "Published cosmetic source must be a transparent 512x512 PNG ({0})",
            "400|T|" + "malformed PNG (bad CRC on {0} chunk)",
            "400|T|" + "unreadable PNG: {0}",
            "400|T|" + "could not process GIF: {0}",
            "400|N|" + "frame_count must be 2-{0}",
            "400|N|" + "frame_no must be 2-{0}",
        };

        // A detail that fills every hole of a template: 1 for a number, x for text.
        private static string Fill(string template, bool text)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < template.Length; i++)
            {
                if (template[i] == '{' && i + 2 < template.Length && template[i + 2] == '}') { sb.Append(text ? "x" : "1"); i += 2; continue; }
                sb.Append(template[i]);
            }
            return sb.ToString();
        }

        // The round-3 template match (^ and $), kept only as the T negative control's witness.
        private static bool R3Template(string d, string template, bool text)
        {
            var sb = new StringBuilder("^");
            for (int i = 0; i < template.Length; i++)
            {
                if (template[i] == '{' && i + 2 < template.Length && template[i + 2] == '}') { sb.Append(text ? "(.+?)" : "(-?[0-9]+(?:\\.[0-9]+)?)"); i += 2; continue; }
                sb.Append(Regex.Escape(template[i].ToString()));
            }
            sb.Append('$');
            return Regex.IsMatch(d, sb.ToString());
        }

        // x placed inside an array inside an object beside a known detail: where
        // the member readers only balance delimiters, so the validator alone refuses it.
        private static string Nest(string x) { return "{\"detail\":\"Sold out\",\"ctx\":{\"a\":[0," + x + "]}}"; }

        // The round-3 reader: the member readers alone, with no validator before them.
        private static string R3DetailError(string body)
        {
            Dictionary<string, string> top, inner;
            string raw, s;
            if (!Members(body, out top) || !top.TryGetValue("detail", out raw)) return null;
            return Members(raw, out inner) && inner.TryGetValue("error", out raw) && JsonString(raw, out s) ? s : null;
        }

        // The round-2 rules, kept here only as the negative controls' witness.
        private static bool R2Album(string resp)
        {
            return resp != null && resp.StartsWith("HTTP 426", StringComparison.Ordinal)
                   && resp.Contains("\"music_purchase_requires_update\"");
        }
        private static bool R2PriceChanged(string resp)
        {
            return resp != null && resp.StartsWith("HTTP 409", StringComparison.Ordinal)
                   && resp.IndexOf("price_changed", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        // Every (status, detail) the protocol, read-gate and middleware rows
        // answer with the server's own text; the coverage test checks this
        // list against ServerTextRules.cs and the server.
        private static readonly string[] EXACT_DETAIL =
        {
            "401|session_required", "403|Invalid signature", "403|service_account_forbidden",
            "400|expected_price_required", "400|scale and offsets must be numbers", "400|scale and offsets must be finite",
            "400|Invalid signature version", "400|Unsupported signature version", "400|Signed placement integers are required",
            "400|Valid upload_request_id is required", "400|Signed animation fields are required", "400|anim_fps must be 0.5-15",
            "400|frames_hash must be sha256 hex", "400|slot must be eyes, mouth or detail", "400|png_base64 is not valid base64",
            "400|submission_id and frame_no are required", "400|frame png_base64 is not valid base64", "400|submission_id is required",
            "400|gif_base64 is not valid base64", "400|Invalid placement request", "400|Invalid placement revision",
            "400|Invalid catalog placement request", "400|Cosmetic slot does not match its catalog SKU",
            "400|PNG hash does not match the payload", "503|HMAC not configured", "503|session_check_unavailable",
            "503|service_policy_unavailable", "503|image_processing_unavailable", "503|gif_processing_unavailable",
            "503|read_gate_unavailable", "429|rate_limited", "503|session_replication_pending", "401|player_session_required",
            "401|operator_key_invalid", "401|read_credential_required", "403|internal_key_required",
            "404|Cosmetic submission not found", "404|Player not found", "409|Sold out",
        };
        private static readonly string[] EXACT_ERROR =
        {
            "403|forbidden", "413|payload_too_large", "429|rate_limited", "503|rate_limited", "503|maintenance",
        };

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            I18nCatalogues.Install();
            I18n.HarnessLocale = "en";

            // -- A: the envelope ---------------------------------------------------
            {
                var a = Read(Env(404, DetailBody("Player not found")));
                Check(r, "A1 a string detail is read whole", a != null && a.Status == 404 && a.Detail == "Player not found",
                      a == null ? null : a.Status + "|" + a.Detail);
                string ra = Env(429, "{\"error\":\"rate_limited\"}") + "\nRetry-After: 30";
                Check(r, "A2 a Retry-After line after the body is not part of it", TrRefusal(ra) == "rate_limited", TrRefusal(ra));
                string esc = Env(409, "{\"detail\":\"Not for sale yet \\u2014 the artist hasn't opened sales\"}");
                Check(r, "A3 an escaped detail is unescaped before it is matched",
                      TrRefusal(esc) == "Not for sale yet — the artist hasn't opened sales", TrRefusal(esc));
                bool none = Read("outdated") == null && Read("no-consent") == null && Read(null) == null
                            && Read("HTTP 200: {}") == null && Read("HTTP 4o4: {}") == null && Read("HTTP 404 {}") == null;
                Check(r, "A4 a sentinel, a success and a malformed status line are not refusals", none, none.ToString());
                var h = Read(Env(503, "<html>busy</html>"));
                Check(r, "A5 a body that is not JSON yields the status alone and no mapping",
                      h != null && h.Status == 503 && h.Detail == null && h.Error == null && TrRefusal(Env(503, "<html>busy</html>")) == null,
                      h == null ? null : h.Status.ToString());
                string dup = Env(404, "{\"detail\":\"Sold out\",\"detail\":\"Player not found\"}");
                Check(r, "A6 a duplicated key makes the body unreadable", TrRefusal(dup) == null, TrRefusal(dup));
                string junk = Env(404, DetailBody("Player not found") + "x");
                Check(r, "A7 anything after the object makes the body unreadable", TrRefusal(junk) == null, TrRefusal(junk));
                string ctl = Env(404, " " + DetailBody("Player not found") + " ");
                Check(r, "A7c control: whitespace around the object is allowed", TrRefusal(ctl) == "Player not found", TrRefusal(ctl));
                string nested = Env(409, "{\"meta\":{\"a\":[1,{\"b\":\"}\"}]},\"detail\":\"Sold out\"}");
                Check(r, "A8 a nested value holding a brace in a string is skipped whole", TrRefusal(nested) == "Sold out",
                      TrRefusal(nested));
            }

            // -- B: a code is recognised only by equality with its field --------------
            {
                string ctx = Env(426, "{\"detail\":{\"error\":\"different_refusal\",\"context\":\"music_purchase_requires_update\"}}");
                Check(r, "B1 the album code inside ANOTHER refusal's context is not the album refusal",
                      TrRefusal(ctx) == null, TrRefusal(ctx));
                Check(r, "B1n negative control: the round-2 substring rule answered yes here", R2Album(ctx), R2Album(ctx).ToString());
                string wf = Env(426, "{\"detail\":{\"code\":\"music_purchase_requires_update\"}}");
                Check(r, "B2 the code in a field other than detail.error is not recognised", TrRefusal(wf) == null, TrRefusal(wf));
                Check(r, "B2n negative control: the round-2 substring rule answered yes here", R2Album(wf), R2Album(wf).ToString());
                string uo = Env(426, "{\"detail\":{\"error\":\"something_new\",\"hint\":\"music_purchase_requires_update\"}}");
                Check(r, "B3 an unknown object detail maps to nothing", TrRefusal(uo) == null, TrRefusal(uo));
                Check(r, "B3n negative control: the round-2 substring rule answered yes here", R2Album(uo), R2Album(uo).ToString());
                string ok = Env(426, "{\"detail\":{\"error\":\"music_purchase_requires_update\",\"required\":\"1.41.0\"}}");
                Check(r, "B4 control: detail.error equal to the album code is the album refusal",
                      TrRefusal(ok) == "This album requires a newer mod version", TrRefusal(ok));
                string top = Env(426, "{\"error\":\"music_purchase_requires_update\"}");
                Check(r, "B5 the album code as a top-level error is not the album refusal", TrRefusal(top) == null, TrRefusal(top));

                string pc = Env(409, "{\"detail\":{\"error\":\"price_changed\",\"price\":1200}}");
                Check(r, "B6 price_changed is detail.error on a 409", IsDetailError(pc, 409, "price_changed"), "");
                string pcx = Env(409, "{\"detail\":{\"error\":\"sold_out\",\"context\":\"price_changed\"}}");
                Check(r, "B7 price_changed in another field of a 409 is not price_changed",
                      !IsDetailError(pcx, 409, "price_changed"), "");
                Check(r, "B7n negative control: the round-2 substring rule answered yes here", R2PriceChanged(pcx), "");
                string pcs = Env(409, DetailBody("price_changed"));
                Check(r, "B8 a string detail spelling price_changed is not the object refusal",
                      !IsDetailError(pcs, 409, "price_changed"), "");
                string pcw = Env(400, "{\"detail\":{\"error\":\"price_changed\"}}");
                Check(r, "B9 price_changed on another status is not the purchase refusal", !IsDetailError(pcw, 409, "price_changed"), "");
                string both = Env(503, "{\"detail\":\"Sold out\",\"error\":\"maintenance\"}");
                Check(r, "B10 a detail wins over a top-level error, and is matched on its own status",
                      TrRefusal(both) == null && TrRefusal(Env(409, "{\"detail\":\"Sold out\",\"error\":\"maintenance\"}")) == "Sold out",
                      TrRefusal(both));
                string mw = Env(503, "{\"error\":\"maintenance\"}");
                Check(r, "B11 a middleware answer is read from its top-level error", TrRefusal(mw) == "maintenance", TrRefusal(mw));
                string mws = Env(500, "{\"error\":\"maintenance\"}");
                Check(r, "B11c control: the same code on a status the middleware never uses maps to nothing",
                      TrRefusal(mws) == null, TrRefusal(mws));
                string rep = Env(503, "{\"error\":\"read_replica\",\"detail\":" + Q("This node serves reads only; writes are handled by the primary. Seeing this means a request reached the standby that should not have.") + "}");
                Check(r, "B12 the replica answer shows its detail sentence, not its error code",
                      TrRefusal(rep) == "This node serves reads only; writes are handled by the primary. Seeing this means a request reached the standby that should not have.", TrRefusal(rep));
                string repo = Env(503, "{\"error\":\"read_replica\"}");
                Check(r, "B12c control: the replica code alone is not a middleware answer this map knows",
                      TrRefusal(repo) == null, TrRefusal(repo));
            }

            // -- C: English is the server's text, nothing added ------------------------
            {
                string bad = null;
                foreach (string k in EXACT_DETAIL)
                {
                    int bar = k.IndexOf('|');
                    string d = k.Substring(bar + 1), got = TrRefusal(Env(int.Parse(k.Substring(0, bar)), DetailBody(d)));
                    if (got != d && bad == null) bad = k + " -> " + (got ?? "(null)");
                }
                foreach (string k in EXACT_ERROR)
                {
                    int bar = k.IndexOf('|');
                    string e = k.Substring(bar + 1), got = TrRefusal(Env(int.Parse(k.Substring(0, bar)), "{\"error\":" + Q(e) + "}"));
                    if (got != e && bad == null) bad = k + " -> " + (got ?? "(null)");
                }
                Check(r, "C1 every protocol, read-gate, route and middleware answer shows the server's English unchanged",
                      bad == null, bad ?? (EXACT_DETAIL.Length + EXACT_ERROR.Length).ToString());
                string fc = TrRefusal(Env(400, DetailBody("frame_count must be 2-12")));
                string fn = TrRefusal(Env(400, DetailBody("frame_no must be 2-12")));
                Check(r, "C2 the two protocol templates show the server's English unchanged",
                      fc == "frame_count must be 2-12" && fn == "frame_no must be 2-12", fc + " / " + fn);
                string unk = TrRefusal(Env(400, DetailBody("a detail this map has never seen")));
                Check(r, "C3 an unknown detail maps to nothing, so the caller keeps the raw text", unk == null, unk);

                I18n.HarnessLocale = "es";
                string miss = null;
                foreach (string k in EXACT_DETAIL)
                {
                    int bar = k.IndexOf('|');
                    string d = k.Substring(bar + 1), got = TrRefusal(Env(int.Parse(k.Substring(0, bar)), DetailBody(d)));
                    bool codeKept = d.IndexOf('_') < 0 || d.IndexOf(' ') >= 0 || (got != null && got.Contains(d));
                    if ((got == null || got == d || !codeKept) && miss == null) miss = k + " -> " + (got ?? "(null)");
                }
                foreach (string k in EXACT_ERROR)
                {
                    int bar = k.IndexOf('|');
                    string e = k.Substring(bar + 1), got = TrRefusal(Env(int.Parse(k.Substring(0, bar)), "{\"error\":" + Q(e) + "}"));
                    if ((got == null || got == e || !got.Contains(e)) && miss == null) miss = k + " -> " + (got ?? "(null)");
                }
                Check(r, "C4 es: every one of those answers reaches its catalogue row, a code kept beside its words",
                      miss == null, miss ?? "ok");
                string fces = TrRefusal(Env(400, DetailBody("frame_count must be 2-12")));
                Check(r, "C5 es: a protocol template reaches its row with the hole filled",
                      fces == "frame_count debe estar entre 2 y 12", fces);
                string alb = TrRefusal(Env(426, "{\"detail\":{\"error\":\"music_purchase_requires_update\"}}"));
                Check(r, "C6 es: the album refusal reaches its row", alb != null && alb != "This album requires a newer mod version", alb);
                I18n.HarnessLocale = "en";
            }

            // -- V: the whole body is one valid JSON value before any member is read --
            {
                string bad = Env(409, "{\"detail\":{\"error\":\"price_changed\",\"context\":{\"bad\":}}}");
                Check(r, "V1 the invalid body with price_changed inside is unreadable, not the price-change answer",
                      !IsDetailError(bad, 409, "price_changed") && TrRefusal(bad) == null, TrRefusal(bad));
                string badBody = bad.Substring(10);
                Check(r, "V1n negative control: removal, the member readers alone (round 3) read price_changed from that body",
                      R3DetailError(badBody) == "price_changed" && !JsonValid(badBody), R3DetailError(badBody));
                string good = Env(409, "{\"detail\":{\"error\":\"price_changed\",\"context\":{\"ok\":[1,-2.5e+3,true,false,null,\"\\u00e9\\n\"]}}}");
                Check(r, "V1p positive control: the valid price_changed body is still the price-change answer",
                      IsDetailError(good, 409, "price_changed"), good);
                string[] escapes = { "\\x", "\\u12G4", "\\u12", "\\'", "\\U0041", "\\" };
                string esc = null;
                foreach (string e in escapes)
                {
                    string body = "{\"detail\":\"Sold out" + e + "\"}", nested = Nest("\"a" + e + "\"");
                    if ((JsonValid(body) || TrRefusal(Env(409, body)) != null || JsonValid(nested)
                         || TrRefusal(Env(409, nested)) != null) && esc == null) esc = e;
                }
                Check(r, "V2 every invalid escape, in the detail or nested, makes the body unreadable", esc == null, esc ?? "ok");
                string[] nums = { "01", "+1", "1.", ".5", "1e", "1e+", "-", "-01", "1.e5", "0x10", "1E", "--1", "Infinity", "NaN", "1_0" };
                string num = null;
                foreach (string n in nums)
                {
                    string body = "{\"detail\":\"Sold out\",\"n\":" + n + "}", nested = Nest(n);
                    if ((JsonValid(body) || TrRefusal(Env(409, body)) != null || JsonValid(nested)
                         || TrRefusal(Env(409, nested)) != null) && num == null) num = n;
                }
                Check(r, "V3 every bad number form, at the top level or nested, makes the body unreadable", num == null, num ?? "ok");
                string[] okNums = { "0", "-0", "10", "1.5", "-0.25", "1e5", "1E-5", "2.5e+10" };
                string okn = null;
                foreach (string n in okNums)
                    if ((TrRefusal(Env(409, "{\"detail\":\"Sold out\",\"n\":" + n + "}")) != "Sold out"
                         || TrRefusal(Env(409, Nest(n))) != "Sold out") && okn == null) okn = n;
                Check(r, "V3p positive control: every grammatical number is accepted", okn == null, okn ?? "ok");
                string[] tails = { " x", "{}", "]", ",", "\"\"", "0" };
                string tail = null;
                foreach (string t in tails)
                    if (TrRefusal(Env(409, "{\"detail\":\"Sold out\"}" + t)) != null && tail == null) tail = t;
                Check(r, "V4 anything after the top value makes the body unreadable", tail == null, tail ?? "ok");
                string[] lits = { "tru", "True", "nul", "NULL", "falsey", "undefined" };
                string lit = null;
                foreach (string l in lits)
                    if ((TrRefusal(Env(409, "{\"detail\":\"Sold out\",\"v\":" + l + "}")) != null
                         || TrRefusal(Env(409, Nest(l))) != null) && lit == null) lit = l;
                Check(r, "V5 only true, false and null are literals, at the top level or nested", lit == null, lit ?? "ok");
                string[] shapes = { "[1,]", "[,1]", "{\"a\":1,}", "{\"a\"}", "{\"a\" 1}", "{a:1}", "[1 2]", "\"a\tb\"" };
                string shape = null;
                foreach (string sh in shapes)
                    if (TrRefusal(Env(409, "{\"detail\":\"Sold out\",\"v\":" + sh + "}")) != null && shape == null) shape = sh;
                Check(r, "V6 a malformed nested array, object or string makes the body unreadable", shape == null, shape ?? "ok");
                string deep = new string('[', 65) + new string(']', 65), deepOk = new string('[', 60) + new string(']', 60);
                Check(r, "V7 nesting deeper than 64 is refused and 60 is accepted",
                      TrRefusal(Env(409, "{\"detail\":\"Sold out\",\"v\":" + deep + "}")) == null
                      && TrRefusal(Env(409, "{\"detail\":\"Sold out\",\"v\":" + deepOk + "}")) == "Sold out", "");
            }

            // -- T: a template matches the whole detail or nothing ---------------------
            {
                string gold = Env(402, "{\"detail\":\"Insufficient gold: have 1, need 2\\n\"}");
                Check(r, "T1 a detail with a final line feed is not the gold sentence: the caller keeps the server's text",
                      TrRefusal(gold) == null, TrRefusal(gold));
                Check(r, "T1n negative control: removal, the round-3 match (^ and $) took that detail for the gold sentence",
                      R3Template("Insufficient gold: have 1, need 2\n", "Insufficient gold: have {0}, need {1}", false), "");
                Check(r, "T1p positive control: the exact gold detail still maps",
                      TrRefusal(Env(402, DetailBody("Insufficient gold: have 1, need 2"))) == "Insufficient gold: have 1, need 2", "");
                string miss = null, extra = null;
                foreach (string row in TEMPLATES)
                {
                    int b1 = row.IndexOf('|'), b2 = row.IndexOf('|', b1 + 1);
                    int st = int.Parse(row.Substring(0, b1));
                    bool text = row[b1 + 1] == 'T';
                    string tpl = row.Substring(b2 + 1), d = Fill(tpl, text);
                    if (TrRefusalDetail(st, d) != d && miss == null) miss = row;
                    foreach (string v in new[] { d + "\n", d + "\r\n", d + " ", " " + d, "\n" + d, d + ".", d + "\t" })
                    {
                        string got = TrRefusalDetail(st, v);
                        if (got != null && got != v && extra == null) extra = row + " <- " + v.Replace("\n", "\\n");
                    }
                }
                Check(r, "T2 every template rule maps its own detail unchanged in English", miss == null, miss ?? TEMPLATES.Length.ToString());
                Check(r, "T3 every template rule, given that detail with a final LF, CRLF, space, tab or dot, or a leading space or LF, answers null or the input unchanged",
                      extra == null, extra ?? "ok");
                string lf = TrRefusalDetail(400, "unreadable PNG: x\ny") ?? TrRefusalDetail(400, "unreadable PNG: x\ry")
                            ?? TrRefusalDetail(400, "unreadable PNG: x\r") ?? TrRefusalDetail(400, "bad frame PNG: \r");
                Check(r, "T4 a text hole takes no CR or LF", lf == null, lf);
            }

            // -- D: the Recent Series FFA labels ----------------------------------------
            {
                Check(r, "D1 en: the FFA labels are shown exactly as the server composed them",
                      SeriesRightLabel("ffa", "6-player FFA") == "6-player FFA" && SeriesScore("ffa", "#1 of 6") == "#1 of 6",
                      SeriesRightLabel("ffa", "6-player FFA") + " / " + SeriesScore("ffa", "#1 of 6"));
                I18n.HarnessLocale = "es";
                string lab = SeriesRightLabel("ffa", "6-player FFA"), sc = SeriesScore("ffa", "#1 of 6");
                Check(r, "D2 es: the FFA labels reach their rows with the count kept",
                      lab == "FFA de 6 jugadores" && sc == "N.º 1 de 6", lab + " / " + sc);
                Check(r, "D3 another mode's labels are shown as sent",
                      SeriesRightLabel("2v2", "6-player FFA") == "6-player FFA" && SeriesScore("2v2", "#1 of 6") == "#1 of 6"
                      && SeriesScore("2v2", "2-1") == "2-1", SeriesRightLabel("2v2", "6-player FFA"));
                Check(r, "D4 a player name or an unknown value in the FFA slots is shown as sent",
                      SeriesRightLabel("ffa", "Ana") == "Ana" && SeriesRightLabel("ffa", "x-player FFA") == "x-player FFA"
                      && SeriesRightLabel("ffa", "-6-player FFA") == "-6-player FFA" && SeriesScore("ffa", "#2 of 6") == "#2 of 6"
                      && SeriesScore("ffa", "#1 of six") == "#1 of six" && SeriesRightLabel("ffa", null) == null
                      && SeriesScore("ffa", "#1 of ") == "#1 of ", SeriesRightLabel("ffa", "x-player FFA"));
                // the bets ledger: the arm from the row's own shape, each composed value by arm
                Check(r, "E1 the arms are told apart by their shapes",
                      BetArm("", "game 2") == "team" && BetArm(null, "1-0") == "team" && BetArm("7656", "game 2") == "ffa"
                      && BetArm("7656", "2-1") == "ranked" && BetArm("7656", "game x") == "ranked" && BetArm("7656", null) == "ranked",
                      BetArm("7656", "game 2"));
                Check(r, "E2 es: the FFA arm's vs label and score and the team arm's side reach their rows",
                      BetVsName("ffa", "5-player FFA") == "FFA de 5 jugadores" && BetScore("ffa", "game 3") == "juego 3"
                      && BetOnName("team", "Team 2") == "Equipo 2",
                      BetVsName("ffa", "5-player FFA") + " / " + BetScore("ffa", "game 3") + " / " + BetOnName("team", "Team 2"));
                Check(r, "E3 a player name in any arm, and the ranked arm's values, are shown as sent",
                      BetOnName("ranked", "Team 2") == "Team 2" && BetVsName("ranked", "5-player FFA") == "5-player FFA"
                      && BetScore("ranked", "game 3") == "game 3" && BetOnName("ffa", "Team 2") == "Team 2"
                      && BetVsName("team", "2v2") == "2v2" && BetOnName("team", "Team two") == "Team two"
                      && BetScore("ffa", "game ") == "game " && BetOnName("team", null) == null,
                      BetOnName("ranked", "Team 2"));
                I18n.HarnessLocale = "en";
                Check(r, "E4 en: every bets label is shown exactly as the server composed it",
                      BetVsName("ffa", "5-player FFA") == "5-player FFA" && BetScore("ffa", "game 3") == "game 3"
                      && BetOnName("team", "Team 2") == "Team 2", BetScore("ffa", "game 3"));
                I18n.HarnessLocale = "es";
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
