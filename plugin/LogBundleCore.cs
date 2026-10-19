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

        /// <summary>
        /// Reads a log file under a cap of <paramref name="maxChars"/> BYTES
        /// (one UTF-8 byte yields at most one character, so the character
        /// count is bounded by the same figure). A file at or under the cap
        /// comes back whole. A larger file comes back as its first
        /// <paramref name="headChars"/> bytes, one marker line naming the
        /// omitted byte range and the full size, and its last
        /// maxChars - headChars bytes. The file length is measured once and
        /// both reads stop at it, so a log that grows during the read cannot
        /// make the marker untrue. Cuts are moved to UTF-8 sequence
        /// boundaries, never into a sequence.
        /// </summary>
        internal static string ReadCapped(string path, int maxChars, int headChars = HEAD_KEEP_CHARS)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !File.Exists(path)) return "";
                if (maxChars <= 0) return "";
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    long len = 0;
                    try { len = fs.Length; } catch { }
                    if (len <= maxChars || !fs.CanSeek)
                        return ReadWhole(fs, maxChars);

                    int head = Math.Min(headChars, maxChars / 2);
                    if (head < 0) head = 0;
                    int tail = maxChars - head;

                    byte[] hb = ReadExactly(fs, 0, head);
                    int headCut = Utf8BoundaryAtOrBefore(hb, hb.Length);
                    int bomSkip = HasUtf8Bom(hb, headCut) ? 3 : 0;

                    long tailStart = len - tail;
                    byte[] tb = ReadExactly(fs, tailStart, (int)(len - tailStart));
                    int skip = 0;
                    while (skip < 3 && skip < tb.Length && (tb[skip] & 0xC0) == 0x80) skip++;
                    tailStart += skip;

                    var utf8 = new UTF8Encoding(false);
                    string headText = utf8.GetString(hb, bomSkip, headCut - bomSkip);
                    string tailText = utf8.GetString(tb, skip, tb.Length - skip);
                    var sb = new StringBuilder(headText.Length + tailText.Length + 256);
                    sb.Append(headText);
                    if (headText.Length > 0 && headText[headText.Length - 1] != '\n') sb.Append('\n');
                    sb.Append(CapMarkerLine(headCut, tailStart, len, maxChars)).Append('\n');
                    sb.Append(tailText);
                    return sb.ToString();
                }
            }
            catch (Exception ex)
            {
                return "[log read error: " + ex.Message + "]";
            }
        }

        /// <summary>The one marker line of a capped file: the omitted byte
        /// range (start inclusive, end exclusive) and the file's full size.</summary>
        internal static string CapMarkerLine(long omitFrom, long omitTo, long fileBytes, int cap)
        {
            return string.Format(CultureInfo.InvariantCulture,
                "{0} omitted bytes {1} to {2} ({3} bytes) of a {4}-byte file; kept the first {1} and the last {5} bytes (cap {6})",
                CapMarkerTag, omitFrom, omitTo, omitTo - omitFrom, fileBytes, fileBytes - omitTo, cap);
        }

        private static string ReadWhole(FileStream fs, int maxChars)
        {
            using (var sr = new StreamReader(fs, new UTF8Encoding(false), true))
            {
                string all = sr.ReadToEnd();
                // A file that grew past the cap between the length read and
                // this read: keep its tail-most window, as the old reader did.
                if (all.Length <= maxChars) return all;
                return all.Substring(all.Length - maxChars);
            }
        }

        private static byte[] ReadExactly(FileStream fs, long offset, int count)
        {
            if (count <= 0) return new byte[0];
            var buf = new byte[count];
            fs.Position = offset;
            int got = 0;
            while (got < count)
            {
                int n = fs.Read(buf, got, count - got);
                if (n <= 0) break;
                got += n;
            }
            if (got == count) return buf;
            var cut = new byte[got];
            Buffer.BlockCopy(buf, 0, cut, 0, got);
            return cut;
        }

        /// <summary>The largest cut at or before <paramref name="end"/> that
        /// does not split a UTF-8 sequence.</summary>
        internal static int Utf8BoundaryAtOrBefore(byte[] b, int end)
        {
            if (end <= 0) return 0;
            if (end > b.Length) end = b.Length;
            // Find the lead byte of the last sequence that starts in the
            // window (at most three continuation bytes trail a lead).
            int i = end - 1;
            int back = 0;
            while (i > 0 && back < 3 && (b[i] & 0xC0) == 0x80) { i--; back++; }
            byte lead = b[i];
            int need;
            if ((lead & 0x80) == 0) need = 1;
            else if ((lead & 0xE0) == 0xC0) need = 2;
            else if ((lead & 0xF0) == 0xE0) need = 3;
            else if ((lead & 0xF8) == 0xF0) need = 4;
            else need = 1;   // a stray continuation run: no sequence to protect
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

        /// <summary>
        /// THREAD-SAFE: reads, assembles and scrubs the bundle. Sections in
        /// the order the senders have always received them: previous session,
        /// current BepInEx, Unity, audio self-check. Each file goes through
        /// ReadCapped, so each keeps its head.
        ///
        /// The senders keep the TAIL-most <paramref name="totalCap"/> chars of
        /// whatever they are handed, so a bundle over that cap would lose the
        /// head of its FIRST section (the previous session's banner). Compose
        /// therefore fits the scrubbed text under the cap itself: when it is
        /// over, the previous session's budget comes down by the overflow and
        /// that section alone is read again (its head is still kept; only its
        /// tail window shrinks). At most three attempts; the per-file caps
        /// are upper bounds and none is raised.
        /// </summary>
        internal static string Compose(string bepPath, string bepPrevPath, string uniPath, string audioSnapshot,
                                       int capBep, int capBepPrev, int capUni, int totalCap,
                                       ScrubFn scrub, ComposeInfo info)
        {
            if (info == null) info = new ComposeInfo();
            info.ThreadId = Thread.CurrentThread.ManagedThreadId;
            string bep = ReadCapped(bepPath, capBep);
            string uni = ReadCapped(uniPath, capUni);
            int prevCap = capBepPrev;
            string cleaned = null;
            int scrubbed = 0;
            for (int attempt = 1; attempt <= 3; attempt++)
            {
                info.Attempts = attempt;
                string bepPrev = ReadCapped(bepPrevPath, prevCap);
                string text = Assemble(bepPath, bepPrevPath, uniPath, audioSnapshot,
                                       bep, bepPrev, uni, capBep, capBepPrev, capUni);
                cleaned = scrub(text, out scrubbed);
                if (cleaned == null) break;
                info.PrevCapUsed = prevCap;
                if (cleaned.Length <= totalCap || string.IsNullOrEmpty(bepPrev) || prevCap <= 0) break;
                int over = cleaned.Length - totalCap;
                prevCap = Math.Max(0, prevCap - over - 4096);
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
