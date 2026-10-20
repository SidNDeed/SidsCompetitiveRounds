using System;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;

namespace CompetitiveRounds
{
    /// <summary>
    /// The Unity-free half of the log bundle (night of 2026-10-19 findings,
    /// lane autolog-bundle). Three jobs, all executable by the DSN-free
    /// harness tools/tests/autolog-bundle-client, which compiles THIS file:
    ///
    ///  1. ReadCapped: a capped read that keeps the HEAD of a log as well as
    ///     its tail. The old tail-only read cut the boot banner, the cr_build
    ///     line and the Harmony patch summary out of every capped
    ///     LogOutput.log, so an upload could not say which build wrote it.
    ///  2. Compose: assembles the sections, scrubs them through the caller's
    ///     scrub and fits the result under the sender cap without cutting any
    ///     file's head.
    ///  3. OffMainJob: the one mechanism that runs a bundle build on a worker
    ///     thread and hands the result back to the main thread, used by both
    ///     producers (the bug form and the automatic upload).
    ///
    /// Plus the [CLOCK] line format, so mod log lines can be placed in time
    /// and two seats aligned.
    ///
    /// Nothing here touches a Unity API, Photon or the logger; every input is
    /// a parameter. Keep it that way: the harness compiles this file alone.
    /// </summary>
    internal static class LogBundleCore
    {
        /// <summary>How much of a capped file's start is always kept: the
        /// boot banner, the cr_build line and the patch summary live there.</summary>
        internal const int HEAD_KEEP_CHARS = 200_000;

        internal const string CapMarkerTag = "[LOG-CAP]";
        internal const string ClockTag = "[CLOCK]";
        internal const double CLOCK_PERIOD_SECONDS = 60.0;

        // ---- main thread identity ---------------------------------------

        private static int _mainThreadId;

        /// <summary>Called once from the main thread (Plugin.Awake). Zero
        /// means not registered, and then nothing compares against it.</summary>
        internal static void RegisterMainThread()
        {
            _mainThreadId = Thread.CurrentThread.ManagedThreadId;
        }

        internal static int MainThreadId { get { return _mainThreadId; } }

        // ---- head-and-tail capped read ----------------------------------

        internal const string ReadUnavailable = "[log read unavailable]";
        private const int READ_ATTEMPTS = 2;

        /// <summary>Verified source intervals. Fitting can only reduce the tail;
        /// the decoded head and its exact source-byte cut stay fixed.</summary>
        private sealed class CapturedWindow
        {
            internal string Head = "", Tail = "", FixedText;
            internal long HeadBytes, TailStart, FileBytes;
            internal int Cap, TailBudget;

            internal string Render(int tailChars)
            {
                if (FixedText != null) return FixedText;
                int start = SuffixStart(Tail, tailChars);
                long tailStart = TailStart + Encoding.UTF8.GetByteCount(Tail.Substring(0, start));
                if (tailStart == HeadBytes) return Head + Tail.Substring(start);
                string gap = Head.Length > 0 && Head[Head.Length - 1] != '\n' ? "\n" : "";
                return Head + gap + CapMarkerLine(HeadBytes, tailStart, FileBytes, Cap)
                     + "\n" + Tail.Substring(start);
            }

            internal bool FitFileCap()
            {
                return FitFileCap(Tail.Length);
            }

            internal bool FitFileCap(int tailChars)
            {
                TailBudget = Math.Min(Tail.Length, Math.Max(0, tailChars));
                for (int attempt = 0; attempt < 8; attempt++)
                {
                    int over = Render(TailBudget).Length - Cap;
                    if (over <= 0) return true;
                    if (TailBudget == 0) return false;
                    TailBudget = Math.Max(0, TailBudget - over);
                }
                TailBudget = 0;
                return Render(0).Length <= Cap;
            }
        }

        /// <summary>Keep decoded head characters and the remaining tail
        /// allowance, with the truthful byte-range marker inside the cap.</summary>
        internal static string ReadCapped(string path, int maxChars, int headChars = HEAD_KEEP_CHARS)
        {
            var captured = CaptureFile(path, maxChars, headChars, null);
            return captured.Render(captured.TailBudget);
        }

        /// <summary>The same read core with an already sampled length.</summary>
        internal static string ReadCappedSnapshot(string path, long sampledLength, int maxChars,
                                                  int headChars = HEAD_KEEP_CHARS)
        {
            var captured = CaptureFile(path, maxChars, headChars, sampledLength);
            return captured.Render(captured.TailBudget);
        }

        private static CapturedWindow FixedWindow(string text, int cap)
        {
            return new CapturedWindow { FixedText = text.Length <= cap ? text : "", Cap = cap };
        }

        private static void RequireCaptured(bool captured)
        {
            if (!captured) throw new EndOfStreamException();
        }

        private static CapturedWindow CaptureFile(string path, int maxChars, int headChars, long? sample)
        {
            if (maxChars <= 0) return FixedWindow("", 0);
            try
            {
                if (string.IsNullOrEmpty(path) || !File.Exists(path)) return FixedWindow("", maxChars);
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    long sampledLength = sample ?? fs.Length;
                    for (int attempt = 0; attempt < READ_ATTEMPTS; attempt++)
                    {
                        try
                        {
                            var captured = CaptureAtLength(fs, sampledLength, maxChars, headChars);
                            RequireCaptured(fs.Length >= sampledLength);
                            if (captured.FitFileCap()) return captured;
                            break;
                        }
                        catch (IOException) { }
                        catch (DecoderFallbackException) { }
                    }
                }
            }
            catch { }
            return FixedWindow(ReadUnavailable, maxChars);
        }

        private static CapturedWindow CaptureAtLength(FileStream fs, long sampledLength, int maxChars, int headChars)
        {
            if (sampledLength < 0) throw new EndOfStreamException();
            int head = Math.Max(0, Math.Min(headChars, maxChars / 2));
            var result = new CapturedWindow { Cap = maxChars, FileBytes = sampledLength };
            var utf8 = new UTF8Encoding(false, true);
            if (sampledLength <= maxChars)
            {
                int bom;
                string all = ReadWhole(fs, sampledLength, maxChars, out bom);
                int keep = PrefixEnd(all, head);
                result.Head = all.Substring(0, keep);
                result.Tail = all.Substring(keep);
                result.HeadBytes = bom + Encoding.UTF8.GetByteCount(result.Head);
                result.TailStart = result.HeadBytes;
                return result;
            }

            int headRead = (int)Math.Min(sampledLength, 4L * head + 3);
            byte[] hb = ReadExactly(fs, 0, headRead, sampledLength);
            int headEnd = Utf8BoundaryAtOrBefore(hb, hb.Length);
            if (headRead == sampledLength && headEnd != hb.Length) throw new DecoderFallbackException();
            int bomSkip = HasUtf8Bom(hb, headEnd) ? 3 : 0;
            string decodedHead = utf8.GetString(hb, bomSkip, headEnd - bomSkip);
            int decodedKeep = PrefixEnd(decodedHead, head);
            result.Head = decodedHead.Substring(0, decodedKeep);
            result.HeadBytes = bomSkip + Encoding.UTF8.GetByteCount(result.Head);

            int tailAllowance = Math.Max(0, maxChars - result.Head.Length);
            int tailRead = (int)Math.Min(sampledLength - result.HeadBytes, 4L * tailAllowance + 3);
            long tailStart = sampledLength - tailRead;
            byte[] tb = ReadExactly(fs, tailStart, tailRead, sampledLength);
            int skip = 0;
            while (skip < tb.Length && skip < 3 && (tb[skip] & 0xC0) == 0x80) skip++;
            string decodedTail = utf8.GetString(tb, skip, tb.Length - skip);
            int tailCut = SuffixStart(decodedTail, tailAllowance);
            result.Tail = decodedTail.Substring(tailCut);
            result.TailStart = tailStart + skip + Encoding.UTF8.GetByteCount(decodedTail.Substring(0, tailCut));
            return result;
        }

        private static int PrefixEnd(string text, int chars)
        {
            int end = 0, decoded = 0;
            while (end < text.Length && decoded < Math.Max(0, chars))
            {
                if (char.IsHighSurrogate(text[end]) && end + 1 < text.Length && char.IsLowSurrogate(text[end + 1])) end += 2;
                else end++;
                decoded++;
            }
            return end;
        }

        private static int SuffixStart(string text, int chars)
        {
            int start = Math.Max(0, text.Length - Math.Max(0, chars));
            if (start > 0 && start < text.Length && char.IsHighSurrogate(text[start - 1]) && char.IsLowSurrogate(text[start])) start++;
            return start;
        }

        internal static string CapMarkerLine(long omitFrom, long omitTo, long fileBytes, int cap)
        {
            return string.Format(CultureInfo.InvariantCulture,
                "{0} omitted bytes {1} to {2} ({3} bytes) of a {4}-byte file; kept the first {1} and the last {5} bytes (cap {6})",
                CapMarkerTag, omitFrom, omitTo, omitTo - omitFrom, fileBytes, fileBytes - omitTo, cap);
        }

        private static string ReadWhole(FileStream fs, long sampledLength, int maxChars, out int bom)
        {
            byte[] all = ReadExactly(fs, 0, (int)sampledLength, sampledLength);
            bom = HasUtf8Bom(all, all.Length) ? 3 : 0;
            return new UTF8Encoding(false, true).GetString(all, bom, all.Length - bom);
        }

        private static byte[] ReadExactly(FileStream fs, long offset, int count, long sampledLength)
        {
            if (offset < 0 || count < 0 || offset > sampledLength - count) throw new EndOfStreamException();
            var buf = new byte[count];
            fs.Position = offset;
            int got = 0;
            while (got < count)
            {
                int n = fs.Read(buf, got, count - got);
                if (n <= 0) break;
                got += n;
            }
            RequireCaptured(got == count);
            return buf;
        }

        /// <summary>Largest cut at or before end that cannot split a UTF-8
        /// sequence. Strict decoding separately rejects malformed input.</summary>
        internal static int Utf8BoundaryAtOrBefore(byte[] b, int end)
        {
            if (end <= 0) return 0;
            if (end > b.Length) end = b.Length;
            int i = end - 1;
            int back = 0;
            while (i > 0 && back < 3 && (b[i] & 0xC0) == 0x80) { i--; back++; }
            byte lead = b[i];
            int need;
            if ((lead & 0x80) == 0) need = 1;
            else if ((lead & 0xE0) == 0xC0) need = 2;
            else if ((lead & 0xF0) == 0xE0) need = 3;
            else if ((lead & 0xF8) == 0xF0) need = 4;
            else need = 1;
            return i + need <= end ? end : i;
        }

        private static bool HasUtf8Bom(byte[] b, int len)
        {
            return len >= 3 && b[0] == 0xEF && b[1] == 0xBB && b[2] == 0xBF;
        }

        // ---- the bundle --------------------------------------------------

        internal delegate string ScrubFn(string text, out int replacements);

        /// <summary>What Compose hands back besides the text.</summary>
        internal sealed class ComposeInfo
        {
            internal int Scrubbed;          // replacements, or -1 when the scrub failed
            internal string Diagnostic;     // the [LOG-SCRUB] line, logged by the caller on the main thread
            internal int ThreadId;          // the thread Compose ran on
            internal int PrevCapUsed;       // the previous-session budget that fit
            internal int Attempts;
        }

        /// <summary>Capture each file once. Every fit keeps that capture's
        /// decoded head, reduces only tail windows, and measures the real scrub.
        /// The final attempt is heads-only; an over-cap mandatory payload is
        /// withheld, so no successful composition reaches a sender over its cap.</summary>
        internal static string Compose(string bepPath, string bepPrevPath, string uniPath, string audioSnapshot,
                                       int capBep, int capBepPrev, int capUni, int totalCap,
                                       ScrubFn scrub, ComposeInfo info)
        {
            if (info == null) info = new ComposeInfo();
            info.ThreadId = Thread.CurrentThread.ManagedThreadId;
            var windows = new[] {
                CaptureFile(bepPrevPath, capBepPrev, HEAD_KEEP_CHARS, null),
                CaptureFile(bepPath, capBep, HEAD_KEEP_CHARS, null),
                CaptureFile(uniPath, capUni, HEAD_KEEP_CHARS, null)
            };
            int initialPrevTail = windows[0].TailBudget;
            Func<bool, string> assemble = headsOnly => Assemble(bepPath, bepPrevPath, uniPath, audioSnapshot,
                windows[1].Render(headsOnly ? 0 : windows[1].TailBudget),
                windows[0].Render(headsOnly ? 0 : windows[0].TailBudget),
                windows[2].Render(headsOnly ? 0 : windows[2].TailBudget),
                capBep, capBepPrev, capUni);
            string cleaned = null;
            string reserved = null;
            int scrubbed = 0;
            for (int attempt = 1; attempt <= 8; attempt++)
            {
                info.Attempts = attempt;
                cleaned = scrub(assemble(false), out scrubbed);
                if (cleaned == null) break;
                info.PrevCapUsed = capBepPrev - (initialPrevTail - windows[0].TailBudget);
                if (cleaned.Length <= totalCap) break;
                if (reserved == null)
                {
                    int ignored;
                    reserved = scrub(assemble(true), out ignored);
                    if (reserved == null) { cleaned = null; break; }
                }
                if (reserved.Length > totalCap || attempt == 8)
                {
                    info.Scrubbed = -1;
                    info.Diagnostic = "[LOG-SCRUB] log bundle withheld: required heads exceed the sender cap";
                    const string unavailable = "[log bundle withheld: required heads exceed the sender cap]";
                    return totalCap >= unavailable.Length ? unavailable : "";
                }
                // Compare actual scrubbed full and head-only payloads. This
                // reserves every head and budgets the expansion of all tails.
                double ratio = (double)(totalCap - reserved.Length) / (cleaned.Length - reserved.Length);
                for (int i = 0; i < windows.Length; i++)
                {
                    int tail = windows[i].TailBudget;
                    int next = attempt == 7 ? 0 : Math.Min(Math.Max(0, tail - 1), (int)(tail * ratio));
                    windows[i].FitFileCap(next);
                }
            }
            if (cleaned == null)
            {
                info.Scrubbed = -1;
                info.Diagnostic = "[LOG-SCRUB] scrub failed — log bundle withheld rather than sent unscrubbed";
                return "[log bundle withheld: the local-path scrub failed on this machine]";
            }
            info.Scrubbed = scrubbed;
            info.Diagnostic = string.Format("[LOG-SCRUB] bundle {0:N0} chars, {1} local-identity replacement(s)",
                                            cleaned.Length, scrubbed);
            return cleaned;
        }

        private static string Assemble(string bepPath, string bepPrevPath, string uniPath, string audioSnapshot,
                                       string bep, string bepPrev, string uni,
                                       int capBep, int capBepPrev, int capUni)
        {
            int size = (bep?.Length ?? 0) + (bepPrev?.Length ?? 0) + (uni?.Length ?? 0)
                     + (audioSnapshot?.Length ?? 0) + 2048;
            var sb = new StringBuilder(size);
            if (!string.IsNullOrEmpty(bepPrev))
            {
                sb.AppendLine($"===== BepInEx LogOutput-prev.log [{bepPrevPath}]  ({bepPrev.Length:N0} chars, cap {capBepPrev:N0}) =====");
                sb.AppendLine(bepPrev);
                sb.AppendLine();
            }
            sb.AppendLine($"===== BepInEx LogOutput.log [{bepPath ?? "(path unknown)"}]  ({(bep?.Length ?? 0):N0} chars, cap {capBep:N0}) =====");
            sb.AppendLine(string.IsNullOrEmpty(bep) ? "(not found)" : bep);
            sb.AppendLine();
            sb.AppendLine($"===== Unity Player.log [{uniPath ?? "(path unknown)"}]  ({(uni?.Length ?? 0):N0} chars, cap {capUni:N0}) =====");
            sb.AppendLine(string.IsNullOrEmpty(uni) ? "(not found)" : uni);
            sb.AppendLine();
            sb.AppendLine("===== audio self-check (at submit) =====");
            sb.AppendLine(audioSnapshot ?? "(audio self-check not captured)");
            return sb.ToString();
        }

        // ---- bounded audio-registry walk ---------------------------------

        /// <summary>Pure walk over captured accessors. Every registry entry or
        /// array slot costs one visit, including null entries. elapsedTicks is
        /// elapsed work from the caller's start, not a wall-clock timestamp.
        /// Failed or exhausted captures publish no partial counts.</summary>
        internal static bool TryCountVoicesBounded(System.Collections.IDictionary eventDict,
            Func<object, System.Collections.IDictionary> transformsOf,
            Func<object, Array> holdersOf, Func<object, Array> voicesOf,
            Func<object, bool> voiceIsLive, int visitLimit, long elapsedLimitTicks,
            Func<long> elapsedTicks, out int active, out int slots)
        {
            active = 0;
            slots = 0;
            if (eventDict == null || visitLimit <= 0 || elapsedLimitTicks <= 0) return false;
            int visits = 0;
            Func<bool> withinTime = () => elapsedTicks() < elapsedLimitTicks;
            Func<bool> visit = () => visits++ < visitLimit && withinTime();
            try
            {
                int foundActive = 0, foundSlots = 0;
                if (!withinTime()) return false;
                foreach (System.Collections.DictionaryEntry eventEntry in eventDict)
                {
                    if (!visit()) return false;
                    var transforms = eventEntry.Value != null ? transformsOf(eventEntry.Value) : null;
                    if (!withinTime()) return false;
                    if (transforms == null) continue;
                    foreach (System.Collections.DictionaryEntry instanceEntry in transforms)
                    {
                        if (!visit()) return false;
                        var holders = instanceEntry.Value != null ? holdersOf(instanceEntry.Value) : null;
                        if (!withinTime()) return false;
                        if (holders == null) continue;
                        for (int h = 0; h < holders.Length; h++)
                        {
                            if (!visit()) return false;
                            object holder = holders.GetValue(h);
                            var voices = holder != null ? voicesOf(holder) : null;
                            if (!withinTime()) return false;
                            if (voices == null) continue;
                            for (int v = 0; v < voices.Length; v++)
                            {
                                if (!visit()) return false;
                                object voice = voices.GetValue(v);
                                if (voice == null) continue;
                                foundSlots++;
                                if (voiceIsLive(voice)) foundActive++;
                                if (!withinTime()) return false;
                            }
                        }
                    }
                }
                if (!withinTime()) return false;
                active = foundActive;
                slots = foundSlots;
                return true;
            }
            catch { return false; }
        }

        // ---- off-main-thread job -------------------------------------------

        /// <summary>
        /// One background build at a time, handed back to the main thread.
        /// Start is MAIN THREAD and O(1): it starts a thread and returns. The
        /// work runs on that thread and publishes its result under a lock,
        /// which is both the exclusion and the memory barrier. TakeFinished is
        /// MAIN THREAD, polled once a frame.
        /// </summary>
        internal sealed class OffMainJob<T> where T : class
        {
            private readonly object _gate = new object();
            private T _ready;
            private int _readyThreadId;
            private bool _busy;          // main thread only

            internal bool Busy { get { return _busy; } }

            /// <summary>False when a build is already running or the thread
            /// could not be started (then nothing runs). <paramref name="onError"/>
            /// turns an exception of the work into a result, so a failed build
            /// still frees the job and still reaches the main thread.</summary>
            internal bool Start(string name, Func<T> work, Func<Exception, T> onError)
            {
                if (_busy) return false;
                _busy = true;
                ThreadStart body = () =>
                {
                    int id = Thread.CurrentThread.ManagedThreadId;
                    T r;
                    try { r = work(); }
                    catch (Exception ex)
                    {
                        try { r = onError(ex); } catch { r = null; }
                    }
                    lock (_gate) { _ready = r; _readyThreadId = id; }
                };
                var t = new Thread(body);
                t.IsBackground = true;          // must never hold the process open
                t.Name = name;
                try
                {
                    t.Start();
                }
                catch
                {
                    _busy = false;
                    return false;
                }
                return true;
            }

            /// <summary>The finished result, or null while the build runs (or
            /// when it produced null). Frees the job when a build has ended.</summary>
            internal T TakeFinished(out int workerThreadId)
            {
                workerThreadId = 0;
                if (!_busy) return null;
                T r;
                bool done;
                lock (_gate)
                {
                    done = _readyThreadId != 0;
                    r = _ready;
                    workerThreadId = _readyThreadId;
                    _ready = null;
                    _readyThreadId = 0;
                }
                if (done) _busy = false;
                return r;
            }
        }

        // ---- [CLOCK] ------------------------------------------------------

        internal static bool ClockDue(double now, double lastAt)
        {
            return lastAt < 0 || now - lastAt >= CLOCK_PERIOD_SECONDS || now < lastAt;
        }

        /// <summary>
        /// The once-a-minute time line. utc is this machine's clock; rt is
        /// Time.realtimeSinceStartup, which every later line can be placed
        /// against; when Photon is connected, photon_server_ms is
        /// PhotonNetwork.ServerTimestamp at the same instant and
        /// photon_offset_ms is that minus Environment.TickCount (the clock
        /// Photon derives its server time from), so two seats' lines can be
        /// aligned on the server clock even when their wall clocks disagree.
        /// </summary>
        internal static string FormatClockLine(DateTime utcNow, double realtimeSinceStartup,
                                               bool photonConnected, int photonServerMs, int localTickMs)
        {
            var sb = new StringBuilder(160);
            sb.Append(ClockTag)
              .Append(" utc=").Append(utcNow.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture))
              .Append(" rt=").Append(realtimeSinceStartup.ToString("F3", CultureInfo.InvariantCulture));
            if (photonConnected)
            {
                int offset = unchecked(photonServerMs - localTickMs);
                sb.Append(" photon_server_ms=").Append(photonServerMs.ToString(CultureInfo.InvariantCulture))
                  .Append(" photon_offset_ms=").Append(offset.ToString(CultureInfo.InvariantCulture));
            }
            else
            {
                sb.Append(" photon=offline");
            }
            return sb.ToString();
        }
    }
}
