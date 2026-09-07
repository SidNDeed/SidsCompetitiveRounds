using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using BepInEx.Configuration;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Sept 6 (Sid, Group 4 item b) — in-game mail, client transport and
    /// parsing. Every list and object from the mail endpoints is sliced with
    /// ApiClient's string-aware helpers (design B-3): a subject carrying
    /// <c>{</c>, <c>]</c>, <c>"</c> or <c>\</c> must never move Delete/Report
    /// to another id, and a truncated page binds NOTHING rather than something
    /// wrong. The UI lives in MailUI.cs; this file never touches uGUI.
    ///
    /// <para>Contract (b1-mail-server.md): POST /api/v1/mail, POST /mail/{id}/reply,
    /// GET /mail/inbox|sent?cursor=&amp;limit=25, GET /mail/{id}, POST /mail/{id}/read,
    /// DELETE /mail/{id}, POST /mail/{id}/report, GET /mail/status, GET|POST
    /// /mail/blocks, DELETE /mail/blocks/{steam_id}, PUT /mail/settings. All
    /// strict-session: the token rides the X-Session-Token header ApiClient
    /// already stamps, and a 401 session_required re-mints through the same
    /// HandleSessionReject path every gated call uses.</para></summary>
    internal static class MailClient
    {
        public const int SUBJECT_MAX = 120;
        public const int BODY_MAX = 2000;
        public const int PAGE_SIZE = 25;

        // ── Models ──────────────────────────────────────────────────────────
        public class Person
        {
            public string steamId = "", name = "", titleColor = "", kind = "";
        }

        public class Summary
        {
            public string id = "", threadId = "", subject = "", createdAt = "", kind = "direct";
            public string readAt;                                   // null = unread
            public Person sender;                                   // inbox rows
            public List<Person> addressees = new List<Person>();    // sent rows
            public bool IsUnread => string.IsNullOrEmpty(readAt);
            public bool IsBroadcast => kind == "system_broadcast";
        }

        public class Message : Summary
        {
            public string body = "";
            public string inReplyTo;
            public List<Person> to = new List<Person>(), cc = new List<Person>();
        }

        public class Page
        {
            public List<Summary> items = new List<Summary>();
            public string nextCursor;                               // null = no more
        }

        public class Status
        {
            public int unread;
            public string revision = "";
            public string mailFrom;                                 // optional; null when the server omits it
        }

        public class Block
        {
            public string steamId = "", name = "", createdAt = "";
        }

        // ── JSON slicing (string-aware) ─────────────────────────────────────
        /// <summary>Index of the closing quote of the JSON string that opens at
        /// s[quotePos]; escapes are skipped; -1 when unterminated.</summary>
        internal static int StringEnd(string s, int quotePos)
        {
            for (int i = quotePos + 1; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '\\') { i++; continue; }
                if (c == '"') return i;
            }
            return -1;
        }

        /// <summary>Decode ONE JSON token: a quoted string is unescaped, a bare
        /// token (number, true/false) is returned trimmed, <c>null</c> → null.</summary>
        internal static string Unquote(string tok)
        {
            if (tok == null) return null;
            tok = tok.Trim();
            if (tok.Length == 0 || tok == "null") return null;
            if (tok[0] != '"') return tok;
            var sb = new StringBuilder(tok.Length);
            for (int i = 1; i < tok.Length; i++)
            {
                char c = tok[i];
                if (c == '"') break;
                if (c == '\\' && i + 1 < tok.Length)
                {
                    char n = tok[++i];
                    switch (n)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'u':
                            int code;
                            if (i + 4 < tok.Length
                                && int.TryParse(tok.Substring(i + 1, 4), NumberStyles.HexNumber,
                                                CultureInfo.InvariantCulture, out code))
                            { sb.Append((char)code); i += 4; }
                            else sb.Append(n);
                            break;
                        default: sb.Append(n); break;
                    }
                    continue;
                }
                sb.Append(c);
            }
            return sb.ToString();
        }

        /// <summary>Top-level elements of the JSON array whose '[' is the first
        /// non-space character of <paramref name="arr"/>, each as its raw token.
        /// A malformed/truncated array yields an EMPTY list: binding nothing is
        /// the safe failure for a list whose rows carry Delete and Report.</summary>
        internal static List<string> Elements(string arr)
        {
            var list = new List<string>();
            if (string.IsNullOrEmpty(arr)) return list;
            int i = 0;
            while (i < arr.Length && char.IsWhiteSpace(arr[i])) i++;
            if (i >= arr.Length || arr[i] != '[') return list;
            int end = ApiClient.FindMatchingBracketStringAwarePublic(arr, i);
            if (end < 0) return list;
            int p = i + 1;
            while (p < end)
            {
                while (p < end && (char.IsWhiteSpace(arr[p]) || arr[p] == ',')) p++;
                if (p >= end) break;
                char c = arr[p];
                int q;
                if (c == '{') q = ApiClient.FindMatchingBraceStringAwarePublic(arr, p);
                else if (c == '[') q = ApiClient.FindMatchingBracketStringAwarePublic(arr, p);
                else if (c == '"') q = StringEnd(arr, p);
                else { q = p; while (q + 1 < end && arr[q + 1] != ',') q++; }
                if (q < 0 || q >= end) { list.Clear(); return list; }
                list.Add(arr.Substring(p, q - p + 1));
                p = q + 1;
            }
            return list;
        }

        internal static bool Members(string obj, out Dictionary<string, string> m)
            => ApiClient.TryTopLevelMembersPublic(obj ?? "", out m);

        internal static string Raw(Dictionary<string, string> m, string key)
        {
            string v;
            return m != null && m.TryGetValue(key, out v) ? v : null;
        }

        internal static string Str(Dictionary<string, string> m, string key) => Unquote(Raw(m, key));

        internal static int Int(Dictionary<string, string> m, string key, int dflt = 0)
        {
            string v = Str(m, key);
            int r;
            return v != null && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out r) ? r : dflt;
        }

        private static bool IsObject(string tok) => tok != null && tok.TrimStart().StartsWith("{");
        private static bool IsArray(string tok) => tok != null && tok.TrimStart().StartsWith("[");

        // ── Parsers ─────────────────────────────────────────────────────────
        internal static Person ParsePerson(string tok)
        {
            var p = new Person();
            if (string.IsNullOrEmpty(tok)) return p;
            if (IsObject(tok))
            {
                Dictionary<string, string> m;
                if (!Members(tok, out m)) return p;
                p.steamId = Str(m, "steam_id") ?? "";
                p.name = Str(m, "name") ?? Str(m, "display_name") ?? "";
                p.titleColor = Str(m, "title_color") ?? "";
                p.kind = Str(m, "kind") ?? "";
            }
            else p.steamId = Unquote(tok) ?? "";     // a bare id
            if (p.name.Length == 0) p.name = p.steamId;
            return p;
        }

        internal static List<Person> ParsePeople(string arrTok)
        {
            var list = new List<Person>();
            if (!IsArray(arrTok)) return list;
            foreach (var e in Elements(arrTok.TrimStart())) list.Add(ParsePerson(e));
            return list;
        }

        private static bool FillSummary(Summary s, string obj)
        {
            Dictionary<string, string> m;
            if (!Members(obj, out m)) return false;
            s.id = Str(m, "id") ?? "";
            s.threadId = Str(m, "thread_id") ?? "";
            s.subject = Str(m, "subject") ?? "";
            s.createdAt = Str(m, "created_at") ?? "";
            s.readAt = Str(m, "read_at");
            s.kind = Str(m, "kind") ?? "direct";
            string sender = Raw(m, "sender");
            if (IsObject(sender)) s.sender = ParsePerson(sender);
            else if (Str(m, "sender_name") != null)
                s.sender = new Person
                {
                    steamId = Str(m, "sender_steam_id") ?? "",
                    name = Str(m, "sender_name"),
                    titleColor = Str(m, "sender_title_color") ?? "",
                };
            string addr = Raw(m, "addressees");
            if (IsArray(addr)) s.addressees = ParsePeople(addr);
            return true;
        }

        internal static Summary ParseSummary(string obj)
        {
            var s = new Summary();
            return FillSummary(s, obj) ? s : null;
        }

        /// <summary>GET /mail/{id}: the summary fields plus body, in_reply_to and
        /// the To/Cc names. Accepts <c>to</c>/<c>cc</c> arrays (objects or bare
        /// ids) and falls back to a kind-tagged <c>addressees</c> array.</summary>
        internal static Message ParseMessage(string json)
        {
            var msg = new Message();
            if (!FillSummary(msg, json ?? "")) return null;
            Dictionary<string, string> m;
            Members(json, out m);
            msg.body = Str(m, "body") ?? "";
            msg.inReplyTo = Str(m, "in_reply_to");
            string to = Raw(m, "to"), cc = Raw(m, "cc");
            if (IsArray(to)) msg.to = ParsePeople(to);
            if (IsArray(cc)) msg.cc = ParsePeople(cc);
            if (!IsArray(to) && !IsArray(cc))
                foreach (var a in msg.addressees) { if (a.kind == "cc") msg.cc.Add(a); else msg.to.Add(a); }
            return msg;
        }

        /// <summary>Inbox / Sent page: either a bare array or an object holding
        /// the array (items | messages | results | the first array member) and
        /// <c>next_cursor</c>. Rows without an id are dropped.</summary>
        internal static Page ParsePage(string json)
        {
            var page = new Page();
            if (string.IsNullOrEmpty(json)) return page;
            string t = json.TrimStart();
            string arr = null;
            if (t.StartsWith("[")) arr = t;
            else
            {
                Dictionary<string, string> m;
                if (!Members(t, out m)) return page;
                page.nextCursor = Str(m, "next_cursor");
                arr = Raw(m, "items") ?? Raw(m, "messages") ?? Raw(m, "results");
                if (!IsArray(arr))
                {
                    arr = null;
                    foreach (var kv in m) if (IsArray(kv.Value)) { arr = kv.Value; break; }
                }
            }
            if (arr == null) return page;
            foreach (var e in Elements(arr.TrimStart()))
            {
                var s = new Summary();
                if (FillSummary(s, e) && s.id.Length > 0) page.items.Add(s);
            }
            return page;
        }

        internal static Status ParseStatus(string json)
        {
            Dictionary<string, string> m;
            if (!Members(json ?? "", out m)) return null;
            return new Status
            {
                unread = Int(m, "unread"),
                revision = Str(m, "revision") ?? "",
                mailFrom = Str(m, "mail_from"),
            };
        }

        internal static List<Block> ParseBlocks(string json)
        {
            var list = new List<Block>();
            if (string.IsNullOrEmpty(json)) return list;
            string t = json.TrimStart();
            string arr = null;
            if (t.StartsWith("[")) arr = t;
            else
            {
                Dictionary<string, string> m;
                if (!Members(t, out m)) return list;
                arr = Raw(m, "items") ?? Raw(m, "blocks");
                if (!IsArray(arr)) { arr = null; foreach (var kv in m) if (IsArray(kv.Value)) { arr = kv.Value; break; } }
            }
            if (arr == null) return list;
            foreach (var e in Elements(arr.TrimStart()))
            {
                Dictionary<string, string> m;
                if (!Members(e, out m)) continue;
                var b = new Block
                {
                    steamId = Str(m, "steam_id") ?? "",
                    name = Str(m, "name") ?? "",
                    createdAt = Str(m, "created_at") ?? "",
                };
                if (b.name.Length == 0) b.name = b.steamId;
                if (b.steamId.Length > 0) list.Add(b);
            }
            return list;
        }

        /// <summary>Human line for a failed call: FastAPI's <c>detail</c> out of
        /// "HTTP nnn: {json}" (the server's own wording — censor hits, the
        /// recipient cap, formatting refusals), else a short local reading of
        /// the status, else the transport error.</summary>
        internal static string ErrorDetail(string resp)
        {
            if (string.IsNullOrEmpty(resp)) return I18n.Tr("Request failed - try again.");
            if (resp == "no-consent") return I18n.Tr("Data sharing is off - allow it in Settings to use mail.");
            if (resp == "outdated") return I18n.Tr("Update the mod to use mail.");
            int brace = resp.IndexOf('{');
            if (brace >= 0)
            {
                string d = ApiClient.ExtractJsonStringPublic(resp.Substring(brace), "detail");
                if (!string.IsNullOrEmpty(d)) return d;
            }
            if (resp.StartsWith("HTTP 401")) return I18n.Tr("Sign-in is not ready yet - try again in a moment.");
            if (resp.StartsWith("HTTP 403")) return I18n.Tr("Not allowed.");
            if (resp.StartsWith("HTTP 404")) return I18n.Tr("Not found - it may have been deleted.");
            if (resp.StartsWith("HTTP 429")) return I18n.Tr("Too many messages - wait a minute and try again.");
            return resp.Length > 160 ? resp.Substring(0, 160) : resp;
        }

        // ── Requests ────────────────────────────────────────────────────────
        private static string Base => ApiClient.BaseUrl;
        private static string E(string s) => Uri.EscapeDataString(s ?? "");
        private static string J(string s) => ApiClient.JsonEscapeFullPublic(s ?? "");

        private static bool Ready(Action<bool, string> fail)
        {
            if (Plugin.Instance != null && !string.IsNullOrEmpty(Base)) return true;
            fail?.Invoke(false, "not ready");
            return false;
        }

        public static void FetchStatus(Action<bool, Status, string> cb)
        {
            if (!Ready((ok, r) => cb?.Invoke(false, null, r))) return;
            ApiClient.SessionGet($"{Base}/api/v1/mail/status", (ok, r) =>
            {
                Status st = ok ? ParseStatus(r) : null;
                cb?.Invoke(ok && st != null, st, ok ? (st == null ? "bad status payload" : null) : r);
            });
        }

        public static void FetchInbox(string cursor, Action<bool, Page, string> cb) => FetchList("inbox", cursor, cb);
        public static void FetchSent(string cursor, Action<bool, Page, string> cb) => FetchList("sent", cursor, cb);

        private static void FetchList(string which, string cursor, Action<bool, Page, string> cb)
        {
            if (!Ready((ok, r) => cb?.Invoke(false, null, r))) return;
            string url = $"{Base}/api/v1/mail/{which}?limit={PAGE_SIZE}"
                       + (string.IsNullOrEmpty(cursor) ? "" : $"&cursor={E(cursor)}");
            ApiClient.SessionGet(url, (ok, r) =>
            {
                Page page = null;
                if (ok) { try { page = ParsePage(r); } catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] {which} parse: {ex.Message}"); } }
                cb?.Invoke(ok && page != null, page, ok ? (page == null ? "bad page payload" : null) : r);
            });
        }

        public static void FetchMessage(string id, Action<bool, Message, string> cb)
        {
            if (!Ready((ok, r) => cb?.Invoke(false, null, r))) return;
            ApiClient.SessionGet($"{Base}/api/v1/mail/{E(id)}", (ok, r) =>
            {
                Message msg = null;
                if (ok) { try { msg = ParseMessage(r); } catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] message parse: {ex.Message}"); } }
                cb?.Invoke(ok && msg != null, msg, ok ? (msg == null ? "bad message payload" : null) : r);
            });
        }

        public static void MarkRead(string id, Action<bool, string> cb)
        {
            if (!Ready(cb)) return;
            ApiClient.SessionPost($"{Base}/api/v1/mail/{E(id)}/read", "{}", cb);
        }

        public static void Delete(string id, Action<bool, string> cb)
        {
            if (!Ready(cb)) return;
            ApiClient.SessionSend("DELETE", $"{Base}/api/v1/mail/{E(id)}", null, cb);
        }

        public static void Report(string id, string reason, Action<bool, string> cb)
        {
            if (!Ready(cb)) return;
            ApiClient.SessionPost($"{Base}/api/v1/mail/{E(id)}/report", $"{{\"reason\":\"{J(reason)}\"}}", cb);
        }

        /// <summary>POST /api/v1/mail. The idempotency key is the COMPOSER
        /// session's: a retry of the same send reuses it (the server returns the
        /// original id), and MailUI regenerates it only after a success.</summary>
        public static void Send(IList<string> to, IList<string> cc, string subject, string body,
                                string idempotencyKey, Action<bool, string, string> cb)
        {
            if (!Ready((ok, r) => cb?.Invoke(false, null, r))) return;
            var sb = new StringBuilder(256 + (body?.Length ?? 0));
            sb.Append("{\"to\":").Append(IdArray(to))
              .Append(",\"cc\":").Append(IdArray(cc))
              .Append(",\"subject\":\"").Append(J(subject)).Append('"')
              .Append(",\"body\":\"").Append(J(body)).Append('"')
              .Append(",\"idempotency_key\":\"").Append(J(idempotencyKey)).Append("\"}");
            ApiClient.SessionPost($"{Base}/api/v1/mail", sb.ToString(),
                (ok, r) => cb?.Invoke(ok, ok ? ApiClient.ExtractJsonStringPublic(r, "id") : null, ok ? null : r));
        }

        public static void Reply(string id, string body, bool all, string idempotencyKey, Action<bool, string, string> cb)
        {
            if (!Ready((ok, r) => cb?.Invoke(false, null, r))) return;
            string json = $"{{\"body\":\"{J(body)}\",\"all\":{(all ? "true" : "false")},\"idempotency_key\":\"{J(idempotencyKey)}\"}}";
            ApiClient.SessionPost($"{Base}/api/v1/mail/{E(id)}/reply", json,
                (ok, r) => cb?.Invoke(ok, ok ? ApiClient.ExtractJsonStringPublic(r, "id") : null, ok ? null : r));
        }

        private static string IdArray(IList<string> ids)
        {
            var sb = new StringBuilder("[");
            if (ids != null)
                for (int i = 0; i < ids.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append('"').Append(J(ids[i])).Append('"');
                }
            return sb.Append(']').ToString();
        }

        public static void FetchBlocks(Action<bool, List<Block>, string> cb)
        {
            if (!Ready((ok, r) => cb?.Invoke(false, null, r))) return;
            ApiClient.SessionGet($"{Base}/api/v1/mail/blocks", (ok, r) =>
            {
                List<Block> list = null;
                if (ok) { try { list = ParseBlocks(r); } catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] blocks parse: {ex.Message}"); } }
                cb?.Invoke(ok && list != null, list, ok ? null : r);
            });
        }

        public static void AddBlock(string steamId, Action<bool, string> cb)
        {
            if (!Ready(cb)) return;
            ApiClient.SessionPost($"{Base}/api/v1/mail/blocks", $"{{\"steam_id\":\"{J(steamId)}\"}}", cb);
        }

        public static void RemoveBlock(string steamId, Action<bool, string> cb)
        {
            if (!Ready(cb)) return;
            ApiClient.SessionSend("DELETE", $"{Base}/api/v1/mail/blocks/{E(steamId)}", null, cb);
        }

        public static void PutSettings(string mailFrom, Action<bool, string> cb)
        {
            if (!Ready(cb)) return;
            ApiClient.SessionSend("PUT", $"{Base}/api/v1/mail/settings", $"{{\"mail_from\":\"{J(mailFrom)}\"}}", cb);
        }

        // ── "Who can mail me" cache ─────────────────────────────────────────
        // The contract has PUT /mail/settings but no read of the current value,
        // so the client remembers what it last set (per account, PlayerPrefs)
        // and takes the server's word whenever /mail/status carries
        // <c>mail_from</c>. Default matches the server's column default.
        public static readonly string[] MAIL_FROM_VALUES = { "everyone", "played", "nobody" };

        public static string MailFrom
        {
            get
            {
                string v = null;
                try { v = PlayerPrefs.GetString(PrefKey("From"), "everyone"); } catch { }
                return Array.IndexOf(MAIL_FROM_VALUES, v) >= 0 ? v : "everyone";
            }
            set
            {
                string v = Array.IndexOf(MAIL_FROM_VALUES, value) >= 0 ? value : "everyone";
                try { PlayerPrefs.SetString(PrefKey("From"), v); } catch { }
            }
        }

        internal static string PrefKey(string what)
        {
            string sid = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(sid) || sid == "unknown") sid = "local";
            return $"CR_Mail_{what}_{sid}";
        }

        // ── Status poll (design B-6) ────────────────────────────────────────
        // 60 s cadence while the game is in a menu or a room, anchored 30 s off
        // the presence ping (which fires at ~15 s and every 60 s after), plus an
        // immediate poll when the Mail tab opens. Nothing polls while a match
        // is being tracked; a queued request fires as soon as tracking ends.
        private static bool pollRequested;
        private static float lastPollAt = -999f;
        private static bool pollInFlight;
        public static Status Last { get; private set; }

        /// <summary>Poll on the next loop wake (≤5 s).</summary>
        public static void RequestPoll() { pollRequested = true; }

        /// <summary>Poll right now if the gates allow (Mail tab open).</summary>
        public static void PollNow()
        {
            pollRequested = false;
            if (!CanPoll()) { pollRequested = true; return; }
            DoPoll();
        }

        private static bool CanPoll()
        {
            if (pollInFlight) return false;
            if (!Plugin.DataConsentGranted) return false;
            if (string.IsNullOrEmpty(SteamAuth.SessionToken)) return false;
            string sid = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(sid) || sid == "unknown") return false;
            if (GameStateWatcher.IsTracking) return false;
            return true;
        }

        private static void DoPoll()
        {
            lastPollAt = Time.realtimeSinceStartup;
            pollInFlight = true;
            FetchStatus((ok, st, err) =>
            {
                pollInFlight = false;
                if (!ok || st == null) return;
                Last = st;
                if (st.mailFrom != null) MailFrom = st.mailFrom;
                try { MailUI.OnStatus(st); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] status handler: {ex.Message}"); }
            });
        }

        public static IEnumerator StatusLoop()
        {
            MaybeSelfTest();
            yield return new WaitForSeconds(45f);
            while (true)
            {
                try { MailUI.TickPending(); } catch { }
                try
                {
                    bool due = Time.realtimeSinceStartup - lastPollAt >= 60f;
                    if ((due || pollRequested) && CanPoll())
                    {
                        pollRequested = false;
                        DoPoll();
                    }
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[MAIL] status tick failed: {ex.Message}");
                }
                yield return new WaitForSeconds(5f);
            }
        }

        // ── Parser self-test (H2HRules.SelfTest shape) ──────────────────────
        private static ConfigEntry<bool> selfTestLever;

        private static void MaybeSelfTest()
        {
            try
            {
                ConfigFile cf = Plugin.ConfigFileForLevers;
                if (cf != null)
                    selfTestLever = cf.Bind(
                        "Mail", "MailParseSelfTest",
                        false,
                        "Development only: once at startup, run the mail parser over canned server responses (subjects carrying { ] \" and \\, a subject that looks like an id member, a truncated page) and log one [MAIL] selftest line per case plus a summary line. Nothing is shown, sent or persisted.");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[MAIL] self-test bind failed: " + ex.Message); }
            bool run = false;
            try { run = selfTestLever != null && selfTestLever.Value; } catch { }
            if (!run) return;
            try
            {
                int fail;
                SelfTest(s => Plugin.Log?.LogInfo(s), out fail);
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[MAIL] self-test failed to run: " + ex.GetType().Name); }
        }

        internal const int SELFTEST_CASES = 13;

        /// <summary>Runs every canned case; returns the number run and reports
        /// the mismatches in <paramref name="fail"/>. Cases marked (control)
        /// prove a fixture has teeth: they assert that a NAIVE slice of the
        /// same payload lands in the wrong place, so a pass on the real parser
        /// is not a pass by accident.</summary>
        internal static int SelfTest(Action<string> log, out int fail)
        {
            int run = 0, failCount = 0;
            Action<string, bool, bool> Case = (name, ok, control) =>
            {
                run++;
                if (!ok) failCount++;
                log?.Invoke("[MAIL] selftest case=" + name + (control ? " (control)" : "") + (ok ? " PASS" : " FAIL"));
            };
            try
            {
                // 1-2: hostile subject and sender name; ids must stay bound.
                string inbox = "{\"items\":[{\"id\":\"m1\",\"thread_id\":\"t1\",\"sender\":{\"steam_id\":\"1\",\"name\":\"Zed{\\\"\",\"title_color\":\"#FF0000\"},"
                             + "\"subject\":\"a{b]c\\\"d\\\\e\",\"created_at\":\"2026-09-06T10:00:00Z\",\"read_at\":null,\"kind\":\"direct\"},"
                             + "{\"id\":\"m2\",\"thread_id\":\"t2\",\"sender\":{\"steam_id\":\"2\",\"name\":\"Ann\"},\"subject\":\"plain\","
                             + "\"created_at\":\"2026-09-06T09:00:00Z\",\"read_at\":\"2026-09-06T09:30:00Z\",\"kind\":\"direct\"}],\"next_cursor\":\"abc\"}";
                var page = ParsePage(inbox);
                Case("inbox_hostile_subject_ids", page.items.Count == 2 && page.items[0].id == "m1" && page.items[1].id == "m2"
                     && page.items[0].subject == "a{b]c\"d\\e" && page.items[0].sender != null && page.items[0].sender.name == "Zed{\""
                     && page.items[0].IsUnread && !page.items[1].IsUnread, false);
                Case("inbox_next_cursor", page.nextCursor == "abc", false);
                // control: a naive bracket/brace end lands INSIDE the hostile subject.
                int open = inbox.IndexOf('[');
                int naiveEnd = inbox.IndexOf(']', open);
                int realEnd = ApiClient.FindMatchingBracketStringAwarePublic(inbox, open);
                Case("naive_bracket_end_is_wrong", naiveEnd > 0 && realEnd > naiveEnd, true);
                int objOpen = inbox.IndexOf('{', open);
                int naiveObjEnd = inbox.IndexOf('}', objOpen);
                int realObjEnd = ApiClient.FindMatchingBraceStringAwarePublic(inbox, objOpen);
                Case("naive_brace_end_is_wrong", naiveObjEnd > 0 && realObjEnd > naiveObjEnd, true);

                // 3: a subject that LOOKS like an id member must not rebind the row.
                string trick = "[{\"subject\":\"x\\\",\\\"id\\\":\\\"WRONG\",\"id\":\"right\"}]";
                var tp = ParsePage(trick);
                Case("subject_shaped_like_id_member", tp.items.Count == 1 && tp.items[0].id == "right"
                     && tp.items[0].subject == "x\",\"id\":\"WRONG", false);

                // 4: bare-array root, null cursor.
                var bare = ParsePage("[{\"id\":\"m9\",\"subject\":\"s\"}]");
                Case("root_array_no_cursor", bare.items.Count == 1 && bare.items[0].id == "m9" && bare.nextCursor == null, false);

                // 5: truncated page binds NOTHING.
                var trunc = ParsePage("{\"items\":[{\"id\":\"m1\",\"subject\":\"x\"},{\"id\":\"m2\"");
                Case("truncated_page_binds_nothing", trunc.items.Count == 0, false);

                // 6-7: full message with to/cc objects; body tags kept raw (escape is the UI's job).
                string msgJson = "{\"id\":\"m1\",\"thread_id\":\"t1\",\"in_reply_to\":null,\"kind\":\"direct\","
                               + "\"sender\":{\"steam_id\":\"1\",\"name\":\"Zed\"},\"subject\":\"hi\",\"body\":\"<b>2 < 3</b>\\nline2\","
                               + "\"created_at\":\"2026-09-06T10:00:00Z\",\"read_at\":null,"
                               + "\"to\":[{\"steam_id\":\"7\",\"name\":\"Tom\"}],\"cc\":[{\"steam_id\":\"8\",\"name\":\"Cy\"},\"9\"]}";
                var msg = ParseMessage(msgJson);
                Case("message_to_cc_body", msg != null && msg.body == "<b>2 < 3</b>\nline2" && msg.inReplyTo == null
                     && msg.to.Count == 1 && msg.to[0].name == "Tom" && msg.cc.Count == 2 && msg.cc[1].steamId == "9", false);
                string msgAddr = "{\"id\":\"m2\",\"subject\":\"s\",\"body\":\"b\",\"addressees\":[{\"steam_id\":\"7\",\"name\":\"Tom\",\"kind\":\"to\"},{\"steam_id\":\"8\",\"name\":\"Cy\",\"kind\":\"cc\"}]}";
                var msg2 = ParseMessage(msgAddr);
                Case("message_addressees_fallback", msg2 != null && msg2.to.Count == 1 && msg2.to[0].steamId == "7" && msg2.cc.Count == 1 && msg2.cc[0].steamId == "8", false);

                // 8: status.
                var st = ParseStatus("{\"unread\":3,\"revision\":\"r-1\",\"mail_from\":\"played\"}");
                Case("status", st != null && st.unread == 3 && st.revision == "r-1" && st.mailFrom == "played", false);
                var st2 = ParseStatus("{\"unread\":0,\"revision\":null}");
                Case("status_null_revision", st2 != null && st2.unread == 0 && st2.revision == "" && st2.mailFrom == null, false);

                // 9: blocks (bare array).
                var blocks = ParseBlocks("[{\"steam_id\":\"5\",\"name\":\"B]a{d\",\"created_at\":\"2026-09-06T10:00:00Z\"}]");
                Case("blocks", blocks.Count == 1 && blocks[0].steamId == "5" && blocks[0].name == "B]a{d", false);

                // 10: unquote escapes.
                Case("unquote_escapes", Unquote("\"\\u0041\\n\\\"x\\\"\"") == "A\n\"x\"" && Unquote("null") == null && Unquote(" 12 ") == "12", false);
            }
            catch (Exception ex)
            {
                failCount++;
                log?.Invoke("[MAIL] selftest harness failed: " + ex.GetType().Name + ": " + ex.Message);
            }
            fail = failCount;
            bool all = run == SELFTEST_CASES && fail == 0;
            log?.Invoke("[MAIL] selftest summary run=" + run + " expected=" + SELFTEST_CASES + " fail=" + fail + (all ? " PASS" : " FAIL"));
            return run;
        }
    }
}
