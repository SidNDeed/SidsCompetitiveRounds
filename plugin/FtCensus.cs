#if SCR_FRAMETIME
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;
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

        internal static long SumOn()
        {
            long s = 0;
            for (int e = 0; e < Count; e++) s += OnLive[e];
            return s;
        }

        internal static long SumGuarded()
        {
            long s = 0;
            for (int e = 0; e < Count; e++) s += Guarded[e];
            return s;
        }

        internal static void Reset()
        {
            for (int e = 0; e < Count; e++) { OnLive[e] = 0; Guarded[e] = 0; Outside[e] = 0; }
        }

        /// <summary>The boot line `[FRAME-TIME] scope census entries=<count> wrapped=<count>` (R-SCOPE, ruling R6-A3.11.147
        /// (3)(f)): entries counts the census's registered collector entry points; wrapped counts those whose every
        /// call site of Skip, found in this plugin's compiled IL (a call to Skip right after the constant that names the
        /// entry), lies in a method that also calls FtSpan.Open and FtSpan.Close, so the entry's work runs inside a
        /// scope. An entry with no call site is not wrapped. FtClock.OnStart, at the first frame boundary, after
        /// FtE.RegisterAll.</summary>
        internal static void LogScopeCensus()
        {
            int entries = 0, wrapped = 0;
            string why = "";
            try
            {
                const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance
                    | BindingFlags.DeclaredOnly;
                int skip = typeof(FtCensus).GetMethod("Skip", BindingFlags.NonPublic | BindingFlags.Static).MetadataToken;
                int open = typeof(FtSpan).GetMethod("Open", BindingFlags.NonPublic | BindingFlags.Static).MetadataToken;
                int close = typeof(FtSpan).GetMethod("Close", BindingFlags.NonPublic | BindingFlags.Static).MetadataToken;
                Module mod = typeof(FtCensus).Module;
                var sites = new int[Capacity];
                var good = new int[Capacity];
                Type[] types;
                try { types = mod.Assembly.GetTypes(); }
                catch (ReflectionTypeLoadException ex) { types = ex.Types; why = " partial=1"; }
                var found = new List<int>();
                foreach (var t in types)
                {
                    if (t == null) continue;
                    var ms = new List<MethodBase>();
                    try { ms.AddRange(t.GetMethods(All)); ms.AddRange(t.GetConstructors(All)); }
                    catch { continue; }
                    foreach (var m in ms)
                    {
                        byte[] il;
                        try { var body = m.GetMethodBody(); il = body != null ? body.GetILAsByteArray() : null; }
                        catch { il = null; }
                        if (il == null) continue;
                        bool opens, closes;
                        found.Clear();
                        ScanIl(il, skip, open, close, found, out opens, out closes);
                        foreach (int e in found)
                        {
                            if (e < 0 || e >= Capacity) continue;
                            sites[e]++;
                            if (opens && closes) good[e]++;
                        }
                    }
                }
                for (int e = 0; e < Count; e++)
                {
                    if (Names[e] == null) continue;
                    entries++;
                    if (sites[e] > 0 && good[e] == sites[e]) wrapped++;
                }
            }
            catch (System.Exception ex) { why = " failed=" + ex.GetType().Name; }
            Plugin.Log.LogInfo("[FRAME-TIME] scope census entries=" + entries + " wrapped=" + wrapped + why);
        }

        private static Dictionary<short, OpCode> _ops;

        /// <summary>One method's IL: the constant before each call to skip (into found), and whether it calls open and
        /// close. Operand sizes come from System.Reflection.Emit's own opcode table.</summary>
        internal static void ScanIl(byte[] il, int skip, int open, int close, List<int> found, out bool opens, out bool closes)
        {
            if (_ops == null)
            {
                var d = new Dictionary<short, OpCode>();
                foreach (var f in typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static))
                    if (f.GetValue(null) is OpCode oc) d[oc.Value] = oc;
                _ops = d;
            }
            opens = closes = false;
            int last = int.MinValue;   // the constant the previous instruction pushed, if it was an ldc.i4
            int i = 0;
            while (i < il.Length)
            {
                short v = il[i] == 0xFE && i + 1 < il.Length ? (short)(0xFE00 | il[i + 1]) : il[i];
                i += il[i] == 0xFE ? 2 : 1;
                OpCode oc;
                if (!_ops.TryGetValue(v, out oc)) return;
                int c = int.MinValue;
                if (v >= 0x15 && v <= 0x1E) c = v - 0x16;                     // ldc.i4.m1 to ldc.i4.8
                else if (v == 0x1F) c = (sbyte)il[i];                          // ldc.i4.s
                else if (v == 0x20) c = BitConverter.ToInt32(il, i);           // ldc.i4
                if (oc.OperandType == OperandType.InlineMethod && (v == 0x28 || v == 0x6F))   // call, callvirt
                {
                    int tok = BitConverter.ToInt32(il, i);
                    if (tok == skip && last != int.MinValue) found.Add(last);
                    else if (tok == skip) found.Add(-1);
                    if (tok == open) opens = true;
                    if (tok == close) closes = true;
                }
                switch (oc.OperandType)
                {
                    case OperandType.InlineNone: break;
                    case OperandType.ShortInlineBrTarget: case OperandType.ShortInlineI: case OperandType.ShortInlineVar: i += 1; break;
                    case OperandType.InlineVar: i += 2; break;
                    case OperandType.InlineI8: case OperandType.InlineR: i += 8; break;
                    case OperandType.InlineSwitch: i += 4 + 4 * BitConverter.ToInt32(il, i); break;
                    default: i += 4; break;
                }
                last = c;
            }
        }
    }
}
#endif
