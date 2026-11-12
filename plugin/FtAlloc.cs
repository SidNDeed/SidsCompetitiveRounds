#if SCR_FRAMETIME
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace CompetitiveRounds
{
    /// <summary>The allocation counter (B11 SHARED.md, "GC: the allocation counter"; ruling R6-A3.11.147 (3)(d)). Mono's
    /// collector, mono-2.0-bdwgc.dll, counts every allocated byte under its lock, and GC_get_total_bytes (RVA 0x4eb550 in
    /// the pinned binary) returns the sum of two 8-byte words, at RVA 0x76efd8 and RVA 0x76efe0. Init finds the loaded
    /// module, hashes its file and checks the function's 15 bytes in the loaded image; on any difference the counter is
    /// unavailable (Ok false), every read fails, and every a* and wa value prints NA. Safe calls only: kernel32 for the
    /// module, Marshal.ReadInt64 and Marshal.ReadByte for the words and the bytes.
    /// One read (Read) takes both words twice and stands when the two takes agree; otherwise it repeats, Tries times
    /// in all, and a read that never agreed counts in AbRetry and returns its last take. A read below the same
    /// thread's previous read counts in AbBack; Delta gives 0 for such a pair. Calibrate prints the K1 boot line.</summary>
    internal static class FtAlloc
    {
        internal const string ModuleName = "mono-2.0-bdwgc.dll";
        internal const string PinSha256 = "55dda361039e3af8238b9c57b7af4828401c27b25a0e51bf9eb6c60e99e14c91";
        internal const int RvaFn = 0x4eb550, RvaA = 0x76efd8, RvaB = 0x76efe0;
        internal const int Tries = 4;

        /// <summary>GC_get_total_bytes in the pinned binary: mov rax,[rip+0x283a81]; add rax,[rip+0x283a82]; ret, which
        /// read RVA 0x76efd8 and RVA 0x76efe0.</summary>
        internal static readonly byte[] FnBytes = { 0x48, 0x8b, 0x05, 0x81, 0x3a, 0x28, 0x00, 0x48, 0x03, 0x05, 0x82, 0x3a, 0x28, 0x00, 0xc3 };

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr GetModuleHandleW(string name);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern uint GetModuleFileNameW(IntPtr module, StringBuilder path, uint size);

        internal static bool Ok;
        internal static string Why = "not_init";
        internal static long AbBack, AbRetry;
        private static IntPtr _wa, _wb;
        [ThreadStatic] private static long _last;

        /// <summary>K1's mutant (k_mutant=k1): every read allocates MutantBytes, so an empty pair of reads moves the
        /// counter. Above the collector's small-object size, so the counter sees each allocation as it is made rather
        /// than when a thread's free list is refilled.</summary>
        internal static bool MutantK1;
        internal const int MutantBytes = 4096;
        private static object _box;

        /// <summary>FtClock.Install, once: the module, the file's sha256 against the pin, the function's bytes.</summary>
        internal static void Init()
        {
            Ok = false;
            try
            {
                IntPtr h = GetModuleHandleW(ModuleName);
                if (h == IntPtr.Zero) { Why = "no_module"; return; }
                var sb = new StringBuilder(1024);
                uint n = GetModuleFileNameW(h, sb, (uint)sb.Capacity);
                if (n == 0 || n >= sb.Capacity) { Why = "no_path"; return; }
                string sha;
                using (var alg = SHA256.Create())
                using (var f = File.OpenRead(sb.ToString(0, (int)n)))
                {
                    var d = alg.ComputeHash(f);
                    var hex = new StringBuilder(64);
                    foreach (byte b in d) hex.Append(b.ToString("x2"));
                    sha = hex.ToString();
                }
                if (sha != PinSha256) { Why = "sha"; return; }
                for (int i = 0; i < FnBytes.Length; i++)
                    if (Marshal.ReadByte(h, RvaFn + i) != FnBytes[i]) { Why = "code"; return; }
                _wa = new IntPtr(h.ToInt64() + RvaA);
                _wb = new IntPtr(h.ToInt64() + RvaB);
                Ok = true;
                Why = "ok";
            }
            catch (Exception ex) { Why = "failed:" + ex.GetType().Name; Ok = false; }
            finally { Plugin.Log.LogInfo("[FRAME-TIME] alloc_init why=" + Why); }
        }

        /// <summary>One read of the total on the calling thread. False when the counter is unavailable.</summary>
        internal static bool Read(out long total)
        {
            total = 0;
            if (!Ok) return false;
            if (MutantK1) _box = new byte[MutantBytes];
            long a = 0, b = 0;
            for (int i = 0; i < Tries; i++)
            {
                a = Marshal.ReadInt64(_wa);
                b = Marshal.ReadInt64(_wb);
                long a2 = Marshal.ReadInt64(_wa), b2 = Marshal.ReadInt64(_wb);
                if (a == a2 && b == b2)
                {
                    total = Back(a + b);
                    return true;
                }
                a = a2;
                b = b2;
            }
            Interlocked.Increment(ref AbRetry);
            total = Back(a + b);
            return true;
        }

        /// <summary>A total below the calling thread's previous total counts in AbBack.</summary>
        private static long Back(long t)
        {
            if (t < _last) Interlocked.Increment(ref AbBack);
            _last = t;
            return t;
        }

        /// <summary>The bytes between two reads of one thread: 0 when the later total is below the earlier.</summary>
        internal static long Delta(long a0, long a1)
        {
            return a1 > a0 ? a1 - a0 : 0;
        }

        internal const int PlantN = 21, EmptyN = 101, PlantBytes = 1 << 20;
        private static byte[] _plant;

        /// <summary>K1, the boot line `[FRAME-TIME] alloc pin=<ok|differs> planted=<median delta>/<bytes asked>
        /// empty=<median delta>`: PlantN byte arrays of PlantBytes, each allocated between two reads, and EmptyN pairs of
        /// reads with nothing between them (the medians are the middle values; both counts are odd). NA when the counter
        /// is unavailable.</summary>
        internal static void Calibrate()
        {
            string planted = "NA", empty = "NA";
            if (Ok)
            {
                var d = new long[PlantN];
                var e = new long[EmptyN];
                for (int i = 0; i < PlantN; i++)
                {
                    long a0, a1;
                    Read(out a0);
                    _plant = new byte[PlantBytes];
                    Read(out a1);
                    d[i] = Delta(a0, a1);
                }
                _plant = null;
                for (int i = 0; i < EmptyN; i++)
                {
                    long a0, a1;
                    Read(out a0);
                    Read(out a1);
                    e[i] = Delta(a0, a1);
                }
                Array.Sort(d);
                Array.Sort(e);
                planted = d[PlantN / 2].ToString();
                empty = e[EmptyN / 2].ToString();
            }
            Plugin.Log.LogInfo("[FRAME-TIME] alloc pin=" + (Ok ? "ok" : "differs") + " planted=" + planted + "/" + PlantBytes
                + " empty=" + empty);
        }
    }
}
#endif
