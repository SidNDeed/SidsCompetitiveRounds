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
        internal static int BucketFlag(bool anyUnfocusedFrame) { return anyUnfocusedFrame ? 0 : 1; }

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
