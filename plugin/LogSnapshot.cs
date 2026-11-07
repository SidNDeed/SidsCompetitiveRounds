using System;

namespace CompetitiveRounds
{
    /// <summary>The quit-time copy of the BepInEx log (LogOutput.log to LogOutput-prev.log),
    /// bounded: a log of at most CAP bytes is copied whole; a longer one keeps its first
    /// HEAD bytes (the banner, the plugin list) and its last CAP - HEAD bytes with a marker
    /// line naming the omitted byte range, so the copy on Unity's main thread at quit never
    /// reads more than CAP bytes however long the session was. One code path for both
    /// cases. Both splice points move to a UTF-8 character boundary, never outward (the
    /// head shrinks, the tail start advances), so the snapshot stays valid UTF-8 for the
    /// bug-report bundle's strict decoder (LogBundleCore.ReadCapped, which caps the result
    /// again head-and-tail). No Unity or BepInEx dependency: the seat's harness exercises
    /// the splice through reflection.</summary>
    internal static class LogSnapshot
    {
        internal const long CAP = 8L * 1024 * 1024;
        internal const int HEAD = 64 * 1024;
        /// <summary>A UTF-8 character is at most 4 bytes, so a splice point moves at most
        /// 3 bytes to reach a boundary; bytes that are not UTF-8 leave it where it was.</summary>
        internal const int MAX_STEPS = 3;

        internal static void Write(string src, string dst)
        {
            var buf = new byte[64 * 1024];
            using (var input = new System.IO.FileStream(src, System.IO.FileMode.Open, System.IO.FileAccess.Read,
                                                        System.IO.FileShare.ReadWrite | System.IO.FileShare.Delete))
            using (var output = new System.IO.FileStream(dst, System.IO.FileMode.Create, System.IO.FileAccess.Write,
                                                         System.IO.FileShare.Read))
            {
                long len = input.Length;
                if (len <= CAP) { CopyRange(input, output, 0, len, buf); return; }
                long headEnd = AlignBack(input, HEAD);
                long tailStart = AlignForward(input, len - (CAP - HEAD), len);
                CopyRange(input, output, 0, headEnd, buf);
                byte[] marker = System.Text.Encoding.UTF8.GetBytes(
                    "\n[BUG-REPORT] snapshot bounded at quit: bytes " + headEnd + " to " + tailStart
                    + " of " + len + " omitted (cap " + CAP + ")\n");
                output.Write(marker, 0, marker.Length);
                CopyRange(input, output, tailStart, len - tailStart, buf);
            }
        }

        /// <summary>The head keeps bytes [0, end): end moves back while the byte AT end
        /// continues a character, so the last kept character is whole.</summary>
        private static long AlignBack(System.IO.FileStream input, long end)
        {
            for (int i = 0; i < MAX_STEPS && end > 0 && IsContinuation(input, end); i++) end--;
            return end;
        }

        /// <summary>The tail keeps bytes [start, len): start moves forward while the byte
        /// AT start continues a character, so the tail begins on a whole character.</summary>
        private static long AlignForward(System.IO.FileStream input, long start, long len)
        {
            for (int i = 0; i < MAX_STEPS && start < len && IsContinuation(input, start); i++) start++;
            return start;
        }

        /// <summary>True when the byte at offset is a UTF-8 continuation byte (10xxxxxx);
        /// false at end of file.</summary>
        private static bool IsContinuation(System.IO.FileStream input, long offset)
        {
            input.Position = offset;
            int b = input.ReadByte();
            return b >= 0 && (b & 0xC0) == 0x80;
        }

        private static void CopyRange(System.IO.FileStream input, System.IO.FileStream output, long offset, long count, byte[] buf)
        {
            input.Position = offset;
            while (count > 0)
            {
                int n = input.Read(buf, 0, (int)Math.Min(buf.Length, count));
                if (n <= 0) break;   // the writer truncated it meanwhile: keep what was read
                output.Write(buf, 0, n);
                count -= n;
            }
        }
    }
}
