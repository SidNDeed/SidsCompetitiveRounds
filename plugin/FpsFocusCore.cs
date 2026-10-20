// Night 2026-10-19 calibration lane: the focus flag carried beside each local
// fps bucket of the match telemetry. Pure, so the DSN-free control in
// tools/tests/net-stall-detect compiles and drives this exact file.
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// local_fps_focus_timeline: one entry per 5 s local fps bucket, in the
    /// same order and under the same decimation as local_fps_timeline (both
    /// are DecimatedList series fed by the same Add calls). 1 = the window had
    /// focus on every frame of the bucket; 0 = it lost focus on at least one,
    /// so that bucket's rate may be the client's own 120 fps focus-loss cap
    /// ([FPSCAP]) and not a deliberate dip. The encoding is the timeline's own:
    /// comma-separated integers, so the server parses both with one reader.
    /// </summary>
    internal static class FpsFocusCore
    {
        // Observe every tracked frame before the caller excludes an FPS
        // outlier. dt is deliberately not a gate on the focus evidence.
        internal static bool ObserveFrame(bool anyUnfocusedFrame, bool focused, float dt)
        {
            return anyUnfocusedFrame || !focused;
        }

        internal static int BucketFlag(bool anyUnfocusedFrame) { return anyUnfocusedFrame ? 0 : 1; }

        // Input is the existing 0/1 CSV. Follow the FPS clamp's retained
        // bucket indices; do not run a separate character-budget clamp here.
        internal static string EncodeRetained(string flagsCsv, IList<int> retainedIndices)
        {
            if (string.IsNullOrEmpty(flagsCsv) || retainedIndices == null || retainedIndices.Count == 0) return "";
            var flags = flagsCsv.Split(',');
            var sb = new StringBuilder(retainedIndices.Count * 2);
            for (int i = 0; i < retainedIndices.Count; i++)
            {
                int source = retainedIndices[i];
                if (source < 0 || source >= flags.Length) return "";
                if (i > 0) sb.Append(',');
                sb.Append(flags[source]);
            }
            return sb.ToString();
        }

        internal static string Encode(IList<int> flags)
        {
            if (flags == null || flags.Count == 0) return "";
            var sb = new StringBuilder(flags.Count * 2);
            for (int i = 0; i < flags.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append((flags[i] != 0 ? 1 : 0).ToString(CultureInfo.InvariantCulture));
            }
            return sb.ToString();
        }
    }
}
