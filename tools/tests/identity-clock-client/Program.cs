// Identity-clock evidence, client half: the harness program. Drives the REAL
// plugin/IdentityClockCore.cs. Modes:
//   fixtures <server fixture dir> <key> <out dir>   records and envelopes of the server fixtures
//   replay <key> <out dir>                          synthetic games' records and envelopes
//   clock <out dir>                                 clock headers
//   units [group...]                                unit cases; "PASS g name" / "FAIL g name"
//   perf <managed> <core> <plugins> <patchers> <root> <game asm>   the survey's cost on this seat's real files
// Exit 0 only when everything the mode checks holds.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using CompetitiveRounds;
using C = CompetitiveRounds.SeatEvidenceCore;
using I = CompetitiveRounds.IdentityClockCore;

internal static class Program
{
    private static int _fails;
    private static HashSet<string> _groups;

    private static int Main(string[] a)
    {
        try
        {
            switch (a.Length > 0 ? a[0] : "")
            {
                case "fixtures": return Fixtures(a[1], a[2], a[3]);
                case "replay": return Replay(a[1], a[2]);
                case "clock": return Clock(a[1]);
                case "units": _groups = a.Length > 1 ? new HashSet<string>(a[1..]) : null; Units(); return _fails == 0 ? 0 : 1;
                case "perf": return Perf(a[1], a[2], a[3], a[4], a[5], a[6]);
            }
            Console.WriteLine("unknown mode");
            return 2;
        }
        catch (Exception ex)
        {
            Console.WriteLine("EXCEPTION " + ex);
            return 3;
        }
    }

    // -- JSON in (the server's fixture inputs) ---------------------------------------------

    private static object FromJson(JsonElement e)
    {
        switch (e.ValueKind)
        {
            case JsonValueKind.Object:
                var o = new C.JObj();
                foreach (var p in e.EnumerateObject()) o.Add(p.Name, FromJson(p.Value));
                return o;
            case JsonValueKind.Array:
                var l = new List<object>();
                foreach (var x in e.EnumerateArray()) l.Add(FromJson(x));
                return l;
            case JsonValueKind.Number: return e.GetInt64();
            case JsonValueKind.String: return e.GetString();
        }
        throw new Exception("unexpected JSON value " + e.ValueKind);
    }

    private static C.JObj Load(string path)
    {
        using (var d = JsonDocument.Parse(File.ReadAllText(path))) return (C.JObj)FromJson(d.RootElement);
    }

    private static string Hmac(string key, string text)
    {
        using (var h = new HMACSHA256(Encoding.UTF8.GetBytes(key))) return I.Hex(h.ComputeHash(Encoding.UTF8.GetBytes(text)));
    }

    // -- fixtures ---------------------------------------------------------------------------

    private static int Fixtures(string dir, string key, string outDir)
    {
        Directory.CreateDirectory(outDir);
        foreach (var name in new[] { "base", "over_cap" })
        {
            var input = Load(Path.Combine(dir, name, "input.json"));
            string text = I.Budget(input);
            File.WriteAllText(Path.Combine(outDir, name + ".record.txt"), text, new UTF8Encoding(false));
            var env = Load(Path.Combine(dir, name, "envelope.json"));
            string seat = (string)env.Get("seat_steam_id"), other = (string)env.Get("other_steam_id");
            string stable = (string)env.Get("stable_game_key"), attach = (string)env.Get("attach_key");
            string sig = Hmac(key, I.Canonical(seat, other, stable, attach, text));
            string mine = I.Envelope(seat, other, stable, attach, text, sig);
            File.WriteAllText(Path.Combine(outDir, name + ".envelope.json"), mine ?? "", new UTF8Encoding(false));
            Console.WriteLine("fixture " + name + " bytes " + text.Length + " sig " + sig.Substring(0, 12));
        }
        return 0;
    }

    private static int Clock(string outDir)
    {
        Directory.CreateDirectory(outDir);
        var rows = new List<object>
        {
            I.ClockHeader("0123456789ab", 5000000, 4000000, 123456) ?? "",
            I.ClockHeader("0123456789ab", 5000000, 4000000, int.MinValue) ?? "",
            I.ClockHeader("0123456789ab", 0, 0, int.MaxValue) ?? "",
            I.ClockHeader("0123456789ab", I.HEADER_MS_MAX, I.HEADER_MS_MAX, -1) ?? "",
            I.ClockHeader("0123456789AB", 1, 1, 1) ?? "",
            I.ClockHeader("0123456789ab", I.HEADER_MS_MAX + 1, 1, 1) ?? "",
            I.ClockHeader("0123456789ab", -1, 1, 1) ?? "",
            I.ClockHeader("0123", 1, 1, 1) ?? "",
        };
        File.WriteAllText(Path.Combine(outDir, "clock.json"), C.Json(rows), new UTF8Encoding(false));
        return 0;
    }

    // -- replay: records the client builds from synthetic games -----------------------------

    private static int Replay(string key, string outDir)
    {
        Directory.CreateDirectory(outDir);
        var cases = new List<KeyValuePair<string, C.JObj>>
        {
            new KeyValuePair<string, C.JObj>("game_full", SyntheticRecord(points: 9, survey: true, postboot: false, wide: false)),
            new KeyValuePair<string, C.JObj>("game_not_yet", SyntheticRecord(points: 3, survey: false, postboot: false, wide: false)),
            new KeyValuePair<string, C.JObj>("game_postboot", SyntheticRecord(points: 4, survey: true, postboot: true, wide: false)),
            new KeyValuePair<string, C.JObj>("game_wide", SyntheticRecord(points: 27, survey: true, postboot: true, wide: true)),
        };
        var full = new List<object>();
        foreach (var kv in cases)
        {
            string text = I.Budget(kv.Value);
            string seat = "1000000000000101", other = "1000000000000102", stable = "room_ic_" + kv.Key, attach = stable + "_r8";
            string sig = Hmac(key, I.Canonical(seat, other, stable, attach, text));
            string env = I.Envelope(seat, other, stable, attach, text, sig);
            File.WriteAllText(Path.Combine(outDir, kv.Key + ".envelope.json"), env ?? "", new UTF8Encoding(false));
            File.WriteAllText(Path.Combine(outDir, kv.Key + ".full.json"), C.Json(kv.Value), new UTF8Encoding(false));
            Console.WriteLine("replay " + kv.Key + " bytes " + text.Length);
        }
        return 0;
    }

    /// <summary>A whole game through the client's accountants: boot, three
    /// moments, a survey over a fake disk, census, points with a stream.</summary>
    private static C.JObj SyntheticRecord(int points, bool survey, bool postboot, bool wide)
    {
        var priv = new I.Privacy(new[] { "qxuser", "QXHOST7" });
        var proc = new I.ProcLedger("0123456789ab");
        proc.Boot(1200, I.PASS, null, priv);
        var runs = new I.GameRuns();
        var src = new I.KeySource(() => new List<string> { "com.competitiverounds.mod" });
        for (int m = 1; m <= 3; m++)
        {
            if (postboot && m == 2) src.PostBoot.Add("scr.ic.testguid");
            bool threw;
            var keys = src.Read(out threw);
            var others = new List<string>();
            var r = new I.Run { Moment = m, TMs = 90000 + m * 1000, Outcome = I.Outcome(keys, "com.competitiverounds.mod", threw, others), NAsm = 40 };
            proc.Count(r, others, priv);
            runs.Add(r);
        }
        var asms = new List<I.AsmIn>();
        int nAsm = wide ? 260 : 40;
        for (int i = 0; i < nAsm; i++) asms.Add(new I.AsmIn { Name = (wide ? new string('N', 60) : "Asm") + i, Version = "1.2.3.4", Origin = i % 7, Dynamic = i % 9 == 0 });
        List<object> asm, asmN; HashSet<string> names;
        I.Census(asms, new HashSet<string> { "Asm1" }, priv, out asm, out asmN, out names);
        var patched = new List<I.PatchedIn>();
        for (int i = 0; i < (wide ? 70 : 6); i++)
        {
            var p = new I.PatchedIn { MethodId = i };
            p.Patches.Add(new KeyValuePair<int, string>(0, "com.competitiverounds.mod"));
            if (postboot && i == 2) p.Patches.Add(new KeyValuePair<int, string>(1, "scr.ic.postboot"));
            patched.Add(p);
        }
        List<object> hp, hpAll; long nf;
        I.Patches(patched, "com.competitiverounds.mod", priv, out hp, out hpAll, out nf);
        var files = new List<I.FileTarget>();
        for (int i = 0; i < 17; i++) files.Add(new I.FileTarget { Id = i, Path = "G/f" + i + ".dll" });
        I.SurveyResult res = null;
        if (survey)
        {
            var fs = new FakeFs();
            for (int i = 0; i < 16; i++) fs.File("G/f" + i + ".dll", 70000 + i);
            fs.Dir("P", wide ? 40 : 3, "P/mod", 100);
            fs.Dir("Q", 0, null, 0);
            fs.File("G/game.dll", 10);
            var s = new I.Survey(fs, files, "P", "Q", "G/game.dll");
            s.Request(1);
            for (int k = 0; k < 100000 && s.ResultFor(1) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
            res = s.ResultFor(1);
        }
        List<object> gdig; C.JObj ldir; int ds; string md;
        I.SurveyFields(res, files, priv, out gdig, out ldir, out ds, out md);
        var book = new I.ClockBook(2000000000);
        Stream(book, points);
        var rpc = new I.RpcNames();
        for (int i = 0; i < (wide ? 150 : 5); i++) rpc.Add("RPCA_" + (wide ? new string('R', 50) : "") + i);
        var cost = new List<I.Cost>();
        for (int i = 0; i < 10; i++) { var c = new I.Cost(i); c.Add(5); cost.Add(c); }
        return I.Record(2000000000, true, cost, proc, runs, asmN, asm, gdig, I.L(0L, "c" + new string('c', 31), (long)ds, md), ldir,
                        hpAll, hp, rpc.Entries(priv), rpc.Overflow, I.L(30L, 30L, 30L, 30L, 0L), book);
    }

    /// <summary>A stream of the other seat over `points` points: 33 ms
    /// stamps, an approach to the target, a held input against a wall, then
    /// movement, aim changes and a shot.</summary>
    private static void Stream(I.ClockBook b, int points)
    {
        int stamp = 2000000000 + 100;
        long sw = 1000;
        for (int pt = 0; pt < points; pt++)
        {
            int ps = stamp;
            b.LastPubFps = pt % 2 == 0 ? 60 : -1;
            b.PointStart(true, ps, ps + 40, sw);
            b.Target(1000, -500);
            b.CurS.MoveStart(sw + 20, 400);
            for (int f = 0; f < 21; f++) b.CurS.MoveFrame(16000);
            b.CurS.Release(sw + 900);
            for (int k = 0; k < 60; k++)
            {
                stamp += 33; sw += 33;
                var p = new I.Pkg { Stamp = stamp, ArrServer = stamp + 45, ArrSw = sw, TdMs = 33 };
                if (k < 20) { p.Px = 1000 + (20 - k) * 30; p.Py = -500; p.Vx = -900; }
                else if (k < 35) { p.Px = 1000; p.Py = -500; p.Dx = 1000000; }
                else { p.Px = 1000 + (k - 35) * 30; p.Py = -500; p.Vx = 900; p.Dx = 1000000; p.Ax = k % 2 == 0 ? 1000000 : 0; p.Ay = k % 2 == 0 ? 0 : 1000000; }
                b.Package(p);
                if (k == 40) b.OtherShot(stamp, stamp + 45);
                if (k == 25) b.CurS.OwnInput(sw);
                b.CurS.GameTime(33.0);
            }
            sw += 500; stamp += 500;
        }
        b.ClosePoint(sw);
    }

    // -- the fake disk ----------------------------------------------------------------------

    private sealed class FakeFs : I.IFs
    {
        internal readonly Dictionary<string, List<I.FsEntry>> Dirs = new Dictionary<string, List<I.FsEntry>>();
        internal readonly Dictionary<string, byte[]> Files = new Dictionary<string, byte[]>();
        internal readonly HashSet<string> ListFail = new HashSet<string>(), OpenFail = new HashSet<string>();
        internal Func<bool> Combat = () => false;
        internal long OpsInCombat, Ops, Reads, ReadsInCombat;

        /// <summary>Runs after every operation that reached this fake disk
        /// (the scenario's world may turn live in between).</summary>
        internal Action OnOp;

        private void W() { Ops++; if (Combat()) OpsInCombat++; if (OnOp != null) OnOp(); }
        private void R() { Reads++; if (Combat()) ReadsInCombat++; if (OnOp != null) OnOp(); }

        /// <summary>A stream of the fake disk whose every Read, Seek and
        /// Length is counted (and counted in combat while the scenario's flag
        /// is up): the witness of stream work the code under test does not see.</summary>
        private sealed class CountStream : Stream
        {
            private readonly MemoryStream _m; private readonly FakeFs _f;
            internal CountStream(byte[] b, FakeFs f) { _m = new MemoryStream(b, false); _f = f; }
            public override bool CanRead { get { return true; } }
            public override bool CanSeek { get { return true; } }
            public override bool CanWrite { get { return false; } }
            public override long Length { get { _f.R(); return _m.Length; } }
            public override long Position { get { return _m.Position; } set { _f.R(); _m.Position = value; } }
            public override int Read(byte[] buffer, int offset, int count) { _f.R(); return _m.Read(buffer, offset, count); }
            public override long Seek(long offset, SeekOrigin origin) { _f.R(); return _m.Seek(offset, origin); }
            public override void Flush() { }
            public override void SetLength(long value) { throw new NotSupportedException(); }
            public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
        }

        internal void File(string path, int size)
        {
            var b = new byte[size];
            for (int i = 0; i < size; i++) b[i] = (byte)(i * 31 + path.Length);
            Files[path] = b;
        }

        internal void Dir(string path, int dlls, string sub, int subDlls)
        {
            var l = new List<I.FsEntry>();
            for (int i = 0; i < dlls; i++) { string f = path + "/a" + i + ".dll"; File(f, 100 + i); l.Add(new I.FsEntry { Path = f }); }
            if (sub != null)
            {
                l.Add(new I.FsEntry { Path = sub, IsDir = true });
                var s = new List<I.FsEntry>();
                for (int i = 0; i < subDlls; i++) { string f = sub + "/b" + i + ".dll"; File(f, 50); s.Add(new I.FsEntry { Path = f }); }
                Dirs[sub] = s;
            }
            Dirs[path] = l;
        }

        public int List(string dir, int max, List<I.FsEntry> into)
        {
            W();
            if (ListFail.Contains(dir)) return 2;
            List<I.FsEntry> l;
            if (!Dirs.TryGetValue(dir, out l)) return 1;
            foreach (var e in l) { if (into.Count > max) break; into.Add(e); }
            return 0;
        }

        public Stream Open(string path, out bool missing)
        {
            W();
            missing = !Files.ContainsKey(path);
            if (missing || OpenFail.Contains(path)) return null;
            return new CountStream(Files[path], this);
        }

        public string AsmName(string path) { W(); return Path.GetFileNameWithoutExtension(path); }
    }

    // -- units ------------------------------------------------------------------------------

    private static void Check(string group, string name, bool ok, string detail = "")
    {
        if (_groups != null && !_groups.Contains(group)) return;
        Console.WriteLine((ok ? "PASS " : "FAIL ") + group + " " + name + (ok ? "" : " " + detail));
        if (!ok) _fails++;
    }

    private static bool On(string g) { return _groups == null || _groups.Contains(g); }

    private static void Units()
    {
        if (On("privacy")) Privacy();
        if (On("sweep")) Sweep();
        if (On("boot")) Boot();
        if (On("outcome")) OutcomeCases();
        if (On("postboot")) PostBootCases();
        if (On("gate")) Gate();
        if (On("reparse")) Reparse();
        if (On("trunc")) Trunc();
        if (On("flight")) Flight();
        if (On("stale")) Stale();
        if (On("pergame")) PerGame();
        if (On("l4")) L4();
        if (On("mvid")) MvidCases();
        if (On("move")) Move();
        if (On("fps")) Fps();
        if (On("stream")) StreamCases();
        if (On("series")) Series();
        if (On("budget")) BudgetCases();
        if (On("combat3")) Combat3();
        if (On("late")) Late();
        if (On("adapter")) Adapter();
        if (On("flush")) Flush();
        if (On("seriesshape")) SeriesShape();
    }

    private static void Privacy()
    {
        var p = new I.Privacy(new[] { "QXHOST7", "qxuser", "ab" });
        Check("privacy", "machine_token_exact_hashed", p.Name("QXHOST7").StartsWith("h:"));
        Check("privacy", "machine_token_case_hashed", p.Name("qxhost7").StartsWith("h:"));
        Check("privacy", "account_inside_name_hashed", p.Name("Lib.qxuser.Ext").StartsWith("h:"));
        Check("privacy", "short_needle_whole_only", p.Name("ab").StartsWith("h:") && p.Name("Cabbage") == "Cabbage");
        Check("privacy", "public_name_kept", p.Name("CompetitiveRounds") == "CompetitiveRounds");
        Check("privacy", "path_hashed", p.Name("C:\\x\\y.dll").StartsWith("h:"));
        Check("privacy", "too_long_hashed_not_cut", p.Name(new string('a', 65)).StartsWith("h:") && p.Name(new string('a', 64)).Length == 64);
        Check("privacy", "hash_form", p.Name("QXHOST7").Length == 14);
    }

    /// <summary>L5 sweep: needles planted in EVERY string-bearing input of a
    /// whole record; the serialized record holds none of them.</summary>
    private static void Sweep()
    {
        var priv = new I.Privacy(new[] { "qxuser", "QXHOST7" });
        var proc = new I.ProcLedger("0123456789ab");
        proc.Boot(10, I.FINDING, new List<string> { "qxuser.plugin", "ok.plugin" }, priv);
        var runs = new I.GameRuns();
        var r = new I.Run { Moment = 1, TMs = 1, Outcome = I.FINDING };
        proc.Count(r, new List<string> { "QXHOST7" }, priv); runs.Add(r);
        List<object> asm, asmN; HashSet<string> names;
        I.Census(new List<I.AsmIn> { new I.AsmIn { Name = "QXHOST7", Version = "1.0" }, new I.AsmIn { Name = "qxuser-lib", Version = "qxuser" } }, null, priv, out asm, out asmN, out names);
        var pm = new I.PatchedIn { MethodId = 1 };
        pm.Patches.Add(new KeyValuePair<int, string>(0, "owner.qxuser"));
        pm.Patches.Add(new KeyValuePair<int, string>(1, "QXHOST7"));
        List<object> hp, hpAll; long nf;
        I.Patches(new List<I.PatchedIn> { pm }, "self", priv, out hp, out hpAll, out nf);
        var rpc = new I.RpcNames(); rpc.Add("RPC_qxuser"); rpc.Add("QXHOST7");
        var fs = new FakeFs();
        fs.Dirs["P"] = new List<I.FsEntry> { new I.FsEntry { Path = "P/qxuser.dll" }, new I.FsEntry { Path = "P/QXHOST7.dll" } };
        fs.File("P/qxuser.dll", 10); fs.File("P/QXHOST7.dll", 10);
        var files = new List<I.FileTarget>();
        var s = new I.Survey(fs, files, "P", "Q", "");
        s.Request(1);
        for (int k = 0; k < 1000 && s.ResultFor(1) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        List<object> gdig; C.JObj ldir; int ds; string md;
        I.SurveyFields(s.ResultFor(1), files, priv, out gdig, out ldir, out ds, out md);
        var rec = I.Record(1, true, new List<I.Cost>(), proc, runs, asmN, asm, gdig, I.L(0L, "", (long)ds, md), ldir, hpAll, hp,
                           rpc.Entries(priv), 0, I.L(30L, 30L, 30L, 30L, 0L), new I.ClockBook(1));
        string text = C.Json(rec).ToLowerInvariant();
        Check("sweep", "no_account_needle", text.IndexOf("qxuser", StringComparison.Ordinal) < 0, text.Length > 400 ? text.Substring(0, 400) : text);
        Check("sweep", "no_machine_needle", text.IndexOf("qxhost7", StringComparison.Ordinal) < 0);
        Check("sweep", "public_kept", text.Contains("ok.plugin"));
    }

    private static void Boot()
    {
        var priv = new I.Privacy(null);
        var proc = new I.ProcLedger("0123456789ab");
        proc.Boot(3100, I.PASS, null, priv);
        proc.Boot(65000, I.PASS, null, priv);
        List<object> chk, plug;
        I.ChkAndPlug(proc, new I.GameRuns(), out chk, out plug);
        var e = (List<object>)proc.Entry();
        Check("boot", "two_occurrences_counted", (long)e[1] == 2 && (long)e[2] == 2, C.Json(e));
        Check("boot", "ordinals_distinct", chk.Count == 2 && (long)((List<object>)chk[0])[1] == 0 && (long)((List<object>)chk[1])[1] == 1, C.Json(chk));
        Check("boot", "process_times_kept", chk.Count == 2 && (long)((List<object>)chk[0])[2] == 3100 && (long)((List<object>)chk[1])[2] == 65000);
        for (int i = 0; i < 10; i++) proc.Boot(70000 + i, I.PASS, null, priv);
        I.ChkAndPlug(proc, new I.GameRuns(), out chk, out plug);
        Check("boot", "kept_bounded_ordinal_below_boots", chk.Count == I.ProcLedger.BOOT_KEEP && (long)((List<object>)chk[chk.Count - 1])[1] < proc.Boots);
        // L1: the first BOOT_KEEP occurrences stay in full (an earlier one is
        // never replaced by a later one); the rest are stated by boots
        bool firstKept = true;
        for (int i = 0; i < chk.Count; i++) firstKept &= (long)((List<object>)chk[i])[1] == i;
        Check("boot", "earliest_kept_never_replaced", firstKept && (long)((List<object>)chk[0])[2] == 3100 && (long)((List<object>)chk[1])[2] == 65000, C.Json(chk));
        e = (List<object>)proc.Entry();
        Check("boot", "omitted_stated_by_boots", (long)e[1] == 12 && (long)e[1] - chk.Count == 12 - I.ProcLedger.BOOT_KEEP, C.Json(e));
    }

    private static void OutcomeCases()
    {
        var o = new List<string>();
        Check("outcome", "threw_not_run", I.Outcome(new List<string> { "self", "x" }, "self", true, o) == I.NOT_RUN && o.Count == 0);
        Check("outcome", "null_not_run", I.Outcome(null, "self", false, new List<string>()) == I.NOT_RUN);
        Check("outcome", "self_pass", I.Outcome(new List<string> { "self" }, "self", false, new List<string>()) == I.PASS);
        o.Clear();
        Check("outcome", "other_finding", I.Outcome(new List<string> { "self", "x" }, "self", false, o) == I.FINDING && o.Count == 1);
    }

    /// <summary>L6: the key source is read at every run; a key added after a
    /// clean boot reaches the later moments, and a foreign Harmony owner
    /// added after boot reaches hp.</summary>
    private static void PostBootCases()
    {
        var live = new List<string> { "self" };
        // A fresh list per read, as the loader's key set is in game: a source
        // that keeps its first answer must miss the late key.
        var src = new I.KeySource(() => new List<string>(live));
        bool threw;
        var o0 = new List<string>();
        int boot = I.Outcome(src.Read(out threw), "self", threw, o0);
        live.Add("late.loader.key");                 // the loader's live set changes after boot
        src.PostBoot.Add("scr.ic.testguid");         // the after-boot fixture adds its key
        var o2 = new List<string>();
        int pick = I.Outcome(src.Read(out threw), "self", threw, o2);
        Check("postboot", "boot_clean", boot == I.PASS);
        Check("postboot", "later_moment_finding", pick == I.FINDING && o2.Contains("scr.ic.testguid") && o2.Contains("late.loader.key"), string.Join(",", o2));
        var throwing = new I.KeySource(() => { throw new InvalidOperationException(); });
        Check("postboot", "throwing_source_not_run", I.Outcome(throwing.Read(out threw), "self", threw, new List<string>()) == I.NOT_RUN);
        var pm = new I.PatchedIn { MethodId = 17 };
        pm.Patches.Add(new KeyValuePair<int, string>(0, "self"));
        pm.Patches.Add(new KeyValuePair<int, string>(1, "scr.ic.postboot"));
        List<object> hp, hpAll; long nf;
        I.Patches(new List<I.PatchedIn> { pm }, "self", new I.Privacy(null), out hp, out hpAll, out nf);
        var e = (List<object>)hp[0];
        Check("postboot", "foreign_owner_in_hp", nf == 1 && (long)e[2] == 1 && (long)e[1] == 0 && ((List<object>)e[5]).Contains("scr.ic.postboot"), C.Json(hp));
        Check("postboot", "hp_all_counts_both", (long)((List<object>)hpAll)[1] == 2);
    }

    private static I.Survey BigSurvey(FakeFs fs, out List<I.FileTarget> files)
    {
        files = new List<I.FileTarget>();
        for (int i = 0; i < 17; i++) { string f = "G/f" + i + ".dll"; fs.File(f, 400000); files.Add(new I.FileTarget { Id = i, Path = f }); }
        fs.Dir("P", 40, "P/sub", 30);
        fs.Dir("Q", 2, null, 0);
        fs.File("G/game.dll", 10);
        return new I.Survey(fs, files, "P", "Q", "G/game.dll");
    }

    /// <summary>M1 gate: frames alternate pick (no combat) and combat; the
    /// fake disk counts every call made while the scenario's combat flag is
    /// up (a witness the code under test does not see). It must stay 0, the
    /// survey must still finish, and no step may exceed its unit bound.</summary>
    private static void Gate()
    {
        var fs = new FakeFs();
        bool combat = false;
        fs.Combat = () => combat;
        List<I.FileTarget> files;
        var s = BigSurvey(fs, out files);
        s.Request(1);
        int maxUnits = 0, frames = 0;
        for (; frames < 200000 && s.ResultFor(1) == null; frames++)
        {
            combat = (frames / 7) % 3 != 0;             // two thirds of the frames are combat
            int n = s.Step(combat ? C.CombatRead.LIVE : C.CombatRead.NOT_LIVE, 2000, () => 0);
            if (n > maxUnits) maxUnits = n;
        }
        Check("gate", "zero_disk_calls_in_combat", fs.OpsInCombat == 0, "ops in combat " + fs.OpsInCombat);
        Check("gate", "finishes_outside_combat", s.ResultFor(1) != null && fs.Ops > 0);
        Check("gate", "step_units_bounded", maxUnits <= I.STEP_UNITS_MAX, "max " + maxUnits);
        Check("gate", "combat_steps_skipped", s.CombatSkips > 0);
    }

    private static List<object> Part(C.JObj ldir, string p) { return (List<object>)ldir.Get(p); }

    private static C.JObj Run(FakeFs fs, string plugins, string patchers, out I.SurveyResult r)
    {
        var files = new List<I.FileTarget>();
        var s = new I.Survey(fs, files, plugins, patchers, "");
        s.Request(1);
        for (int k = 0; k < 200000 && s.ResultFor(1) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        r = s.ResultFor(1);
        List<object> gdig; C.JObj ldir; int ds; string md;
        I.SurveyFields(r, files, new I.Privacy(null), out gdig, out ldir, out ds, out md);
        return ldir;
    }

    private static void Reparse()
    {
        var fs = new FakeFs();
        fs.Dir("P", 2, null, 0);
        fs.Dirs["P"].Add(new I.FsEntry { Path = "P/junction", IsDir = true, IsReparse = true });
        fs.Dirs["P"].Add(new I.FsEntry { Path = "P/link.dll", IsReparse = true });
        var many = new List<I.FsEntry>();
        for (int i = 0; i < 50; i++) { fs.File("P/junction/x" + i + ".dll", 10); many.Add(new I.FsEntry { Path = "P/junction/x" + i + ".dll" }); }
        fs.Dirs["P/junction"] = many;
        fs.File("P/link.dll", 10);
        I.SurveyResult r;
        var ldir = Run(fs, "P", "Q", out r);
        var p = Part(ldir, "plugins");
        Check("reparse", "junction_not_followed", (long)p[1] == 2 && ((List<object>)p[3]).Count == 2, C.Json(p));
        Check("reparse", "not_truncated", (long)p[2] == 0);
    }

    private static void Trunc()
    {
        var fs = new FakeFs();
        fs.Dir("P", 600, null, 0);
        I.SurveyResult r;
        var ldir = Run(fs, "P", "Q", out r);
        var p = Part(ldir, "plugins");
        Check("trunc", "files_capped_and_flagged", (long)p[0] == I.OK && (long)p[1] == I.FILES_MAX && (long)p[2] == 1, C.Json(I.L(p[0], p[1], p[2])));
        Check("trunc", "list_bounded", ((List<object>)p[3]).Count <= I.LDIR_PLUGINS_MAX);
        // deep tree: depth bound
        var fs2 = new FakeFs();
        string d = "D";
        for (int i = 0; i < 10; i++) { string n = d + "/s"; fs2.Dirs[d] = new List<I.FsEntry> { new I.FsEntry { Path = n, IsDir = true } }; d = n; }
        fs2.Dirs[d] = new List<I.FsEntry>();
        var ldir2 = Run(fs2, "D", "Q", out r);
        Check("trunc", "depth_flagged", (long)Part(ldir2, "plugins")[2] == 1);
        // more than plugins cap but under FILES_MAX: still flagged (not all hashed)
        var fs3 = new FakeFs();
        fs3.Dir("P", 40, null, 0);
        var ldir3 = Run(fs3, "P", "Q", out r);
        Check("trunc", "unhashed_files_flagged", (long)Part(ldir3, "plugins")[1] == 40 && (long)Part(ldir3, "plugins")[2] == 1);
    }

    private static void Flight()
    {
        var fs = new FakeFs();
        List<I.FileTarget> files;
        var s = BigSurvey(fs, out files);
        s.Request(1);
        for (int k = 0; k < 5; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        s.Request(1);
        Check("flight", "same_gen_continues", s.Abandoned == 0 && s.RunningGen == 1);
        s.Request(2);
        Check("flight", "older_abandoned_single_job", s.Abandoned == 1 && s.RunningGen == 2);
        for (int k = 0; k < 200000 && s.ResultFor(2) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        Check("flight", "only_newest_published", s.ResultFor(2) != null && s.ResultFor(1) == null && !s.Running);
    }

    private static void Stale()
    {
        var fs = new FakeFs();
        List<I.FileTarget> files;
        var s = BigSurvey(fs, out files);
        s.Request(2);
        for (int k = 0; k < 200000 && s.ResultFor(2) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        var late = new I.SurveyResult { Gen = 1 };
        bool took = s.TryPublish(late);
        Check("stale", "late_older_refused", !took && s.StaleRefused == 1 && s.ResultFor(2) != null && s.ResultFor(1) == null);
    }

    /// <summary>L3: a same-size, same-time content change between two games
    /// yields the new digest (every generation reads the bytes).</summary>
    private static void PerGame()
    {
        var fs = new FakeFs();
        fs.File("G/a.dll", 100000);
        var files = new List<I.FileTarget> { new I.FileTarget { Id = 0, Path = "G/a.dll" } };
        var s = new I.Survey(fs, files, "", "", "");
        s.Request(1);
        for (int k = 0; k < 100000 && s.ResultFor(1) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        string d1 = (string)((List<object>)s.ResultFor(1).Gdig[0])[1];
        var b = fs.Files["G/a.dll"]; b[500] ^= 0x5A;   // same length; the fake disk has no times at all
        s.Request(2);
        for (int k = 0; k < 100000 && s.ResultFor(2) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        var r2 = s.ResultFor(2);
        string d2 = r2 != null ? (string)((List<object>)r2.Gdig[0])[1] : "";
        string want; using (var h = SHA256.Create()) want = I.Hex(h.ComputeHash(b));
        Check("pergame", "changed_content_new_digest", d2 == want && d1 != d2, d1 + " " + d2);
    }

    /// <summary>L4: no survey and incomplete surveys are never empty clean ones.</summary>
    private static void L4()
    {
        var files = new List<I.FileTarget> { new I.FileTarget { Id = 0, Path = "G/a.dll" }, new I.FileTarget { Id = 1, Path = "G/b.dll" } };
        List<object> gdig; C.JObj ldir; int ds; string md;
        I.SurveyFields(null, files, new I.Privacy(null), out gdig, out ldir, out ds, out md);
        bool allNotYet = gdig.Count == 2;
        foreach (List<object> e in gdig) allNotYet &= (long)e[2] == I.NOT_YET && (string)e[1] == "";
        Check("l4", "no_result_not_yet", allNotYet && (long)Part(ldir, "plugins")[0] == I.NOT_YET && (long)Part(ldir, "patchers")[0] == I.NOT_YET && ds == I.NOT_YET && md == "", C.Json(ldir));
        var fs = new FakeFs();
        fs.ListFail.Add("P");
        I.SurveyResult r;
        var l2 = Run(fs, "P", "Q", out r);
        var p = Part(l2, "plugins"); var q = Part(l2, "patchers");
        Check("l4", "unreadable_root_read_failed", (long)p[0] == I.READ_FAILED && (long)p[1] == 0 && ((List<object>)p[3]).Count == 0, C.Json(p));
        Check("l4", "missing_root_no_file", (long)q[0] == I.NO_FILE && (long)q[1] == 0);
        var fs2 = new FakeFs();
        fs2.File("G/a.dll", 10);
        fs2.OpenFail.Add("G/a.dll");
        var s = new I.Survey(fs2, files, "", "", "G/game.dll");
        s.Request(1);
        for (int k = 0; k < 1000 && s.ResultFor(1) == null; k++) s.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        I.SurveyFields(s.ResultFor(1), files, new I.Privacy(null), out gdig, out ldir, out ds, out md);
        Check("l4", "open_failure_read_failed", (long)((List<object>)gdig[0])[2] == I.READ_FAILED && (long)((List<object>)gdig[1])[2] == I.NO_FILE, C.Json(gdig));
        Check("l4", "aload_missing_no_file", ds == I.NO_FILE && md == "", ds.ToString());
        // an aload file that exists but cannot be opened is read_failed, never no_file
        var fs3 = new FakeFs();
        fs3.File("G/game.dll", 10); fs3.OpenFail.Add("G/game.dll");
        var s3 = new I.Survey(fs3, new List<I.FileTarget>(), "", "", "G/game.dll");
        s3.Request(1);
        for (int k = 0; k < 1000 && s3.ResultFor(1) == null; k++) s3.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        Check("l4", "aload_unopenable_read_failed", s3.ResultFor(1) != null && s3.ResultFor(1).AloadDiskState == I.READ_FAILED);
        // a game assembly that is not a PE image is read_failed
        var fs4 = new FakeFs();
        fs4.File("G/game.dll", 300);
        var s4 = new I.Survey(fs4, new List<I.FileTarget>(), "", "", "G/game.dll");
        s4.Request(1);
        for (int k = 0; k < 1000 && s4.ResultFor(1) == null; k++) s4.Step(C.CombatRead.NOT_LIVE,long.MaxValue, () => 0);
        Check("l4", "aload_not_pe_read_failed", s4.ResultFor(1) != null && s4.ResultFor(1).AloadDiskState == I.READ_FAILED);
    }

    private static void MvidCases()
    {
        var paths = new List<string> { typeof(Program).Assembly.Location, typeof(object).Assembly.Location, typeof(JsonDocument).Assembly.Location };
        string game = Environment.GetEnvironmentVariable("IC_GAME_ASM");
        if (!string.IsNullOrEmpty(game) && File.Exists(game)) paths.Add(game);
        int n = 0;
        foreach (var p in paths)
        {
            string want;
            using (var fs = File.OpenRead(p))
            using (var pe = new PEReader(fs))
            {
                var md = pe.GetMetadataReader();
                want = md.GetGuid(md.GetModuleDefinition().Mvid).ToString("N");
            }
            string got;
            using (var fs = File.OpenRead(p)) got = I.Mvid.FromPe(fs);
            Check("mvid", "equals_metadata_reader_" + (n++), got == want, Path.GetFileName(p) + " " + got + " " + want);
        }
        using (var ms = new MemoryStream(new byte[300])) Check("mvid", "not_pe_null", I.Mvid.FromPe(ms) == null);
    }

    /// <summary>L7: input held into a wall is not movement.</summary>
    private static void Move()
    {
        var b = new I.ClockBook(0);
        b.PointStart(true, 1000, 1040, 0);
        b.Target(0, 0);
        int st = 1000;
        for (int k = 0; k < 5; k++) { st += 33; b.Package(new I.Pkg { Stamp = st, ArrServer = st + 40, Px = 0, Py = 0, TdMs = 33 }); }
        int heldFrom = st + 33;
        for (int k = 0; k < 15; k++) { st += 33; b.Package(new I.Pkg { Stamp = st, ArrServer = st + 40, Px = 2, Py = 0, Dx = 1000000, TdMs = 33 }); }
        int movedAt = st + 33;
        for (int k = 0; k < 5; k++) { st += 33; b.Package(new I.Pkg { Stamp = st, ArrServer = st + 40, Px = 100 * (k + 1), Py = 0, Vx = 500, Dx = 1000000, TdMs = 33 }); }
        var o = b.PtO[0];
        Check("move", "input_first_at_hold", o.InFirst == heldFrom - 1000, o.InFirst.ToString());
        Check("move", "move_first_at_motion", o.MoveFirst == movedAt - 1000, o.MoveFirst + " want " + (movedAt - 1000));
        Check("move", "distinct", o.MoveFirst > o.InFirst);
        var e = o.Entry();
        Check("move", "wire_positions", (long)e[11] == o.InFirst && (long)e[13] == o.MoveFirst && (long)e[14] == o.MoveFirstArr);
    }

    /// <summary>L8: the frame rate is the published one or unknown.</summary>
    private static void Fps()
    {
        Check("fps", "unpublished_unknown", I.PubFps(false, 60) == -1);
        Check("fps", "published_nonpositive_zero", I.PubFps(true, 0) == 0 && I.PubFps(true, -5) == 0);
        Check("fps", "published_value", I.PubFps(true, 144) == 144 && I.PubFps(true, 5000) == I.FPS_MAX);
        var b = new I.ClockBook(0);
        int st = 100;
        b.PointStart(true, st, st, 0);
        for (int k = 0; k < 10; k++) { st += 33; b.Package(new I.Pkg { Stamp = st, ArrServer = st, TdMs = 33 }); }
        b.PointStart(true, st + 10, st + 10, 400);
        Check("fps", "no_serialization_fallback", b.PtO[0].PubFps == -1 && b.PtO[1].PubFps == -1, b.PtO[1].PubFps.ToString());
        b.LastPubFps = 75;
        b.PointStart(true, st + 20, st + 20, 800);
        Check("fps", "published_carried", b.PtO[2].PubFps == 75);
    }

    private static void StreamCases()
    {
        var b = new I.ClockBook(0);
        int st = 0; long sw = 0; double swD = 0;
        b.PointStart(true, 0, 0, 0);
        for (int k = 0; k < 600; k++)
        {
            // the receiver's clock runs 0.1 % faster than the stated intervals
            st += 33; swD += 33 * 1.001; sw = (long)Math.Round(swD);
            b.Package(new I.Pkg { Stamp = st, ArrServer = st + 30, ArrSw = sw, TdMs = 33, Vx = 100 });
        }
        b.FlushBucket();
        var first = (List<object>)b.CadB[0];
        Check("stream", "cad_medians", (long)first[2] == 33 && (long)first[3] == 33, C.Json(first));
        bool ordered = true;
        for (int i = 1; i < b.CadB.Count; i++) ordered &= (long)((List<object>)b.CadB[i])[0] > (long)((List<object>)b.CadB[i - 1])[0];
        Check("stream", "cad_buckets_increasing", ordered && b.CadB.Count >= 2);
        var t = b.Tdg();
        long sum = 0; foreach (long x in (List<object>)t[2]) sum += x;
        Check("stream", "tdg_sum_is_n", sum == (long)t[0] && (long)t[1] <= (long)t[0] && (long)t[0] == 599);
        var g = b.Gclk();
        long cppm = (long)g[0];
        Check("stream", "gclk_rate_sign_and_size", cppm < -90000 && cppm > -110000 && (long)g[1] == 599, C.Json(g));
        Check("stream", "median_lower", I.ClockBook.Median(new[] { 0, 1, 1, 0, 1 }, 3) == 2);
    }

    private static void Series()
    {
        Check("series", "match_live", I.SeriesStatus(true, true, true, true, 5, 60) == "live");
        Check("series", "fresh_negative_none", I.SeriesStatus(true, false, true, true, 5, 60) == "none");
        Check("series", "failed_read_unknown", I.SeriesStatus(true, false, true, false, 5, 60) == "unknown");
        Check("series", "no_cache_unknown", I.SeriesStatus(true, false, false, true, 5, 60) == "unknown");
        Check("series", "stale_unknown", I.SeriesStatus(true, false, true, true, 61, 60) == "unknown");
        Check("series", "no_fighters_unknown", I.SeriesStatus(false, false, true, true, 5, 60) == "unknown");
        Check("series", "match_in_stale_cache_live", I.SeriesStatus(true, true, true, false, 500, 60) == "live");
    }

    private static void BudgetCases()
    {
        var rec = SyntheticRecord(points: 27, survey: true, postboot: true, wide: true);
        string text = I.Budget(rec);
        Check("budget", "within_bound", text.Length <= I.RECORD_MAX_BYTES, text.Length.ToString());
        Check("budget", "keys_in_order", text.StartsWith("{\"schema\":1,\"consts\":1,") && text.IndexOf("\"omit\":{\"asm\":", StringComparison.Ordinal) > 0);
    }

    /// <summary>M1, three states: a throwing game-state read, a throwing
    /// diagnostic read, and both, each make the frame UNKNOWN; in every case
    /// the survey does zero steps and touches no disk, and a disk call made
    /// while the state is unknown is COUNTED by the witness (never silently 0).</summary>
    private static void Combat3()
    {
        Func<bool> thr = () => { throw new InvalidOperationException(); };
        Func<bool> no = () => false, yes = () => true;
        Check("combat3", "both_not_live", C.CombatRead.Of(no, no) == C.CombatRead.NOT_LIVE);
        Check("combat3", "game_live", C.CombatRead.Of(yes, no) == C.CombatRead.LIVE && C.CombatRead.Of(yes, thr) == C.CombatRead.LIVE);
        Check("combat3", "diag_live", C.CombatRead.Of(no, yes) == C.CombatRead.LIVE && C.CombatRead.Of(thr, yes) == C.CombatRead.LIVE);
        Check("combat3", "unknown_counts_as_live", C.CombatRead.Live(C.CombatRead.UNKNOWN) && C.CombatRead.Live(C.CombatRead.LIVE) && !C.CombatRead.Live(C.CombatRead.NOT_LIVE));
        var cases = new[] { new[] { thr, no }, new[] { no, thr }, new[] { thr, thr } };
        string[] names = { "game_read_throws", "diag_read_throws", "both_throw" };
        for (int c = 0; c < cases.Length; c++)
        {
            var g = cases[c][0]; var d = cases[c][1];
            Func<int> state = () => C.CombatRead.Of(g, d);
            var fs = new FakeFs();
            var wit = new I.WitnessFs(fs, state);
            List<I.FileTarget> files;
            var s = BigSurveyOn(fs, wit, out files);
            s.Request(1);
            int units = 0;
            for (int k = 0; k < 500; k++) units += s.Step(state(), 2000, () => 0);
            Check("combat3", names[c] + "_unknown", state() == C.CombatRead.UNKNOWN);
            Check("combat3", names[c] + "_zero_steps", units == 0 && s.StepsWorked == 0 && fs.Ops == 0 && s.UnknownSkips == 500,
                  "units " + units + " ops " + fs.Ops + " unknown skips " + s.UnknownSkips);
            // the gate itself, on a disk call made while the state is unknown:
            // counted AND refused (the fake disk is never reached)
            var into = new List<I.FsEntry>();
            long opsAt = fs.Ops;
            bool refused = false;
            try { wit.List("P", 10, into); } catch (Exception) { refused = true; }
            Check("combat3", names[c] + "_witness_counts_unknown", wit.Unknown == 1 && wit.InCombat == 0, "unknown " + wit.Unknown + " in combat " + wit.InCombat);
            Check("combat3", names[c] + "_witness_refuses_unknown", refused && fs.Ops == opsAt && into.Count == 0, "refused " + refused + " ops " + (fs.Ops - opsAt));
        }
        // the gate counts and refuses a live frame, forwards a not-live one uncounted
        bool live = true;
        var fsw = new FakeFs();
        fsw.Dir("P", 2, null, 0);
        var w2 = new I.WitnessFs(fsw, () => C.CombatRead.Of(() => live, () => false));
        bool liveRefused = false;
        try { w2.List("P", 10, new List<I.FsEntry>()); } catch (Exception) { liveRefused = true; }
        long opsLive = fsw.Ops;
        live = false;
        var got = new List<I.FsEntry>();
        int rc = w2.List("P", 10, got);
        Check("combat3", "witness_live_counted_not_live_not", w2.InCombat == 1 && w2.Unknown == 0);
        Check("combat3", "witness_live_refused_not_live_forwarded", liveRefused && opsLive == 0 && rc == 0 && got.Count == 2 && fsw.Ops == 1,
              "refused " + liveRefused + " ops at live " + opsLive + " rc " + rc + " got " + got.Count);
        // a step under a state read that turns unknown mid-run does nothing from then on
        bool fail = false;
        Func<int> st2 = () => C.CombatRead.Of(() => { if (fail) throw new Exception(); return false; }, () => false);
        var fs3 = new FakeFs();
        List<I.FileTarget> f3;
        var s3 = BigSurveyOn(fs3, new I.WitnessFs(fs3, st2), out f3);
        s3.Request(1);
        for (int k = 0; k < 3; k++) s3.Step(st2(), 2000, () => 0);
        long opsBefore = fs3.Ops;
        Check("combat3", "mid_run_still_running", s3.Running && s3.ResultFor(1) == null);
        fail = true;
        for (int k = 0; k < 50; k++) s3.Step(st2(), 2000, () => 0);
        Check("combat3", "turns_unknown_stops", opsBefore > 0 && fs3.Ops == opsBefore && s3.UnknownSkips == 50);
    }

    private static I.Survey BigSurveyOn(FakeFs fs, I.IFs disk, out List<I.FileTarget> files)
    {
        files = new List<I.FileTarget>();
        for (int i = 0; i < 17; i++) { string f = "G/f" + i + ".dll"; fs.File(f, 400000); files.Add(new I.FileTarget { Id = i, Path = f }); }
        fs.Dir("P", 40, "P/sub", 30);
        fs.Dir("Q", 2, null, 0);
        fs.File("G/game.dll", 10);
        return new I.Survey(disk, files, "P", "Q", "G/game.dll");
    }

    private static string D(object o)
    {
        var l = o as List<object>;
        if (l != null)
        {
            var parts = new List<string>();
            foreach (var e in l) parts.Add(D(e));
            return "[" + string.Join(",", parts) + "]";
        }
        return o == null ? "null" : Convert.ToString(o, CultureInfo.InvariantCulture);
    }

    /// <summary>Everything a finished job read, units and bytes included.</summary>
    private static string Dump(I.SurveyResult r)
    {
        if (r == null) return "none";
        return "gdig=" + D(r.Gdig) + ";plugins=" + D(r.Ldir[0]) + ";patchers=" + D(r.Ldir[1]) + ";aload=" + r.AloadDiskState
            + ";mvid=" + r.MvidDisk + ";trunc=" + r.Truncated + ";units=" + r.Units + ";bytes=" + r.Bytes;
    }

    private static I.Survey SmallSurveyOn(FakeFs fs, I.IFs disk)
    {
        var files = new List<I.FileTarget>();
        for (int i = 0; i < 3; i++) { string f = "G/f" + i + ".dll"; fs.File(f, 150000); files.Add(new I.FileTarget { Id = i, Path = f }); }
        fs.Dir("P", 3, "P/sub", 2);
        fs.Dir("Q", 1, null, 0);
        fs.File("G/game.dll", 10);
        return new I.Survey(disk, files, "P", "Q", "G/game.dll");
    }

    /// <summary>One late-verdict run. The step's entry read is NOT_LIVE every
    /// frame (an earlier verdict); the WORLD turns live (kind 0) or its read
    /// starts failing (kind 1, UNKNOWN) after `permit(frame)` operations have
    /// reached the fake disk in that frame (int.MaxValue: never), and is not
    /// live again at the next frame. The gate reads the world itself; the fake
    /// disk counts every operation (List, Open, AsmName, Read, Seek, Length)
    /// that reaches it while the world is live. Returns the finished result.</summary>
    private static I.SurveyResult LateRun(bool small, int kind, Func<int, int> permit, out FakeFs fsOut, out I.WitnessFs witOut,
                                          out bool threw, out int lateFrames)
    {
        var fs = new FakeFs();
        bool flipped = false;
        int inFrame = 0, allow = int.MaxValue;
        fs.Combat = () => flipped;
        fs.OnOp = () => { if (++inFrame >= allow) flipped = true; };
        int kk = kind;
        Func<int> world = () =>
        {
            if (!flipped) return C.CombatRead.NOT_LIVE;
            if (kk == 0) return C.CombatRead.LIVE;
            throw new InvalidOperationException("late read fails");
        };
        var wit = new I.WitnessFs(fs, world);
        List<I.FileTarget> files;
        var s = small ? SmallSurveyOn(fs, wit) : BigSurveyOn(fs, wit, out files);
        s.Request(1);
        threw = false; lateFrames = 0;
        for (int frame = 0; frame < 400000 && s.ResultFor(1) == null; frame++)
        {
            inFrame = 0; allow = permit(frame);
            flipped = allow <= 0;
            if (allow != int.MaxValue) lateFrames++;
            try { s.Step(C.CombatRead.NOT_LIVE, 2000, () => 0); } catch (Exception) { threw = true; }
        }
        flipped = false;
        fsOut = fs; witOut = wit;
        return s.ResultFor(1);
    }

    private static string Reference(bool small, out long ops)
    {
        var fs0 = new FakeFs();
        List<I.FileTarget> f0;
        var s0 = small ? SmallSurveyOn(fs0, new I.WitnessFs(fs0, () => C.CombatRead.NOT_LIVE))
                       : BigSurveyOn(fs0, new I.WitnessFs(fs0, () => C.CombatRead.NOT_LIVE), out f0);
        s0.Request(1);
        for (int k = 0; k < 400000 && s0.ResultFor(1) == null; k++) s0.Step(C.CombatRead.NOT_LIVE, 2000, () => 0);
        ops = fs0.Ops + fs0.Reads;
        return Dump(s0.ResultFor(1));
    }

    /// <summary>M1, late verdicts (round 2's open MEDIUM; design 9.3 "nothing
    /// heavy in combat", and for the survey unknown counts as combat). The
    /// step's entry read said NOT_LIVE, then the world turns LIVE or its read
    /// fails (UNKNOWN) before a disk operation. Required: that operation and
    /// every later one in the frame (stream reads included) never reach the
    /// disk under the late verdict; the verdict is counted; the job is held,
    /// not consumed: when frames are not live again the result equals an
    /// uninterrupted run's, units and bytes included. Two runs per kind: a
    /// SWEEP that turns the world live once before EACH operation index of a
    /// small survey in turn (every operation kind is the late one at least
    /// once; exactly one verdict is held per sweep run), and a long run over
    /// the big survey with two frames in three late after 0 to 4 operations.</summary>
    private static void Late()
    {
        long smallOps, bigOps;
        string wantSmall = Reference(true, out smallOps), wantBig = Reference(false, out bigOps);
        Check("late", "reference_finishes", wantSmall != "none" && wantBig != "none" && smallOps > 20, "small ops " + smallOps);
        string[] kinds = { "late_live", "late_unknown" };
        for (int kind = 0; kind < 2; kind++)
        {
            // the sweep: run j turns the world live just before operation j (counted across frames)
            int forwardedBad = 0, consumed = 0, heldWrong = 0, threwN = 0;
            string firstBad = "";
            for (long j = 0; j < smallOps; j++)
            {
                FakeFs fs; I.WitnessFs wit; bool threw;
                var r = LateRunSweep(kind, j, out fs, out wit, out threw);
                long held = kind == 0 ? wit.InCombat : wit.Unknown;
                long other = kind == 0 ? wit.Unknown : wit.InCombat;
                if (fs.OpsInCombat != 0 || fs.ReadsInCombat != 0) { forwardedBad++; if (firstBad == "") firstBad = "op " + j + ": ops " + fs.OpsInCombat + " reads " + fs.ReadsInCombat; }
                if (Dump(r) != wantSmall) { consumed++; if (firstBad == "") firstBad = "op " + j + ": result differs"; }
                if (held != 1 || other != 0) { heldWrong++; if (firstBad == "") firstBad = "op " + j + ": held " + held + " other " + other; }
                if (threw) threwN++;
            }
            Check("late", kinds[kind] + "_sweep_no_op_forwarded", forwardedBad == 0, forwardedBad + " of " + smallOps + " runs; " + firstBad);
            Check("late", kinds[kind] + "_sweep_job_held_not_consumed", consumed == 0, consumed + " of " + smallOps + " runs; " + firstBad);
            Check("late", kinds[kind] + "_sweep_verdict_recorded_once", heldWrong == 0, heldWrong + " of " + smallOps + " runs; " + firstBad);
            Check("late", kinds[kind] + "_sweep_step_contained", threwN == 0, threwN + " runs threw");
            // a frame late from its first operation: the job does not move
            {
                FakeFs fs; I.WitnessFs wit; bool threw; int lf;
                int calls = 0;
                var fsx = new FakeFs();
                bool live = true;
                fsx.Combat = () => live;
                int kk = kind;
                var witx = new I.WitnessFs(fsx, () => { calls++; if (kk == 0) return C.CombatRead.LIVE; throw new InvalidOperationException(); });
                var sx = SmallSurveyOn(fsx, witx);
                sx.Request(1);
                for (int k = 0; k < 20; k++) sx.Step(C.CombatRead.NOT_LIVE, 2000, () => 0);
                Check("late", kinds[kind] + "_first_op_late_job_still", fsx.Ops == 0 && fsx.Reads == 0 && sx.Running && sx.ResultFor(1) == null && calls == 20,
                      "ops " + fsx.Ops + " reads " + fsx.Reads + " gate reads " + calls);
                // the long run
                var r = LateRun(false, kind, f => f % 3 != 0 ? f % 5 : int.MaxValue, out fs, out wit, out threw, out lf);
                long held = kind == 0 ? wit.InCombat : wit.Unknown;
                long other = kind == 0 ? wit.Unknown : wit.InCombat;
                Check("late", kinds[kind] + "_long_no_op_forwarded", fs.OpsInCombat == 0 && fs.ReadsInCombat == 0,
                      "ops under the late verdict " + fs.OpsInCombat + ", stream reads " + fs.ReadsInCombat);
                Check("late", kinds[kind] + "_long_verdict_recorded", held > 0 && other == 0 && lf > 0, "held " + held + " late frames " + lf + " other " + other);
                Check("late", kinds[kind] + "_long_step_contained", !threw);
                string got = Dump(r);
                Check("late", kinds[kind] + "_long_job_held_not_consumed", got == wantBig, "got " + got.Substring(0, Math.Min(200, got.Length)));
            }
        }
    }

    /// <summary>A sweep run over the small survey: the world turns live (or
    /// its read fails) just before the operation with index `j` (operations
    /// counted across frames as they reach the fake disk) and stays so until
    /// the end of the frame in which a combat read first observes it; every
    /// step's entry read is NOT_LIVE (the earlier verdict).</summary>
    private static I.SurveyResult LateRunSweep(int kind, long j, out FakeFs fsOut, out I.WitnessFs witOut, out bool threw)
    {
        var fs = new FakeFs();
        bool flipped = false, fired = false, observed = false;
        long count = 0;
        fs.Combat = () => flipped;
        fs.OnOp = () => { if (++count == j && !fired) { fired = true; flipped = true; } };
        int kk = kind;
        Func<int> world = () =>
        {
            if (!flipped) return C.CombatRead.NOT_LIVE;
            observed = true;
            if (kk == 0) return C.CombatRead.LIVE;
            throw new InvalidOperationException("late read fails");
        };
        var wit = new I.WitnessFs(fs, world);
        var s = SmallSurveyOn(fs, wit);
        s.Request(1);
        threw = false;
        for (int frame = 0; frame < 100000 && s.ResultFor(1) == null; frame++)
        {
            if (j == 0 && !fired) { fired = true; flipped = true; }
            else flipped = fired && !observed;
            try { s.Step(C.CombatRead.NOT_LIVE, 2000, () => 0); } catch (Exception) { threw = true; }
        }
        flipped = false;
        fsOut = fs; witOut = wit;
        return s.ResultFor(1);
    }

    /// <summary>M1 and L4 on the PRODUCTION adapter (I.DiskFs) over real
    /// temporary files: not-found is no_file, an access or I/O failure is
    /// read_failed, and a loader root that is itself a junction is refused.</summary>
    private static void Adapter()
    {
        string root = Path.Combine(Path.GetTempPath(), "scr-ic-adapter-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(root);
        try
        {
            var fs = new I.DiskFs();
            bool missing;
            var none = fs.Open(Path.Combine(root, "absent.dll"), out missing);
            Check("adapter", "open_not_found_missing", none == null && missing);
            var none2 = fs.Open(Path.Combine(root, "nofolder", "absent.dll"), out missing);
            Check("adapter", "open_folder_not_found_missing", none2 == null && missing);
            string locked = Path.Combine(root, "locked.dll");
            File.WriteAllBytes(locked, new byte[64]);
            using (var hold = new FileStream(locked, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                var s = fs.Open(locked, out missing);
                Check("adapter", "open_sharing_failure_not_missing", s == null && !missing);
                // through the survey: the locked target is read_failed, the absent one no_file
                var tf = new List<I.FileTarget> { new I.FileTarget { Id = 0, Path = locked }, new I.FileTarget { Id = 1, Path = Path.Combine(root, "absent.dll") } };
                var sv = new I.Survey(fs, tf, "", "", "");
                sv.Request(1);
                for (int k = 0; k < 1000 && sv.ResultFor(1) == null; k++) sv.Step(C.CombatRead.NOT_LIVE, long.MaxValue, () => 0);
                List<object> gd; C.JObj ld; int dst; string mdd;
                I.SurveyFields(sv.ResultFor(1), tf, new I.Privacy(null), out gd, out ld, out dst, out mdd);
                Check("adapter", "survey_locked_read_failed_absent_no_file", (long)((List<object>)gd[0])[2] == I.READ_FAILED && (long)((List<object>)gd[1])[2] == I.NO_FILE, C.Json(gd));
            }
            var ok = fs.Open(locked, out missing);
            Check("adapter", "open_ok", ok != null && !missing);
            if (ok != null) ok.Dispose();
            Check("adapter", "open_directory_not_missing", fs.Open(root, out missing) == null && !missing);
            Check("adapter", "list_not_found_1", fs.List(Path.Combine(root, "nodir"), 10, new List<I.FsEntry>()) == 1);
            Check("adapter", "list_a_file_2", fs.List(locked, 10, new List<I.FsEntry>()) == 2);
            string real = Path.Combine(root, "real");
            Directory.CreateDirectory(real);
            File.WriteAllBytes(Path.Combine(real, "inside.dll"), new byte[10]);
            var into = new List<I.FsEntry>();
            Check("adapter", "list_real_0", fs.List(real, 10, into) == 0 && into.Count == 1);
            string junction = Path.Combine(root, "junction");
            var p = Process.Start(new ProcessStartInfo("cmd.exe", "/c mklink /J \"" + junction + "\" \"" + real + "\"") { UseShellExecute = false, RedirectStandardOutput = true, CreateNoWindow = true });
            p.WaitForExit(10000);
            bool made = Directory.Exists(junction) && (File.GetAttributes(junction) & FileAttributes.ReparsePoint) != 0;
            Check("adapter", "junction_made", made);
            var into2 = new List<I.FsEntry>();
            Check("adapter", "root_junction_refused", fs.List(junction, 10, into2) == I.LIST_REFUSED_REPARSE && into2.Count == 0);
            // through the survey: the loader root a junction is read_failed with nothing listed
            var s2 = new I.Survey(fs, new List<I.FileTarget>(), junction, real, "");
            s2.Request(1);
            for (int k = 0; k < 1000 && s2.ResultFor(1) == null; k++) s2.Step(C.CombatRead.NOT_LIVE, long.MaxValue, () => 0);
            List<object> gdig; C.JObj ldir; int ds; string md;
            I.SurveyFields(s2.ResultFor(1), new List<I.FileTarget>(), new I.Privacy(null), out gdig, out ldir, out ds, out md);
            var pp = Part(ldir, "plugins"); var pq = Part(ldir, "patchers");
            Check("adapter", "survey_root_junction_read_failed", (long)pp[0] == I.READ_FAILED && (long)pp[1] == 0 && ((List<object>)pp[3]).Count == 0, C.Json(pp));
            Check("adapter", "survey_real_root_listed", (long)pq[0] == I.OK && (long)pq[1] == 1, C.Json(pq));
            try { Directory.Delete(junction); } catch { }
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }

    /// <summary>The quit flush loop (production FlushOnQuit runs it): a live
    /// capture is built and handed to the spool once; one line per capture;
    /// ONE summary line after the loop, a quit with no capture included.</summary>
    private static void Flush()
    {
        var info = new List<string>(); var warn = new List<string>();
        var spooled = new List<string>();
        I.EnvBuilder<string> build = (string c, out string text) => { text = "rec-" + c; return c == "bad" ? null : "env-" + c; };
        var caps = new List<string> { "g1" };
        int kept = I.FlushCaptures(caps, 4, build, e => { spooled.Add(e); return true; }, (c, t) => c + ":" + t, info.Add, warn.Add, () => { });
        Check("flush", "live_capture_spooled_once", kept == 1 && spooled.Count == 1 && spooled[0] == "env-g1" && caps.Count == 0);
        Check("flush", "kept_line_then_summary", info.Count == 2 && info[0].Contains("record kept for the next launch: g1:rec-g1")
              && info[1].Contains("quit flush ran: 1 capture(s), 1 kept"), string.Join(" | ", info));
        info.Clear(); warn.Clear(); spooled.Clear();
        I.FlushCaptures(new List<string>(), 4, build, e => { spooled.Add(e); return true; }, (c, t) => c, info.Add, warn.Add, () => { });
        Check("flush", "no_capture_summary_only", info.Count == 1 && info[0].Contains("quit flush ran: 0 capture(s), 0 kept") && spooled.Count == 0);
        info.Clear(); warn.Clear();
        int faults = 0;
        kept = I.FlushCaptures(new List<string> { "bad", "g2", "g3" }, 4, build, e => e != "env-g3", (c, t) => c, info.Add, warn.Add, () => faults++);
        Check("flush", "each_outcome_logged", kept == 1 && warn.Count == 2 && warn[0].Contains("outside the contract") && warn[1].Contains("closing file was not written")
              && info[info.Count - 1].Contains("quit flush ran: 3 capture(s), 1 kept"), string.Join(" | ", warn));
        info.Clear(); warn.Clear();
        I.EnvBuilder<string> thrower = (string c, out string text) => { throw new InvalidOperationException(); };
        I.FlushCaptures(new List<string> { "x" }, 4, thrower, e => true, (c, t) => c, info.Add, warn.Add, () => faults++);
        Check("flush", "throw_counted_and_summarized", faults == 1 && warn.Count == 1 && info.Count == 1 && info[0].Contains("1 capture(s), 0 kept"));
        var many = new List<string> { "a", "b", "c", "d", "e", "f" };
        info.Clear();
        I.FlushCaptures(many, 4, build, e => true, (c, t) => c, info.Add, warn.Add, () => { });
        Check("flush", "capped", many.Count == 2 && info[info.Count - 1].Contains("4 capture(s), 4 kept"));
    }

    /// <summary>L13: the series body parsed structurally; a malformed body is
    /// never a complete read; a completed read (failed included) invalidates
    /// the cached status at once.</summary>
    private static void SeriesShape()
    {
        Check("seriesshape", "empty_list", I.SeriesBodyShape("{\"series\":[]}") == 0);
        Check("seriesshape", "two_objects", I.SeriesBodyShape("{\"series\": [ {\"series_id\":\"a\",\"x\":[1,{\"y\":\"]\"}]}, {\"series_id\":\"b\"} ], \"n\": 2}") == 2);
        Check("seriesshape", "other_keys_first", I.SeriesBodyShape("{\"a\":{\"series\":5},\"series\":[{\"series_id\":\"z\"}]}") == 1);
        string[] bad = { null, "", "series", "<html>series</html>", "{\"series\":", "{\"series\":{}}", "[\"series\"]", "{\"x\":\"series\"}",
                         "{\"series\":[1]}", "{\"series\":[{}]} trailing", "{\"series\":[{\"a\":1},]}", "{\"series\":[{\"a\":1}]", "{}",
                         "{\"series\":[],\"series\":[]}", "{\"detail\":\"\\\"series\\\" unavailable\"}" };
        bool allBad = true; string which = "";
        foreach (var b in bad) if (I.SeriesBodyShape(b) != -1) { allBad = false; which += "[" + b + "]"; }
        Check("seriesshape", "malformed_refused", allBad, which);
        // fix pass 3, L13: only the JSON grammar is accepted, for strings
        // (escapes) and numbers, beside an empty series list and inside an element
        string[] badVals = { "\"\\x\"", "\"\\u12G4\"", "\"\\u12\"", "\"\\'\"", "\"\\a\"", "+1", "01", "-01", "1.", ".5", "1e", "1e+", "1.e5", "--1", "0x10",
                             "NaN", "Infinity", "-Infinity", "tru", "nul", "truex", "falsey", "1x", "TRUE", "\"\t\"" };
        // the core's nesting bound, read by reflection so this program also builds against an older core
        var depthField = typeof(I).GetField("JSON_DEPTH_MAX", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
        int depthMax = depthField != null ? (int)depthField.GetValue(null) : 64;
        string deep = new string('[', depthMax + 1) + new string(']', depthMax + 1);
        bool gBad = true; string gWhich = "";
        foreach (var v in badVals)
        {
            if (I.SeriesBodyShape("{\"series\":[],\"k\":" + v + "}") != -1) { gBad = false; gWhich += "[top " + v + "]"; }
            if (I.SeriesBodyShape("{\"series\":[{\"series_id\":\"a\",\"k\":" + v + "}]}") != -1) { gBad = false; gWhich += "[elem " + v + "]"; }
        }
        if (I.SeriesBodyShape("{\"series\":[],\"k\":" + deep + "}") != -1) { gBad = false; gWhich += "[deep]"; }
        Check("seriesshape", "grammar_malformed_refused", gBad, gWhich);
        string[] goodVals = { "\"\\\" \\\\ \\/ \\b \\f \\n \\r \\t \\u00e9 \\uABCD\"", "0", "-0", "0.5", "-1.5E-3", "1e10", "12e+3", "123", "true", "false", "null",
                              "[1,[2,{\"a\":[]}]]", "{}", "[]", "\"\"" };
        bool gGood = true; string gMiss = "";
        foreach (var v in goodVals)
            if (I.SeriesBodyShape("{\"series\":[{\"series_id\":\"a\",\"k\":" + v + "}],\"m\":" + v + "}") != 1) { gGood = false; gMiss += "[" + v + "]"; }
        string okDeep = new string('[', depthMax - 2) + new string(']', depthMax - 2);
        if (I.SeriesBodyShape("{\"series\":[],\"k\":" + okDeep + "}") != 0) { gGood = false; gMiss += "[depth under the bound]"; }
        Check("seriesshape", "grammar_valid_accepted", gGood, gMiss);
        // a malformed body is never a complete read, so never "none"
        bool parsed = I.SeriesBodyShape("{\"detail\":\"series\"}") >= 0;
        Check("seriesshape", "malformed_never_none", I.SeriesStatus(true, false, true, parsed, 1, 60) == "unknown");
        Check("seriesshape", "cache_fresh_same_gen", I.SeriesCacheFresh(1, 5, 7, 7));
        Check("seriesshape", "cache_invalid_after_any_read", !I.SeriesCacheFresh(1, 5, 8, 7));
        Check("seriesshape", "cache_invalid_when_old", !I.SeriesCacheFresh(5, 5, 7, 7) && !I.SeriesCacheFresh(-1, 5, 7, 7));
    }

    // -- perf: the survey over this seat's own files (read only), through the production adapter

    private static int Perf(string managed, string core, string plugins, string patchers, string root, string gameAsm)
    {
        var names = new[] { "Assembly-CSharp.dll", "Assembly-CSharp-firstpass.dll", "Photon3Unity3D.dll", "PhotonRealtime.dll",
            "PhotonUnityNetworking.dll", "PhotonUnityNetworking.Utilities.dll", "UnityEngine.CoreModule.dll", "UnityEngine.Physics2DModule.dll" };
        var loader = new[] { "BepInEx.dll", "BepInEx.Preloader.dll", "0Harmony.dll", "BepInEx.Harmony.dll", "HarmonyXInterop.dll",
            "MonoMod.RuntimeDetour.dll", "MonoMod.Utils.dll", "Mono.Cecil.dll" };
        var files = new List<I.FileTarget>();
        int id = 0;
        foreach (var n in names) files.Add(new I.FileTarget { Id = id++, Path = Path.Combine(managed, n) });
        foreach (var n in loader) files.Add(new I.FileTarget { Id = id++, Path = Path.Combine(core, n) });
        files.Add(new I.FileTarget { Id = id++, Path = Path.Combine(root, "winhttp.dll") });
        var sw = Stopwatch.StartNew();
        Func<long> us = () => sw.ElapsedTicks * 1000000L / Stopwatch.Frequency;
        for (int rep = 0; rep < 3; rep++)
        {
            var s = new I.Survey(new I.DiskFs(), files, plugins, patchers, gameAsm);
            s.Request(1);
            var steps = new List<long>();
            long start = us();
            while (s.ResultFor(1) == null && steps.Count < 100000)
            {
                long t = us();
                s.Step(C.CombatRead.NOT_LIVE,2000, us);
                steps.Add(us() - t);
            }
            long total = us() - start;
            steps.Sort();
            var r = s.ResultFor(1);
            int ok = 0; foreach (List<object> e in r.Gdig) if ((long)e[2] == I.OK) ok++;
            Console.WriteLine(string.Format(CultureInfo.InvariantCulture,
                "perf rep {0}: steps {1} p50_us {2} p99_us {3} max_us {4} total_ms {5} units {6} bytes {7} gdig_ok {8}/{9} ldir {10} aload {11} truncated {12}",
                rep, steps.Count, steps[steps.Count / 2], steps[(int)(steps.Count * 0.99)], steps[steps.Count - 1], total / 1000, r.Units, r.Bytes,
                ok, r.Gdig.Count, C.Json(I.L(((List<object>)r.Ldir[0])[0], ((List<object>)r.Ldir[0])[1], ((List<object>)r.Ldir[1])[0])),
                r.AloadDiskState, r.Truncated));
        }
        return 0;
    }
}
