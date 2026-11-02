#if SCR_FRAMETIME
using System;
using System.Collections.Generic;
using System.IO;

namespace CompetitiveRounds
{
    /// <summary>FrameTime (B11 format M) settings. They come only from the sentinel file
    /// BepInEx/frametime/arm, one key=value per line, never from the shared cfg: a
    /// Config.Bind would write a new key into com.competitiverounds.mod.cfg, which VR6
    /// pins by sha256 (FORMAT-M-PLAN.md V2 part b, F01). Keys: seed (integer), force
    /// (ON, OFF or none: the menu self-check), f18 (A or B: section 5 of the build brief;
    /// A when absent). The file's presence is also the arming input of part b.</summary>
    internal static class FtConfig
    {
        internal static string Dir => Path.Combine(BepInEx.Paths.BepInExRootPath, "frametime");
        internal static string ArmPath => Path.Combine(Dir, "arm");

        internal static bool Present;
        internal static int Seed;
        internal static string Force = "none";
        internal static string F18 = "A";
        internal static int PlantUs = -1;     // plant_us: c_plant fixed by the sentinel (M5); -1 = derived
        internal static string Problems = "";

        private static readonly Dictionary<string, string> Kv = new Dictionary<string, string>(StringComparer.Ordinal);

        internal static void Load()
        {
            Kv.Clear();
            Problems = "";
            Present = File.Exists(ArmPath);
            if (Present)
            {
                foreach (string raw in File.ReadAllLines(ArmPath))
                {
                    string ln = raw.Trim();
                    if (ln.Length == 0 || ln[0] == '#') continue;
                    int i = ln.IndexOf('=');
                    if (i <= 0) { Problems += " bad-line"; continue; }
                    Kv[ln.Substring(0, i).Trim()] = ln.Substring(i + 1).Trim();
                }
            }
            string s = Get("seed", "0");
            if (!int.TryParse(s, out Seed)) { Seed = 0; Problems += " bad-seed"; }
            string f = Get("force", "none");
            Force = f == "ON" || f == "OFF" ? f : "none";
            if (f != Force) Problems += " bad-force";
            string r = Get("f18", "A");
            F18 = r == "B" ? "B" : "A";
            if (r != "A" && r != "B") Problems += " bad-f18";
            string pu = Get("plant_us", "-1");
            if (!int.TryParse(pu, out PlantUs) || PlantUs < -1) { PlantUs = -1; Problems += " bad-plant_us"; }
        }

        internal static string Get(string key, string fallback)
        {
            string v;
            return Kv.TryGetValue(key, out v) ? v : fallback;
        }
    }
}
#endif
