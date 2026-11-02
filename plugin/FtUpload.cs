#if SCR_FRAMETIME
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>FrameTime part b (FORMAT-M-PLAN.md V2 section 3), uploads: in this variant nothing the
    /// sitting builds leaves the seat, then or at any later launch, and no pending file changes. Each
    /// path is closed by a branch that exists only in this variant: the seat-evidence queue (Enqueue
    /// returns as on success without loading or saving), the closing files (SpoolClosing likewise,
    /// without writing), the pump and the queue's Load, the report outbox (EnqueueFailedReport,
    /// LoadOutbox, PersistOutbox, OutboxTick), chat (ChatClient.Connect) and every request the route
    /// classifier refuses. Closed is a property, not a constant, so the original code after each
    /// branch stays reachable to the compiler and the warning count stays Release's.
    /// Each refusal is counted per what and route. Refuse logs every refusal with the pair's running
    /// count (these paths are rare); RefuseQuiet, for the route classifier's frequent polls, logs only
    /// the first of each pair. Every pair's count is logged at each game over and at quit (VR6).</summary>
    internal static class FtUpload
    {
        internal static bool Closed => true;

        private static readonly Dictionary<string, long> _counts = new Dictionary<string, long>();

        internal static void Refuse(string what, string route)
        {
            long n = Count(what, route);
            Plugin.Log.LogInfo("[FRAME-TIME] refused what=" + what + " route=" + (route ?? "-") + " n=" + n);
        }

        internal static void RefuseQuiet(string what, string route)
        {
            if (Count(what, route) == 1)
                Plugin.Log.LogInfo("[FRAME-TIME] refused what=" + what + " route=" + (route ?? "-") + " n=1");
        }

        internal static long Count(string what, string route)
        {
            string k = what + ":" + (route ?? "-");
            lock (_counts)
            {
                long n;
                _counts.TryGetValue(k, out n);
                _counts[k] = n + 1;
                return n + 1;
            }
        }

        internal static void LogCounts(string why)
        {
            var sb = new StringBuilder(200);
            sb.Append("[FRAME-TIME] refusals why=").Append(why).Append(" pairs=").Append(_counts.Count);
            lock (_counts) foreach (var kv in _counts) sb.Append(' ').Append(kv.Key).Append('=').Append(kv.Value);
            Plugin.Log.LogInfo(sb.ToString());
        }
    }
}
#endif
