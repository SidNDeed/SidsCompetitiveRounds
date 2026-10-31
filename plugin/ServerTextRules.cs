using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace CompetitiveRounds
{
    /// <summary>
    /// Server text on the shop, ladder, artist and series surfaces, shown in
    /// the player's language. Kept free of Unity, Photon and BepInEx so that
    /// tools/client-rules-harness compiles it with I18nCatalogues.cs and
    /// EXECUTES it (ServerTextRulesSelfTest.cs, suite "servertext"); the plugin
    /// build compiles only this half of the partial class.
    ///
    /// Refusals. The request helpers hand a refusal back as
    /// "HTTP &lt;status&gt;: &lt;body&gt;" (SecureRouteRules.RequestErrorText; a
    /// "Retry-After: n" line may follow). Read parses the body as ONE JSON
    /// object and answers its top-level "detail" when that is a string, its
    /// detail.error when detail is an object, or its top-level "error" (the
    /// middleware answers). A code is recognised only by equality with the
    /// field the server documents, never by finding it somewhere in the
    /// answer. TrRefusal maps every (status, text) the shop purchase route,
    /// the artist routes (the preview GET included), the helpers they call,
    /// the app middleware and the read gate can send, each to a catalogue row
    /// whose English is the server's own text, so an English player reads
    /// exactly what the server sent; a composed detail goes through a template
    /// whose holes are parsed narrowly. Anything else returns null and the
    /// caller keeps its raw text. backend/tests/test_i18n_late_label_coverage.py
    /// enumerates the server's side and fails on a gap or a stale row.
    ///
    /// Series labels. The Recent Series feed's FFA rows carry two composed
    /// English labels (main.py, the multimode series feed): "N-player FFA" and
    /// "#1 of N". They are mapped for mode "ffa" only, before the line is
    /// fitted and marked up; any other value is shown as sent.
    /// </summary>
    internal static partial class ServerTextRules
    {
        internal sealed class Refusal
        {
            internal int Status;
            internal string Detail;        // "detail" as a string
            internal string DetailError;   // detail.error, detail being an object
            internal string Error;         // top-level "error" (no "detail")
        }

        /// <summary>The refusal in an "HTTP status: body" answer, or null when
        /// the answer is not one. A body that is not one valid JSON object
        /// (JsonValid over the whole body) yields the status alone, so every
        /// map below answers null and the caller keeps its raw text.</summary>
        internal static Refusal Read(string resp)
        {
            if (string.IsNullOrEmpty(resp) || resp.Length < 10 || !resp.StartsWith("HTTP ", StringComparison.Ordinal)
                || resp[8] != ':' || resp[9] != ' ')
                return null;
            int status;
            if (!int.TryParse(resp.Substring(5, 3), NumberStyles.None, CultureInfo.InvariantCulture, out status)
                || status < 400 || status > 599)
                return null;
            string body = resp.Substring(10);
            int ra = body.LastIndexOf("\nRetry-After: ", StringComparison.Ordinal);
            if (ra >= 0) body = body.Substring(0, ra);
            var r = new Refusal { Status = status };
            if (!JsonValid(body)) return r;
            Dictionary<string, string> top;
            if (!Members(body, out top)) return r;
            string raw, s;
            if (top.TryGetValue("detail", out raw))
            {
                Dictionary<string, string> inner;
                if (JsonString(raw, out s)) r.Detail = s;
                else if (Members(raw, out inner) && inner.TryGetValue("error", out raw) && JsonString(raw, out s))
                    r.DetailError = s;
            }
            else if (top.TryGetValue("error", out raw) && JsonString(raw, out s))
                r.Error = s;
            return r;
        }

        /// <summary>True when resp is a refusal with this status whose detail is
        /// an object with error == code.</summary>
        internal static bool IsDetailError(string resp, int status, string code)
        {
            var r = Read(resp);
            return r != null && r.Status == status && r.DetailError != null
                   && string.Equals(r.DetailError, code, StringComparison.Ordinal);
        }

        /// <summary>The refusal in the player's language, or null when this map
        /// does not know it (the caller keeps its raw text).</summary>
        internal static string TrRefusal(string resp)
        {
            var r = Read(resp);
            if (r == null) return null;
            if (r.Detail != null) return TrRefusalDetail(r.Status, r.Detail);
            if (r.DetailError != null) return TrRefusalObject(r.Status, r.DetailError);
            if (r.Error != null) return TrMiddleware(r.Status, r.Error);
            return null;
        }

        // An object-shaped detail. price_changed (409) is answered by both
        // purchase callbacks before this is called (the sentinel PurchaseItem hands them).
        private static string TrRefusalObject(int status, string code)
        {
            string k = status + "|" + code;
            if (k == "426|music_purchase_requires_update") return I18n.Tr("This album requires a newer mod version");
            return null;
        }

        // The app middleware's answers that carry only an error code
        // (main.py: rate_limit_gate and the limiter it calls, maintenance_gate;
        // replica_write_gate's answer also carries a detail sentence, which
        // wins and is mapped with the route details). The 426
        // "outdated" answer never reaches here: the request helpers answer it
        // with the "outdated" sentinel and the update prompt.
        private static string TrMiddleware(int status, string code)
        {
            string k = status + "|" + code;
            if (k == "403|forbidden") return I18n.Tr("forbidden");
            if (k == "413|payload_too_large") return I18n.Tr("payload_too_large");
            if (k == "429|rate_limited") return I18n.Tr("rate_limited");
            if (k == "503|rate_limited") return I18n.Tr("rate_limited");
            if (k == "503|maintenance") return I18n.Tr("maintenance");
            return null;
        }

        private static string TrRefusalDetail(int status, string d)
        {
            if (string.IsNullOrEmpty(d)) return null;
            string k = status + "|" + d;
            // the shop purchase route
            if (k == "404|Player not found") return I18n.Tr("Player not found");
            if (k == "410|Account deleted") return I18n.Tr("Account deleted");
            if (k == "404|Item not found") return I18n.Tr("Item not found");
            if (k == "409|This cosmetic is approved but has not shipped in the mod yet") return I18n.Tr("This cosmetic is approved but has not shipped in the mod yet");
            if (k == "409|This album requires a newer mod version") return I18n.Tr("This album requires a newer mod version");
            if (k == "409|This item requires a newer mod version") return I18n.Tr("This item requires a newer mod version");
            if (k == "403|Unlocked by achievement, not purchasable") return I18n.Tr("Unlocked by achievement, not purchasable");
            if (k == "403|This artist has restricted you from buying their items") return I18n.Tr("This artist has restricted you from buying their items");
            if (k == "409|Not for sale yet — the artist hasn't opened sales") return I18n.Tr("Not for sale yet — the artist hasn't opened sales");
            if (k == "409|Sold out") return I18n.Tr("Sold out");
            if (k == "402|Insufficient gold") return I18n.Tr("Insufficient gold");
            // the artist routes
            if (k == "403|Not an artist account") return I18n.Tr("Not an artist account");
            if (k == "403|Not your item") return I18n.Tr("Not your item");
            if (k == "400|Name can't be empty") return I18n.Tr("Name can't be empty");
            if (k == "400|render_scale must be between 0.50 and 2.25") return I18n.Tr("render_scale must be between 0.50 and 2.25");
            if (k == "400|placement is outside the character editor limit") return I18n.Tr("placement is outside the character editor limit");
            if (k == "400|name too short (letters/numbers/spaces only)") return I18n.Tr("name too short (letters/numbers/spaces only)");
            if (k == "400|frame PNG missing or too large") return I18n.Tr("frame PNG missing or too large");
            if (k == "404|submission not found") return I18n.Tr("submission not found");
            if (k == "409|submission is not accepting frames") return I18n.Tr("submission is not accepting frames");
            if (k == "409|submission is not finalizable") return I18n.Tr("submission is not finalizable");
            if (k == "400|GIF is missing") return I18n.Tr("GIF is missing");
            if (k == "400|not a GIF file") return I18n.Tr("not a GIF file");
            if (k == "400|GIF has no transparent background — export it with transparency, or the cosmetic renders as a solid square.") return I18n.Tr("GIF has no transparent background — export it with transparency, or the cosmetic renders as a solid square.");
            if (k == "404|Cosmetic submission not found") return I18n.Tr("Cosmetic submission not found");
            // the middleware's replica answer (replica_write_gate): its detail
            if (k == "503|This node serves reads only; writes are handled by the primary. Seeing this means a request reached the standby that should not have.") return I18n.Tr("This node serves reads only; writes are handled by the primary. Seeing this means a request reached the standby that should not have.");
            if (k == "409|Denied artwork cannot be reopened by a placement change") return I18n.Tr("Denied artwork cannot be reopened by a placement change");
            if (k == "409|Placement changed since this preview; reload it and try again") return I18n.Tr("Placement changed since this preview; reload it and try again");
            if (k == "429|Too many cosmetic changes are already awaiting review") return I18n.Tr("Too many cosmetic changes are already awaiting review");
            if (k == "400|PNG payload is missing or too large") return I18n.Tr("PNG payload is missing or too large");
            if (k == "400|Invalid PNG data") return I18n.Tr("Invalid PNG data");
            if (k == "404|Artist-owned face cosmetic not found") return I18n.Tr("Artist-owned face cosmetic not found");
            if (k == "409|This cosmetic has not shipped yet; adjust its existing submission instead") return I18n.Tr("This cosmetic has not shipped yet; adjust its existing submission instead");
            if (k == "409|Music albums have no stock — they are unlimited by design") return I18n.Tr("Music albums have no stock — they are unlimited by design");
            if (k == "409|This cosmetic has not shipped in the mod yet; stock stays closed until it does") return I18n.Tr("This cosmetic has not shipped in the mod yet; stock stays closed until it does");
            if (k == "409|This cosmetic has not shipped in the mod yet and cannot be gifted") return I18n.Tr("This cosmetic has not shipped in the mod yet and cannot be gifted");
            if (k == "404|Player not found — they need to have used the mod once") return I18n.Tr("Player not found — they need to have used the mod once");
            if (k == "409|This item requires a newer mod version than the recipient has used; they need to update the mod first") return I18n.Tr("This item requires a newer mod version than the recipient has used; they need to update the mod first");
            if (k == "409|Sold out — raise the stock cap first") return I18n.Tr("Sold out — raise the stock cap first");
            // the PNG checks the upload routes forward (a ValueError's text)
            if (k == "400|not a PNG file") return I18n.Tr("not a PNG file");
            if (k == "400|PNG has no transparent background — export with an alpha layer") return I18n.Tr("PNG has no transparent background — export with an alpha layer");
            if (k == "400|PNG is too large once re-encoded — reduce its complexity") return I18n.Tr("PNG is too large once re-encoded — reduce its complexity");
            if (k == "400|PNG has an implausible number of chunks") return I18n.Tr("PNG has an implausible number of chunks");
            if (k == "400|truncated PNG (chunk header runs past end of file)") return I18n.Tr("truncated PNG (chunk header runs past end of file)");
            if (k == "400|malformed PNG (invalid chunk type)") return I18n.Tr("malformed PNG (invalid chunk type)");
            if (k == "400|malformed PNG (chunk length runs past end of file)") return I18n.Tr("malformed PNG (chunk length runs past end of file)");
            if (k == "400|malformed PNG (IHDR is not the first chunk)") return I18n.Tr("malformed PNG (IHDR is not the first chunk)");
            if (k == "400|malformed PNG (no IEND chunk)") return I18n.Tr("malformed PNG (no IEND chunk)");
            // protocol details: a field the mod signs or sends, or a server
            // service; each is its own key, so English shows the server's text
            if (k == "401|session_required") return I18n.Tr("session_required");
            if (k == "403|Invalid signature") return I18n.Tr("Invalid signature");
            if (k == "403|service_account_forbidden") return I18n.Tr("service_account_forbidden");
            if (k == "400|expected_price_required") return I18n.Tr("expected_price_required");
            if (k == "400|scale and offsets must be numbers") return I18n.Tr("scale and offsets must be numbers");
            if (k == "400|scale and offsets must be finite") return I18n.Tr("scale and offsets must be finite");
            if (k == "400|Invalid signature version") return I18n.Tr("Invalid signature version");
            if (k == "400|Unsupported signature version") return I18n.Tr("Unsupported signature version");
            if (k == "400|Signed placement integers are required") return I18n.Tr("Signed placement integers are required");
            if (k == "400|Valid upload_request_id is required") return I18n.Tr("Valid upload_request_id is required");
            if (k == "400|Signed animation fields are required") return I18n.Tr("Signed animation fields are required");
            if (k == "400|anim_fps must be 0.5-15") return I18n.Tr("anim_fps must be 0.5-15");
            if (k == "400|frames_hash must be sha256 hex") return I18n.Tr("frames_hash must be sha256 hex");
            if (k == "400|slot must be eyes, mouth or detail") return I18n.Tr("slot must be eyes, mouth or detail");
            if (k == "400|png_base64 is not valid base64") return I18n.Tr("png_base64 is not valid base64");
            if (k == "400|submission_id and frame_no are required") return I18n.Tr("submission_id and frame_no are required");
            if (k == "400|frame png_base64 is not valid base64") return I18n.Tr("frame png_base64 is not valid base64");
            if (k == "400|submission_id is required") return I18n.Tr("submission_id is required");
            if (k == "400|gif_base64 is not valid base64") return I18n.Tr("gif_base64 is not valid base64");
            if (k == "400|Invalid placement request") return I18n.Tr("Invalid placement request");
            if (k == "400|Invalid placement revision") return I18n.Tr("Invalid placement revision");
            if (k == "400|Invalid catalog placement request") return I18n.Tr("Invalid catalog placement request");
            if (k == "400|Cosmetic slot does not match its catalog SKU") return I18n.Tr("Cosmetic slot does not match its catalog SKU");
            if (k == "400|PNG hash does not match the payload") return I18n.Tr("PNG hash does not match the payload");
            if (k == "503|HMAC not configured") return I18n.Tr("HMAC not configured");
            if (k == "503|session_check_unavailable") return I18n.Tr("session_check_unavailable");
            if (k == "503|service_policy_unavailable") return I18n.Tr("service_policy_unavailable");
            if (k == "503|image_processing_unavailable") return I18n.Tr("image_processing_unavailable");
            if (k == "503|gif_processing_unavailable") return I18n.Tr("gif_processing_unavailable");
            // the read gate's answers to the artist preview (a GET; read_gate.py)
            if (k == "503|read_gate_unavailable") return I18n.Tr("read_gate_unavailable");
            if (k == "429|rate_limited") return I18n.Tr("rate_limited");
            if (k == "503|session_replication_pending") return I18n.Tr("session_replication_pending");
            if (k == "401|player_session_required") return I18n.Tr("player_session_required");
            if (k == "401|operator_key_invalid") return I18n.Tr("operator_key_invalid");
            if (k == "401|read_credential_required") return I18n.Tr("read_credential_required");
            if (k == "403|internal_key_required") return I18n.Tr("internal_key_required");
            string[] a;
            if (status == 402 && RefusalTemplate(d, "Insufficient gold: have {0}, need {1}", false, out a))
                return I18n.TrF("Insufficient gold: have {0}, need {1}", a);
            if (status == 429 && RefusalTemplate(d, "{0} submissions already awaiting review — wait for those first", false, out a))
                return I18n.TrF("{0} submissions already awaiting review — wait for those first", a);
            if (status == 400 && RefusalTemplate(d, "PNG missing or too large ({0} MB, 1,600,000 base64 characters max)", false, out a))
                return I18n.TrF("PNG missing or too large ({0} MB, 1,600,000 base64 characters max)", a);
            if (status == 409 && RefusalTemplate(d, "missing frames: have {0} of {1}", false, out a))
                return I18n.TrF("missing frames: have {0} of {1}", a);
            if (status == 400 && RefusalTemplate(d, "GIF is {0} KB — the limit is {1} KB. Reduce the frame size or the number of colours and re-export.", false, out a))
                return I18n.TrF("GIF is {0} KB — the limit is {1} KB. Reduce the frame size or the number of colours and re-export.", a);
            if (status == 400 && RefusalTemplate(d, "GIF frames are {0}x{1} — the limit is 2048x2048", false, out a))
                return I18n.TrF("GIF frames are {0}x{1} — the limit is 2048x2048", a);
            if (status == 400 && RefusalTemplate(d, "GIF has {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).", false, out a))
                return I18n.TrF("GIF has {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).", a);
            if (status == 400 && RefusalTemplate(d, "GIF has more than {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).", false, out a))
                return I18n.TrF("GIF has more than {0} frames — the limit is {1}. Reduce the frame count in your editor; the server will not resample it for you (that would change the timing).", a);
            if (status == 400 && RefusalTemplate(d, "GIF has {0} frame(s) — an animation needs at least 2. Upload a PNG instead for static art.", false, out a))
                return I18n.TrF("GIF has {0} frame(s) — an animation needs at least 2. Upload a PNG instead for static art.", a);
            if (status == 400 && RefusalTemplate(d, "GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at least {5} ms and re-export; the server will not change the speed for you.", false, out a))
                return I18n.TrF("GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at least {5} ms and re-export; the server will not change the speed for you.", a);
            if (status == 400 && RefusalTemplate(d, "GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at most {5} ms and re-export; the server will not change the speed for you.", false, out a))
                return I18n.TrF("GIF frame rate is {0} fps ({1} frames, ~{2} ms each) — supported range is {3}-{4} fps. Set the frame delay to at most {5} ms and re-export; the server will not change the speed for you.", a);
            if (status == 400 && RefusalTemplate(d, "converted frame {0} is {1} KB — the per-image limit is {2} KB. Simplify the art or reduce its colour count.", false, out a))
                return I18n.TrF("converted frame {0} is {1} KB — the per-image limit is {2} KB. Simplify the art or reduce its colour count.", a);
            if (status == 400 && RefusalTemplate(d, "GIF decoded inconsistently ({0} of {1} frames) — re-export it and try again.", false, out a))
                return I18n.TrF("GIF decoded inconsistently ({0} of {1} frames) — re-export it and try again.", a);
            if (status == 400 && RefusalTemplate(d, "must be exactly 512x512 (got {0}x{1})", false, out a))
                return I18n.TrF("must be exactly 512x512 (got {0}x{1})", a);
            if (status == 400 && RefusalTemplate(d, "PNG has {0} stray byte(s) after IEND", false, out a))
                return I18n.TrF("PNG has {0} stray byte(s) after IEND", a);
            // text holes: a forwarded PNG check (translated in turn), a chunk
            // type, or a library's exception text (shown as sent)
            if (status == 400 && RefusalTemplate(d, "bad frame PNG: {0}", true, out a))
                return I18n.TrF("bad frame PNG: {0}", TrRefusalDetail(status, a[0]) ?? a[0]);
            if (status == 400 && RefusalTemplate(d, "Published cosmetic source must be a transparent 512x512 PNG ({0})", true, out a))
                return I18n.TrF("Published cosmetic source must be a transparent 512x512 PNG ({0})", TrRefusalDetail(status, a[0]) ?? a[0]);
            if (status == 400 && RefusalTemplate(d, "malformed PNG (bad CRC on {0} chunk)", true, out a))
                return I18n.TrF("malformed PNG (bad CRC on {0} chunk)", a);
            if (status == 400 && RefusalTemplate(d, "unreadable PNG: {0}", true, out a))
                return I18n.TrF("unreadable PNG: {0}", a);
            if (status == 400 && RefusalTemplate(d, "could not process GIF: {0}", true, out a))
                return I18n.TrF("could not process GIF: {0}", a);
            // protocol templates (fields the mod sends)
            if (status == 400 && RefusalTemplate(d, "frame_count must be 2-{0}", false, out a))
                return I18n.TrF("frame_count must be 2-{0}", a);
            if (status == 400 && RefusalTemplate(d, "frame_no must be 2-{0}", false, out a))
                return I18n.TrF("frame_no must be 2-{0}", a);
            return null;
        }

        // Matches d against an English template whose holes are {0}..{9} in
        // ascending order. A numeric hole accepts a signed decimal number
        // only; with textHoles every hole accepts any non-empty text without
        // a line break. The match is anchored at the absolute start and end
        // (\A, \z: never ^ or $, which also match before a final line feed)
        // and must cover the whole detail, so a detail with anything before
        // or after the template, a trailing line feed included, stops
        // matching and the caller keeps the server's text.
        private static bool RefusalTemplate(string d, string template, bool textHoles, out string[] args)
        {
            args = null;
            var sb = new StringBuilder("\\A");
            int holes = 0;
            for (int i = 0; i < template.Length; i++)
            {
                char c = template[i];
                if (c == '{' && i + 2 < template.Length && template[i + 2] == '}' && template[i + 1] >= '0' && template[i + 1] <= '9')
                {
                    sb.Append(textHoles ? "([^\\r\\n]+?)" : "(-?[0-9]+(?:\\.[0-9]+)?)");
                    holes++;
                    i += 2;
                    continue;
                }
                sb.Append(Regex.Escape(c.ToString()));
            }
            sb.Append("\\z");
            var m = Regex.Match(d, sb.ToString(), RegexOptions.CultureInvariant);
            if (!m.Success || m.Index != 0 || m.Length != d.Length) return false;
            args = new string[holes];
            for (int k = 0; k < holes; k++) args[k] = m.Groups[k + 1].Value;
            return true;
        }


        // ---- the FFA rows of the Recent Series feed ----

        /// <summary>"N-player FFA" (mode "ffa" only) in the player's language;
        /// any other value as sent.</summary>
        internal static string SeriesRightLabel(string mode, string label)
        {
            const string suffix = "-player FFA";
            int n;
            if (mode == "ffa" && label != null && label.EndsWith(suffix, StringComparison.Ordinal)
                && ParseCount(label.Substring(0, label.Length - suffix.Length), out n))
                return I18n.TrF("{0}-player FFA", n);
            return label;
        }

        /// <summary>"#1 of N" (mode "ffa" only) in the player's language; any
        /// other value as sent.</summary>
        internal static string SeriesScore(string mode, string score)
        {
            const string prefix = "#1 of ";
            int n;
            if (mode == "ffa" && score != null && score.StartsWith(prefix, StringComparison.Ordinal)
                && ParseCount(score.Substring(prefix.Length), out n))
                return I18n.TrF("#1 of {0}", n);
            return score;
        }

        // ---- the bets ledger (GET /players/{id}/bets) ----

        /// <summary>Which arm of the server's bets UNION produced a row, from
        /// the arms' own shapes: the team arm sends no bet_on_steam_id, the FFA
        /// arm's series_score is "game N" (the ranked arm's is "a-b").</summary>
        internal static string BetArm(string betOnSteamId, string seriesScore)
        {
            if (string.IsNullOrEmpty(betOnSteamId)) return "team";
            int n;
            if (seriesScore != null && seriesScore.StartsWith("game ", StringComparison.Ordinal)
                && ParseCount(seriesScore.Substring(5), out n)) return "ffa";
            return "ranked";
        }

        /// <summary>The team arm's "Team N"; a name as sent.</summary>
        internal static string BetOnName(string arm, string name)
        {
            int n;
            if (arm == "team" && name != null && name.StartsWith("Team ", StringComparison.Ordinal)
                && ParseCount(name.Substring(5), out n))
                return I18n.TrF("Team {0}", n);
            return name;
        }

        /// <summary>The FFA arm's "N-player FFA"; a name as sent.</summary>
        internal static string BetVsName(string arm, string name)
            => SeriesRightLabel(arm == "ffa" ? "ffa" : null, name);

        /// <summary>The FFA arm's "game N"; a score as sent.</summary>
        internal static string BetScore(string arm, string score)
        {
            int n;
            if (arm == "ffa" && score != null && score.StartsWith("game ", StringComparison.Ordinal)
                && ParseCount(score.Substring(5), out n))
                return I18n.TrF("game {0}", n);
            return score;
        }

        // ASCII digits only (the server sends str(int)), no sign, six digits at most.
        private static bool ParseCount(string s, out int n)
        {
            n = 0;
            if (string.IsNullOrEmpty(s) || s.Length > 6) return false;
            foreach (char c in s)
                if (c < '0' || c > '9') return false;
            return int.TryParse(s, NumberStyles.None, CultureInfo.InvariantCulture, out n);
        }

        // ---- a strict JSON validator (RFC 8259) over the whole body ----

        /// <summary>True when s is exactly one JSON value with only whitespace
        /// around it: objects, arrays, strings whose every escape is one of
        /// \" \\ \/ \b \f \n \r \t or \u and four hex digits, numbers by the
        /// JSON grammar (no leading zero, no plus sign, no bare dot or
        /// exponent), the literals true, false and null; nesting at most 64
        /// deep. The member readers below run only on a body this accepted.</summary>
        internal static bool JsonValid(string s)
        {
            if (s == null) return false;
            int i = Ws(s, 0);
            if (!JValue(s, ref i, 0)) return false;
            return Ws(s, i) == s.Length;
        }

        private static bool JValue(string s, ref int i, int depth)
        {
            if (i >= s.Length) return false;
            char c = s[i];
            if (c == '{') return JObject(s, ref i, depth + 1);
            if (c == '[') return JArray(s, ref i, depth + 1);
            if (c == '"') return JString(s, ref i);
            if (c == '-' || (c >= '0' && c <= '9')) return JNumber(s, ref i);
            return JLiteral(s, ref i, "true") || JLiteral(s, ref i, "false") || JLiteral(s, ref i, "null");
        }

        private static bool JObject(string s, ref int i, int depth)
        {
            if (depth > 64) return false;
            i = Ws(s, i + 1);
            if (i < s.Length && s[i] == '}') { i++; return true; }
            while (true)
            {
                if (i >= s.Length || s[i] != '"' || !JString(s, ref i)) return false;
                i = Ws(s, i);
                if (i >= s.Length || s[i] != ':') return false;
                i = Ws(s, i + 1);
                if (!JValue(s, ref i, depth)) return false;
                i = Ws(s, i);
                if (i < s.Length && s[i] == ',') { i = Ws(s, i + 1); continue; }
                if (i < s.Length && s[i] == '}') { i++; return true; }
                return false;
            }
        }

        private static bool JArray(string s, ref int i, int depth)
        {
            if (depth > 64) return false;
            i = Ws(s, i + 1);
            if (i < s.Length && s[i] == ']') { i++; return true; }
            while (true)
            {
                if (!JValue(s, ref i, depth)) return false;
                i = Ws(s, i);
                if (i < s.Length && s[i] == ',') { i = Ws(s, i + 1); continue; }
                if (i < s.Length && s[i] == ']') { i++; return true; }
                return false;
            }
        }

        // s[i] is the opening quote; i moves past the closing one.
        private static bool JString(string s, ref int i)
        {
            for (int j = i + 1; j < s.Length; j++)
            {
                char c = s[j];
                if (c == '"') { i = j + 1; return true; }
                if (c < ' ') return false;
                if (c != '\\') continue;
                if (++j >= s.Length) return false;
                char e = s[j];
                if (e == 'u')
                {
                    if (j + 4 >= s.Length) return false;
                    for (int k = 1; k <= 4; k++)
                        if (!IsHex(s[j + k])) return false;
                    j += 4;
                }
                else if ("\"\\/bfnrt".IndexOf(e) < 0) return false;
            }
            return false;
        }

        private static bool IsHex(char c)
        {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
        }

        // -? (0 | [1-9][0-9]*) (. [0-9]+)? ([eE] [+-]? [0-9]+)?
        private static bool JNumber(string s, ref int i)
        {
            int j = i;
            if (s[j] == '-') j++;
            if (j >= s.Length) return false;
            if (s[j] == '0') j++;
            else if (s[j] >= '1' && s[j] <= '9') { while (j < s.Length && s[j] >= '0' && s[j] <= '9') j++; }
            else return false;
            if (j < s.Length && s[j] == '.')
            {
                int d = ++j;
                while (j < s.Length && s[j] >= '0' && s[j] <= '9') j++;
                if (j == d) return false;
            }
            if (j < s.Length && (s[j] == 'e' || s[j] == 'E'))
            {
                j++;
                if (j < s.Length && (s[j] == '+' || s[j] == '-')) j++;
                int d = j;
                while (j < s.Length && s[j] >= '0' && s[j] <= '9') j++;
                if (j == d) return false;
            }
            i = j;
            return true;
        }

        private static bool JLiteral(string s, ref int i, string lit)
        {
            if (i + lit.Length > s.Length || string.CompareOrdinal(s, i, lit, 0, lit.Length) != 0) return false;
            i += lit.Length;
            return true;
        }

        // ---- the top-level member reader (on a validated body only) ----

        /// <summary>Every member of ONE JSON object, key to its raw value span;
        /// false on a duplicate key, junk between members, an unbalanced
        /// value or anything after the closing brace.</summary>
        private static bool Members(string s, out Dictionary<string, string> members)
        {
            members = new Dictionary<string, string>(StringComparer.Ordinal);
            if (s == null) return false;
            int i = Ws(s, 0);
            if (i >= s.Length || s[i] != '{') return false;
            i = Ws(s, i + 1);
            if (i < s.Length && s[i] == '}') return Ws(s, i + 1) == s.Length;
            while (true)
            {
                int ke = StringEnd(s, i);
                if (ke < 0) return false;
                string key;
                if (!JsonString(s.Substring(i, ke - i + 1), out key)) return false;
                i = Ws(s, ke + 1);
                if (i >= s.Length || s[i] != ':') return false;
                int vs = Ws(s, i + 1);
                int ve = ValueEnd(s, vs);
                if (ve < 0 || members.ContainsKey(key)) return false;
                members[key] = s.Substring(vs, ve - vs);
                i = Ws(s, ve);
                if (i < s.Length && s[i] == ',') { i = Ws(s, i + 1); continue; }
                if (i < s.Length && s[i] == '}') return Ws(s, i + 1) == s.Length;
                return false;
            }
        }

        private static int Ws(string s, int i)
        {
            while (i < s.Length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n')) i++;
            return i;
        }

        // The index of the closing quote of the string opening at i, or -1.
        private static int StringEnd(string s, int i)
        {
            if (i >= s.Length || s[i] != '"') return -1;
            for (int j = i + 1; j < s.Length; j++)
            {
                if (s[j] == '\\') { j++; continue; }
                if (s[j] == '"') return j;
                if (s[j] < ' ') return -1;
            }
            return -1;
        }

        // The index just past the value starting at i, or -1.
        private static int ValueEnd(string s, int i)
        {
            if (i >= s.Length) return -1;
            char c = s[i];
            if (c == '"') { int e = StringEnd(s, i); return e < 0 ? -1 : e + 1; }
            if (c == '{' || c == '[')
            {
                var stack = new Stack<char>();
                for (int j = i; j < s.Length; j++)
                {
                    char x = s[j];
                    if (x == '"') { int e = StringEnd(s, j); if (e < 0) return -1; j = e; continue; }
                    if (x == '{' || x == '[') { if (stack.Count >= 64) return -1; stack.Push(x == '{' ? '}' : ']'); continue; }
                    if (x == '}' || x == ']')
                    {
                        if (stack.Count == 0 || stack.Pop() != x) return -1;
                        if (stack.Count == 0) return j + 1;
                    }
                }
                return -1;
            }
            int k = i;
            while (k < s.Length && s[k] != ',' && s[k] != '}' && s[k] != ']' && s[k] != ' ' && s[k] != '\t'
                   && s[k] != '\r' && s[k] != '\n') k++;
            string tok = s.Substring(i, k - i);
            if (tok == "true" || tok == "false" || tok == "null") return k;
            double ignored;
            if (tok.Length > 0 && (tok[0] == '-' || (tok[0] >= '0' && tok[0] <= '9'))
                && double.TryParse(tok, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint | NumberStyles.AllowExponent,
                                   CultureInfo.InvariantCulture, out ignored))
                return k;
            return -1;
        }

        /// <summary>A raw span that is exactly one JSON string, unescaped.</summary>
        private static bool JsonString(string raw, out string val)
        {
            val = null;
            if (string.IsNullOrEmpty(raw) || raw.Length < 2 || raw[0] != '"' || StringEnd(raw, 0) != raw.Length - 1)
                return false;
            var sb = new StringBuilder(raw.Length);
            for (int i = 1; i < raw.Length - 1; i++)
            {
                char c = raw[i];
                if (c != '\\') { sb.Append(c); continue; }
                if (i + 1 >= raw.Length - 1) return false;
                char n = raw[++i];
                switch (n)
                {
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'u':
                        int code;
                        if (i + 4 >= raw.Length - 1
                            || !int.TryParse(raw.Substring(i + 1, 4), NumberStyles.AllowHexSpecifier,
                                             CultureInfo.InvariantCulture, out code))
                            return false;
                        sb.Append((char)code);
                        i += 4;
                        break;
                    default:
                        return false;
                }
            }
            val = sb.ToString();
            return true;
        }
    }
}
