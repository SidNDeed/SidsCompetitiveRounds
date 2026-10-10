using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using BepInEx.Configuration;

namespace CompetitiveRounds.Item19
{
    /// <summary>Item 19 fix pass 1, M10: the config witness against a
    /// CONTROLLED same-lineage baseline. The real BepInEx ConfigFile (the
    /// game's own BepInEx.dll) writes the mod's cfg twice from the lane's own
    /// Config.Bind list, in source order: once without the four item 19 keys
    /// (the baseline) and once with them. Every value is the bind's DEFAULT,
    /// so no player value is read or written. The witness then proves:
    ///   1. each of the four entries has BepInEx's normal shape (a blank
    ///      line, "## description", "# Setting type", "# Default value",
    ///      "Key = value"), inside [UI], contiguous, in bind order;
    ///   2. removing exactly those four blocks from the second file gives the
    ///      baseline back BYTE FOR BYTE (nothing unrelated moved, changed,
    ///      retyped or was re-commented);
    ///   3. two negative controls: an unrelated description edit and an
    ///      unrelated retype in the second write are each DETECTED by step 2.
    /// Usage: item19-cfgwitness BINDS.json WORKDIR. Exit 0 only on PASS.</summary>
    internal static class CfgWitness
    {
        private sealed class BindRow
        {
            public string section { get; set; }
            public string key { get; set; }
            public string kind { get; set; }
            public string value { get; set; }
            public string description { get; set; }
        }

        private sealed class Input
        {
            public List<BindRow> binds { get; set; }
            public List<string> avatar { get; set; }
        }

        private static void Bind(ConfigFile cf, BindRow b, string kindOverride = null, string descOverride = null)
        {
            string kind = kindOverride ?? b.kind;
            string desc = descOverride ?? b.description ?? "";
            var ic = System.Globalization.CultureInfo.InvariantCulture;
            switch (kind)
            {
                case "bool": cf.Bind(b.section, b.key, b.value == "true", desc); break;
                case "int": cf.Bind(b.section, b.key, int.Parse(b.value, ic), desc); break;
                case "float": cf.Bind(b.section, b.key, float.Parse(b.value, ic), desc); break;
                default: cf.Bind(b.section, b.key, b.value ?? "", desc); break;
            }
        }

        private static byte[] Write(string path, IEnumerable<BindRow> rows, Func<BindRow, (string kind, string desc)> perturb = null)
        {
            if (File.Exists(path)) File.Delete(path);
            var cf = new ConfigFile(path, false);
            foreach (var b in rows)
            {
                if (perturb == null) { Bind(cf, b); continue; }
                var p = perturb(b);
                Bind(cf, b, p.kind, p.desc);
            }
            cf.Save();
            return File.ReadAllBytes(path);
        }

        /// <summary>The second file with the four avatar blocks cut out, the
        /// blocks themselves, and the [section] each block sat in.</summary>
        private static (string rest, List<string[]> blocks, List<string> sections) Cut(string text, IList<string> keys)
        {
            var lines = text.Split(new[] { "\r\n" }, StringSplitOptions.None).ToList();
            var blocks = new List<string[]>();
            var sections = new List<string>();
            foreach (var key in keys)
            {
                int at = lines.FindIndex(l => l.StartsWith(key + " = ", StringComparison.Ordinal));
                if (at < 0) { blocks.Add(null); sections.Add(null); continue; }
                int start = at;
                while (start > 0 && lines[start - 1].Length > 0) start--;
                start--;                                   // the blank line BepInEx writes before every entry
                string sec = null;
                for (int i = start; i >= 0; i--) if (lines[i].StartsWith("[", StringComparison.Ordinal)) { sec = lines[i]; break; }
                blocks.Add(lines.GetRange(start, at - start + 1).ToArray());
                sections.Add(sec);
                lines.RemoveRange(start, at - start + 1);
            }
            return (string.Join("\r\n", lines), blocks, sections);
        }

        // -----------------------------------------------------------------
        // Fix pass 2 (M10): the real-config upgrade. Usage:
        //   item19-cfgwitness --real OLD.json NEW.json BACKUP.cfg WORKDIR
        // OLD.json is the bind list of the same-lineage build this lane
        // branched from, NEW.json the lane's own. Each is applied by the
        // game's BepInEx ConfigFile to its OWN copy of ONE backed-up real
        // configuration file (the seat's mod cfg, copied under the holds; the
        // witness never opens the original). It proves every key the real
        // file already held keeps its value and its type through BOTH builds,
        // every non-avatar entry is byte-identical between the two upgrades,
        // and only the item 19 keys are added. No value is ever printed.
        // Three negative controls (a bool bind retyped to string, an int bind
        // retyped to bool, a description edit) must each be DETECTED.
        // -----------------------------------------------------------------

        private sealed class Entry
        {
            public string Key, Value, Type, Block;
        }

        private static Dictionary<string, Entry> Parse(string text)
        {
            var map = new Dictionary<string, Entry>();
            string sec = null;
            var pending = new List<string>();
            foreach (var line in text.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None))
            {
                if (line.StartsWith("[", StringComparison.Ordinal) && line.EndsWith("]", StringComparison.Ordinal))
                { sec = line.Substring(1, line.Length - 2); pending.Clear(); continue; }
                if (line.Length == 0) { pending.Clear(); continue; }
                if (line.StartsWith("#", StringComparison.Ordinal)) { pending.Add(line); continue; }
                int eq = line.IndexOf(" = ", StringComparison.Ordinal);
                if (eq < 0) { pending.Clear(); continue; }
                var e = new Entry { Key = line.Substring(0, eq), Value = line.Substring(eq + 3) };
                foreach (var c in pending)
                    if (c.StartsWith("# Setting type: ", StringComparison.Ordinal)) e.Type = c.Substring(16);
                e.Block = string.Join("\n", pending) + "\n" + line;
                map[sec + "\u0001" + e.Key] = e;
                pending.Clear();
            }
            return map;
        }

        private static string KeyName(string k) => k.Substring(k.IndexOf('\u0001') + 1);

        private static byte[] Upgrade(string path, string backup, IEnumerable<BindRow> rows, Func<BindRow, (string kind, string desc)> perturb)
        {
            File.Copy(backup, path, true);
            var cf = new ConfigFile(path, false);
            foreach (var b in rows)
            {
                if (perturb == null) { Bind(cf, b); continue; }
                var p = perturb(b);
                Bind(cf, b, p.kind, p.desc);
            }
            cf.Save();
            return File.ReadAllBytes(path);
        }

        private sealed class Verdict
        {
            public int Pre, ValueKept, TypeKept, Blocks, BlocksSame;
            public List<string> Added = new List<string>(), Lost = new List<string>(), Retyped = new List<string>(), Revalued = new List<string>();
            public bool AddedOnlyAvatar;
            public bool Pass => Pre > 0 && ValueKept == Pre && TypeKept == Pre && BlocksSame == Blocks && AddedOnlyAvatar && Lost.Count == 0;
        }

        private static Verdict Compare(Dictionary<string, Entry> orig, Dictionary<string, Entry> a, Dictionary<string, Entry> b, IList<string> avatar)
        {
            var v = new Verdict();
            foreach (var kv in orig)
            {
                v.Pre++;
                Entry ea, eb;
                bool inA = a.TryGetValue(kv.Key, out ea), inB = b.TryGetValue(kv.Key, out eb);
                if (!inA || !inB) { v.Lost.Add(KeyName(kv.Key)); continue; }
                if (ea.Value == kv.Value.Value && eb.Value == kv.Value.Value) v.ValueKept++;
                string t0 = kv.Value.Type;
                bool typeOk = (eb.Type ?? t0) == (t0 ?? eb.Type) && (ea.Type == null || eb.Type == null || ea.Type == eb.Type);
                if (typeOk) v.TypeKept++;
                else v.Retyped.Add(KeyName(kv.Key) + " (" + (t0 ?? "none") + " -> old " + (ea.Type ?? "none") + ", new " + (eb.Type ?? "none") + ")");
                if (ea.Value != kv.Value.Value || eb.Value != kv.Value.Value)
                    v.Revalued.Add(KeyName(kv.Key) + " (old build kept=" + (ea.Value == kv.Value.Value) + ", new build kept=" + (eb.Value == kv.Value.Value) + ")");
            }
            foreach (var k in a.Keys.Union(b.Keys))
            {
                if (avatar.Contains(KeyName(k))) continue;
                v.Blocks++;
                Entry ea, eb;
                if (a.TryGetValue(k, out ea) && b.TryGetValue(k, out eb) && ea.Block == eb.Block) v.BlocksSame++;
            }
            // a key the NEW build writes and the OLD build's upgrade of the
            // same file does not: only the item 19 keys may appear here
            foreach (var k in b.Keys) if (!a.ContainsKey(k)) { if (!v.Added.Contains(KeyName(k))) v.Added.Add(KeyName(k)); }
            foreach (var k in a.Keys) if (!b.ContainsKey(k)) v.Lost.Add(KeyName(k));
            v.AddedOnlyAvatar = v.Added.All(avatar.Contains);
            return v;
        }

        private static int Real(string[] args)
        {
            var oldIn = JsonSerializer.Deserialize<Input>(File.ReadAllText(args[1]));
            var newIn = JsonSerializer.Deserialize<Input>(File.ReadAllText(args[2]));
            string backup = args[3], work = args[4];
            Directory.CreateDirectory(work);
            var avatar = newIn.avatar;
            var orig = Parse(File.ReadAllText(backup));
            var A = Parse(Encoding.UTF8.GetString(Upgrade(Path.Combine(work, "old-build.cfg"), backup, oldIn.binds, null)));
            var B = Parse(Encoding.UTF8.GetString(Upgrade(Path.Combine(work, "new-build.cfg"), backup, newIn.binds, null)));
            var v = Compare(orig, A, B, avatar);
            Console.WriteLine("CFGWITNESS-REAL old binds=" + oldIn.binds.Count + " new binds=" + newIn.binds.Count
                + " real-file entries=" + orig.Count + " (item 19 keys already in it: "
                + string.Join(",", orig.Keys.Select(KeyName).Where(avatar.Contains)) + ")");
            Console.WriteLine("CFGWITNESS-REAL pre-existing keys=" + v.Pre + " value kept=" + v.ValueKept + " type kept=" + v.TypeKept
                + " lost=" + v.Lost.Count + " non-avatar blocks identical=" + v.BlocksSame + "/" + v.Blocks
                + " keys added by the new build=[" + string.Join(",", v.Added) + "] (all item 19 keys=" + v.AddedOnlyAvatar + ")");
            Console.WriteLine("CFGWITNESS-REAL retyped (key names and type names only)=[" + string.Join("; ", v.Retyped)
                + "] revalued (key names only)=[" + string.Join("; ", v.Revalued) + "] lost=[" + string.Join(",", v.Lost) + "]");

            // the three negative controls: each perturbs ONE pre-existing,
            // non-avatar bind in the NEW list; Compare must then fail
            var present = newIn.binds.Where(r => !avatar.Contains(r.key) && orig.ContainsKey(r.section + "\u0001" + r.key)).ToList();
            var vBool = present.First(r => r.kind == "bool");
            var vInt = present.First(r => r.kind == "int" && !string.Equals(orig[r.section + "\u0001" + r.key].Value, "true", StringComparison.OrdinalIgnoreCase)
                                          && !string.Equals(orig[r.section + "\u0001" + r.key].Value, "false", StringComparison.OrdinalIgnoreCase));
            var vDesc = present.First(r => r.key != vBool.key && r.key != vInt.key);
            bool Detects(string file, BindRow victim, string kind, string suffix)
            {
                var C = Parse(Encoding.UTF8.GetString(Upgrade(Path.Combine(work, file), backup, newIn.binds,
                    r => r.key == victim.key && r.section == victim.section ? (kind ?? r.kind, (r.description ?? "") + suffix) : (r.kind, r.description))));
                return !Compare(orig, A, C, avatar).Pass;
            }
            bool d1 = Detects("control-retype-bool.cfg", vBool, "string", "");
            bool d2 = Detects("control-retype-int.cfg", vInt, "bool", "");
            bool d3 = Detects("control-description.cfg", vDesc, null, " (edited)");
            Console.WriteLine("CFGWITNESS-REAL negative-control retype bool->string detected=" + d1 + " | retype int->bool detected=" + d2
                + " | description edit detected=" + d3 + " (victims " + vBool.key + ", " + vInt.key + ", " + vDesc.key + ")");
            bool pass = v.Pass && d1 && d2 && d3;
            Console.WriteLine("CFGWITNESS-REAL verdict=" + (pass ? "PASS" : "FAIL")
                + " baseline=real-config (two same-lineage bind lists, one backed-up real file, BepInEx ConfigFile; no value printed)");
            return pass ? 0 : 1;
        }

        private static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--real") return Real(args);
            var input = JsonSerializer.Deserialize<Input>(File.ReadAllText(args[0]));
            string work = args[1];
            Directory.CreateDirectory(work);
            var avatar = input.avatar;
            var all = input.binds;
            var baseRows = all.Where(b => !avatar.Contains(b.key)).ToList();

            byte[] b0 = Write(Path.Combine(work, "baseline.cfg"), baseRows);
            byte[] b1 = Write(Path.Combine(work, "with-item19.cfg"), all);
            string t1 = Encoding.UTF8.GetString(b1);
            var cut = Cut(t1, avatar);
            bool same = cut.rest == Encoding.UTF8.GetString(b0);

            bool shapes = true;
            var sb = new StringBuilder();
            for (int i = 0; i < avatar.Count; i++)
            {
                var blk = cut.blocks[i];
                var row = all.First(b => b.key == avatar[i]);
                string type = row.kind == "bool" ? "Boolean" : row.kind == "int" ? "Int32" : "?";
                bool ok = blk != null && blk.Length == 5 && blk[0] == "" && blk[1] == "## " + row.description
                    && blk[2] == "# Setting type: " + type && blk[3] == "# Default value: " + row.value
                    && blk[4] == row.key + " = " + row.value && cut.sections[i] == "[UI]";
                shapes &= ok;
                Console.WriteLine("CFGWITNESS block " + avatar[i] + " shape=" + (ok ? "BepInEx-normal" : "WRONG")
                    + " section=" + (cut.sections[i] ?? "none"));
                if (blk != null) foreach (var l in blk.Skip(2)) Console.WriteLine("    " + l);
            }

            // contiguous and in bind order: the four keys' line indices in the
            // second file are strictly increasing, five lines apart
            var lines1 = t1.Split(new[] { "\r\n" }, StringSplitOptions.None).ToList();
            var idx = avatar.Select(k => lines1.FindIndex(l => l.StartsWith(k + " = ", StringComparison.Ordinal))).ToList();
            bool contiguous = idx.All(x => x >= 0) && Enumerable.Range(1, idx.Count - 1).All(j => idx[j] - idx[j - 1] == 5);

            // negative controls: the same comparison must SEE an unrelated change
            var victim = baseRows.First(b => b.section == "UI" && b.kind == "bool");
            byte[] nDesc = Write(Path.Combine(work, "control-description.cfg"), all,
                b => b.key == victim.key ? (b.kind, b.description + " (edited)") : (b.kind, b.description));
            byte[] nType = Write(Path.Combine(work, "control-retype.cfg"), all,
                b => b.key == victim.key ? ("string", b.description) : (b.kind, b.description));
            bool seesDesc = Cut(Encoding.UTF8.GetString(nDesc), avatar).rest != Encoding.UTF8.GetString(b0);
            bool seesType = Cut(Encoding.UTF8.GetString(nType), avatar).rest != Encoding.UTF8.GetString(b0);

            Console.WriteLine("CFGWITNESS binds=" + all.Count + " baseline_binds=" + baseRows.Count
                + " baseline_bytes=" + b0.Length + " with_item19_bytes=" + b1.Length
                + " lines_added=" + (lines1.Count - Encoding.UTF8.GetString(b0).Split(new[] { "\r\n" }, StringSplitOptions.None).Length));
            Console.WriteLine("CFGWITNESS unrelated_bytes_equal=" + same + " four_blocks_normal_shape=" + shapes
                + " contiguous_in_bind_order=" + contiguous);
            Console.WriteLine("CFGWITNESS negative-control unrelated description edit detected=" + seesDesc
                + " | unrelated retype detected=" + seesType + " (victim key " + victim.key + ")");
            bool pass = same && shapes && contiguous && seesDesc && seesType;
            Console.WriteLine("CFGWITNESS verdict=" + (pass ? "PASS" : "FAIL") + " baseline=same-lineage (one BepInEx writer, the lane's own bind list, defaults only)");
            return pass ? 0 : 1;
        }
    }
}
