#if SCR_FRAMETIME
using System;
using System.Diagnostics;
using System.Text;
using System.Threading;

namespace CompetitiveRounds
{
    /// <summary>FrameTime A3 (integrator ruling FRAME-TIME-ROUND-R1-A1, route D; METHOD-V4.1 section 0): the counts
    /// and calibrations behind U's fifth term, which bounds the carryover of every content-dependent survivor the
    /// whole-entry gate leaves (tools/frametime/SURVIVORS.md; tools/frametime/gate_specs/a3.py lists the rows with the
    /// same names). Two kinds of row register here, each once, from its component's own FtA3Rows:
    ///
    /// DEPENDENT (Set): every survivor that is neither proven zero by the survivor sweep (no write of its fields
    /// reachable live) nor probed drained (ruling FRAME-TIME-ROUND-R2 (1), default-deny). Its live writers call Wrote and
    /// EVERY live reader member calls Read (survivor_sweep.py lists the readers from the sweep and fails when one lacks
    /// it, or when a Read sits anywhere else), inside #if SCR_FRAMETIME at the component's own sites; only main-thread
    /// calls in the live frames of a point the gate leaves open (an ON point) count. A reader that is cheap whatever the
    /// content is still counted: its row's calibration bounds the costliest read, so the count can only overstate. A row with a steady state (steady
    /// true) holds only the current point's content once `refill` writes have happened since the point's first live
    /// frame; reads_win counts its reads before that. A row without one (steady false: it accumulates over the game)
    /// counts every read in reads_win. The row's calibration (FtCalib.Run, every game start) runs the read on a scratch
    /// copy of the structure EMPTY (u) and in its costliest content at CAPACITY (p), 20 batches of n reads.
    ///
    /// DRAINED (SetDrained): a survivor SURVIVORS.md finds emptied between points (a queue or ring the component drains
    /// on the non-live frames). Its zero is checked, not assumed: at the boundary of every point's first live frame
    /// (after the last non-live frame's work, before any live work) the structure must be EMPTY, so nothing written
    /// before the point reaches its live reads. nonempty counts the points that started with the structure holding
    /// entries; faults counts fill probes that threw (each also counted nonempty).
    ///
    /// FtSchedule.FlushGame writes one a3 line per dependent row and one a3drain line per drained row; the parser
    /// (ft_parse.a3) refuses a game without each, a drained row with nonempty or faults above 0, and a calibration
    /// without each dependent row.</summary>
    internal static class FtA3
    {
        internal const int Capacity = 48;
        private const int Batches = 20;

        // The rows (gate_specs/a3.py, same names). Dependent:
        internal const int CE_Top = 0, CE_Ht = 1, CE_Ping = 2, CE_Pos = 3, CE_Recent = 4, CE_B5c = 5;
        internal const int SE_Hw = 6, SE_Logs = 7, IC_Rpc = 8, IC_Clock = 9;
        // Drained:
        internal const int CE_Wait = 10, CE_Rings = 11, CE_Gun = 12, HE_Flush = 13, PE_Rec = 14;
        // Dependent by default-deny (ruling FRAME-TIME-ROUND-R2 (1): the 21 former zero rows, whose fields the sweep
        // finds written live) and round-2 HIGH 3's HashSet growth (HE_hitset, split from HE_game):
        internal const int CE_lhat_cache = 15, CE_anchor = 16, CE_counters = 17, CE_scratch = 18, CE_gun_scalars = 19;
        internal const int CE_gun_account = 20, CE_aimset = 21, CE_capture = 22, CE_perf_probe = 23;
        internal const int SE_ordinals = 24, SE_frames = 25, SE_scalars = 26;
        internal const int HE_game = 27, HE_point = 28, HE_sender = 29, PE_map = 30;
        internal const int IC_scalars = 31, IC_point = 32, IC_game = 33, CD_notes = 34, PB_printed = 35, HE_hitset = 36;
        internal const int Rows = 37;

        private static bool _registered;

        /// <summary>Once, at clock install (beside FtE.RegisterAll): every component registers its rows.</summary>
        internal static void RegisterAll()
        {
            if (_registered) return;
            _registered = true;
            CombatEvidence.FtA3Rows();
            SeatEvidence.FtA3Rows();
            IdentityClockEvidence.FtA3Rows();
            HitEvidence.FtA3Rows();
            PointEvidence.FtA3Rows();
            CardDrawEvidence.FtA3Rows();
            PeerBuild.FtA3Rows();
            int missing = 0;
            for (int k = 0; k < Rows; k++) if (Names[k] == null) missing++;
            Plugin.Log.LogInfo("[FRAME-TIME] a3rows registered=" + Count + " expected=" + Rows + " missing=" + missing
                + " duplicates=" + Duplicates);
        }

        /// <summary>One calibration batch: n reads on a scratch structure, empty (full false) or at capacity;
        /// returns the batch's Stopwatch ticks.</summary>
        internal delegate long CalBatch(bool full, int n);

        /// <summary>A drained row's fill: how many entries the structure holds now (0 when empty or absent).</summary>
        internal delegate int Fill();

        internal static readonly string[] Names = new string[Capacity];
        private static readonly bool[] _drained = new bool[Capacity];
        private static readonly int[] _refill = new int[Capacity];
        private static readonly bool[] _steady = new bool[Capacity];
        private static readonly CalBatch[] _cal = new CalBatch[Capacity];
        private static readonly int[] _calN = new int[Capacity];
        private static readonly Fill[] _fill = new Fill[Capacity];
        private static readonly long[] _writesPt = new long[Capacity];
        private static readonly long[] _writesOn = new long[Capacity];
        private static readonly long[] _readsOn = new long[Capacity];
        private static readonly long[] _readsWin = new long[Capacity];
        private static readonly long[] _starts = new long[Capacity];
        private static readonly long[] _nonempty = new long[Capacity];
        private static readonly long[] _faults = new long[Capacity];
        internal static int Count;
        internal static int Duplicates;

        /// <summary>The game's serial (Reset adds one): a row that counts once per game per instance keeps the
        /// serial it last counted in.</summary>
        internal static int Serial;

        private static void Name(int k, string name)
        {
            if (Names[k] != null) Duplicates++;
            Names[k] = name;
            if (k + 1 > Count) Count = k + 1;
        }

        /// <summary>A dependent row. refill: the writes since the point's first live frame after which the structure
        /// holds only this point's content (a code constant; unused when steady is false).</summary>
        internal static void Set(int k, string name, int refill, bool steady, CalBatch cal, int calN)
        {
            Name(k, name);
            _refill[k] = refill;
            _steady[k] = steady;
            _cal[k] = cal;
            _calN[k] = calN;
        }

        /// <summary>A drained row.</summary>
        internal static void SetDrained(int k, string name, Fill fill)
        {
            Name(k, name);
            _drained[k] = true;
            _fill[k] = fill;
        }

        private static bool OnLive()
        {
            return FtSchedule.Live && !FtGate.Off && Thread.CurrentThread.ManagedThreadId == FtSpan.MainThread;
        }

        private static bool Empty(int k)
        {
            try { return _fill[k]() == 0; }
            catch { _faults[k]++; return false; }
        }

        /// <summary>FtSchedule.StartPoint, at the boundary of every point's first live frame (before its work): the
        /// writes since that frame restart, and each drained row is probed for emptiness.</summary>
        internal static void PointStart()
        {
            for (int k = 0; k < Count; k++)
            {
                _writesPt[k] = 0;
                if (!_drained[k]) continue;
                _starts[k]++;
                if (!Empty(k)) _nonempty[k]++;
            }
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
            if (!_steady[k] || _writesPt[k] < _refill[k]) _readsWin[k]++;
        }

        /// <summary>A growth row's read (HE_hitset; SE_Logs keeps its own SeatEvidenceCore.FtLogRead): ONCE per
        /// instance per game. The instance keeps the Serial it last counted in, stored only when this call counts (an
        /// ON live frame on the main thread), so an instance first touched outside one is still counted at its first
        /// touch inside one. The row's calibration is the instance's whole growth sequence to its cap.</summary>
        internal static void ReadOnce(int k, ref int serial)
        {
            if (serial == Serial) return;
            if (!OnLive()) return;
            Read(k);
            serial = Serial;
        }

        /// <summary>FtSchedule.GameStart: the game's counts restart.</summary>
        internal static void Reset()
        {
            Serial++;
            for (int k = 0; k < Count; k++)
            {
                _writesPt[k] = 0; _writesOn[k] = 0; _readsOn[k] = 0; _readsWin[k] = 0;
                _starts[k] = 0; _nonempty[k] = 0; _faults[k] = 0;
            }
        }

        /// <summary>At FtSchedule.FlushGame: one a3 line per dependent row, one a3drain line per drained row.</summary>
        internal static void LogGame(int game)
        {
            for (int k = 0; k < Count; k++)
            {
                if (Names[k] == null) continue;
                if (_drained[k])
                    Plugin.Log.LogInfo("[FRAME-TIME] a3drain g=" + game + " k=" + Names[k] + " starts=" + _starts[k]
                        + " nonempty=" + _nonempty[k] + " faults=" + _faults[k]);
                else
                    Plugin.Log.LogInfo("[FRAME-TIME] a3 g=" + game + " k=" + Names[k] + " cap=" + _refill[k] + " steady=" + (_steady[k] ? 1 : 0)
                        + " reads_on=" + _readsOn[k] + " reads_win=" + _readsWin[k] + " writes_on=" + _writesOn[k]);
            }
        }

        /// <summary>Every dependent row's calibration, from FtCalib.Run (outside live combat).</summary>
        internal static void Calibrate(int i, string why)
        {
            for (int k = 0; k < Count; k++)
            {
                if (Names[k] == null || _drained[k]) continue;
                if (_cal[k] == null)
                {
                    Plugin.Log.LogWarning("[FRAME-TIME] cal i=" + i + " why=" + why + " kind=a3 k=" + Names[k] + " failed: no calibration");
                    continue;
                }
                var u = new long[Batches];
                var p = new long[Batches];
                try
                {
                    int warm = Math.Min(100, _calN[k]);
                    _cal[k](false, warm);
                    _cal[k](true, warm);
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
