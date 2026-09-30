using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Threading;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>The playback's in-game test levers (design S8 T39, T40, T41,
    /// T49, T50, T51), reached ONLY from the broadcast seat's identity-gated
    /// `[Broadcast] TestPlayerCards = motion:...` value. A lever installs a
    /// local fake transport (no request leaves the process), seeds a synthetic
    /// binder, and drives the product path: the read, the atlas answer, the
    /// worker decode, the band uploads, the overlays and the clock. Mutant
    /// arms are flags set here and cleared by the next lever.</summary>
    internal static partial class PlayerCardMotion
    {
        internal static bool DevFrameByTicks;       // T41 mutant: the index counted in ticks
        internal static bool DevSkipSpriteDestroy;  // T40 mutant: eviction leaves the cell sprites
        internal static bool DevT39KeyByBind;       // T39 mutant: clip state keyed by the tile's bindSeq
        internal static bool DevNoCooldown;         // T49 mutant: a 429 stops the visit only
        internal static bool DevT51AnchorToRect;    // T51 mutant: the overlay laid over the Image's own rect
        internal static bool DevAnimOff;            // the AnimatedCosmetics toggle without writing the cfg

        private sealed class Fake
        {
            internal int ReadStatus = 200, AtlasStatus = 200, PendingFirst, Frames = 120, Ms = 50, Delay = 1, RevBump;
            internal string ReadError, AtlasError;
            internal byte[] CardPng, TilePng;
            internal string Source = "synthetic";
            internal readonly Dictionary<string, int> PendingSeen = new Dictionary<string, int>(StringComparer.Ordinal);
        }
        private static Fake DevFake;
        private static readonly List<KeyValuePair<int, Action>> devDue = new List<KeyValuePair<int, Action>>();
        private static int devReads, devAtlases;
        private static readonly List<double> devReadTimes = new List<double>();
        private static double devStallMsPerMiB;
        private static bool devMeasuring;
        private static readonly List<double> devSlices = new List<double>();
        private static int devBands;
        private static readonly Dictionary<string, double> devReadyAt = new Dictionary<string, double>(StringComparer.Ordinal);
        private static int devRun;   // the running lever's number; a new lever supersedes it

        // -- hooks the product file calls (inert unless a lever set them) ---------

        private static long DevTickStart() { return devMeasuring ? Stopwatch.GetTimestamp() : 0; }

        private static void DevTickEnd(long t0)
        {
            if (!devMeasuring || t0 == 0) return;
            devSlices.Add((Stopwatch.GetTimestamp() - t0) * 1000.0 / Stopwatch.Frequency);
        }

        private static void DevPumpDue()
        {
            if (devDue.Count == 0) return;
            int f = Time.frameCount;
            for (int i = 0; i < devDue.Count;)
            {
                if (devDue[i].Key > f) { i++; continue; }
                var act = devDue[i].Value;
                devDue.RemoveAt(i);
                try { act(); } catch (Exception ex) { Plugin.Log.LogWarning("[MOTION-DEV] fake answer threw " + ex.Message); }
            }
        }

        private static void DevOnClear() { devDue.Clear(); }

        private static void DevCount(bool read)
        {
            if (read) { devReads++; devReadTimes.Add(Time.unscaledTime); }
            else devAtlases++;
        }

        private static int DevStatus(int code) { return DevNoCooldown && code == 429 ? 500 : code; }

        private static void DevStall(int bytes)
        {
            devBands++;
            if (devStallMsPerMiB <= 0) return;
            // the calibrated arm of T50 (finding M9): a deterministic busy wait
            // proportional to the band's bytes stands in for a slow upload
            double ms = bytes / 1048576.0 * devStallMsPerMiB;
            long until = Stopwatch.GetTimestamp() + (long)(ms * Stopwatch.Frequency / 1000.0);
            while (Stopwatch.GetTimestamp() < until) { }
        }

        private static void DevAtlasReady(string key, string size)
        {
            if (DevFake != null) devReadyAt[key] = Time.unscaledTime;
        }

        private static void DevFakeRead(List<string> ids, string locale, Action<bool, string> cb)
        {
            var f = DevFake;
            string resp;
            bool ok = f.ReadStatus == 200;
            if (ok)
            {
                var parts = new List<string>(ids.Count);
                string rev = "d" + f.Frames + "x" + f.Ms + "r" + f.RevBump;
                foreach (var id in ids) parts.Add(id + ":dev:" + rev + ":" + f.Frames + ":" + f.Ms);
                resp = "{\"m\":\"" + string.Join("|", parts.ToArray()) + "\"}";
            }
            else resp = "HTTP " + f.ReadStatus + ": {\"detail\":{\"error\":\"" + (f.ReadError ?? "refused") + "\",\"retry_after\":1}}";
            devDue.Add(new KeyValuePair<int, Action>(Time.frameCount + f.Delay, () => cb(ok, resp)));
        }

        private static void DevFakeAtlas(string printId, string size, Action<bool, byte[], long, string> cb)
        {
            var f = DevFake;
            string k = printId + "/" + size;
            int seen;
            f.PendingSeen.TryGetValue(k, out seen);
            f.PendingSeen[k] = seen + 1;
            Action act;
            if (seen < f.PendingFirst)
                act = () => cb(false, null, 503, "HTTP 503: {\"detail\":{\"error\":\"motion_pending\",\"retry_after\":1}}");
            else if (f.AtlasStatus != 200)
                act = () => cb(false, null, f.AtlasStatus, "HTTP " + f.AtlasStatus + ": {\"detail\":{\"error\":\"" + (f.AtlasError ?? "refused") + "\"}}");
            else
            {
                var png = size == "card" ? f.CardPng : f.TilePng;
                act = () => cb(png != null, png, png != null ? 200 : 404, png != null ? null : "HTTP 404: no fixture");
            }
            devDue.Add(new KeyValuePair<int, Action>(Time.frameCount + f.Delay, act));
        }

        // -- the lever -------------------------------------------------------------

        /// <summary>`motion:<verb>[,k=v...]`: seed, card, close, t39, t40, t41,
        /// t49, t50, t51, off (uninstall the fake and clear the mutants).</summary>
        internal static void DevRun(string spec)
        {
            var o = DevOpts(spec);
            string verb = o.ContainsKey("_verb") ? o["_verb"] : "";
            devRun++;
            DevFrameByTicks = DevSkipSpriteDestroy = DevT39KeyByBind = DevNoCooldown = DevT51AnchorToRect = DevAnimOff = false;
            devStallMsPerMiB = 0; frameGate.Max = 1; devMeasuring = false;
            Plugin.Log.LogInfo("[MOTION-DEV] lever " + spec);
            try
            {
                switch (verb)
                {
                    case "seed": DevSeed(o); return;
                    case "card": PlayerCardsUI.DevMotionAct("card", DevInt(o, "i", 0)); return;
                    case "close": PlayerCardsUI.DevMotionAct("close", 0); return;
                    case "off": DevFake = null; Clear(); Plugin.Log.LogInfo("[MOTION-DEV] fake transport off"); return;
                    case "t51": DevT51(o.ContainsKey("mutant")); return;
                    case "t50": Plugin.Instance.StartCoroutine(DevT50(devRun, o)); return;
                    case "t41": Plugin.Instance.StartCoroutine(DevT41(devRun, o)); return;
                    case "t40": Plugin.Instance.StartCoroutine(DevT40(devRun, o)); return;
                    case "t39": Plugin.Instance.StartCoroutine(DevT39(devRun, o)); return;
                    case "t49": Plugin.Instance.StartCoroutine(DevT49(devRun, o)); return;
                }
                Plugin.Log.LogWarning("[MOTION-DEV] unknown verb '" + verb + "'");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[MOTION-DEV] FAIL: lever threw " + ex); }
        }

        private static Dictionary<string, string> DevOpts(string spec)
        {
            var o = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var parts = (spec ?? "").Split(',');
            for (int i = 0; i < parts.Length; i++)
            {
                string p = parts[i].Trim();
                if (p.Length == 0) continue;
                int eq = p.IndexOf('=');
                if (i == 0) { o["_verb"] = p.ToLowerInvariant(); continue; }
                if (eq < 0) o[p] = "1"; else o[p.Substring(0, eq).Trim()] = p.Substring(eq + 1).Trim();
            }
            return o;
        }

        private static int DevInt(Dictionary<string, string> o, string k, int d)
        {
            string v; int r;
            return o.TryGetValue(k, out v) && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out r) ? r : d;
        }

        private static double DevDouble(Dictionary<string, string> o, string k, double d)
        {
            string v; double r;
            return o.TryGetValue(k, out v) && double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out r) ? r : d;
        }

        /// <summary>seed[,n=20][,frames=120][,ms=50][,noise][,card=file][,tile=file][,delay=1]:
        /// a synthetic binder of n prints whose faces carry face_rev "dev", and
        /// the fake transport answering every read with motion and every atlas
        /// with a generated atlas (or a file from BepInEx/dance_corpus).</summary>
        private static void DevSeed(Dictionary<string, string> o)
        {
            var f = new Fake { Frames = DevInt(o, "frames", 120), Ms = DevInt(o, "ms", 50), Delay = Math.Max(0, DevInt(o, "delay", 1)) };
            bool noise = o.ContainsKey("noise");
            string cardFile, tileFile;
            o.TryGetValue("card", out cardFile); o.TryGetValue("tile", out tileFile);
            f.CardPng = DevLoad(cardFile) ?? DevAtlasPng(f.Frames, "card", noise, 1);
            f.TilePng = DevLoad(tileFile) ?? DevAtlasPng(f.Frames, "tile", noise, 2);
            if (cardFile != null || tileFile != null) f.Source = "file card=" + (cardFile ?? "-") + " tile=" + (tileFile ?? "-");
            else if (noise) f.Source = "synthetic+noise";
            Clear();
            DevFake = f;
            devReads = devAtlases = 0; devReadTimes.Clear(); devReadyAt.Clear();
            int n = DevInt(o, "n", 20);
            PlayerCardsUI.DevMotionAct("seed", n);
            Plugin.Log.LogInfo("[MOTION-DEV] seeded n=" + n + " frames=" + f.Frames + " ms=" + f.Ms + " card_png=" + (f.CardPng != null ? f.CardPng.Length : 0)
                + "B tile_png=" + (f.TilePng != null ? f.TilePng.Length : 0) + "B source=" + f.Source + " delay=" + f.Delay);
        }

        private static byte[] DevLoad(string name)
        {
            if (string.IsNullOrEmpty(name) || name.IndexOf("..", StringComparison.Ordinal) >= 0) return null;
            try
            {
                string p = Path.Combine(Path.Combine(BepInEx.Paths.BepInExRootPath, "dance_corpus"), name);
                return File.Exists(p) ? File.ReadAllBytes(p) : null;
            }
            catch { return null; }
        }

        /// <summary>A generated atlas of the shape the server serves: each cell
        /// its own hue with a bar that moves across the frames; `noise` adds
        /// per-pixel noise so the PNG is as incompressible as a real one.</summary>
        private static byte[] DevAtlasPng(int frames, string size, bool noise, int seed)
        {
            int cell, w, h;
            if (!PlayerCardMotionCore.AtlasShape(frames, size, out cell, out w, out h)) return null;
            var rgba = new byte[w * h * 4];
            uint x = (uint)(seed * 747796405 + 2891336453u);
            for (int k = 0; k < frames; k++)
            {
                int cx = (k % PlayerCardMotionCore.ATLAS_COLUMNS) * cell, cy = (k / PlayerCardMotionCore.ATLAS_COLUMNS) * cell;
                Color32 c = Color.HSVToRGB((float)k / frames, 0.7f, 0.9f);
                int bar = frames > 1 ? k * (cell - 8) / (frames - 1) : 0;
                for (int y = 0; y < cell; y++)
                    for (int xx = 0; xx < cell; xx++)
                    {
                        int i = ((cy + y) * w + cx + xx) * 4;
                        int nz = 0;
                        if (noise) { x ^= x << 13; x ^= x >> 17; x ^= x << 5; nz = (int)(x & 31); }
                        bool onBar = xx >= bar && xx < bar + 8;
                        rgba[i] = (byte)(onBar ? 255 : Math.Min(255, c.r + nz));
                        rgba[i + 1] = (byte)(onBar ? 255 : Math.Min(255, c.g + nz));
                        rgba[i + 2] = (byte)(onBar ? 255 : Math.Min(255, c.b + nz));
                        rgba[i + 3] = 255;
                    }
            }
            return ScrPng.EncodeRgba(rgba, w, h, false);
        }

        private static void DevEnsureSeed(Dictionary<string, string> o, int n, int frames)
        {
            if (DevFake != null && DevFake.Frames == frames && !o.ContainsKey("reseed")) return;
            var so = new Dictionary<string, string>(o, StringComparer.OrdinalIgnoreCase);
            if (!so.ContainsKey("n")) so["n"] = n.ToString(CultureInfo.InvariantCulture);
            if (!so.ContainsKey("frames")) so["frames"] = frames.ToString(CultureInfo.InvariantCulture);
            DevSeed(so);
        }

        private static string DevF(double v) { return v.ToString("F2", CultureInfo.InvariantCulture); }

        private static string DevF3(double v) { return v.ToString("F3", CultureInfo.InvariantCulture); }

        private static void DevStats(List<double> xs, out double max, out double p95)
        {
            max = 0; p95 = 0;
            if (xs.Count == 0) return;
            var s = new List<double>(xs); s.Sort();
            max = s[s.Count - 1];
            p95 = s[Math.Min(s.Count - 1, (int)Math.Ceiling(s.Count * 0.95) - 1)];
        }

        // -- T50: popup atlas hitch (finding M9) -----------------------------------

        /// <summary>t50[,stall=MS_PER_MIB][,max=K][,tileonly][,card=file]: every
        /// PlayerCardMotion tick's main-thread time is measured from the popup's
        /// open (or, tile-only, the visit's start) until the atlas is up and its
        /// first frame shows; PASS when the largest slice is at most 33 ms. The
        /// real measurement is stall=0,max=1; the calibrated arm stall=10 (a
        /// 2 MiB card band then costs 20 ms); its mutant max=2 (two band uploads
        /// in one Unity frame); the control tileonly.</summary>
        private static IEnumerator DevT50(int run, Dictionary<string, string> o)
        {
            DevEnsureSeed(o, 20, DevInt(o, "frames", 120));
            yield return null;
            bool tileOnly = o.ContainsKey("tileonly");
            double stall = DevDouble(o, "stall", 0);
            int max = Math.Max(1, DevInt(o, "max", 1));
            string arm = tileOnly ? "control" : (stall <= 0 ? "real" : (max > 1 ? "mutant" : "calibrated"));
            PlayerCardsUI.DevMotionAct("close", 0);
            Clear();
            devReadyAt.Clear();
            yield return null;
            PlayerCardsUI.DevMotionAct("tab", 0);   // a fresh visit: the page reads again
            // let the page's own atlases land first when the card is measured, so
            // the measured window holds the card's bands and nothing else
            float until = Time.unscaledTime + 30f;
            if (!tileOnly)
            {
                while (Time.unscaledTime < until && run == devRun && devReadyAt.Count < 10) yield return null;
                PlayerCardsUI.DevMotionAct("card", 0);
                yield return null;
            }
            devStallMsPerMiB = stall; frameGate.Max = max;
            devSlices.Clear(); devBands = 0; devMeasuring = true;
            double start = Time.unscaledTime;
            until = Time.unscaledTime + 60f;
            bool ready = false;
            while (Time.unscaledTime < until && run == devRun)
            {
                if (tileOnly) ready = devReadyAt.Count >= 10;
                else foreach (var kv in devReadyAt) if (kv.Key.EndsWith("/card", StringComparison.Ordinal)) ready = true;
                if (ready) { yield return null; yield return null; break; }
                yield return null;
            }
            devMeasuring = false;
            devStallMsPerMiB = 0; frameGate.Max = 1;
            if (run != devRun) yield break;
            double mx, p95;
            DevStats(devSlices, out mx, out p95);
            bool pass = ready && mx <= 33.0;
            Plugin.Log.LogInfo("[MOTION-T50] arm=" + arm + " source=" + (DevFake != null ? DevFake.Source : "-") + " frames=" + (DevFake != null ? DevFake.Frames : 0)
                + " stall_ms_per_mib=" + DevF(stall) + " max_steps=" + max + " bands=" + devBands + " ticks=" + devSlices.Count
                + " max_slice_ms=" + DevF(mx) + " p95_ms=" + DevF(p95) + " ready=" + ready + " ready_after_s=" + DevF(Time.unscaledTime - start)
                + " result=" + (pass ? "PASS" : "FAIL"));
            if (!tileOnly) PlayerCardsUI.DevMotionAct("close", 0);
        }

        // -- T41: the clip length at a low frame rate ------------------------------

        /// <summary>t41[,fps=10][,mutant]: with the frame rate capped, the clip
        /// of the first tile -- a clip of this visit, seen PLAYING -- ends at
        /// t0 + N x period within the frames the seat actually ran (finding
        /// S2F9). An arm whose seen frame rate stays above 1.5x the cap fails:
        /// the cap never held (the broadcast seat's frame-rate director
        /// re-asserts its own cap over this one). Mutant: the index counted in
        /// ticks.</summary>
        private static IEnumerator DevT41(int run, Dictionary<string, string> o)
        {
            DevEnsureSeed(o, 20, DevInt(o, "frames", 120));
            int fps = Math.Max(5, DevInt(o, "fps", 10));
            int oldRate = Application.targetFrameRate, oldVsync = QualitySettings.vSyncCount;
            QualitySettings.vSyncCount = 0; Application.targetFrameRate = fps;
            DevFrameByTicks = o.ContainsKey("mutant");
            try
            {
                yield return null;
                PlayerCardsUI.DevMotionAct("close", 0);
                // Finding S2F9: the previous visit's clips go first. Read straight
                // after TabEntered, before the next tick's Sync cleared them, the
                // first tile's DONE clip of the LAST visit ended the wait below at
                // once and its old t0 was measured (unity_frames=0 in every arm).
                Clear();
                yield return null;
                PlayerCardsUI.DevMotionAct("tab", 0);
                double tabAt = Time.unscaledTime;
                string pid = PlayerCardsUI.DevMotionFirstPrint();
                MotionClips.Clip c = null;
                float until = Time.unscaledTime + 60f;
                while (Time.unscaledTime < until && run == devRun && (c == null || c.State == ClipState.None)) { if (pid != null) clips.TryGet(pid, out c); yield return null; }
                if (c == null || run != devRun) { Plugin.Log.LogInfo("[MOTION-T41] result=FAIL reason=no-clip"); yield break; }
                if (c.State != ClipState.Playing || c.T0 < tabAt)
                {
                    Plugin.Log.LogInfo("[MOTION-T41] result=FAIL reason=stale-clip state=" + c.State + " t0_after_visit_s=" + DevF3(c.T0 - tabAt));
                    yield break;
                }
                double t0 = c.T0, expect = t0 + c.Frames * c.Ms / 1000.0, done = -1;
                int frames0 = Time.frameCount;
                double start = Time.unscaledTime, prev1 = start, prev2 = start;
                until = Time.unscaledTime + 60f;
                while (Time.unscaledTime < until && run == devRun)
                {
                    double nowT = Time.unscaledTime;
                    if (c.State == ClipState.Done) { done = nowT; break; }
                    prev2 = prev1; prev1 = nowT;
                    yield return null;
                }
                int unityFrames = Time.frameCount - frames0;
                double span = (done < 0 ? Time.unscaledTime : done) - start;
                double seenFps = span > 0 ? unityFrames / span : 0;
                bool capHeld = seenFps <= fps * 1.5;
                double err = done < 0 ? double.PositiveInfinity : done - expect;
                // The first tick at or after `expect` (real time) sets DONE and
                // this loop sees it in that frame or the next, so the error is
                // under the last two frame intervals the seat actually ran -- not
                // 1/fps: a seat that renders slower than the cap still ends the
                // clip on time, and one that renders faster never held the cap.
                double bound = done < 0 ? 0 : done - prev2;
                bool pass = capHeld && done >= 0 && err >= -0.002 && err < bound + 0.002;
                Plugin.Log.LogInfo("[MOTION-T41] fps=" + fps + " mutant=" + DevFrameByTicks + " frames=" + c.Frames + " ms=" + c.Ms + " expect_s=" + DevF(expect - t0)
                    + " observed_s=" + (done < 0 ? "none" : DevF3(done - t0)) + " err_s=" + (done < 0 ? "inf" : DevF3(err)) + " bound_s=" + DevF3(bound)
                    + " unity_frames=" + unityFrames + " seen_fps=" + DevF(seenFps) + " cap_held=" + capHeld
                    + " result=" + (pass ? "PASS" : "FAIL"));
            }
            finally
            {
                DevFrameByTicks = false;
                Application.targetFrameRate = oldRate; QualitySettings.vSyncCount = oldVsync;
            }
        }

        // -- T40: memory baseline over cycles --------------------------------------

        private static void DevCounts(out int tex, out int spr, out int roots)
        {
            tex = spr = roots = 0;
            foreach (var t in Resources.FindObjectsOfTypeAll<Texture2D>()) if (t != null && t.name == "DcMoTex") tex++;
            foreach (var s in Resources.FindObjectsOfTypeAll<Sprite>()) if (s != null && s.name == "DcMoCell") spr++;
            foreach (var g in Resources.FindObjectsOfTypeAll<GameObject>()) if (g != null && g.name == "DcMo") roots++;
        }

        /// <summary>t40[,cycles=100][,mutant][,single]: page, open and tab cycles,
        /// the fake bumping the motion revision each cycle so every cycle
        /// downloads, decodes, evicts and destroys; after the teardown the
        /// counts of band textures, cell sprites and overlay roots return to the
        /// baseline and the budget never held more than 64 MiB. Mutant: the
        /// eviction skips the sprite destroy. Control: a single visit.</summary>
        private static IEnumerator DevT40(int run, Dictionary<string, string> o)
        {
            DevEnsureSeed(o, 20, DevInt(o, "frames", 40));
            DevSkipSpriteDestroy = o.ContainsKey("mutant");
            bool single = o.ContainsKey("single");
            int cycles = single ? 1 : Math.Max(1, DevInt(o, "cycles", 100));
            PlayerCardsUI.DevMotionAct("close", 0);
            Clear();
            yield return null; yield return null;
            int tex0, spr0, roots0;
            DevCounts(out tex0, out spr0, out roots0);
            long maxHeld = 0;
            for (int i = 0; i < cycles && run == devRun; i++)
            {
                DevFake.RevBump = i;
                devReadyAt.Clear();
                if (!single) PlayerCardsUI.DevMotionAct(i % 2 == 0 ? "next" : "prev", 0); else PlayerCardsUI.DevMotionAct("tab", 0);
                float until = Time.unscaledTime + 8f;
                while (Time.unscaledTime < until && run == devRun && devReadyAt.Count < 10) { maxHeld = Math.Max(maxHeld, budget.Total); yield return null; }
                if (single) break;
                PlayerCardsUI.DevMotionAct("card", i % 10);
                until = Time.unscaledTime + 8f;
                bool card = false;
                while (Time.unscaledTime < until && run == devRun && !card)
                {
                    foreach (var kv in devReadyAt) if (kv.Key.EndsWith("/card", StringComparison.Ordinal)) card = true;
                    maxHeld = Math.Max(maxHeld, budget.Total);
                    yield return null;
                }
                PlayerCardsUI.DevMotionAct("close", 0);
                PlayerCardsUI.DevMotionAct("tab", 0);
                yield return null;
            }
            if (run != devRun) { DevSkipSpriteDestroy = false; yield break; }
            int texMid, sprMid, rootsMid;
            DevCounts(out texMid, out sprMid, out rootsMid);
            long evictions = budget.Evictions;
            Clear();   // the teardown every close path runs
            yield return null; yield return null;
            int tex1, spr1, roots1;
            DevCounts(out tex1, out spr1, out roots1);
            bool pass = tex1 == tex0 && spr1 == spr0 && roots1 == roots0 && maxHeld <= PlayerCardMotionCore.CACHE_CAP_BYTES;
            Plugin.Log.LogInfo("[MOTION-T40] cycles=" + cycles + " mutant=" + DevSkipSpriteDestroy + " baseline tex/spr/roots=" + tex0 + "/" + spr0 + "/" + roots0
                + " before-teardown=" + texMid + "/" + sprMid + "/" + rootsMid + " after=" + tex1 + "/" + spr1 + "/" + roots1
                + " max_held_mib=" + DevF(maxHeld / 1048576.0) + " evictions=" + evictions + " reads=" + devReads + " atlases=" + devAtlases
                + " result=" + (pass ? "PASS" : "FAIL"));
            DevSkipSpriteDestroy = false;
        }

        // -- T39: the visit truth table through the real hooks ---------------------

        private static int devT39Fails;

        private static void DevStep(string name, int before, int expectDelta)
        {
            int d = visit.Serial - before;
            bool ok = d == expectDelta;
            if (!ok) devT39Fails++;
            Plugin.Log.LogInfo("[MOTION-T39] step=" + name + " delta=" + d + " expect=" + expectDelta + " " + (ok ? "PASS" : "FAIL"));
        }

        private static IEnumerator DevFrames(int n) { for (int i = 0; i < n; i++) yield return null; }

        /// <summary>t39[,mutant]: each S5.3 event through the hook that fires it
        /// in the product, with the serial's expected move; then the re-arm
        /// rows: a DONE clip is not replayed by a repaint (a new bindSeq) and
        /// IS replayed after a page change. Mutant: clips keyed by bindSeq.</summary>
        private static IEnumerator DevT39(int run, Dictionary<string, string> o)
        {
            DevEnsureSeed(o, 20, 10);
            DevT39KeyByBind = o.ContainsKey("mutant");
            devT39Fails = 0;
            PlayerCardsUI.DevMotionAct("close", 0);
            PlayerCardsUI.DevMotionAct("page0", 0);
            yield return DevFrames(3);
            int s;
            s = visit.Serial; PlayerCardsUI.DevMotionAct("tab", 0); yield return DevFrames(3); DevStep("tab-entered", s, 1);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("next", 0); yield return DevFrames(3); DevStep("page-next", s, 1);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("prev", 0); yield return DevFrames(3); DevStep("page-prev-return", s, 1);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("view", 0); yield return DevFrames(3); DevStep("subview-switch", s, 1);
            PlayerCardsUI.DevMotionAct("binder", 0); yield return DevFrames(3);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("repaint", 0); yield return DevFrames(3); DevStep("repaint", s, 0);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("refresh", 0); yield return DevFrames(3); DevStep("api-refresh", s, 0);
            PlayerCardsUI.DevMotionAct("next", 0); yield return DevFrames(3);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("sort", 0); yield return DevFrames(3); DevStep("sort-to-page-1", s, 0);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("card", 0); yield return DevFrames(3); DevStep("popup-open", s, 0);
            s = visit.Serial; PlayerCardsUI.DevMotionAct("close", 0); yield return DevFrames(3); DevStep("popup-close", s, 0);
            s = visit.Serial; DevAnimOff = true; yield return DevFrames(3); DevAnimOff = false; yield return DevFrames(3); DevStep("animated-toggle", s, 0);
            s = visit.Serial; foreach (var k in new List<string>(atlases.Keys)) { budget.Remove(k, releaseKey); break; } yield return DevFrames(3); DevStep("eviction", s, 0);
            // closing the overlay arms the next visit; the tab's own throttled
            // tick counts it (OnTabEntered), once, and nothing is asked before
            s = visit.Serial; PlayerCardsUI.DevMotionAct("overlay-close", 0);
            float wait = Time.unscaledTime + 5f;
            while (Time.unscaledTime < wait && run == devRun && visit.Serial == s) yield return null;
            yield return DevFrames(3); DevStep("overlay-reopen", s, 1);
            PlayerCardsUI.DevMotionAct("seed", 20);   // the reopen's own collection fetch may have replaced the synthetic binder
            yield return DevFrames(3);
            // the re-arm rows: the first tile's overlay shows, then hides (DONE)
            GameObject face = PlayerCardsUI.DevMotionFirstFace();
            bool shown = false, doneSeen = false;
            float until = Time.unscaledTime + 30f;
            while (Time.unscaledTime < until && run == devRun && !doneSeen)
            {
                bool now = DevOverlayShownFor(face);
                if (now) shown = true; else if (shown) doneSeen = true;
                yield return null;
            }
            PlayerCardsUI.DevMotionAct("repaint", 0);
            float look = Time.unscaledTime + 1.5f;
            bool replayedByRepaint = false;
            while (Time.unscaledTime < look && run == devRun && !replayedByRepaint) { replayedByRepaint = DevOverlayShownFor(face); yield return null; }
            bool rowRepaint = doneSeen && !replayedByRepaint;
            if (!rowRepaint) devT39Fails++;
            Plugin.Log.LogInfo("[MOTION-T39] row=repaint-does-not-rearm done_seen=" + doneSeen + " replayed=" + replayedByRepaint + " " + (rowRepaint ? "PASS" : "FAIL"));
            PlayerCardsUI.DevMotionAct("next", 0); yield return DevFrames(3);
            PlayerCardsUI.DevMotionAct("prev", 0);
            until = Time.unscaledTime + 10f;
            bool replayedByPage = false;
            while (Time.unscaledTime < until && run == devRun && !replayedByPage) { replayedByPage = DevOverlayShownFor(PlayerCardsUI.DevMotionFirstFace()); yield return null; }
            if (!replayedByPage) devT39Fails++;
            Plugin.Log.LogInfo("[MOTION-T39] row=page-change-rearms replayed=" + replayedByPage + " " + (replayedByPage ? "PASS" : "FAIL"));
            Plugin.Log.LogInfo("[MOTION-T39] mutant=" + DevT39KeyByBind + " fails=" + devT39Fails + " result=" + (devT39Fails == 0 ? "PASS" : "FAIL"));
            DevT39KeyByBind = false;
        }

        private static bool DevOverlayShownFor(GameObject face)
        {
            if (face == null) return false;
            Overlay ov;
            return overlays.TryGetValue(face.GetInstanceID(), out ov) && ov.Go != null && ov.Go.activeSelf;
        }

        // -- T49: the 429 cooldown across visits -----------------------------------

        /// <summary>t49[,mutant][,control]: the read answers 429; for the next 60 s
        /// no motion request is sent across page changes, and the first visit
        /// after it sends one read. Control: no 429, one read per visit.
        /// Mutant: a 429 stops the visit only.</summary>
        private static IEnumerator DevT49(int run, Dictionary<string, string> o)
        {
            DevEnsureSeed(o, 20, 10);
            bool control = o.ContainsKey("control");
            DevNoCooldown = o.ContainsKey("mutant");
            PlayerCardsUI.DevMotionAct("close", 0);
            Clear();
            DevFake.ReadStatus = control ? 200 : 429; DevFake.ReadError = control ? null : "rate_limited";
            devReads = 0; devReadTimes.Clear();
            PlayerCardsUI.DevMotionAct("page0", 0);
            PlayerCardsUI.DevMotionAct("tab", 0);
            float until = Time.unscaledTime + 10f;
            while (Time.unscaledTime < until && run == devRun && devReads == 0) yield return null;
            double first = devReadTimes.Count > 0 ? devReadTimes[0] : Time.unscaledTime;
            yield return DevFrames(3);
            DevFake.ReadStatus = 200; DevFake.ReadError = null;   // the server would answer now: only the cooldown holds the client back
            int visits = 0;
            for (int i = 0; i < 5 && run == devRun; i++)
            {
                PlayerCardsUI.DevMotionAct(i % 2 == 0 ? "next" : "prev", 0);
                visits++;
                float w = Time.unscaledTime + 8f;
                while (Time.unscaledTime < w && run == devRun) yield return null;
            }
            int inWindow = 0;
            foreach (double t in devReadTimes) if (t > first && t < first + PlayerCardMotionCore.COOLDOWN_429_S) inWindow++;
            while (Time.unscaledTime < first + PlayerCardMotionCore.COOLDOWN_429_S + 1.0 && run == devRun) yield return null;
            int before = devReads;
            // Finding S2F11: a real page change. After the five alternations the
            // binder sits on its second page -- with the 20 seeded prints the
            // last one, where "next" is clamped, moves no visit and reads
            // nothing (reads_after=0 in every arm).
            PlayerCardsUI.DevMotionAct(visits % 2 == 0 ? "next" : "prev", 0);
            until = Time.unscaledTime + 5f;
            while (Time.unscaledTime < until && run == devRun && devReads == before) yield return null;
            int after = devReads - before;
            bool pass = control ? (inWindow == visits && after == 1) : (inWindow == 0 && after == 1);
            Plugin.Log.LogInfo("[MOTION-T49] arm=" + (control ? "control" : (DevNoCooldown ? "mutant" : "429")) + " first_read_status=" + (control ? 200 : 429)
                + " page_changes=" + visits + " reads_in_60s=" + inWindow + " reads_after=" + after + " result=" + (pass ? "PASS" : "FAIL"));
            DevNoCooldown = false;
        }

        // -- T51: the overlay over a letterboxed face --------------------------------

        /// <summary>t51[,mutant]: a face slot exactly 750:1050, then wider, then
        /// taller; the overlay placed by the product path must cover the drawn
        /// picture's window within 1 unit. The drawn picture is read back from
        /// the Image's own mesh (OnPopulateMesh through reflection), so the
        /// check does not share the placement's arithmetic.</summary>
        private static void DevT51(bool mutant)
        {
            DevT51AnchorToRect = mutant;
            var parent = NativeUI.OverlayRoot;
            var tex = new Texture2D(75, 105, TextureFormat.RGBA32, false);
            var spr = Sprite.Create(tex, new Rect(0, 0, 75, 105), new Vector2(0.5f, 0.5f), 100f);
            var shapes = new[] { new Vector2(375, 525), new Vector2(600, 300), new Vector2(240, 600) };
            string[] names = { "exact", "wider", "taller" };
            int fails = 0;
            try
            {
                for (int i = 0; i < shapes.Length; i++)
                {
                    GameObject face = null;
                    try
                    {
                        face = parent != null ? UIFactory.CreatePanel("T51Face", parent, Color.white) : new GameObject("T51Face", typeof(RectTransform));
                        var frt = face.GetComponent<RectTransform>();
                        frt.anchorMin = frt.anchorMax = frt.pivot = new Vector2(0.5f, 0.5f);
                        frt.sizeDelta = shapes[i];
                        PlayerCardFaces.SetFace(face, spr);
                        var ov = PlayerCardsUI.CreateMotionOverlay(face);
                        PlayerCardsUI.PlaceMotionOverlay(face, ov);
                        Rect drawn; string how;
                        if (!DevDrawnRect(face, out drawn, out how)) { fails++; Plugin.Log.LogInfo("[MOTION-T51] slot=" + names[i] + " result=FAIL reason=no-mesh"); continue; }
                        var want = new Rect(drawn.xMin + PlayerCardMotionCore.WIN_X * drawn.width,
                                            drawn.yMax - (PlayerCardMotionCore.WIN_Y + PlayerCardMotionCore.WIN_H) * drawn.height,
                                            PlayerCardMotionCore.WIN_W * drawn.width, PlayerCardMotionCore.WIN_H * drawn.height);
                        var ort = ov.GetComponent<RectTransform>();
                        Vector2 c = (Vector2)ort.localPosition;
                        Rect r = ort.rect;
                        var got = new Rect(c.x + r.xMin, c.y + r.yMin, r.width, r.height);
                        float err = Mathf.Max(Mathf.Max(Mathf.Abs(got.xMin - want.xMin), Mathf.Abs(got.xMax - want.xMax)),
                                              Mathf.Max(Mathf.Abs(got.yMin - want.yMin), Mathf.Abs(got.yMax - want.yMax)));
                        bool ok = err <= 1f;
                        if (!ok) fails++;
                        Plugin.Log.LogInfo("[MOTION-T51] slot=" + names[i] + " size=" + shapes[i].x + "x" + shapes[i].y + " drawn=" + DevF(drawn.width) + "x" + DevF(drawn.height)
                            + " via=" + how + " err=" + DevF(err) + " " + (ok ? "PASS" : "FAIL"));
                    }
                    finally { if (face != null) UnityEngine.Object.Destroy(face); }
                }
            }
            finally
            {
                UnityEngine.Object.Destroy(spr); UnityEngine.Object.Destroy(tex);
                Plugin.Log.LogInfo("[MOTION-T51] mutant=" + mutant + " fails=" + fails + " result=" + (fails == 0 ? "PASS" : "FAIL"));
                DevT51AnchorToRect = false;
            }
        }

        /// <summary>The mutant placement of T51: the window fractions of the
        /// Image's own rect, ignoring the letterbox the picture is drawn in.</summary>
        internal static void DevPlaceByRect(GameObject face, GameObject child)
        {
            var frt = face.GetComponent<RectTransform>(); var crt = child.GetComponent<RectTransform>();
            if (frt == null || crt == null) return;
            Rect r = frt.rect;
            crt.anchoredPosition = new Vector2((PlayerCardMotionCore.WIN_X + PlayerCardMotionCore.WIN_W / 2f - 0.5f) * r.width,
                                               (0.5f - PlayerCardMotionCore.WIN_Y - PlayerCardMotionCore.WIN_H / 2f) * r.height);
            crt.sizeDelta = new Vector2(PlayerCardMotionCore.WIN_W * r.width, PlayerCardMotionCore.WIN_H * r.height);
        }

        private static bool DevDrawnRect(GameObject face, out Rect drawn, out string how)
        {
            drawn = default(Rect); how = "mesh";
            try
            {
                var tImg = UIFactory.tImage;
                var img = tImg != null ? face.GetComponent(tImg) : null;
                if (img == null) return false;
                var tVH = tImg.Assembly.GetType("UnityEngine.UI.VertexHelper");
                var vh = Activator.CreateInstance(tVH);
                var bf = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
                var pop = tImg.GetMethod("OnPopulateMesh", bf, null, new[] { tVH }, null);
                pop.Invoke(img, new[] { vh });
                int n = (int)tVH.GetProperty("currentVertCount").GetValue(vh, null);
                var populate = tVH.GetMethod("PopulateUIVertex");
                var tVert = populate.GetParameters()[0].ParameterType.GetElementType();
                var fPos = tVert.GetField("position");
                float x0 = float.MaxValue, y0 = float.MaxValue, x1 = float.MinValue, y1 = float.MinValue;
                for (int i = 0; i < n; i++)
                {
                    var args = new object[] { Activator.CreateInstance(tVert), i };
                    populate.Invoke(vh, args);
                    var pos = (Vector3)fPos.GetValue(args[0]);
                    x0 = Mathf.Min(x0, pos.x); y0 = Mathf.Min(y0, pos.y); x1 = Mathf.Max(x1, pos.x); y1 = Mathf.Max(y1, pos.y);
                }
                try { (vh as IDisposable)?.Dispose(); } catch { }
                if (n < 4) return false;
                drawn = new Rect(x0, y0, x1 - x0, y1 - y0);
                return true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[MOTION-T51] mesh read threw " + ex.Message); return false; }
        }
    }
}
