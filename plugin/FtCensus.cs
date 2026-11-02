#if SCR_FRAMETIME
using System.Runtime.CompilerServices;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>FrameTime M3 census (METHOD-V4.md 3.1, 3.12; VR5): every gated entry is
    /// registered once, with its component and its patch shape (the shape names of
    /// FtCalib's dispatch calibration, or "call" for a direct call), and counts its calls:
    /// in live frames with the gate clear (ON), guarded returns in live frames with the
    /// gate set (OFF), and calls outside live combat. VR5 requires every entry that ran in
    /// ON live frames to show guarded returns in OFF live frames.
    /// Use, first line of a gated entry: if (FtCensus.Skip(FtCensus.SomeEntry)) return closedValue;</summary>
    internal static class FtCensus
    {
        private const int Capacity = 256;
        internal static readonly string[] Names = new string[Capacity];
        internal static readonly int[] ComponentOf = new int[Capacity];
        internal static readonly string[] ShapeOf = new string[Capacity];
        internal static readonly long[] OnLive = new long[Capacity];
        internal static readonly long[] Guarded = new long[Capacity];
        internal static readonly long[] Outside = new long[Capacity];
        internal static int Count;
        internal static int Duplicates;

        /// <summary>Register entry id (FtE's numbering); Count is one past the highest id set.</summary>
        internal static void Set(int id, string name, int component, string shape)
        {
            if (Names[id] != null) Duplicates++;
            Names[id] = name;
            ComponentOf[id] = component;
            ShapeOf[id] = shape;
            if (id + 1 > Count) Count = id + 1;
        }

        internal static int Register(string name, int component, string shape)
        {
            int id = Count++;
            Names[id] = name;
            ComponentOf[id] = component;
            ShapeOf[id] = shape;
            return id;
        }

        /// <summary>True when the entry must return its closed value now (the gate is set). The gate is read
        /// first and only the gate decides: it is constant within a frame (FtSchedule), while Moment may change
        /// mid-frame and only sorts the counts.</summary>
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        internal static bool Skip(int entry)
        {
            if (FtGate.Off) { Guarded[entry]++; return true; }
            if (FtSpan.Moment == FtSpan.Live) OnLive[entry]++;
            else Outside[entry]++;
            return false;
        }

        /// <summary>The census line, at each game end: per entry, then per component the
        /// span ticks and calls per moment, phase and kind (non-zero cells only).</summary>
        internal static void LogGame(int game)
        {
            var sb = new StringBuilder();
            for (int e = 0; e < Count; e++)
            {
                if (Names[e] == null) continue;
                sb.Length = 0;
                sb.Append("[FRAME-TIME] census g=").Append(game).Append(" entry=").Append(Names[e])
                  .Append(" comp=").Append(FtSpan.ComponentNames[ComponentOf[e]]).Append(" shape=").Append(ShapeOf[e])
                  .Append(" on=").Append(OnLive[e]).Append(" guarded=").Append(Guarded[e]).Append(" outside=").Append(Outside[e]);
                Plugin.Log.LogInfo(sb.ToString());
            }
            for (int c = 0; c < FtSpan.Cal; c++)
            {
                sb.Length = 0;
                sb.Append("[FRAME-TIME] spans g=").Append(game).Append(" comp=").Append(FtSpan.ComponentNames[c]);
                for (int m = 0; m < FtSpan.Moments; m++)
                    for (int p = 0; p < FtSpan.Phases; p++)
                        for (int k = 0; k < FtSpan.Kinds; k++)
                        {
                            int i = FtSpan.Index(c, m, p, k);
                            if (FtSpan.Calls[i] == 0) continue;
                            sb.Append(' ').Append(FtSpan.MomentNames[m]).Append('.').Append(p == 0 ? "in" : "out").Append('.')
                              .Append(FtSpan.KindNames[k]).Append('=').Append(FtSpan.Ticks[i]).Append('/').Append(FtSpan.Calls[i]);
                        }
                Plugin.Log.LogInfo(sb.ToString());
            }
        }

        internal static void Reset()
        {
            for (int e = 0; e < Count; e++) { OnLive[e] = 0; Guarded[e] = 0; Outside[e] = 0; }
        }
    }
}
#endif
