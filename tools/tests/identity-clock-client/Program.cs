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
            for (int k = 0; k < 100000 && s.ResultFor(1) == null; k++) s.Step(false, long.MaxValue, () => 0);
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
        internal long OpsInCombat, Ops;

        private void W() { Ops++; if (Combat()) OpsInCombat++; }

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
            return new MemoryStream(Files[path], false);
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
        for (int k = 0; k < 1000 && s.ResultFor(1) == null; k++) s.Step(false, long.MaxValue, () => 0);
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
        var src = new I.KeySource(() => live);
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
            int n = s.Step(combat, 2000, () => 0);
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
        for (int k = 0; k < 200000 && s.ResultFor(1) == null; k++) s.Step(false, long.MaxValue, () => 0);
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
        for (int k = 0; k < 5; k++) s.Step(false, long.MaxValue, () => 0);
        s.Request(1);
        Check("flight", "same_gen_continues", s.Abandoned == 0 && s.RunningGen == 1);
        s.Request(2);
        Check("flight", "older_abandoned_single_job", s.Abandoned == 1 && s.RunningGen == 2);
        for (int k = 0; k < 200000 && s.ResultFor(2) == null; k++) s.Step(false, long.MaxValue, () => 0);
        Check("flight", "only_newest_published", s.ResultFor(2) != null && s.ResultFor(1) == null && !s.Running);
    }

    private static void Stale()
    {
        var fs = new FakeFs();
        List<I.FileTarget> files;
        var s = BigSurvey(fs, out files);
        s.Request(2);
        for (int k = 0; k < 200000 && s.ResultFor(2) == null; k++) s.Step(false, long.MaxValue, () => 0);
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
        for (int k = 0; k < 100000 && s.ResultFor(1) == null; k++) s.Step(false, long.MaxValue, () => 0);
        string d1 = (string)((List<object>)s.ResultFor(1).Gdig[0])[1];
        var b = fs.Files["G/a.dll"]; b[500] ^= 0x5A;   // same length; the fake disk has no times at all
        s.Request(2);
        for (int k = 0; k < 100000 && s.ResultFor(2) == null; k++) s.Step(false, long.MaxValue, () => 0);
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
        for (int k = 0; k < 1000 && s.ResultFor(1) == null; k++) s.Step(false, long.MaxValue, () => 0);
        I.SurveyFields(s.ResultFor(1), files, new I.Privacy(null), out gdig, out ldir, out ds, out md);
        Check("l4", "open_failure_read_failed", (long)((List<object>)gdig[0])[2] == I.READ_FAILED && (long)((List<object>)gdig[1])[2] == I.NO_FILE, C.Json(gdig));
        Check("l4", "aload_missing_no_file", ds == I.NO_FILE && md == "", ds.ToString());
        // an aload file that exists but cannot be opened is read_failed, never no_file
        var fs3 = new FakeFs();
        fs3.File("G/game.dll", 10); fs3.OpenFail.Add("G/game.dll");
        var s3 = new I.Survey(fs3, new List<I.FileTarget>(), "", "", "G/game.dll");
        s3.Request(1);
        for (int k = 0; k < 1000 && s3.ResultFor(1) == null; k++) s3.Step(false, long.MaxValue, () => 0);
        Check("l4", "aload_unopenable_read_failed", s3.ResultFor(1) != null && s3.ResultFor(1).AloadDiskState == I.READ_FAILED);
        // a game assembly that is not a PE image is read_failed
        var fs4 = new FakeFs();
        fs4.File("G/game.dll", 300);
        var s4 = new I.Survey(fs4, new List<I.FileTarget>(), "", "", "G/game.dll");
        s4.Request(1);
        for (int k = 0; k < 1000 && s4.ResultFor(1) == null; k++) s4.Step(false, long.MaxValue, () => 0);
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
        int st = 0; long sw = 0;
        b.PointStart(true, 0, 0, 0);
        for (int k = 0; k < 600; k++)
        {
            st += 33; sw += (long)Math.Round(33 * 1.001);
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

    // -- perf: the survey over this seat's own files (read only) ---------------------------

    private sealed class RealFs : I.IFs
    {
        public int List(string dir, int max, List<I.FsEntry> into)
        {
            try
            {
                var d = new DirectoryInfo(dir);
                if (!d.Exists) return 1;
                foreach (var e in d.EnumerateFileSystemInfos())
                {
                    if (into.Count > max) break;
                    into.Add(new I.FsEntry { Path = e.FullName, IsDir = (e.Attributes & FileAttributes.Directory) != 0, IsReparse = (e.Attributes & FileAttributes.ReparsePoint) != 0 });
                }
                return 0;
            }
            catch { return 2; }
        }
        public Stream Open(string path, out bool missing)
        {
            missing = string.IsNullOrEmpty(path) || !File.Exists(path);
            if (missing) return null;
            try { return new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 4096); } catch { return null; }
        }
        public string AsmName(string path) { try { return System.Reflection.AssemblyName.GetAssemblyName(path).Name; } catch { return null; } }
    }

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
            var s = new I.Survey(new RealFs(), files, plugins, patchers, gameAsm);
            s.Request(1);
            var steps = new List<long>();
            long start = us();
            while (s.ResultFor(1) == null && steps.Count < 100000)
            {
                long t = us();
                s.Step(false, 2000, us);
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
