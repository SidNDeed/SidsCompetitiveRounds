using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using CompetitiveRounds;

namespace AutologBundleTests
{
    /// <summary>
    /// Cases over plugin/LogBundleCore.cs. With no argument every case runs;
    /// with names, only those (run_tests.py runs a mutant's target and control
    /// case by name). Exit 0 only when every selected case passes.
    /// </summary>
    internal static class Program
    {
        private static int _failed;
        private static string _dir;

        private static int Main(string[] args)
        {
            CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
            LogBundleCore.RegisterMainThread();
            _dir = Path.Combine(AppContext.BaseDirectory, "case-data-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_dir);
            var cases = new Dictionary<string, Action>
            {
                { "headtail", HeadTail },
                { "headtail_default", HeadTailDefaultHead },
                { "atcap", AtCap },
                { "below", Below },
                { "utf8", Utf8Boundaries },
                { "head_characters", HeadCharacters },
                { "snapshot", Snapshot },
                { "changing_file", ChangingFile },
                { "compose", Compose },
                { "compose_real_scrub", ComposeRealScrub },
                { "offmain", OffMain },
                { "busy", Busy },
                { "viewer_reopen", ViewerReopen },
                { "viewer_refresh", ViewerRefresh },
                { "pending_worker", PendingWorker },
                { "pending_answer", PendingAnswer },
                { "clock", Clock },
                { "voice_counts", VoiceCounts },
                { "voice_visit_budget", VoiceVisitBudget },
                { "voice_elapsed_budget", VoiceElapsedBudget },
            };
            var run = args.Length == 0 ? new List<string>(cases.Keys) : new List<string>(args);
            try
            {
                foreach (string name in run)
                {
                    Action c;
                    if (!cases.TryGetValue(name, out c)) { Fail(name, "no such case"); continue; }
                    int before = _failed;
                    try { c(); }
                    catch (Exception ex) { Fail(name, "threw " + ex.GetType().Name + ": " + ex.Message); }
                    Console.WriteLine("CASE " + name + " " + (_failed == before ? "PASS" : "FAIL"));
                }
            }
            finally
            {
                try { Directory.Delete(_dir, true); } catch { }
            }
            Console.WriteLine(_failed == 0 ? "ALL PASS" : "FAILED " + _failed);
            return _failed == 0 ? 0 : 1;
        }

        private static void Fail(string where, string what)
        {
            _failed++;
            Console.WriteLine("  FAIL " + where + ": " + what);
        }

        private static void Check(bool ok, string where, string what)
        {
            if (!ok) Fail(where, what);
        }

        private static string Write(string name, string text)
        {
            string p = Path.Combine(_dir, name);
            File.WriteAllBytes(p, new UTF8Encoding(false).GetBytes(text));
            return p;
        }

        /// <summary>A log of exactly <paramref name="bytes"/> ASCII bytes:
        /// a banner, numbered filler lines, and a tail sentinel last.</summary>
        private static string MakeLog(int bytes, string banner, string tailSentinel)
        {
            var sb = new StringBuilder(bytes + 64);
            sb.Append(banner);
            int n = 0;
            string end = tailSentinel + "\n";
            while (sb.Length + end.Length < bytes)
            {
                string line = "[Info   :Competitive ROUNDS] filler line " + (n++).ToString(CultureInfo.InvariantCulture) + "\n";
                if (sb.Length + line.Length + end.Length > bytes)
                    line = new string('x', bytes - end.Length - sb.Length - 1) + "\n";
                sb.Append(line);
            }
            sb.Append(end);
            if (sb.Length != bytes) throw new InvalidOperationException("log size " + sb.Length + " != " + bytes);
            return sb.ToString();
        }

        private static int Count(string hay, string needle)
        {
            int n = 0, at = 0;
            while ((at = hay.IndexOf(needle, at, StringComparison.Ordinal)) >= 0) { n++; at += needle.Length; }
            return n;
        }

        private const string Banner =
            "[Message:   BepInEx] BepInEx 5.4.1901 - ROUNDS\n" +
            "[Info   :Competitive ROUNDS] Competitive ROUNDS v1.41.0 loaded! [SCR_BUILD_VARIANT=STANDALONE]\n" +
            "[Info   :Competitive ROUNDS] [BUILD-PROP] staged cr_build=1.41.0|standalone|0123456789ab\n" +
            "[Info   :Competitive ROUNDS] Patches applied: 321 ok, 0 failed\n";

        // ---- bounded audio capture ----------------------------------------

        private static System.Collections.IDictionary VoiceRegistry(int count)
        {
            var voices = new object[count];
            for (int i = 0; i < count; i++) voices[i] = i % 2 == 0;
            var instances = new System.Collections.Hashtable
            {
                { "instance", new object[] { voices } }
            };
            return new System.Collections.Hashtable { { "event", instances } };
        }

        private static bool CountVoices(System.Collections.IDictionary events, int visits,
            long ticks, Func<long> clock, out int active, out int slots)
        {
            return LogBundleCore.TryCountVoicesBounded(events,
                e => (System.Collections.IDictionary)e, i => (Array)i, h => (Array)h,
                v => (bool)v, visits, ticks, clock, out active, out slots);
        }

        private static void VoiceCounts()
        {
            const string where = "voice_counts";
            int active, slots;
            bool ok = CountVoices(VoiceRegistry(6), 9, 100, () => 0, out active, out slots);
            Check(ok && active == 3 && slots == 6, where,
                "under-limit registry did not return exact complete counts");
        }

        private static void VoiceVisitBudget()
        {
            const string where = "voice_visit_budget";
            int active, slots;
            bool ok = CountVoices(VoiceRegistry(5000), 64, 100, () => 0, out active, out slots);
            Check(!ok && active == 0 && slots == 0, where,
                "visit exhaustion returned success or partial counts");
            var sparse = new System.Collections.Hashtable();
            for (int i = 0; i < 5000; i++) sparse.Add(i, null);
            ok = CountVoices(sparse, 64, 100, () => 0, out active, out slots);
            Check(!ok && active == 0 && slots == 0, where,
                "null registry entries escaped the visit limit");
        }

        private static void VoiceElapsedBudget()
        {
            const string where = "voice_elapsed_budget";
            int active, slots;
            long now = 0;
            bool ok = CountVoices(VoiceRegistry(30), 100, 12, () => ++now, out active, out slots);
            Check(!ok && active == 0 && slots == 0, where,
                "elapsed exhaustion returned success or partial counts");
            now = 0;
            ok = LogBundleCore.TryCountVoicesBounded(VoiceRegistry(1),
                e => (System.Collections.IDictionary)e, i => (Array)i, h => (Array)h,
                v => { now = 20; return (bool)v; }, 100, 12, () => now, out active, out slots);
            Check(!ok && active == 0 && slots == 0, where,
                "last accessor crossed the elapsed limit without failing closed");
        }

        // ---- the capped read ----------------------------------------------

        private static Match Marker(string text, string where)
        {
            var matches = Regex.Matches(text, @"\[LOG-CAP\] omitted bytes (\d+) to (\d+) \((\d+) bytes\) of a (\d+)-byte file; kept the first (\d+) and the last (\d+) bytes \(cap (\d+)\)");
            Check(matches.Count == 1, where, "expected exactly one byte-range marker");
            return matches.Count == 1 ? matches[0] : null;
        }

        private static void CheckRange(string where, string got, byte[] source, int cap, long expectedHead)
        {
            Check(got.Length <= cap, where, "the marker-inclusive result exceeds its character cap");
            Check(got.IndexOf('\uFFFD') < 0, where, "capture introduced U+FFFD");
            Match m = Marker(got, where);
            if (m == null) return;
            long from = long.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
            long to = long.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture);
            long total = long.Parse(m.Groups[4].Value, CultureInfo.InvariantCulture);
            Check(from == expectedHead, where, "head cut is " + from + " bytes, expected " + expectedHead);
            Check(total == source.Length && to >= from && to <= total, where, "range or sampled size is false");
            Check(long.Parse(m.Groups[3].Value) == to - from && long.Parse(m.Groups[5].Value) == from && long.Parse(m.Groups[6].Value) == total - to,
                  where, "marker retained/omitted byte counts disagree");
            Check(int.Parse(m.Groups[7].Value) == cap, where, "marker cap changed");
            if (from < 0 || to < from || to > source.Length) return;
            var utf8 = new UTF8Encoding(false, true);
            int bom = source.Length >= 3 && source[0] == 0xEF && source[1] == 0xBB && source[2] == 0xBF ? 3 : 0;
            string head = utf8.GetString(source, bom, (int)from - bom);
            string tail = utf8.GetString(source, (int)to, source.Length - (int)to);
            string expected = head + (head.Length > 0 && head[head.Length - 1] != '\n' ? "\n" : "") + m.Value + "\n" + tail;
            Check(got == expected, where, "marker does not describe the exact captured intervals");
        }

        private static void HeadTail()
        {
            const string where = "headtail";
            int cap = 20_000, head = 4_000;
            string text = MakeLog(75_000, Banner, "TAIL-END-SENTINEL");
            string got = LogBundleCore.ReadCapped(Write("big.log", text), cap, head);
            Check(got.StartsWith(text.Substring(0, head), StringComparison.Ordinal), where, "the complete decoded head is not kept");
            Check(got.EndsWith("TAIL-END-SENTINEL\n", StringComparison.Ordinal), where, "the tail is not kept");
            CheckRange(where, got, Encoding.UTF8.GetBytes(text), cap, head);
        }

        private static void HeadTailDefaultHead()
        {
            const string where = "headtail_default";
            const int cap = 1_500_000;
            string text = MakeLog(4_000_000, Banner, "TAIL-END-SENTINEL");
            string got = LogBundleCore.ReadCapped(Write("bigger.log", text), cap);
            Check(LogBundleCore.HEAD_KEEP_CHARS >= 200_000, where, "HEAD_KEEP_CHARS is under 200,000");
            Check(got.StartsWith(text.Substring(0, 200_000), StringComparison.Ordinal), where, "the first 200,000 decoded characters are not kept");
            Check(got.EndsWith("TAIL-END-SENTINEL\n", StringComparison.Ordinal), where, "the tail is not kept");
            CheckRange(where, got, Encoding.UTF8.GetBytes(text), cap, 200_000);
        }

        private static void AtCap()
        {
            const string where = "atcap";
            int cap = 20_000;
            string text = MakeLog(cap, Banner, "TAIL-END-SENTINEL");
            string got = LogBundleCore.ReadCapped(Write("atcap.log", text), cap, 4_000);
            Check(got == text, where, "a file at the cap is not returned whole");
            Check(Count(got, LogBundleCore.CapMarkerTag) == 0, where, "a file at the cap carries a marker");
        }

        private static void Below()
        {
            const string where = "below";
            int cap = 20_000;
            string text = MakeLog(cap - 1_234, Banner, "TAIL-END-SENTINEL");
            string got = LogBundleCore.ReadCapped(Write("below.log", text), cap, 4_000);
            Check(got == text, where, "a file under the cap is not returned whole");
            Check(Count(got, LogBundleCore.CapMarkerTag) == 0, where, "a file under the cap carries a marker");
            Check(LogBundleCore.ReadCapped(Path.Combine(_dir, "absent.log"), cap) == "", where, "an absent file is not empty");
        }

        private static void Utf8Boundaries()
        {
            const string where = "utf8";
            int cap = 2_000, head = 999;
            var sb = new StringBuilder(new string('a', 998) + "\U0001F600" + new string('m', 8_000));
            for (int i = 0; i < 600; i++) sb.Append("\u20AC\U0001F600");
            string text = sb.Append("TAIL\n").ToString();
            string got = LogBundleCore.ReadCapped(Write("utf8.log", text), cap, head);
            Check(got.StartsWith(new string('a', 998) + "\U0001F600", StringComparison.Ordinal), where, "a head-ending surrogate pair was split or dropped");
            Check(got.EndsWith("TAIL\n", StringComparison.Ordinal), where, "UTF-8 tail missing");
            CheckRange(where, got, Encoding.UTF8.GetBytes(text), cap, 1002);
        }

        private static void HeadCharacters()
        {
            const string where = "head_characters";
            string[] units = { "a", "\u00E9", "\u20AC", "\U0001F600" };
            int n = 0;
            foreach (int cap in new[] { 1_500_000, 1_000_000 })
            foreach (string unit in units)
            {
                const string sentinel = "HEAD-END\n";
                var prefix = new StringBuilder();
                for (int decoded = 0; decoded < 200_000 - sentinel.Length; decoded++) prefix.Append(unit);
                prefix.Append(sentinel);
                string text = prefix.ToString() + new string('m', cap + 1_000) + "TAIL-END\n";
                byte[] body = Encoding.UTF8.GetBytes(text);
                bool bom = unit == "a";
                byte[] all = new byte[body.Length + (bom ? 3 : 0)];
                if (bom) { all[0] = 0xEF; all[1] = 0xBB; all[2] = 0xBF; }
                Buffer.BlockCopy(body, 0, all, bom ? 3 : 0, body.Length);
                string path = Path.Combine(_dir, "characters-" + n++ + ".log");
                File.WriteAllBytes(path, all);
                string got = LogBundleCore.ReadCapped(path, cap);
                Check(got.StartsWith(prefix.ToString(), StringComparison.Ordinal), where, "the sentinel ending at decoded scalar character 200,000 was lost");
                Check(got.EndsWith("TAIL-END\n", StringComparison.Ordinal), where, "tail sentinel missing");
                CheckRange(where, got, all, cap, Encoding.UTF8.GetByteCount(prefix.ToString()) + (bom ? 3 : 0));
            }
        }

        private static void Snapshot()
        {
            const string where = "snapshot";
            string sampled = MakeLog(12_000, Banner, "SAMPLED-END");
            string path = Write("append-small.log", sampled + new string('z', 60_000) + "APPENDED");
            string got = LogBundleCore.ReadCappedSnapshot(path, sampled.Length, 20_000, 4_000);
            Check(got == sampled, where, "whole-file read escaped its sampled byte limit");
            string large = MakeLog(55_000, Banner, "SAMPLED-TAIL");
            path = Write("append-large.log", large + new string('z', 60_000) + "APPENDED");
            got = LogBundleCore.ReadCappedSnapshot(path, large.Length, 20_000, 4_000);
            Check(got.StartsWith(large.Substring(0, 4_000), StringComparison.Ordinal) && got.EndsWith("SAMPLED-TAIL\n", StringComparison.Ordinal), where, "capped snapshot lost its head or sampled tail");
            Check(!got.Contains("APPENDED"), where, "post-sample content entered the capture");
            CheckRange(where, got, Encoding.UTF8.GetBytes(large), 20_000, 4_000);
        }

        private static void ChangingFile()
        {
            const string where = "changing_file";
            foreach (int size in new[] { 3_000, 90_000 })
            {
                string text = MakeLog(size, Banner, "BEFORE-TRUNCATION");
                string got = LogBundleCore.ReadCappedSnapshot(Write("short-" + size + ".log", text), size + 1_000, 20_000, 4_000);
                Check(got == LogBundleCore.ReadUnavailable, where, "a short read did not yield the fixed unavailable line");
                Check(!got.Contains(LogBundleCore.CapMarkerTag), where, "a requested interval was reported as captured after truncation");
            }
            foreach (byte[] partial in new[] { new byte[] { 0xE2, 0x82 }, new byte[] { 0xF0, 0x9F, 0x98 } })
            foreach (int size in new[] { 3_000, 90_000 })
            {
                byte[] bytes = new byte[size + partial.Length];
                for (int i = 0; i < size; i++) bytes[i] = (byte)'a';
                Buffer.BlockCopy(partial, 0, bytes, size, partial.Length);
                string path = Path.Combine(_dir, "partial-" + size + "-" + partial.Length + ".log");
                File.WriteAllBytes(path, bytes);
                string got = LogBundleCore.ReadCappedSnapshot(path, bytes.Length, 20_000, 4_000);
                Check(got == LogBundleCore.ReadUnavailable, where, "an incomplete sampled UTF-8 endpoint was not unavailable after retry");
                Check(got.IndexOf('\uFFFD') < 0, where, "partial append introduced U+FFFD");
            }
        }

        // ---- the composer ---------------------------------------------------

        private static string Identity(string text, out int n) { n = 0; return text; }
        private static string Refuse(string text, out int n) { n = 0; return null; }

        /// <summary>Three capped files whose capped sum is over the sender cap:
        /// the scrubbed bundle fits the sender cap, and every file still opens
        /// with its own banner (the sender's tail trim would otherwise cut the
        /// previous session's head); the audio self-check is last; a refused
        /// scrub withholds the text.</summary>
        private static void Compose()
        {
            const string where = "compose";
            int capCur = 30_000, capPrev = 20_000, capUni = 20_000, total = 70_000;
            string prevBanner = "PREV-BANNER cr_build=prev\n";
            string curBanner = "CUR-BANNER cr_build=cur\n";
            string uniBanner = "UNI-BANNER engine\n";
            string prev = Write("LogOutput-prev.log", MakeLog(90_000, prevBanner, "PREV-TAIL"));
            string cur = Write("LogOutput.log", MakeLog(90_000, curBanner, "CUR-TAIL"));
            string uni = Write("Player.log", MakeLog(90_000, uniBanner, "UNI-TAIL"));
            var info = new LogBundleCore.ComposeInfo();
            string got = LogBundleCore.Compose(cur, prev, uni, "AUDIO-SNAPSHOT", capCur, capPrev, capUni, total, Identity, info);
            Check(got.Length <= total, where, "the bundle (" + got.Length + ") is over the sender cap " + total);
            Check(info.Attempts >= 2, where, "the overflow was not fitted (attempts " + info.Attempts + ")");
            Check(info.PrevCapUsed < capPrev, where, "the previous session's window did not narrow");
            foreach (var banner in new[] { prevBanner, curBanner, uniBanner })
                Check(got.Contains("]  (") && got.Contains(banner), where, "a section lost its head: " + banner.Trim());
            foreach (var t in new[] { "PREV-TAIL", "CUR-TAIL", "UNI-TAIL" })
                Check(got.Contains(t), where, "a section lost its tail: " + t);
            Check(Count(got, LogBundleCore.CapMarkerTag) == 3, where, "expected one marker per capped file");
            Check(got.TrimEnd().EndsWith("AUDIO-SNAPSHOT", StringComparison.Ordinal), where, "the audio self-check is not last");
            int ip = got.IndexOf("LogOutput-prev.log", StringComparison.Ordinal);
            int ic = got.IndexOf("===== BepInEx LogOutput.log", StringComparison.Ordinal);
            int iu = got.IndexOf("===== Unity Player.log", StringComparison.Ordinal);
            Check(ip >= 0 && ip < ic && ic < iu, where, "section order changed");
            Check(info.Scrubbed == 0 && info.Diagnostic != null && info.Diagnostic.StartsWith("[LOG-SCRUB] bundle "), where, "diagnostic missing");
            // Under the cap from the start: one attempt, every window intact.
            var info2 = new LogBundleCore.ComposeInfo();
            string fits = LogBundleCore.Compose(cur, prev, uni, "AUDIO", capCur, capPrev, capUni, 1_000_000, Identity, info2);
            Check(info2.Attempts == 1 && info2.PrevCapUsed == capPrev, where, "a bundle under the cap was re-read");
            Check(fits.Contains(prevBanner) && fits.Contains("PREV-TAIL"), where, "prev section incomplete when it fits");
            var info3 = new LogBundleCore.ComposeInfo();
            string withheld = LogBundleCore.Compose(cur, prev, uni, "AUDIO", capCur, capPrev, capUni, total, Refuse, info3);
            Check(info3.Scrubbed == -1, where, "a refused scrub is not reported as -1");
            Check(!withheld.Contains(curBanner), where, "a refused scrub still returned log text");
        }

        private static string RealScrub(string text, out int replacements)
        {
            return LogScrub.Scrub(text, "abc", null, out replacements);
        }

        private static string ExpandingLog(string banner, string headSentinel, string tailSentinel)
        {
            var text = new StringBuilder(banner);
            while (text.Length + 4 <= 200_000 - headSentinel.Length) text.Append("abc\n");
            while (text.Length < 200_000 - headSentinel.Length) text.Append('a');
            text.Append(headSentinel);
            while (text.Length < 2_000_000) text.Append("abc\n");
            return text.Append(tailSentinel).ToString();
        }

        private static void ComposeRealScrub()
        {
            const string where = "compose_real_scrub";
            string[] banners = { "PREV-EXPAND\n", "CUR-EXPAND\n", "UNI-EXPAND\n" };
            string[] heads = { "PREV-HEAD-END\n", "CUR-HEAD-END\n", "UNI-HEAD-END\n" };
            string[] tails = { "PREV-TAIL-END\n", "CUR-TAIL-END\n", "UNI-TAIL-END\n" };
            string[] texts = new string[3], paths = new string[3];
            int[] caps = { 1_000_000, 1_500_000, 1_000_000 };
            for (int i = 0; i < 3; i++)
            {
                texts[i] = ExpandingLog(banners[i], heads[i], tails[i]);
                paths[i] = Write("expanding-" + i + ".log", texts[i]);
            }
            var info = new LogBundleCore.ComposeInfo();
            string got = LogBundleCore.Compose(paths[1], paths[0], paths[2], "AUDIO-EXPAND-LAST",
                caps[1], caps[0], caps[2], 3_500_000, RealScrub, info);
            Check(got.Length <= 3_500_000, where, "real scrub expansion escaped the sender cap");
            Check(info.Attempts >= 2 && info.Scrubbed > 0, where, "the expanding scrub was not measured while fitting");
            Check(Count(got, LogBundleCore.CapMarkerTag) == 3, where, "a section or its one cap marker was discarded");
            Check(got.TrimEnd().EndsWith("AUDIO-EXPAND-LAST", StringComparison.Ordinal), where, "audio is not last");
            string[] headers = { "===== BepInEx LogOutput-prev.log", "===== BepInEx LogOutput.log", "===== Unity Player.log", "===== audio self-check" };
            int last = -1;
            for (int i = 0; i < 3; i++)
            {
                int section = got.IndexOf(headers[i], StringComparison.Ordinal);
                int next = got.IndexOf(headers[i + 1], StringComparison.Ordinal);
                Check(section > last && next > section, where, "section order or presence changed");
                last = section;
                if (section < 0 || next <= section) continue;
                int content = got.IndexOf('\n', section) + 1;
                int end = next - 2 * Environment.NewLine.Length;
                string chunk = got.Substring(content, end - content);
                Match m = Marker(chunk, where);
                Check(chunk.Contains(banners[i]) && chunk.Contains(heads[i]) && chunk.EndsWith(tails[i], StringComparison.Ordinal),
                      where, "a fitted section lost its head sentinel or tail sentinel");
                if (m == null) continue;
                int from = int.Parse(m.Groups[1].Value), to = int.Parse(m.Groups[2].Value);
                Check(from == 200_000 && int.Parse(m.Groups[4].Value) == Encoding.UTF8.GetByteCount(texts[i]),
                      where, "a fitted marker changed the reserved head or sampled byte size");
                Check(to > from && to < texts[i].Length && int.Parse(m.Groups[3].Value) == to - from
                      && int.Parse(m.Groups[5].Value) == from && int.Parse(m.Groups[6].Value) == texts[i].Length - to,
                      where, "a fitted marker reports false retained intervals");
                Check(int.Parse(m.Groups[7].Value) == caps[i], where, "the production file cap changed");
                if (to < from || to > texts[i].Length) continue;
                string raw = texts[i].Substring(0, from) + m.Value + "\n" + texts[i].Substring(to);
                Check(raw.Length <= caps[i], where, "a fitted section exceeded its original file cap");
                int ignored;
                Check(chunk == RealScrub(raw, out ignored), where, "fitted marker does not describe the scrubbed captured intervals");
                Check(chunk.IndexOf('\uFFFD') < 0, where, "fitting introduced U+FFFD");
            }
            var tinyInfo = new LogBundleCore.ComposeInfo();
            string tiny = LogBundleCore.Compose(paths[1], paths[0], paths[2], "AUDIO",
                caps[1], caps[0], caps[2], 100, RealScrub, tinyInfo);
            Check(tiny.Length <= 100 && tinyInfo.Scrubbed == -1 && !tiny.Contains(banners[0]), where,
                  "mandatory content that cannot fit did not fail closed within the cap");
        }

        // ---- the off-main job -----------------------------------------------

        private sealed class Result
        {
            internal bool StartReturnedFirst;
            internal LogBundleCore.ComposeInfo Info;
            internal string Text;
        }

        /// <summary>The bundle builder never runs on the main thread: the job
        /// returns from Start before the work finishes, the composer's thread
        /// id differs from the registered main thread, and the worker id the
        /// job reports is the composer's.</summary>
        private static void OffMain()
        {
            const string where = "offmain";
            string cur = Write("om-LogOutput.log", MakeLog(50_000, Banner, "TAIL"));
            var started = new ManualResetEventSlim(false);
            var job = new LogBundleCore.OffMainJob<Result>();
            bool ok = job.Start("test-bundle", () =>
            {
                var r = new Result();
                // Released only after Start has returned on the main thread.
                // A synchronous Start never reaches the release, so the wait
                // times out and the flag stays false.
                r.StartReturnedFirst = started.Wait(2_000);
                r.Info = new LogBundleCore.ComposeInfo();
                r.Text = LogBundleCore.Compose(cur, null, null, "AUDIO", 20_000, 10_000, 10_000, 100_000, Identity, r.Info);
                return r;
            }, ex => null);
            started.Set();
            Check(ok, where, "Start refused an idle job");
            Check(LogBundleCore.MainThreadId == Thread.CurrentThread.ManagedThreadId, where, "the main thread is not registered");
            Result got = null;
            int workerId = 0;
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (got == null && DateTime.UtcNow < deadline)
            {
                got = job.TakeFinished(out workerId);
                if (got == null) Thread.Sleep(2);
            }
            Check(got != null, where, "the job never finished");
            if (got == null) return;
            Check(got.StartReturnedFirst, where, "Start did not return before the work ran: the build ran on the caller's thread");
            Check(got.Info.ThreadId != 0 && got.Info.ThreadId != LogBundleCore.MainThreadId, where,
                  "the bundle was composed on the main thread (" + got.Info.ThreadId + ")");
            Check(workerId == got.Info.ThreadId, where, "the reported worker id is not the composer's thread");
            Check(!job.Busy, where, "the job stays busy after its result was taken");
            Check(got.Text.StartsWith("===== BepInEx LogOutput.log", StringComparison.Ordinal) && got.Text.Contains("cr_build="), where,
                  "the off-main compose did not produce the bundle");
        }

        /// <summary>One build at a time; a failed build still frees the job
        /// and reaches the main thread through the error delegate.</summary>
        private static void Busy()
        {
            const string where = "busy";
            var hold = new ManualResetEventSlim(false);
            var job = new LogBundleCore.OffMainJob<string>();
            Check(job.Start("hold", () => { hold.Wait(5_000); return "first"; }, ex => "error"), where, "first Start refused");
            Check(job.Busy, where, "a running job is not busy");
            Check(!job.Start("second", () => "second", ex => "error"), where, "a second Start ran beside the first");
            int wid;
            Check(job.TakeFinished(out wid) == null, where, "a result before the work finished");
            hold.Set();
            string r = null;
            var deadline = DateTime.UtcNow.AddSeconds(10);
            while (r == null && DateTime.UtcNow < deadline) { r = job.TakeFinished(out wid); if (r == null) Thread.Sleep(2); }
            Check(r == "first", where, "the first result was not handed back");
            var job2 = new LogBundleCore.OffMainJob<string>();
            job2.Start("throws", () => { throw new InvalidOperationException("boom"); }, ex => "error:" + ex.GetType().Name);
            r = null;
            deadline = DateTime.UtcNow.AddSeconds(10);
            while (r == null && DateTime.UtcNow < deadline) { r = job2.TakeFinished(out wid); if (r == null) Thread.Sleep(2); }
            Check(r == "error:InvalidOperationException", where, "a throwing build did not come back through the error delegate");
            Check(!job2.Busy, where, "a failed build left the job busy");
        }

        // ---- bug-form lifecycle, with the real worker job ------------------

        private static string TakePendingResult(LogBundleCore.OffMainJob<string> job)
        {
            string result = null;
            var deadline = DateTime.UtcNow.AddSeconds(10);
            int workerId;
            while (result == null && DateTime.UtcNow < deadline)
            {
                result = job.TakeFinished(out workerId);
                if (result == null) Thread.Sleep(2);
            }
            return result;
        }

        private static void PendingWorker()
        {
            const string where = "pending_worker";
            const string status = "Submitting...";
            var state = new LogBundleCore.PendingSubmission();
            var job = new LogBundleCore.OffMainJob<string>();
            var release = new ManualResetEventSlim(false);
            int requests = 0, accepted = 0;
            Func<bool> submit = () =>
            {
                if (!state.Begin(status) || job.Busy) return false;
                accepted++;
                return job.Start("pending-worker", () =>
                {
                    if (!release.Wait(10_000)) throw new TimeoutException();
                    return "body";
                }, ex => "build-error");
            };
            try
            {
                Check(submit(), where, "the initial Submit was refused");
                // Closing has no completion transition; reopen runs the real state.
                state.Reopen();
                Check(!state.CanSubmit, where, "reopen enabled Submit during the build");
                Check(state.Status == status, where, "reopen hid the pending status");
                Check(!submit(), where, "a second Submit was accepted during the build");
                release.Set();
                string body = TakePendingResult(job);
                if (body == "body") requests++;
                Check(body == "body", where, "the delayed build did not reach handoff");
                int wid;
                Check(job.TakeFinished(out wid) == null, where, "a built body was handed off twice");
                Check(accepted == 1 && requests == 1, where, "one accepted Submit did not produce exactly one request");
                Check(!state.CanSubmit, where, "handoff ended pending before the answer");
                state.Answer("sent");
                Check(state.CanSubmit && state.Status == "sent", where, "answer did not finish pending");
            }
            finally { release.Set(); }
        }

        private static void PendingAnswer()
        {
            const string where = "pending_answer";
            const string status = "Submitting...";
            var state = new LogBundleCore.PendingSubmission();
            var job = new LogBundleCore.OffMainJob<string>();
            var release = new ManualResetEventSlim(false);
            Check(state.Begin(status), where, "the initial Submit was refused");
            Check(job.Start("pending-answer", () =>
            {
                if (!release.Wait(10_000)) throw new TimeoutException();
                return "body";
            }, ex => "build-error"), where, "the delayed worker was refused");
            release.Set();
            int requests = TakePendingResult(job) == "body" ? 1 : 0;
            Check(requests == 1 && !job.Busy, where, "the build did not finish before the delayed answer");
            state.Reopen();
            Check(!state.CanSubmit, where, "reopen enabled Submit before the answer");
            Check(state.Status == status, where, "reopen hid the in-flight status");
            Check(!state.Begin(status), where, "a second Submit was accepted before the answer");
            int wid;
            Check(job.TakeFinished(out wid) == null && requests == 1, where, "the request was delivered again");
            state.Answer("request failed");
            Check(state.CanSubmit && state.Status == "request failed", where, "a failed answer did not finish pending");
            Check(state.Begin(status), where, "the form could not submit after an answer");
            state.BuildFailure("builder failed");
            Check(state.CanSubmit && state.Status == "builder failed", where, "an explicit build failure left pending");
            state.Reopen();
            Check(state.CanSubmit && state.Status == "", where, "an idle reopen did not clear the completed status");
        }

        // ---- viewer freshness, with the real worker job --------------------

        private static void ViewerReopen() { ViewerReadScenario("viewer_reopen", true); }
        private static void ViewerRefresh() { ViewerReadScenario("viewer_refresh", false); }

        private static void ViewerReadScenario(string where, bool reopen)
        {
            string path = Write(where + ".log", "BEFORE\n");
            var job = new LogBundleCore.OffMainJob<string>();
            var latch = new LogBundleCore.ReadRequestLatch();
            var captured = new ManualResetEventSlim(false);
            var release = new ManualResetEventSlim(false);
            Thread firstWorker = null;
            int starts = 0;
            Func<bool> dispatch = () =>
            {
                int ordinal = starts + 1;
                bool started = job.Start("viewer-read", () =>
                {
                    string text = File.ReadAllText(path);
                    if (ordinal == 1)
                    {
                        firstWorker = Thread.CurrentThread;
                        captured.Set();
                        if (!release.Wait(10_000)) throw new TimeoutException();
                    }
                    return text;
                }, ex => "read-error");
                if (started) starts++;
                return started;
            };
            try
            {
                int wid;
                latch.Request();
                Check(latch.Pump(job, dispatch, out wid) == null, where, "an initial request already returned a result");
                Check(starts == 1, where, "an idle request did not dispatch");
                bool firstCaptured = captured.Wait(10_000);
                Check(firstCaptured, where, "the first read never captured its snapshot");
                if (!firstCaptured) return;
                if (reopen)
                {
                    // The viewer is closed: finish and publish A without consuming it.
                    release.Set();
                    Check(firstWorker.Join(10_000), where, "the closed read did not finish");
                    File.AppendAllText(path, "APPENDED\n");
                    latch.Request();
                }
                else
                {
                    File.AppendAllText(path, "APPENDED\n");
                    latch.Request();
                    latch.Request();
                    Check(latch.Pump(job, dispatch, out wid) == null, where, "a held read completed before release");
                    Check(starts == 1, where, "refresh started a second concurrent read");
                    release.Set();
                    Check(firstWorker.Join(10_000), where, "the busy read did not finish");
                }
                string latest = latch.Pump(job, dispatch, out wid);
                Check(latest == "BEFORE\n", where, "the completed old read was not consumed first");
                Check(starts == 2, where, "the pending refresh was not dispatched after consuming the finished read");
                var deadline = DateTime.UtcNow.AddSeconds(10);
                while (job.Busy && DateTime.UtcNow < deadline)
                {
                    string result = latch.Pump(job, dispatch, out wid);
                    if (result != null) latest = result;
                    if (job.Busy) Thread.Sleep(2);
                }
                Check(!job.Busy, where, "the fresh read never finished");
                Check(latest != null && latest.Contains("APPENDED\n"), where, "the published refresh lost fresh lines");
                Check(latch.Pump(job, dispatch, out wid) == null, where, "a read was published twice");
                Check(starts == 2, where, "refresh requests did not coalesce into exactly one further read");
            }
            finally { release.Set(); }
        }

        // ---- [CLOCK] --------------------------------------------------------

        private static readonly Regex ClockConnected = new Regex(
            @"^\[CLOCK\] utc=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z rt=\d+\.\d{3} photon_server_ms=-?\d+ photon_offset_ms=-?\d+$");
        private static readonly Regex ClockOffline = new Regex(
            @"^\[CLOCK\] utc=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z rt=\d+\.\d{3} photon=offline$");

        private static void Clock()
        {
            const string where = "clock";
            var saved = CultureInfo.CurrentCulture;
            try
            {
                // A comma-decimal culture must not leak into the line.
                CultureInfo.CurrentCulture = new CultureInfo("de-DE");
                var t = new DateTime(2026, 10, 19, 21, 40, 8, 123, DateTimeKind.Utc);
                string on = LogBundleCore.FormatClockLine(t, 1234.5, true, 5_000_250, 5_000_000);
                Check(ClockConnected.IsMatch(on), where, "connected line has the wrong format: " + on);
                Check(on == "[CLOCK] utc=2026-10-19T21:40:08.123Z rt=1234.500 photon_server_ms=5000250 photon_offset_ms=250",
                      where, "connected line content: " + on);
                string wrap = LogBundleCore.FormatClockLine(t, 1, true, int.MinValue + 5, int.MaxValue - 4);
                Check(wrap.EndsWith(" photon_offset_ms=10", StringComparison.Ordinal), where, "the offset does not wrap like Photon's tick math: " + wrap);
                string off = LogBundleCore.FormatClockLine(t, 0.25, false, 0, 0);
                Check(ClockOffline.IsMatch(off), where, "offline line has the wrong format: " + off);
                var local = new DateTime(2026, 10, 19, 14, 40, 8, 123, DateTimeKind.Local);
                Check(LogBundleCore.FormatClockLine(local, 1, false, 0, 0).Contains("utc=" + local.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture)),
                      where, "a local time is not written as UTC");
            }
            finally { CultureInfo.CurrentCulture = saved; }
            Check(LogBundleCore.CLOCK_PERIOD_SECONDS == 60.0, where, "the period is not one minute");
            Check(LogBundleCore.ClockDue(5.0, -1), where, "the first line is not due at once");
            Check(!LogBundleCore.ClockDue(64.9, 5.0), where, "a line is due before a minute passed");
            Check(LogBundleCore.ClockDue(65.0, 5.0), where, "a line is not due after a minute");
        }
    }
}
