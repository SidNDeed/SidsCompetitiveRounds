#if SCR_FRAMETIME
using System;
using System.Diagnostics;
using System.Text;
using System.Threading;

namespace CompetitiveRounds
{
    /// <summary>FrameTime A3 (integrator ruling FRAME-TIME-ROUND-R1-A1, route D; METHOD-V4.1 section 0): the counts
    /// and calibrations behind U's fifth term, which bounds the carryover of every class (iii) structure the
    /// whole-entry gate leaves (SURVIVORS.md; tools/frametime/gate_specs/a3.py lists the rows).
    /// Each content-dependent survivor registers once (Set) with its capacity passed as the code constant that
    /// sizes it, never a typed number, and whether it has a steady state (a refilling structure: after capacity
    /// writes since the point's first live frame it holds only this point's content) or not (it accumulates over
    /// the game, so every read can differ). Its writers call Wrote and its content-dependent live readers call
    /// Read, both inside #if SCR_FRAMETIME at the component's own sites; only main-thread calls in the live frames
    /// of a point the gate leaves open (an ON point) count. reads_win counts the reads whose work can differ from an
    /// always-ON game's: every read for a structure without a steady state, else the reads made while fewer than
    /// capacity writes have happened since the point's first live frame. The game's line is written by
    /// FtSchedule.FlushGame. Calibration (FtCalib.Run, every game start): each row's own Cal runs the real read
    /// on a scratch copy of the structure EMPTY (u) and at its CAPACITY (p), 20 batches of n reads.</summary>
    internal static class FtA3
    {
        internal const int Capacity = 32;
        private const int Batches = 20;

        // The rows (gate_specs/a3.py's "dependent" rows, same names; the parser refuses a game without each line).
        internal const int CE_Top = 0, CE_Ht = 1;
        internal const int Rows = 2;

        private static bool _registered;

        /// <summary>Once, at clock install (beside FtE.RegisterAll): every row with its capacity constant.</summary>
        internal static void RegisterAll()
        {
            if (_registered) return;
            _registered = true;
            Set(CE_Top, "CE_Top", CombatEvidence.TOP_CAP, false, CombatEvidence.FtCalTop, 2000);
            Set(CE_Ht, "CE_Ht", CombatEvidence.HT_CAP, false, CombatEvidence.FtCalHt, 2000);
            int missing = 0;
            for (int k = 0; k < Rows; k++) if (Names[k] == null) missing++;
            Plugin.Log.LogInfo("[FRAME-TIME] a3rows registered=" + Count + " expected=" + Rows + " missing=" + missing
                + " duplicates=" + Duplicates);
        }

        /// <summary>One calibration batch: n reads on a scratch structure, empty (full false) or at capacity;
        /// returns the batch's Stopwatch ticks.</summary>
        internal delegate long CalBatch(bool full, int n);

        internal static readonly string[] Names = new string[Capacity];
        private static readonly int[] _cap = new int[Capacity];
        private static readonly bool[] _steady = new bool[Capacity];
        private static readonly CalBatch[] _cal = new CalBatch[Capacity];
        private static readonly int[] _calN = new int[Capacity];
        private static readonly long[] _writesPt = new long[Capacity];
        private static readonly long[] _writesOn = new long[Capacity];
        private static readonly long[] _readsOn = new long[Capacity];
        private static readonly long[] _readsWin = new long[Capacity];
        internal static int Count;
        internal static int Duplicates;

        internal static void Set(int k, string name, int cap, bool steady, CalBatch cal, int calN)
        {
            if (Names[k] != null) Duplicates++;
            Names[k] = name;
            _cap[k] = cap;
            _steady[k] = steady;
            _cal[k] = cal;
            _calN[k] = calN;
            if (k + 1 > Count) Count = k + 1;
        }

        private static bool OnLive()
        {
            return FtSchedule.Live && !FtGate.Off && Thread.CurrentThread.ManagedThreadId == FtSpan.MainThread;
        }

        /// <summary>FtFrames.StartPoint, at every point's start: the writes since the point's first live frame restart.</summary>
        internal static void PointStart()
        {
            for (int k = 0; k < Count; k++) _writesPt[k] = 0;
        }

        internal static void Wrote(int k)
        {
            if (!OnLive()) return;
            _writesPt[k]++;
            _writesOn[k]++;
        }

        internal static void Read(int k)
        {
            if (!OnLive()) return;
            _readsOn[k]++;
            if (!_steady[k] || _writesPt[k] < _cap[k]) _readsWin[k]++;
        }

        internal static void Reset()
        {
            for (int k = 0; k < Count; k++) { _writesPt[k] = 0; _writesOn[k] = 0; _readsOn[k] = 0; _readsWin[k] = 0; }
        }

        /// <summary>At FtSchedule.FlushGame: one a3 line per registered structure.</summary>
        internal static void LogGame(int game)
        {
            for (int k = 0; k < Count; k++)
            {
                if (Names[k] == null) continue;
                Plugin.Log.LogInfo("[FRAME-TIME] a3 g=" + game + " k=" + Names[k] + " cap=" + _cap[k] + " steady=" + (_steady[k] ? 1 : 0)
                    + " reads_on=" + _readsOn[k] + " reads_win=" + _readsWin[k] + " writes_on=" + _writesOn[k]);
            }
        }

        /// <summary>Every registered structure's calibration, from FtCalib.Run (outside live combat).</summary>
        internal static void Calibrate(int i, string why)
        {
            for (int k = 0; k < Count; k++)
            {
                if (Names[k] == null) continue;
                if (_cal[k] == null)
                {
                    Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=a3 k=" + Names[k] + " failed: no calibration");
                    continue;
                }
                var u = new long[Batches];
                var p = new long[Batches];
                try
                {
                    _cal[k](false, 100);
                    _cal[k](true, 100);
                    for (int b = 0; b < Batches; b++)
                    {
                        u[b] = _cal[k](false, _calN[k]);
                        p[b] = _cal[k](true, _calN[k]);
                    }
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=a3 k=" + Names[k] + " failed: " + ex.GetType().Name + ": " + ex.Message);
                    continue;
                }
                Plugin.Log.LogInfo("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=a3 k=" + Names[k] + " n=" + _calN[k]
                    + " u=" + string.Join(",", u) + " p=" + string.Join(",", p));
            }
        }
    }
}
#endif
