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

        private static int Main(string[] args)
        {
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
