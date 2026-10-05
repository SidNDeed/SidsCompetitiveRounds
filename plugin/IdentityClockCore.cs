using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using C = CompetitiveRounds.SeatEvidenceCore;

namespace CompetitiveRounds
{
    /// <summary>IDENTITY, CLOCK AND CONNECTION EVIDENCE, the pure half
    /// (ai-collab/integrity-1001/IDENTITY-CLOCK-EVIDENCE-DESIGN-V1.md as
    /// corrected by its design report). No Unity, no Photon, no Harmony:
    /// tools/tests/identity-clock-client compiles this file as it ships, beside
    /// SeatEvidenceCore.cs (whose serializer it reuses).
    ///
    /// This half records and serialises. It holds no deciding value: every
    /// number it emits is a count, a stamp difference, a digest, a median or a
    /// rate of what this seat read or received, at the measurement resolution
    /// named in the constants below (version CONSTS), and the server compares.
    ///
    /// The record text must equal the server's reference budgeter
    /// (backend/api/identity_clock_evidence.py::ice_budget_record) byte for
    /// byte; the harness runs both over the server lane's fixtures.</summary>
    internal static class IdentityClockCore
    {
        // -- the wire (server IC_WIRE; the harness compares every value) ------------------

        internal const int CONTRACT = 2;
        internal const int SCHEMA = 1;
        internal const int CONSTS = 1;
        internal const int RECORD_MAX_BYTES = 16384;
        internal const int COST_MAX = 16, CHK_MAX = 32, PLUG_MAX = 16, ASM_MAX = 200, GDIG_MAX = 24;
        internal const int LDIR_PLUGINS_MAX = 32, LDIR_PATCHERS_MAX = 16, HP_MAX = 48, HP_OWNERS_MAX = 4;
        internal const int HP_ALL_OWNERS_MAX = 16, RPC_MAX = 64, CAD_MAX = 360, TDG_BINS_MAX = 32, PT_MAX = 32, RUNGS_MAX = 4;
        internal const int NAME_MAX = 64;
        internal const long COUNT_MAX = 10000000L, SMALL_MAX = 9999, MS_POINT_MAX = 600000, MS_DAY_MAX = 86400000L;
        internal const long AGE_MAX = 600000, CU_MAX = 1000000, US_MAX = 10000000, RATE_MAX = 1000, FPS_MAX = 1000;
        internal const long TD_MS_MAX = 100, BUCKET_MAX = 720, GCLK_CPPM_MAX = 100000000L, FRAMES_MAX = 99999, PATCHED_MAX = 99999;
        internal const int ORDINAL_MAX = 255, ID_MAX = 255, KIND_MAX = 99, COLLECTOR_MAX = 63;
        internal const long HEADER_MS_MAX = 1000000000000L;

        internal static readonly string[] KEYS = {
            "schema", "consts", "t0", "t0_src", "cost", "proc", "chk", "plug", "asm_n", "asm",
            "gdig", "aload", "ldir", "hp_all", "hp", "rpc_o", "send_cfg", "gclk", "tdg",
            "cad_b", "pt_s", "pt_o", "unpair", "omit" };
        /// <summary>Trimmed by the budgeter, in this order among equals.</summary>
        internal static readonly string[] TRIM = { "asm", "cad_b", "rpc_o", "hp", "ldir" };
        internal static readonly string[] LDIR_PARTS = { "plugins", "patchers" };

        // wire codes (server ICM_CODES)
        internal const int PASS = 0, FINDING = 1, NOT_RUN = 2;
        internal const int OK = 0, NO_FILE = 1, READ_FAILED = 2, NOT_YET = 3;
        internal const int ORIGIN_GAME = 0, ORIGIN_CORE = 1, ORIGIN_PLUGINS = 2, ORIGIN_PATCHERS = 3,
                           ORIGIN_OTHER = 4, ORIGIN_NONE = 5, ORIGIN_UNREADABLE = 6;
        internal const int MOMENT_BOOT = 0, MOMENT_START = 1, MOMENT_PICK = 2, MOMENT_OVER = 3;

        // -- measurement resolution (client constants, version CONSTS) --------------------

        /// <summary>Distance rungs for "in position", centi-units; REF_RUNG is
        /// the rung whose arrival time and in-position moment the other point
        /// fields refer to. Resolution only: which rung a review reads is not
        /// decided here.</summary>
        internal static readonly int[] RUNGS_CU = { 25, 50, 100, 200 };
        internal const int REF_RUNG = 1;
        /// <summary>Movement resolution (L7): a position change from the
        /// in-position package beyond MOVE_RES_CU, or a velocity change beyond
        /// VEL_RES_CU per second, is movement; input alone is not.</summary>
        internal const int MOVE_RES_CU = 10;
        internal const int VEL_RES_CU = 50;
        /// <summary>Aim resolution: the cosine of 2 degrees, scaled 1e6.</summary>
        internal const long AIM_COS_1E6 = 999391;
        /// <summary>(stamp gap - stated interval) bin edges in ms (tdg); a value
        /// below the first edge is bin 0, at or above the last is the last bin.</summary>
        internal static readonly int[] TDG_EDGES = { 0, 10, 20, 35, 50, 75, 100, 150, 250, 500, 1000 };
        internal const int BUCKET_MS = 10000;
        internal const int TD_CEIL_MS = 100;

        // -- small helpers ------------------------------------------------------------------

        internal static long Clamp(long v, long lo, long hi) { return v < lo ? lo : (v > hi ? hi : v); }
        internal static int WrapDiff(int a, int b) { return unchecked(a - b); }
        internal static int FloorDiv(int x, int d) { int q = x / d; if ((x % d != 0) && (x < 0)) q--; return q; }

        internal static string Sha256Hex(byte[] data)
        {
            using (var h = SHA256.Create()) return Hex(h.ComputeHash(data));
        }

        internal static string Hex(byte[] h)
        {
            var sb = new StringBuilder(h.Length * 2);
            foreach (byte b in h) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        internal static List<object> L(params object[] xs) { return new List<object>(xs); }

        // -- privacy (design 3.4, report L5) ------------------------------------------------

        /// <summary>Every string the record carries passes Name: a string of
        /// [A-Za-z0-9_.-] within its bound that contains no local privacy
        /// needle (the account, machine and domain names and the profile
        /// folder's name of this seat, read by the caller) is kept; anything
        /// else is replaced whole by "h:" + the first 12 hex of its SHA-256,
        /// never cut. A needle of three characters or more matches anywhere in
        /// the string, case-insensitively; a shorter one matches the whole
        /// string only.</summary>
        internal sealed class Privacy
        {
            private readonly List<string> _needles = new List<string>();

            internal Privacy(IEnumerable<string> needles)
            {
                if (needles == null) return;
                foreach (var n in needles)
                {
                    if (string.IsNullOrEmpty(n)) continue;
                    string t = n.Trim().ToLowerInvariant();
                    if (t.Length > 0 && !_needles.Contains(t)) _needles.Add(t);
                }
            }

            internal int Needles { get { return _needles.Count; } }

            internal bool HasNeedle(string s)
            {
                if (string.IsNullOrEmpty(s)) return false;
                string lower = s.ToLowerInvariant();
                foreach (var n in _needles)
                    if (n.Length >= 3 ? lower.IndexOf(n, StringComparison.Ordinal) >= 0 : lower == n) return true;
                return false;
            }

            internal string Name(string s)
            {
                if (s != null && s.Length >= 1 && s.Length <= NAME_MAX && Alphabet(s) && !HasNeedle(s)) return s;
                return Hashed(s);
            }

            /// <summary>As Name, but "" stays "" (a name the metadata could not give).</summary>
            internal string NameOrEmpty(string s)
            {
                return string.IsNullOrEmpty(s) ? "" : Name(s);
            }

            internal static string Hashed(string s)
            {
                return "h:" + Sha256Hex(Encoding.UTF8.GetBytes(s ?? "")).Substring(0, 12);
            }

            internal static bool Alphabet(string s)
            {
                for (int i = 0; i < s.Length; i++)
                {
                    char c = s[i];
                    bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '-';
                    if (!ok) return false;
                }
                return true;
            }
        }

        /// <summary>An assembly version "a.b.c.d" (each 1-5 digits, at most
        /// four parts, at most 23 characters), or "".</summary>
        internal static string Version(string v)
        {
            if (string.IsNullOrEmpty(v) || v.Length > 23) return "";
            string[] p = v.Split('.');
            if (p.Length > 4) return "";
            foreach (var s in p)
            {
                if (s.Length < 1 || s.Length > 5) return "";
                for (int i = 0; i < s.Length; i++) if (s[i] < '0' || s[i] > '9') return "";
            }
            return v;
        }

        // -- process and boot occurrences (report L1) ---------------------------------------

        /// <summary>One check run's entry: [moment, ordinal, t_ms, outcome,
        /// n_plugins, n_asm, n_foreign]. t_ms is process-relative (ms since the
        /// game process started, as the caller reads it).</summary>
        internal sealed class Run
        {
            internal int Moment, Ordinal, Outcome;
            internal long TMs, NPlugins, NAsm, NForeign;
            internal List<string> Plugins = new List<string>();
            internal List<object> Entry()
            {
                return L((long)Moment, (long)Ordinal, Clamp(TMs, 0, MS_DAY_MAX), (long)Outcome,
                         Outcome == FINDING ? Clamp(NPlugins, 1, SMALL_MAX) : 0L, Clamp(NAsm, 0, SMALL_MAX), Clamp(NForeign, 0, SMALL_MAX));
            }
        }

        /// <summary>The process's own ledger: a random id per process, every
        /// boot occurrence (each execution of the initialisation gate is its own
        /// occurrence, with its ordinal and process time: a persistent-host
        /// respawn runs it again in the same process), and run totals.</summary>
        internal sealed class ProcLedger
        {
            internal const int BOOT_KEEP = 4;
            internal readonly string ProcId;
            internal int Boots;
            internal long Runs, Findings, NotRun;
            internal readonly List<Run> BootRuns = new List<Run>();

            internal ProcLedger(string procId) { ProcId = procId; }

            internal static string NewProcId(byte[] random6)
            {
                return Hex(random6).Substring(0, 12);
            }

            /// <summary>Records one execution of the boot gate as an occurrence.</summary>
            internal Run Boot(long tMs, int outcome, IList<string> plugins, Privacy priv)
            {
                var r = new Run { Moment = MOMENT_BOOT, Ordinal = Math.Min(Boots, ORDINAL_MAX - 1), TMs = tMs, Outcome = outcome };
                Boots = Math.Min(Boots + 1, ORDINAL_MAX);
                Count(r, plugins, priv);
                BootRuns.Add(r);
                if (BootRuns.Count > BOOT_KEEP) BootRuns.RemoveAt(0);
                return r;
            }

            /// <summary>Counts a run of any moment and fills its plug-in list
            /// (names through the privacy filter, at most PLUG_MAX, never empty
            /// for a finding).</summary>
            internal void Count(Run r, IList<string> plugins, Privacy priv)
            {
                Runs = Math.Min(Runs + 1, COUNT_MAX);
                if (r.Outcome == FINDING)
                {
                    Findings = Math.Min(Findings + 1, COUNT_MAX);
                    if (plugins != null)
                        foreach (var g in plugins)
                        {
                            string n = priv.Name(g);
                            if (!r.Plugins.Contains(n) && r.Plugins.Count < PLUG_MAX) r.Plugins.Add(n);
                        }
                    if (r.Plugins.Count == 0) r.Plugins.Add(Privacy.Hashed(""));
                    r.NPlugins = r.Plugins.Count;
                }
                else if (r.Outcome == NOT_RUN) NotRun = Math.Min(NotRun + 1, COUNT_MAX);
            }

            internal List<object> Entry()
            {
                return L(ProcId, (long)Boots, Runs, Findings, NotRun);
            }
        }

        /// <summary>The outcome of one plug-in enumeration: `keys` the loader's
        /// plug-in keys (null: the source was null), `self` this mod's key,
        /// `threw` the enumeration threw. A run that threw or had no source is
        /// not_run, never pass.</summary>
        internal static int Outcome(IList<string> keys, string self, bool threw, List<string> others)
        {
            if (threw || keys == null) return NOT_RUN;
            foreach (var k in keys) if (k != self) others.Add(k);
            return others.Count > 0 ? FINDING : PASS;
        }

        /// <summary>The plug-in keys a run reads (report L6): the loader's live
        /// key set, READ AGAIN AT EVERY RUN (never cached from boot), plus the
        /// keys the after-boot fixture added. Additive only: nothing here can
        /// remove a key the loader reports. Null when the source was null;
        /// `threw` when reading it threw.</summary>
        internal sealed class KeySource
        {
            private readonly Func<IList<string>> _read;
            internal readonly List<string> PostBoot = new List<string>();
            internal KeySource(Func<IList<string>> read) { _read = read; }
            internal IList<string> Read(out bool threw)
            {
                threw = false;
                try
                {
                    var src = _read();
                    if (src == null) return null;
                    var l = new List<string>(src);
                    l.AddRange(PostBoot);
                    return l;
                }
                catch { threw = true; return null; }
            }
        }

        /// <summary>One game's check runs at moments 1-3, appended in order;
        /// the record's chk list is the kept boot occurrences then these, at
        /// most CHK_MAX in all (the game-over run always kept).</summary>
        internal sealed class GameRuns
        {
            internal readonly List<Run> Runs = new List<Run>();
            internal int Picks;
            internal void Add(Run r)
            {
                int room = CHK_MAX - ProcLedger.BOOT_KEEP - 1;
                if (r.Moment == MOMENT_OVER || Runs.Count < room) Runs.Add(r);
            }
        }

        internal static void ChkAndPlug(ProcLedger proc, GameRuns game, out List<object> chk, out List<object> plug)
        {
            chk = new List<object>();
            plug = new List<object>();
            var all = new List<Run>(proc.BootRuns);
            all.AddRange(game.Runs);
            foreach (var r in all)
            {
                if (chk.Count >= CHK_MAX) break;
                chk.Add(r.Entry());
                if (r.Outcome == FINDING)
                    foreach (var n in r.Plugins) if (!plug.Contains(n) && plug.Count < PLUG_MAX) plug.Add(n);
            }
        }

        // -- census (moments 1-3) -----------------------------------------------------------

        /// <summary>One loaded assembly as the caller read it.</summary>
        internal struct AsmIn { internal string Name, Version; internal int Origin; internal bool Dynamic; }

        /// <summary>The origin class of a location string, compared with the
        /// loader's folders (paths never leave this comparison).</summary>
        internal static int Origin(bool dynamic, bool unreadable, string location, string managed, string core, string plugins, string patchers)
        {
            if (unreadable) return ORIGIN_UNREADABLE;
            if (dynamic || string.IsNullOrEmpty(location)) return ORIGIN_NONE;
            string l = Norm(location);
            if (Under(l, plugins)) return ORIGIN_PLUGINS;
            if (Under(l, patchers)) return ORIGIN_PATCHERS;
            if (Under(l, core)) return ORIGIN_CORE;
            if (Under(l, managed)) return ORIGIN_GAME;
            return ORIGIN_OTHER;
        }

        private static string Norm(string p) { return (p ?? "").Replace('\\', '/').TrimEnd('/').ToLowerInvariant(); }
        private static bool Under(string l, string dir)
        {
            if (string.IsNullOrEmpty(dir)) return false;
            string d = Norm(dir);
            return d.Length > 0 && l.StartsWith(d + "/", StringComparison.Ordinal);
        }

        /// <summary>asm entries (every loaded assembly; the budgeter cuts to
        /// ASM_MAX and counts) and asm_n [total, dynamic, added, removed] with
        /// added/removed against the names at game start.</summary>
        internal static void Census(IList<AsmIn> asms, ICollection<string> atStart, Privacy priv, out List<object> asm, out List<object> asmN, out HashSet<string> names)
        {
            asm = new List<object>();
            names = new HashSet<string>(StringComparer.Ordinal);
            long dyn = 0;
            foreach (var a in asms)
            {
                string n = priv.Name(a.Name);
                names.Add(n);
                if (a.Dynamic) dyn++;
                asm.Add(L(n, Version(a.Version), (long)Clamp(a.Origin, 0, 6)));
            }
            long added = 0, removed = 0;
            if (atStart != null)
            {
                foreach (var n in names) if (!atStart.Contains(n)) added++;
                foreach (var n in atStart) if (!names.Contains(n)) removed++;
            }
            long total = Clamp(asms.Count, 0, SMALL_MAX);
            asmN = L(total, Clamp(dyn, 0, total), Clamp(added, 0, SMALL_MAX), Clamp(removed, 0, SMALL_MAX));
            if (asm.Count > total) asm.RemoveRange((int)total, asm.Count - (int)total);
        }

        /// <summary>One patched method as the caller read it from Harmony:
        /// method_id (-1 when it is not in the dependency list) and each
        /// patch's owner by kind (0 prefix, 1 postfix, 2 transpiler, 3 finalizer).</summary>
        internal sealed class PatchedIn
        {
            internal int MethodId = -1;
            internal readonly List<KeyValuePair<int, string>> Patches = new List<KeyValuePair<int, string>>();
        }

        /// <summary>hp (one entry per dependency-list method that any owner
        /// patched: foreign patches counted by kind, foreign owners named),
        /// hp_all [patched methods, distinct owners, owners] over every
        /// patched method (owners include this mod's), and the number of
        /// patched methods with a foreign owner (the run's n_foreign).</summary>
        internal static void Patches(IList<PatchedIn> methods, string selfOwner, Privacy priv, out List<object> hp, out List<object> hpAll, out long nForeign)
        {
            hp = new List<object>();
            var owners = new List<string>();
            nForeign = 0;
            foreach (var m in methods)
            {
                long[] k = new long[4];
                var mo = new List<object>();
                bool foreign = false;
                foreach (var p in m.Patches)
                {
                    string o = priv.Name(p.Value);
                    if (!owners.Contains(o)) owners.Add(o);
                    if (p.Value == selfOwner) continue;
                    foreign = true;
                    if (p.Key >= 0 && p.Key < 4) k[p.Key] = Math.Min(k[p.Key] + 1, KIND_MAX);
                    if (!mo.Contains(o) && mo.Count < HP_OWNERS_MAX) mo.Add(o);
                }
                if (foreign) nForeign++;
                if (m.MethodId >= 0 && m.MethodId <= ID_MAX)
                    hp.Add(L((long)m.MethodId, k[0], k[1], k[2], k[3], mo));
            }
            var ol = new List<object>();
            foreach (var o in owners) if (ol.Count < HP_ALL_OWNERS_MAX) ol.Add(o);
            hpAll = L(Clamp(methods.Count, 0, PATCHED_MAX), Clamp(owners.Count, 0, SMALL_MAX), ol);
        }

        // -- the disk survey (design 3.3 gdig/ldir/aload; report M1, L3, L4) -----------------

        /// <summary>One directory entry as the file system reports it.</summary>
        internal struct FsEntry { internal string Path; internal bool IsDir, IsReparse; }

        /// <summary>The survey's only access to the disk. Every call is one
        /// bounded unit of work.</summary>
        internal interface IFs
        {
            /// <summary>0 listed, 1 no such directory, 2 failed. At most
            /// `max` + 1 entries are added (one more than max says "more").</summary>
            int List(string dir, int max, List<FsEntry> into);
            /// <summary>Opened for reading, or null: `missing` says no such file.</summary>
            Stream Open(string path, out bool missing);
            /// <summary>The assembly simple name from metadata, null when unreadable.</summary>
            string AsmName(string path);
        }

        /// <summary>Public bounds of one survey job (each a work bound, not a
        /// judging value). A job over any of them stops and says so.</summary>
        internal const int CHUNK_BYTES = 65536;
        internal const long FILE_BYTES_MAX = 64L * 1024 * 1024;
        internal const long JOB_BYTES_MAX = 192L * 1024 * 1024;
        internal const int JOB_UNITS_MAX = 8192;
        internal const int DIRS_MAX = 128, DEPTH_MAX = 6, DIR_ENTRIES_MAX = 512, FILES_MAX = 512;
        internal const int STEP_UNITS_MAX = 8;

        internal sealed class FileTarget { internal int Id; internal string Path; }

        /// <summary>What one finished job read: gdig entries, the two ldir
        /// parts and the disk half of aload, for exactly one generation.</summary>
        internal sealed class SurveyResult
        {
            internal long Gen;
            internal List<object> Gdig = new List<object>();
            internal List<object>[] Ldir = new List<object>[2];
            internal int AloadDiskState = NOT_YET;
            internal string MvidDisk = "";
            internal long Units, Bytes;
            internal bool Truncated;
        }

        /// <summary>The survey: single-flight (one job object; a request for a
        /// newer generation abandons an older job), stepped by the caller in
        /// bounded units ONLY when the caller says no combat is live (a step
        /// with combat live does nothing at all), never following a reparse
        /// point, every bound public, truncation stated in the result, and a
        /// result published only for the generation currently wanted (a late
        /// result of an older generation is refused). Per game: every
        /// generation reads every listed byte again (no digest is reused
        /// across generations, so a same-size same-time content change can
        /// never be reported with the old digest).</summary>
        internal sealed class Survey
        {
            private readonly IFs _fs;
            private readonly IList<FileTarget> _files;
            private readonly string[] _dirs;              // plugins, patchers
            private readonly string _gameAsm;
            private Job _job;
            private SurveyResult _result;
            internal long Wanted;
            internal long StaleRefused, Abandoned, CombatSkips, StepsWorked, UnitsTotal;

            internal Survey(IFs fs, IList<FileTarget> files, string pluginsDir, string patchersDir, string gameAsm)
            {
                _fs = fs; _files = files; _dirs = new[] { pluginsDir, patchersDir }; _gameAsm = gameAsm;
            }

            internal bool Running { get { return _job != null; } }
            internal long RunningGen { get { return _job != null ? _job.Gen : -1; } }

            /// <summary>Asks for a survey of generation `gen` (one per game).
            /// Single-flight: an equal running job continues; an older one is
            /// abandoned and replaced; a result already published for `gen`
            /// stands.</summary>
            internal void Request(long gen)
            {
                if (gen > Wanted) Wanted = gen;
                if (_result != null && _result.Gen == gen) return;
                if (_job != null && _job.Gen == gen) return;
                if (_job != null) Abandoned++;
                // per game: every generation re-reads every byte
                _job = new Job(this, gen);
            }

            /// <summary>The result for exactly `gen`, or null (not yet).</summary>
            internal SurveyResult ResultFor(long gen)
            {
                return _result != null && _result.Gen == gen ? _result : null;
            }

            /// <summary>Publishes a finished result only for the generation
            /// wanted now; anything older is refused and counted.</summary>
            internal bool TryPublish(SurveyResult r)
            {
                if (r == null || r.Gen != Wanted) { StaleRefused++; return false; }
                _result = r;
                return true;
            }

            /// <summary>One step from the caller's tick. Combat live: nothing
            /// at all is done. Otherwise at most STEP_UNITS_MAX units, stopping
            /// early once `budgetUs` has elapsed on `clockUs`. Returns units done.</summary>
            internal int Step(bool combatLive, long budgetUs, Func<long> clockUs)
            {
                if (combatLive) { CombatSkips++; return 0; }
                if (_job == null) return 0;
                long t0 = clockUs();
                int n = 0;
                while (_job != null && n < STEP_UNITS_MAX)
                {
                    bool more = _job.Unit();
                    n++; UnitsTotal++;
                    if (!more)
                    {
                        var j = _job;
                        _job = null;
                        TryPublish(j.R);
                        break;
                    }
                    if (clockUs() - t0 >= budgetUs) break;
                }
                if (n > 0) StepsWorked++;
                return n;
            }

            private sealed class Job
            {
                private readonly Survey _s;
                internal readonly long Gen;
                internal readonly SurveyResult R;
                private int _phase;            // 0 gdig, 1 plugins, 2 patchers, 3 aload, 4 done
                private int _fileIx;
                private Stream _stream;
                private SHA256 _hash;
                private long _fileBytes;
                private readonly byte[] _buf = new byte[CHUNK_BYTES];
                // directory walk of the current ldir part
                private readonly Queue<KeyValuePair<string, int>> _pending = new Queue<KeyValuePair<string, int>>();
                private readonly List<string> _dlls = new List<string>();
                private int _dirsSeen, _dllIx, _partState, _partFiles;
                private bool _partTrunc, _walked, _partStarted;
                private string _dllName;
                private readonly List<object> _partList = new List<object>();
                private readonly List<FsEntry> _entries = new List<FsEntry>();

                internal Job(Survey s, long gen)
                {
                    _s = s; Gen = gen;
                    R = new SurveyResult { Gen = gen };
                }

                private int PartCap { get { return _phase == 1 ? LDIR_PLUGINS_MAX : LDIR_PATCHERS_MAX; } }

                /// <summary>One bounded unit. False when the job is done.</summary>
                internal bool Unit()
                {
                    if (R.Units >= JOB_UNITS_MAX || R.Bytes >= JOB_BYTES_MAX) { Stop(); return false; }
                    R.Units++;
                    try
                    {
                        switch (_phase)
                        {
                            case 0: GdigUnit(); break;
                            case 1: case 2: LdirUnit(); break;
                            case 3: AloadUnit(); break;
                        }
                    }
                    catch
                    {
                        // a fault inside a unit settles the item it was on, never the job as clean
                        Fault();
                    }
                    return _phase < 4;
                }

                private void GdigUnit()
                {
                    if (_fileIx >= _s._files.Count || _fileIx >= GDIG_MAX) { _phase = 1; return; }
                    var f = _s._files[_fileIx];
                    if (_stream == null)
                    {
                        bool missing;
                        _stream = _s._fs.Open(f.Path, out missing);
                        if (_stream == null) { NextFile(missing ? NO_FILE : READ_FAILED, "", 0); return; }
                        _hash = SHA256.Create(); _fileBytes = 0;
                        return;
                    }
                    int n = _stream.Read(_buf, 0, _buf.Length);
                    if (n > 0)
                    {
                        _hash.TransformBlock(_buf, 0, n, null, 0);
                        _fileBytes += n; R.Bytes += n;
                        if (_fileBytes > FILE_BYTES_MAX) { R.Truncated = true; NextFile(READ_FAILED, "", 0); }
                        return;
                    }
                    _hash.TransformFinalBlock(_buf, 0, 0);
                    NextFile(OK, Hex(_hash.Hash), _fileBytes);
                }

                private void NextFile(int state, string sha, long size)
                {
                    var f = _s._files[_fileIx];
                    R.Gdig.Add(L((long)f.Id, state == OK ? sha : "", (long)state, state == OK ? Clamp(size, 0, int.MaxValue) : 0L));
                    CloseStream();
                    _fileIx++;
                }

                private void CloseStream()
                {
                    try { if (_stream != null) _stream.Dispose(); } catch { }
                    try { if (_hash != null) _hash.Dispose(); } catch { }
                    _stream = null; _hash = null;
                }

                private void LdirUnit()
                {
                    string root = _s._dirs[_phase - 1];
                    if (!_partStarted)
                    {
                        _partStarted = true; _walked = false; _pending.Clear(); _dlls.Clear(); _partList.Clear();
                        _dirsSeen = 0; _dllIx = 0; _partState = OK; _partFiles = 0; _partTrunc = false; _dllName = null;
                        if (string.IsNullOrEmpty(root)) { _partState = NO_FILE; EndPart(); return; }
                        _pending.Enqueue(new KeyValuePair<string, int>(root, 0));
                        return;
                    }
                    if (!_walked)
                    {
                        if (_pending.Count == 0) { _walked = true; return; }
                        var d = _pending.Dequeue();
                        _dirsSeen++;
                        _entries.Clear();
                        int st = _s._fs.List(d.Key, DIR_ENTRIES_MAX, _entries);
                        if (st != 0)
                        {
                            if (d.Value == 0) { _partState = st == 1 ? NO_FILE : READ_FAILED; EndPart(); return; }
                            _partTrunc = true;      // an unreadable subfolder: the survey is incomplete
                            return;
                        }
                        if (_entries.Count > DIR_ENTRIES_MAX) _partTrunc = true;
                        int lim = Math.Min(_entries.Count, DIR_ENTRIES_MAX);
                        for (int i = 0; i < lim; i++)
                        {
                            var e = _entries[i];
                            if (e.IsReparse) continue;                 // never followed, never read
                            if (e.IsDir)
                            {
                                if (d.Value + 1 > DEPTH_MAX || _dirsSeen + _pending.Count >= DIRS_MAX) { _partTrunc = true; continue; }
                                _pending.Enqueue(new KeyValuePair<string, int>(e.Path, d.Value + 1));
                            }
                            else if (e.Path != null && e.Path.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
                            {
                                if (_dlls.Count >= FILES_MAX) { _partTrunc = true; continue; }
                                _dlls.Add(e.Path);
                            }
                        }
                        return;
                    }
                    _partFiles = _dlls.Count;
                    if (_dllIx >= _dlls.Count || _dllIx >= PartCap)
                    {
                        if (_dlls.Count > PartCap) _partTrunc = true;
                        EndPart();
                        return;
                    }
                    string path = _dlls[_dllIx];
                    if (_dllName == null && _stream == null)
                    {
                        _dllName = _s._fs.AsmName(path) ?? "";
                        return;
                    }
                    if (_stream == null)
                    {
                        bool missing;
                        _stream = _s._fs.Open(path, out missing);
                        if (_stream == null) { _partTrunc = true; NextDll(null); return; }
                        _hash = SHA256.Create(); _fileBytes = 0;
                        return;
                    }
                    int n = _stream.Read(_buf, 0, _buf.Length);
                    if (n > 0)
                    {
                        _hash.TransformBlock(_buf, 0, n, null, 0);
                        _fileBytes += n; R.Bytes += n;
                        if (_fileBytes > FILE_BYTES_MAX) { _partTrunc = true; NextDll(null); }
                        return;
                    }
                    _hash.TransformFinalBlock(_buf, 0, 0);
                    NextDll(Hex(_hash.Hash));
                }

                private void NextDll(string sha)
                {
                    if (sha != null) _partList.Add(L(_dllName ?? "", sha));
                    CloseStream();
                    _dllName = null;
                    _dllIx++;
                }

                private void EndPart()
                {
                    CloseStream();
                    var part = _partState == OK
                        ? L((long)OK, Clamp(_partFiles, 0, SMALL_MAX), _partTrunc ? 1L : 0L, new List<object>(_partList))
                        : L((long)_partState, 0L, 0L, new List<object>());
                    if (_partTrunc) R.Truncated = true;
                    R.Ldir[_phase - 1] = part;
                    _partStarted = false;
                    _phase++;
                }

                private void AloadUnit()
                {
                    bool missing = true;
                    Stream s = string.IsNullOrEmpty(_s._gameAsm) ? null : _s._fs.Open(_s._gameAsm, out missing);
                    if (s == null) { R.AloadDiskState = missing ? NO_FILE : READ_FAILED; _phase = 4; return; }
                    try
                    {
                        string m = Mvid.FromPe(s);
                        if (m != null) { R.MvidDisk = m; R.AloadDiskState = OK; }
                        else R.AloadDiskState = READ_FAILED;
                    }
                    finally { try { s.Dispose(); } catch { } }
                    _phase = 4;
                }

                /// <summary>A fault: the item in hand becomes read_failed (a
                /// gdig file), an incomplete part (ldir) or read_failed (aload).</summary>
                private void Fault()
                {
                    if (_phase == 0 && _fileIx < _s._files.Count) NextFile(READ_FAILED, "", 0);
                    else if (_phase == 1 || _phase == 2)
                    {
                        _partTrunc = true;
                        if (_walked && _dllIx < _dlls.Count) NextDll(null);
                        else if (!_walked && !_partStarted) { _partState = READ_FAILED; EndPart(); }
                    }
                    else if (_phase == 3) { R.AloadDiskState = READ_FAILED; _phase = 4; }
                }

                /// <summary>Over a job bound: whatever was not reached stays
                /// not_yet (gdig, aload) or a truncated part.</summary>
                private void Stop()
                {
                    CloseStream();
                    R.Truncated = true;
                    if (_phase == 1 || _phase == 2)
                    {
                        _partTrunc = true;
                        if (_partStarted && _partState == OK) { int p = _phase; EndPart(); _phase = p + 1; }
                    }
                    _phase = 4;
                }
            }
        }

        /// <summary>The record's gdig, ldir and the disk half of aload for one
        /// game: from the result of exactly that game's generation, or
        /// not_yet everywhere (never an empty clean survey). Every assembly
        /// name an ldir part carries passes `priv` here, so no survey name
        /// reaches a record unfiltered.</summary>
        internal static void SurveyFields(SurveyResult r, IList<FileTarget> files, Privacy priv, out List<object> gdig, out C.JObj ldir, out int diskState, out string mvidDisk)
        {
            gdig = new List<object>();
            ldir = new C.JObj();
            if (r == null)
            {
                int n = 0;
                foreach (var f in files) { if (n++ >= GDIG_MAX) break; gdig.Add(L((long)f.Id, "", (long)NOT_YET, 0L)); }
                ldir.Add("plugins", L((long)NOT_YET, 0L, 0L, new List<object>())).Add("patchers", L((long)NOT_YET, 0L, 0L, new List<object>()));
                diskState = NOT_YET; mvidDisk = "";
                return;
            }
            gdig.AddRange(r.Gdig);
            // a file the job never reached (it stopped at a bound) is not_yet
            var seen = new HashSet<long>();
            foreach (List<object> e in r.Gdig) seen.Add((long)e[0]);
            foreach (var f in files) if (!seen.Contains(f.Id) && gdig.Count < GDIG_MAX) gdig.Add(L((long)f.Id, "", (long)NOT_YET, 0L));
            for (int i = 0; i < 2; i++)
            {
                var part = r.Ldir[i];
                if (part == null) { ldir.Add(LDIR_PARTS[i], L((long)NOT_YET, 0L, 0L, new List<object>())); continue; }
                var named = new List<object>();
                foreach (List<object> e in (List<object>)part[3]) named.Add(L(priv.NameOrEmpty((string)e[0]), e[1]));
                ldir.Add(LDIR_PARTS[i], L(part[0], part[1], part[2], named));
            }
            diskState = r.AloadDiskState;
            mvidDisk = r.AloadDiskState == OK ? r.MvidDisk : "";
        }

        // -- the module version id read from a file (design 3.3 aload) ----------------------

        /// <summary>The Module table's Mvid of a .NET PE file, as the loaded
        /// module reports it (Guid "N" form), read with bounded seeks; null
        /// when the file is not one.</summary>
        internal static class Mvid
        {
            internal static string FromPe(Stream s)
            {
                if (s == null || !s.CanSeek) return null;
                int lfanew = I32(s, 0x3C);
                if (lfanew <= 0 || lfanew > 4096) return null;
                if (I32(s, lfanew) != 0x00004550) return null;
                int coff = lfanew + 4;
                int nSections = U16(s, coff + 2);
                int optSize = U16(s, coff + 16);
                int opt = coff + 20;
                int magic = U16(s, opt);
                int dirs = magic == 0x10b ? opt + 96 : (magic == 0x20b ? opt + 112 : -1);
                if (dirs < 0) return null;
                int cliRva = I32(s, dirs + 14 * 8);
                int secTab = opt + optSize;
                if (nSections <= 0 || nSections > 96) return null;
                int cli = RvaToOffset(s, secTab, nSections, cliRva);
                if (cli < 0) return null;
                int mdRva = I32(s, cli + 8);
                int md = RvaToOffset(s, secTab, nSections, mdRva);
                if (md < 0 || I32(s, md) != 0x424A5342) return null;
                int vlen = I32(s, md + 12);
                if (vlen < 0 || vlen > 256) return null;
                int nStreams = U16(s, md + 16 + vlen + 2);
                int p = md + 16 + vlen + 4;
                int tbl = -1, guid = -1, guidSize = 0;
                for (int i = 0; i < nStreams && i < 16; i++)
                {
                    int off = I32(s, p), size = I32(s, p + 4);
                    string name = CStr(s, p + 8, 32);
                    if (name == null) return null;
                    if (name == "#~" || name == "#-") tbl = md + off;
                    else if (name == "#GUID") { guid = md + off; guidSize = size; }
                    p += 8 + ((name.Length + 4) & ~3);
                }
                if (tbl < 0 || guid < 0) return null;
                int heapSizes = U8(s, tbl + 6);
                long valid = I64(s, tbl + 8);
                if ((valid & 1) == 0) return null;
                int rows = tbl + 24;
                for (int b = 0; b < 64; b++) if (((valid >> b) & 1) != 0) rows += 4;
                if ((heapSizes & 0x40) != 0) rows += 4;
                int strIdx = (heapSizes & 0x01) != 0 ? 4 : 2;
                int guidIdx = (heapSizes & 0x02) != 0 ? 4 : 2;
                int mvidAt = rows + 2 + strIdx;
                int ix = guidIdx == 4 ? I32(s, mvidAt) : U16(s, mvidAt);
                if (ix < 1 || (ix * 16) > guidSize) return null;
                byte[] g = Bytes(s, guid + (ix - 1) * 16, 16);
                if (g == null) return null;
                return new Guid(g).ToString("N");
            }

            private static int RvaToOffset(Stream s, int secTab, int n, int rva)
            {
                for (int i = 0; i < n; i++)
                {
                    int e = secTab + i * 40;
                    int vsize = I32(s, e + 8), va = I32(s, e + 12), rawSize = I32(s, e + 16), raw = I32(s, e + 20);
                    int span = Math.Max(vsize, rawSize);
                    if (rva >= va && rva < va + span) return rva - va + raw;
                }
                return -1;
            }

            private static byte[] Bytes(Stream s, long at, int n)
            {
                if (at < 0 || at + n > s.Length) return null;
                s.Seek(at, SeekOrigin.Begin);
                var b = new byte[n];
                int got = 0;
                while (got < n) { int r = s.Read(b, got, n - got); if (r <= 0) return null; got += r; }
                return b;
            }

            private static int U8(Stream s, long at) { var b = Bytes(s, at, 1); return b == null ? -1 : b[0]; }
            private static int U16(Stream s, long at) { var b = Bytes(s, at, 2); return b == null ? -1 : b[0] | (b[1] << 8); }
            private static int I32(Stream s, long at) { var b = Bytes(s, at, 4); return b == null ? -1 : BitConverter.ToInt32(b, 0); }
            private static long I64(Stream s, long at) { var b = Bytes(s, at, 8); return b == null ? 0 : BitConverter.ToInt64(b, 0); }
            private static string CStr(Stream s, long at, int max)
            {
                var b = Bytes(s, at, max);
                if (b == null) return null;
                int n = Array.IndexOf(b, (byte)0);
                return n < 0 ? null : Encoding.ASCII.GetString(b, 0, n);
            }
        }

        // -- the other seat's player stream and the points (design 4.2, 4.3; L7, L8) --------

        /// <summary>One received package of the other seat's player view, as
        /// the hook read it: the sender's stamp, this seat's own server-time
        /// estimate and Stopwatch ms at arrival, position and velocity in
        /// centi-units, input and aim direction scaled 1e6, jump flags and the
        /// stated interval in ms (already clamped by the game's reader).</summary>
        internal struct Pkg
        {
            internal int Stamp, ArrServer;
            internal long ArrSw;
            internal int Px, Py, Vx, Vy;
            internal int Dx, Dy, Ax, Ay;
            internal bool Jump, HoldJump;
            internal int TdMs;
        }

        /// <summary>The frame rate the other seat published (L8): three-valued.
        /// Unknown (-1): nothing published. Published without a measurement
        /// (0): a value that is not a positive frame rate. Measured (&gt;0).
        /// The serialization interval is never a substitute.</summary>
        internal static int PubFps(bool published, int value)
        {
            if (!published) return -1;
            return value > 0 ? (int)Clamp(value, 1, FPS_MAX) : 0;
        }

        /// <summary>Per-point and per-game accounting of the other seat's
        /// stream and this seat's own point timings. Fixed-size state per
        /// package; medians come from fixed histograms reset per bucket.</summary>
        internal sealed class ClockBook
        {
            internal int T0;
            // cadence (cad_b)
            internal readonly List<object> CadB = new List<object>();
            private int _bucket = int.MinValue, _bBatches, _bTdSat, _bGapN, _bTdN;
            private readonly int[] _gapHist = new int[1001];
            private readonly int[] _tdHist = new int[TD_CEIL_MS + 1];
            // stream state
            private bool _have;
            private Pkg _prev;
            // tdg and gclk
            internal readonly long[] TdgBins = new long[TDG_EDGES.Length + 1];
            internal long TdgN, TdgSat;
            private double _gTd, _gArr; private long _gPairs;
            // points
            internal readonly List<PointO> PtO = new List<PointO>();
            internal readonly List<PointS> PtS = new List<PointS>();
            internal int PointCount;          // every point-start RPC since t0
            internal long NoStamp, OverCap;
            internal PointO CurO; internal PointS CurS;
            internal int LastPubFps = -1;

            internal ClockBook(int t0) { T0 = t0; }

            /// <summary>N7: the point-start RPC executed here.</summary>
            internal void PointStart(bool hasStamp, int ps, int ownServerNow, long swNow)
            {
                ClosePoint(swNow);
                int pt = PointCount++;
                if (!hasStamp) { NoStamp++; return; }
                if (PtO.Count >= PT_MAX) { OverCap++; return; }
                int age = (int)Clamp(WrapDiff(ownServerNow, ps), -AGE_MAX, AGE_MAX);
                CurO = new PointO { Pt = pt, Ps = ps, PsAge = age, PubFps = LastPubFps, StartSw = swNow };
                CurS = new PointS { Pt = pt, Ps = ps, PsAge = age, ExecSw = swNow };
                PtO.Add(CurO); PtS.Add(CurS);
            }

            /// <summary>N8: the other seat's spawn target for this point.</summary>
            internal void Target(int x, int y)
            {
                if (CurO == null || CurO.HasTgt) return;
                CurO.HasTgt = true; CurO.Tx = x; CurO.Ty = y;
            }

            /// <summary>The point ends on this seat (first death, or the next
            /// point start, or game over).</summary>
            internal void ClosePoint(long swNow)
            {
                if (CurO != null && CurO.End < 0) CurO.End = (int)Clamp(swNow - CurO.StartSw, -1, MS_POINT_MAX);
                if (CurS != null) CurS.Close(swNow);
                CurO = null; CurS = null;
            }

            internal void EndOfPointSeen(long swNow) { ClosePoint(swNow); }

            /// <summary>The other seat's first ammunition-using shot (its
            /// RPCA_Init) as received: sender stamp and own arrival estimate.</summary>
            internal void OtherShot(int stamp, int arrServer)
            {
                var o = CurO;
                if (o == null || o.ShotFirst >= 0) return;
                int d = WrapDiff(stamp, o.Ps);
                if (d < 0) return;
                o.ShotFirst = (int)Clamp(d, 0, MS_POINT_MAX);
                o.ShotFirstArr = (int)Clamp(WrapDiff(arrServer, o.Ps), -1, MS_POINT_MAX);
            }

            /// <summary>One package of the other seat's player view. O(1).</summary>
            internal void Package(Pkg p)
            {
                Cadence(p);
                if (_have)
                {
                    int gap = WrapDiff(p.Stamp, _prev.Stamp);
                    bool moving = p.Vx != 0 || p.Vy != 0;
                    if (gap > 0 && moving)
                    {
                        int d = gap - p.TdMs;
                        int bin = 0;
                        while (bin < TDG_EDGES.Length && d >= TDG_EDGES[bin]) bin++;
                        TdgBins[bin]++; TdgN++;
                        if (p.TdMs >= TD_CEIL_MS) TdgSat++;
                        long arr = p.ArrSw - _prev.ArrSw;
                        if (p.TdMs > 0 && gap < 2 * p.TdMs && arr >= 0)
                        {
                            _gTd += p.TdMs; _gArr += arr; _gPairs++;
                        }
                    }
                }
                PointPkg(p);
                _prev = p; _have = true;
            }

            private void Cadence(Pkg p)
            {
                int b = FloorDiv(WrapDiff(p.ArrServer, T0), BUCKET_MS);
                if (b < 0 || b > BUCKET_MAX) return;
                if (b != _bucket)
                {
                    if (b < _bucket) return;
                    FlushBucket();
                    _bucket = b;
                }
                bool newBatch = !_have || p.Stamp != _prev.Stamp;
                if (!newBatch) return;
                _bBatches++;
                if (_have)
                {
                    int gap = WrapDiff(p.Stamp, _prev.Stamp);
                    if (gap > 0) { _gapHist[gap > 1000 ? 1000 : gap]++; _bGapN++; }
                }
                int td = p.TdMs < 0 ? 0 : (p.TdMs > TD_CEIL_MS ? TD_CEIL_MS : p.TdMs);
                _tdHist[td]++; _bTdN++;
                if (p.TdMs >= TD_CEIL_MS) _bTdSat++;
            }

            /// <summary>Closes the open bucket: [bucket, batches, median gap,
            /// median stated interval, saturated]; a median is the lower median
            /// of the 1-ms histogram (gaps above 1000 ms count as 1000), -1
            /// when there is no value.</summary>
            internal void FlushBucket()
            {
                if (_bucket == int.MinValue) return;
                if (_bBatches > 0 && CadB.Count < CAD_MAX + 64)
                    CadB.Add(L((long)_bucket, Clamp(_bBatches, 0, COUNT_MAX), (long)Median(_gapHist, _bGapN),
                               (long)Median(_tdHist, _bTdN), Clamp(_bTdSat, 0, COUNT_MAX)));
                Array.Clear(_gapHist, 0, _gapHist.Length); Array.Clear(_tdHist, 0, _tdHist.Length);
                _bBatches = _bTdSat = _bGapN = _bTdN = 0;
                _bucket = int.MinValue;
            }

            internal static int Median(int[] hist, int n)
            {
                if (n <= 0) return -1;
                int want = (n - 1) / 2, acc = 0;
                for (int i = 0; i < hist.Length; i++) { acc += hist[i]; if (acc > want) return i; }
                return hist.Length - 1;
            }

            private void PointPkg(Pkg p)
            {
                var o = CurO;
                if (o == null) return;
                int rel = WrapDiff(p.Stamp, o.Ps);
                if (rel < 0) return;
                int relC = (int)Clamp(rel, 0, MS_POINT_MAX);
                int arr = (int)Clamp(WrapDiff(p.ArrServer, o.Ps), -1, MS_POINT_MAX);
                long dist = -1;
                if (o.HasTgt)
                {
                    double dx = (double)p.Px - o.Tx, dy = (double)p.Py - o.Ty;
                    dist = (long)Math.Floor(Math.Sqrt(dx * dx + dy * dy));
                }
                if (!o.Seen) { o.Seen = true; o.DistStart = dist < 0 ? -1 : (int)Clamp(dist, 0, CU_MAX); }
                bool inpos = o.Inpos[REF_RUNG] >= 0;
                if (!inpos && p.TdMs > o.TdMax) o.TdMax = (int)Clamp(p.TdMs, 0, TD_MS_MAX);
                if (!inpos && p.TdMs >= TD_CEIL_MS) o.TdSat++;
                if (dist >= 0)
                    for (int k = 0; k < RUNGS_CU.Length; k++)
                        if (o.Inpos[k] < 0 && dist <= RUNGS_CU[k])
                        {
                            o.Inpos[k] = relC;
                            if (k == REF_RUNG) { o.InposArr = arr; o.RefX = p.Px; o.RefY = p.Py; o.RefVx = p.Vx; o.RefVy = p.Vy; }
                        }
                bool input = p.Dx != 0 || p.Dy != 0 || p.Jump || p.HoldJump;
                if (o.InFirst < 0)
                {
                    o.NPk++;
                    if (o.HavePrevStamp)
                    {
                        int g = WrapDiff(p.Stamp, o.PrevStamp);
                        if (g > o.GapMax) o.GapMax = (int)Clamp(g, 0, MS_POINT_MAX);
                    }
                    if (input) { o.InFirst = relC; o.InFirstArr = arr; }
                }
                // L7: movement, not input: after in position, a position change
                // from the in-position package, or a velocity change, beyond
                // the movement resolution
                if (inpos && o.MoveFirst < 0)
                {
                    double mdx = (double)p.Px - o.RefX, mdy = (double)p.Py - o.RefY;
                    double vdx = (double)p.Vx - o.RefVx, vdy = (double)p.Vy - o.RefVy;
                    if (mdx * mdx + mdy * mdy > (double)MOVE_RES_CU * MOVE_RES_CU || vdx * vdx + vdy * vdy > (double)VEL_RES_CU * VEL_RES_CU)
                    { o.MoveFirst = relC; o.MoveFirstArr = arr; }
                }
                if (inpos && o.AimFirst < 0 && o.HavePrevAim && AimChanged(o.PrevAx, o.PrevAy, p.Ax, p.Ay)) o.AimFirst = relC;
                o.PrevAx = p.Ax; o.PrevAy = p.Ay; o.HavePrevAim = true;
                o.PrevStamp = p.Stamp; o.HavePrevStamp = true;
            }

            internal static bool AimChanged(int ax, int ay, int bx, int by)
            {
                double na = Math.Sqrt((double)ax * ax + (double)ay * ay), nb = Math.Sqrt((double)bx * bx + (double)by * by);
                if (na <= 0 || nb <= 0) return na != nb;
                double cos = ((double)ax * bx + (double)ay * by) / (na * nb);
                return cos * 1e6 < AIM_COS_1E6;
            }

            internal List<object> Gclk()
            {
                if (_gPairs == 0 || _gArr <= 0) return L(0L, 0L, 0L);
                double rate = (_gTd / _gArr - 1.0) * 1e8;      // centi-ppm
                return L(Clamp((long)Math.Round(rate), -GCLK_CPPM_MAX, GCLK_CPPM_MAX), Clamp(_gPairs, 1, COUNT_MAX),
                         Clamp((long)Math.Round(_gArr), 0, MS_DAY_MAX));
            }

            internal List<object> Tdg()
            {
                var bins = new List<object>();
                foreach (var b in TdgBins) bins.Add(Clamp(b, 0, COUNT_MAX));
                long n = 0; foreach (var b in TdgBins) n += Clamp(b, 0, COUNT_MAX);
                return L(Clamp(n, 0, COUNT_MAX), Clamp(TdgSat, 0, n), bins);
            }
        }

        /// <summary>The other seat at one point, as this seat saw it (pt_o).</summary>
        internal sealed class PointO
        {
            internal int Pt, Ps, PsAge, PubFps = -1;
            internal long StartSw;
            internal bool HasTgt, Seen, HavePrevStamp, HavePrevAim;
            internal int Tx, Ty, DistStart = -1, PrevStamp, PrevAx, PrevAy;
            internal int RefX, RefY, RefVx, RefVy;
            internal readonly int[] Inpos = { -1, -1, -1, -1 };
            internal int InposArr = -1, GapMax = -1, TdMax = -1, InFirst = -1, InFirstArr = -1;
            internal int MoveFirst = -1, MoveFirstArr = -1, AimFirst = -1, ShotFirst = -1, ShotFirstArr = -1, End = -1;
            internal long NPk, TdSat;

            internal List<object> Entry()
            {
                var rungs = new List<object>();
                for (int k = 0; k < RUNGS_CU.Length && k < RUNGS_MAX; k++) rungs.Add((long)Inpos[k]);
                return L((long)Clamp(Pt, 0, ID_MAX), (long)Ps, (long)PsAge,
                         HasTgt ? L((long)Clamp(Tx, -CU_MAX, CU_MAX), (long)Clamp(Ty, -CU_MAX, CU_MAX)) : new List<object>(),
                         (long)DistStart, rungs, (long)InposArr, Clamp(NPk, 0, COUNT_MAX), (long)GapMax, (long)TdMax,
                         Clamp(TdSat, 0, COUNT_MAX), (long)InFirst, (long)InFirstArr, (long)MoveFirst, (long)MoveFirstArr,
                         (long)AimFirst, (long)ShotFirst, (long)ShotFirstArr, (long)End, (long)Clamp(PubFps, -1, FPS_MAX));
            }
        }

        /// <summary>This seat at one point, about itself (pt_s).</summary>
        internal sealed class PointS
        {
            internal int Pt, Ps, PsAge;
            internal long ExecSw, MoveStartSw = -1, ReleaseSw = -1;
            internal int MapWait = -1, Rel = -1, MvFrames = -1, MvFtMaxUs = -1, MvT = -1, InFirst = -1, ShotFirst = -1;
            internal double ThMs; internal int Th = -1, Wall = -1;
            internal bool Closed;
            private int _frames; private long _ftMax;

            /// <summary>The tick: own isPlaying falling edge (the move starts).</summary>
            internal void MoveStart(long sw, int curveMs)
            {
                if (Closed || MoveStartSw >= 0) return;
                MoveStartSw = sw; MapWait = (int)Clamp(sw - ExecSw, -1, MS_POINT_MAX);
                MvT = curveMs < 0 ? -1 : (int)Clamp(curveMs, 0, MS_POINT_MAX);
                _frames = 0; _ftMax = 0;
            }

            /// <summary>The tick, between move start and release: one frame of `frameUs`.</summary>
            internal void MoveFrame(long frameUs)
            {
                if (Closed || MoveStartSw < 0 || ReleaseSw >= 0) return;
                _frames++; if (frameUs > _ftMax) _ftMax = frameUs;
            }

            /// <summary>The tick: own isPlaying rising edge (release).</summary>
            internal void Release(long sw)
            {
                if (Closed || ReleaseSw >= 0) return;
                ReleaseSw = sw; Rel = (int)Clamp(sw - ExecSw, -1, MS_POINT_MAX);
                if (MoveStartSw >= 0) { MvFrames = (int)Clamp(_frames, 0, FRAMES_MAX); MvFtMaxUs = (int)Clamp(_ftMax, 0, US_MAX); }
                ThMs = 0;
            }

            internal void GameTime(double dtMs) { if (!Closed && ReleaseSw >= 0) ThMs += dtMs; }

            internal void OwnInput(long sw) { if (!Closed && InFirst < 0) InFirst = (int)Clamp(sw - ExecSw, 0, MS_POINT_MAX); }
            internal void OwnShot(long sw) { if (!Closed && ShotFirst < 0) ShotFirst = (int)Clamp(sw - ExecSw, 0, MS_POINT_MAX); }

            internal void Close(long sw)
            {
                if (Closed) return;
                Closed = true;
                if (ReleaseSw >= 0) { Th = (int)Clamp((long)Math.Round(ThMs), 0, MS_POINT_MAX); Wall = (int)Clamp(sw - ReleaseSw, 0, MS_POINT_MAX); }
            }

            internal List<object> Entry()
            {
                return L((long)Clamp(Pt, 0, ID_MAX), (long)Ps, (long)PsAge, (long)MapWait, (long)Rel, (long)MvFrames, (long)MvFtMaxUs,
                         (long)MvT, (long)InFirst, (long)ShotFirst, (long)Th, (long)Wall);
            }
        }

        // -- the other seat's RPC names (rpc_o) ---------------------------------------------

        internal sealed class RpcNames
        {
            internal const int KEEP = 128;
            private readonly List<string> _names = new List<string>();
            private readonly List<long> _n = new List<long>();
            internal long Overflow;
            internal void Add(string name)
            {
                string k = name ?? "";
                int i = _names.IndexOf(k);
                if (i >= 0) { if (_n[i] < COUNT_MAX) _n[i]++; return; }
                if (_names.Count >= KEEP) { Overflow++; return; }
                _names.Add(k); _n.Add(1);
            }
            internal List<object> Entries(Privacy priv)
            {
                var l = new List<object>();
                for (int i = 0; i < _names.Count; i++) l.Add(L(priv.Name(_names[i]), _n[i]));
                return l;
            }
        }

        // -- the record ---------------------------------------------------------------------

        /// <summary>The cost row of one collector: [id, calls, faults, us_total, us_max].</summary>
        internal sealed class Cost
        {
            internal readonly int Id; internal long Calls, Faults, UsTotal, UsMax;
            internal Cost(int id) { Id = id; }
            internal void Add(long us) { if (Calls < COUNT_MAX) Calls++; if (us < 0) us = 0; UsTotal = Math.Min(UsTotal + us, COUNT_MAX); if (us > UsMax) UsMax = Math.Min(us, COUNT_MAX); }
            internal void Fault() { if (Faults < COUNT_MAX) Faults++; }
            internal List<object> Entry() { return L((long)Id, Calls, Math.Min(Faults, Calls), UsTotal, UsMax); }
        }

        /// <summary>Every layout key in order. Lists may exceed their caps;
        /// Budget cuts them.</summary>
        internal static C.JObj Record(int t0, bool fromToken, IList<Cost> cost, ProcLedger proc, GameRuns runs,
            List<object> asmN, List<object> asm, List<object> gdig, List<object> aload, C.JObj ldir,
            List<object> hpAll, List<object> hp, List<object> rpcO, long rpcOverflow, List<object> sendCfg,
            ClockBook book)
        {
            List<object> chk, plug;
            ChkAndPlug(proc, runs, out chk, out plug);
            var costL = new List<object>();
            foreach (var c in cost) if (costL.Count < COST_MAX) costL.Add(c.Entry());
            book.FlushBucket();
            var ptS = new List<object>(); foreach (var s in book.PtS) ptS.Add(s.Entry());
            var ptO = new List<object>(); foreach (var o in book.PtO) ptO.Add(o.Entry());
            var omit = new C.JObj();
            foreach (var k in TRIM) omit.Add(k, k == "rpc_o" ? Clamp(rpcOverflow, 0, COUNT_MAX) : 0L);
            return new C.JObj()
                .Add("schema", (long)SCHEMA).Add("consts", (long)CONSTS).Add("t0", (long)t0).Add("t0_src", fromToken ? "m" : "o")
                .Add("cost", costL).Add("proc", proc.Entry()).Add("chk", chk).Add("plug", plug)
                .Add("asm_n", asmN).Add("asm", asm).Add("gdig", gdig).Add("aload", aload).Add("ldir", ldir)
                .Add("hp_all", hpAll).Add("hp", hp).Add("rpc_o", rpcO).Add("send_cfg", sendCfg)
                .Add("gclk", book.Gclk()).Add("tdg", book.Tdg()).Add("cad_b", new List<object>(book.CadB))
                .Add("pt_s", ptS).Add("pt_o", ptO).Add("unpair", L(Clamp(book.NoStamp, 0, SMALL_MAX), Clamp(book.OverCap, 0, SMALL_MAX)))
                .Add("omit", omit);
        }

        // -- the budgeter (line for line ice_budget_record) ---------------------------------

        private static int TrimCap(string k)
        {
            switch (k) { case "asm": return ASM_MAX; case "cad_b": return CAD_MAX; case "rpc_o": return RPC_MAX; case "hp": return HP_MAX; }
            return -1;
        }

        private static int ProtectedCap(string k)
        {
            switch (k) { case "cost": return COST_MAX; case "chk": return CHK_MAX; case "plug": return PLUG_MAX; case "gdig": return GDIG_MAX;
                         case "pt_s": return PT_MAX; case "pt_o": return PT_MAX; }
            return -1;
        }

        private static List<object> LdirList(C.JObj o, int part) { return (List<object>)((List<object>)((C.JObj)o.Get("ldir")).Get(LDIR_PARTS[part]))[3]; }

        private static int TrimLen(C.JObj o, string k)
        {
            if (k == "ldir") return LdirList(o, 0).Count + LdirList(o, 1).Count;
            return ((List<object>)o.Get(k)).Count;
        }

        private static void TrimOne(C.JObj o, string k)
        {
            if (k == "ldir")
            {
                var a = LdirList(o, 0); var b = LdirList(o, 1);
                var lst = a.Count >= b.Count ? a : b;
                lst.RemoveAt(lst.Count - 1);
            }
            else
            {
                var l = (List<object>)o.Get(k);
                l.RemoveAt(l.Count - 1);
            }
        }

        private static object Copy(object v)
        {
            if (v is C.JObj)
            {
                var s = (C.JObj)v; var d = new C.JObj();
                for (int i = 0; i < s.Keys.Count; i++) d.Add(s.Keys[i], Copy(s.Values[i]));
                return d;
            }
            if (v is System.Collections.IList && !(v is string))
            {
                var d = new List<object>();
                foreach (var x in (System.Collections.IList)v) d.Add(Copy(x));
                return d;
            }
            return v;
        }

        /// <summary>The record text: every layout key in order; lists over
        /// their cap cut to it (trimmable ones counted in omit, a protected
        /// one over its cap is the caller's error); then, while over `limit`,
        /// the longest trimmable list loses its last entry (ties: TRIM order;
        /// ldir counts both parts and loses from the longer, plugins on a tie),
        /// each removal counted.</summary>
        internal static string Budget(C.JObj rec, int limit = RECORD_MAX_BYTES)
        {
            var o = new C.JObj();
            foreach (var k in KEYS)
            {
                object v = rec.Get(k);
                if (v == null) throw new ArgumentException("missing key " + k);
                o.Add(k, Copy(v));
            }
            var recOmit = (C.JObj)rec.Get("omit");
            var omit = new C.JObj();
            foreach (var k in TRIM) { object x = recOmit.Get(k); omit.Add(k, x == null ? 0L : Convert.ToInt64(x, CultureInfo.InvariantCulture)); }
            foreach (var k in new[] { "cost", "chk", "plug", "gdig", "pt_s", "pt_o" })
                if (((List<object>)o.Get(k)).Count > ProtectedCap(k)) throw new ArgumentException("protected list over its cap: " + k);
            foreach (var k in new[] { "asm", "cad_b", "rpc_o", "hp" })
            {
                var l = (List<object>)o.Get(k);
                int cap = TrimCap(k);
                if (l.Count > cap) { omit.Set(k, (long)omit.Get(k) + (l.Count - cap)); l.RemoveRange(cap, l.Count - cap); }
            }
            for (int p = 0; p < 2; p++)
            {
                var l = LdirList(o, p);
                int cap = p == 0 ? LDIR_PLUGINS_MAX : LDIR_PATCHERS_MAX;
                if (l.Count > cap) { omit.Set("ldir", (long)omit.Get("ldir") + (l.Count - cap)); l.RemoveRange(cap, l.Count - cap); }
            }
            o.Set("omit", omit);
            string body = C.Json(o);
            while (body.Length > limit)
            {
                string longest = null; int best = -1;
                foreach (var k in TRIM) { int n = TrimLen(o, k); if (n > best) { best = n; longest = k; } }
                if (best == 0) throw new ArgumentException("the protected fields alone exceed the limit");
                TrimOne(o, longest);
                omit.Set(longest, (long)omit.Get(longest) + 1);
                body = C.Json(o);
            }
            return body;
        }

        // -- signing, envelope, clock header ------------------------------------------------

        internal const string SIGN_PREFIX = "identity-clock-evidence:v1:";

        internal static string Canonical(string seat, string other, string stable, string attach, string recordText)
        {
            return SIGN_PREFIX + seat + ":" + other + ":" + Sha256Hex(Encoding.ASCII.GetBytes(stable)) + ":"
                   + Sha256Hex(Encoding.ASCII.GetBytes(attach)) + ":" + Sha256Hex(Encoding.ASCII.GetBytes(recordText));
        }

        internal static string Envelope(string seat, string other, string stable, string attach, string recordText, string sig)
        {
            if (!C.IsSteamId(seat) || !C.IsSteamId(other) || seat == other) return null;
            if (!C.IsAttachKey(stable, attach)) return null;
            if (string.IsNullOrEmpty(recordText) || recordText.Length > RECORD_MAX_BYTES) return null;
            for (int i = 0; i < recordText.Length; i++) if (recordText[i] > '~') return null;
            if (sig == null || sig.Length != 64) return null;
            return C.Json(new C.JObj().Add("contract", (long)CONTRACT).Add("seat_steam_id", seat).Add("other_steam_id", other)
                .Add("stable_game_key", stable).Add("attach_key", attach).Add("record", recordText).Add("sig", sig));
        }

        /// <summary>X-Seat-Clock, read immediately before each send:
        /// "proc.stopwatch_ms.unity_unscaled_ms.photon_server_ts", or null
        /// when a part is outside the header's bounds (the request then goes
        /// without it, which the server stores as absent).</summary>
        internal static string ClockHeader(string procId, long swMs, long unityMs, int photonTs)
        {
            if (procId == null || procId.Length != 12) return null;
            for (int i = 0; i < 12; i++) { char c = procId[i]; if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return null; }
            if (swMs < 0 || swMs > HEADER_MS_MAX || unityMs < 0 || unityMs > HEADER_MS_MAX) return null;
            return procId + "." + swMs.ToString(CultureInfo.InvariantCulture) + "." + unityMs.ToString(CultureInfo.InvariantCulture)
                   + "." + photonTs.ToString(CultureInfo.InvariantCulture);
        }

        // -- the broadcast status producer's series state (report L13) ----------------------

        /// <summary>The watched fighters' ranked-series state for the
        /// broadcast status lease: "live" when an active series of theirs is in
        /// the cache (whatever its age: the conservative answer), "none" only
        /// when the last active-series read completed and parsed fully, is no
        /// older than `freshS`, and holds none of theirs; "unknown" otherwise
        /// (no fighters known, no read yet, a failed or partial read, or a
        /// stale one). Mode is a separate field.</summary>
        internal static string SeriesStatus(bool fightersKnown, bool matched, bool cachePresent, bool lastReadOk, double ageS, double freshS)
        {
            if (fightersKnown && matched) return "live";
            if (!fightersKnown || !cachePresent || !lastReadOk) return "unknown";
            if (ageS < 0 || ageS > freshS) return "unknown";
            return "none";
        }
    }
}
