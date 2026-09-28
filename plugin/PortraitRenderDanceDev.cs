using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Dance cards: the capture's dev lever and its VM tests (broadcast
    /// identity only, through TickTestPlayerCards like every portrait verb;
    /// refused by DevLeverBlocked at dispatch). A lever capture always runs in
    /// LOCAL mode: nothing is uploaded, the still, the container and the frame
    /// hashes go to BepInEx/dance_corpus/.
    ///
    ///   TestPlayerCards = portrait:dance[,sku=dance_floss|all][,tag=NAME][,hold=N]
    ///                     [,fps=N][,fdt=SECONDS][,tclock]              T36 (tclock: the mutant arm)
    ///                     [,faultat=K][,gatestartonly]                 T37 (gatestartonly: the mutant arm)
    ///                     [,injectpv][,m1=cloneonly]                   T38/M1 (cloneonly: the mutant arm)
    ///                     [,selffail]                                  T48 (a local refusal, remembered)
    ///                     [,matteq][,matteqflip]                       the matte equality (matteqflip: its negative arm)
    ///                     [,faultframe=K][,teardownmutant]             T45's job teardown arm, L1's order (teardownmutant: the mutant arm)
    ///                     [,multi=K][,jobs=N]                          S2F3 evidence: K same-state repeats of each frame's black pass compared; N job workers
    ///                     [,msaa4]                                     S2F3: T36's mutant arm, the frames and the still through the old 4x MSAA targets
    ///   TestPlayerCards = portrait:dance,t38[,mutant]                  T38's TryGetPose harness
    ///   TestPlayerCards = portrait:dance,decide[,sku=S][,nomemory][,recolor][,stored=dance|base|none]   T48's decision probe
    ///
    /// Sentinels: [DANCE-CAPTURE], [DANCE-ROOTS], [DANCE-MATTEQ], [DANCE-T38],
    /// [DANCE-T48]. The mutant arms exist only here: every one is a field of a
    /// DanceOpts the lever built, or a DanceEmotes flag the t38 call sets and
    /// clears itself; the product path never builds either.
    /// </summary>
    internal static partial class PortraitRender
    {
        private static string DanceCorpusDir()
        {
            string d = Path.Combine(BepInEx.Paths.BepInExRootPath, "dance_corpus");
            Directory.CreateDirectory(d);
            return d;
        }

        internal static void DanceDevRun(string spec)
        {
            var parts = spec.Split(',');
            var opt = new DanceOpts { local = true, tag = "lever" };
            string sku = "dance_floss";
            string sub = null;
            bool mutant = false, nomemory = false, recolor = false;
            string stored = "none";
            for (int i = 1; i < parts.Length; i++)
            {
                string p = parts[i].Trim().ToLowerInvariant();
                if (p.Length == 0) continue;
                int iv; float fv;
                if (p == "t38" || p == "decide") sub = p;
                else if (p == "mutant") mutant = true;
                else if (p == "nomemory") nomemory = true;
                else if (p == "recolor") recolor = true;
                else if (p.StartsWith("stored=")) stored = p.Substring(7);
                else if (p.StartsWith("sku=")) sku = p.Substring(4);
                else if (p.StartsWith("tag=")) opt.tag = SafeTag(p.Substring(4));
                else if (p.StartsWith("hold=") && int.TryParse(p.Substring(5), out iv)) opt.holdFrames = Mathf.Clamp(iv, 1, 6);
                else if (p.StartsWith("fps=") && int.TryParse(p.Substring(4), out iv)) opt.fps = Mathf.Clamp(iv, 5, 240);
                else if (p.StartsWith("fdt=") && float.TryParse(p.Substring(4), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out fv)) opt.fixedDt = Mathf.Clamp(fv, 0.005f, 0.1f);
                else if (p == "tclock") opt.tclock = true;
                else if (p.StartsWith("faultat=") && int.TryParse(p.Substring(8), out iv)) opt.faultAt = Mathf.Max(0, iv);
                else if (p == "gatestartonly") opt.gateStartOnly = true;
                else if (p == "injectpv") opt.injectPv = true;
                else if (p == "m1=cloneonly") opt.m1CloneOnly = true;
                else if (p == "selffail") opt.selfFail = true;
                else if (p == "matteq") opt.matteq = true;
                else if (p == "matteqflip") { opt.matteq = true; opt.matteqFlip = true; }
                else if (p.StartsWith("faultframe=") && int.TryParse(p.Substring(11), out iv)) opt.faultFrame = Mathf.Max(0, iv);
                else if (p == "teardownmutant") opt.teardownMutant = true;
                else if (p.StartsWith("multi=") && int.TryParse(p.Substring(6), out iv)) opt.multi = Mathf.Clamp(iv, 0, 16);
                else if (p.StartsWith("jobs=") && int.TryParse(p.Substring(5), out iv)) opt.jobs = Mathf.Max(0, iv);
                else if (p == "msaa4") opt.msaa4 = true;
                else Plugin.Log.LogInfo("[DANCE] lever: unknown option '" + p + "'");
            }
            if (sub == "t38") { DanceDevT38(mutant); return; }
            if (sub == "decide") { DanceDevDecide(sku, nomemory, recolor, stored); return; }
            if (sku == "all") { Plugin.Instance.StartCoroutine(DanceDevAll(opt)); return; }
            int idx = DanceIndex(sku);
            if (idx < 0) { Plugin.Log.LogInfo("[DANCE] lever: unknown dance '" + sku + "'"); return; }
            if (!StartDance("lever-" + opt.tag, sku, idx, opt))
                Plugin.Log.LogInfo("[DANCE-CAPTURE] tag=" + opt.tag + " sku=" + sku + " result=not-started reason=\"" + DanceLastResult + " " + LastResult + "\"");
        }

        /// <summary>Every dance in table order, one job at a time (the corpus).</summary>
        private static IEnumerator DanceDevAll(DanceOpts template)
        {
            for (int i = 0; i < DanceEmotes.Defs.Length; i++)
            {
                var o = new DanceOpts
                {
                    local = true, tag = template.tag, holdFrames = template.holdFrames, fps = template.fps, fixedDt = template.fixedDt,
                    tclock = template.tclock, matteq = template.matteq, multi = template.multi, jobs = template.jobs, msaa4 = template.msaa4,
                };
                float waitUntil = Time.realtimeSinceStartup + 30f;
                while ((Rendering || UploadInFlight) && Time.realtimeSinceStartup < waitUntil) yield return null;
                string blocked = DevLeverBlocked(0);
                if (blocked != null) { Plugin.Log.LogInfo("[DANCE-CAPTURE] tag=" + o.tag + " all: stopped before " + DanceEmotes.Defs[i].Sku + ": " + blocked); yield break; }
                if (!StartDance("lever-" + o.tag, DanceEmotes.Defs[i].Sku, i, o))
                {
                    Plugin.Log.LogInfo("[DANCE-CAPTURE] tag=" + o.tag + " sku=" + DanceEmotes.Defs[i].Sku + " result=not-started reason=\"" + DanceLastResult + "\"");
                    yield break;
                }
                yield return null;
                float cap = Time.realtimeSinceStartup + 240f;
                while (Rendering && Time.realtimeSinceStartup < cap) yield return null;
            }
            Plugin.Log.LogInfo("[DANCE-CAPTURE] tag=" + template.tag + " all: done");
        }

        /// <summary>The lever's job teardown arm (L1's order, round two): the
        /// verdict on the job finally's one teardown. PASS when the rig owed at
        /// least one entry, every owed entry was undone while PortraitPose still
        /// named the rig and none after it was cleared, the pose is cleared and
        /// no entry is left.</summary>
        private static string DanceTeardownLine(DanceOpts opt, int owed)
        {
            int under = DanceEmotes.DevUndoneUnderPose, after = DanceEmotes.DevUndoneAfterClear, left = DanceEmotes.AppliedEntryCount;
            bool cleared = !DanceEmotes.PortraitPose.HasValue;
            bool pass = owed >= 1 && under == owed && after == 0 && cleared && left == 0;
            return " teardown=" + (pass ? "PASS" : "FAIL") + " td-arm=" + (opt.teardownMutant ? "mutant(clear-first)" : "control")
                 + " owed=" + owed + " undone-under-pose=" + under + " undone-after-clear=" + after + " pose-cleared=" + cleared + " left=" + left;
        }

        // S2F3 (round two), evidence lever `multi=K`: after a frame's pair, the
        // black pass rendered K more times in the same Unity frame from the same
        // state -- nothing runs between those renders -- each resolved into a
        // slot-sized target by the same blit as the pair's own, read back and
        // compared byte for byte with the pair's black pass. A frame whose
        // renders disagree is logged with how many of the K did, where, and how
        // many distinct images the disagreeing ones made. Under `msaa4` (T36's
        // mutant arm) the repeats go through the old 4x MSAA target.
        private static int _danceMulti;
        private static string _danceMultiTag = "";
        private static int _danceMultiFrames, _danceMultiDiffer;
        private static RenderTexture _danceMultiRt;
        private static Texture2D _danceMultiTex;
        private static byte[] _danceMultiRef;
        private static readonly List<uint> _danceMultiSeen = new List<uint>();   // the disagreeing repeats' distinct images

        private static void DanceMultiCheck(Camera cam, RenderTexture target, DanceSlot slot, int k)
        {
            int w = slot.B.width, h = slot.B.height;
            var prev = RenderTexture.active;
            try
            {
                if (_danceMultiRt == null || _danceMultiRt.width != w || _danceMultiRt.height != h)
                {
                    if (_danceMultiRt != null) UnityEngine.Object.Destroy(_danceMultiRt);
                    _danceMultiRt = new RenderTexture(w, h, 0, slot.B.format) { hideFlags = HideFlags.HideAndDontSave };
                    _danceMultiRt.Create();
                }
                if (_danceMultiTex == null || _danceMultiTex.width != w || _danceMultiTex.height != h)
                {
                    if (_danceMultiTex != null) UnityEngine.Object.Destroy(_danceMultiTex);
                    _danceMultiTex = new Texture2D(w, h, TextureFormat.RGBA32, false) { hideFlags = HideFlags.HideAndDontSave };
                }
                RenderTexture.active = slot.B;
                _danceMultiTex.ReadPixels(new Rect(0, 0, w, h), 0, 0, false);
                var raw = _danceMultiTex.GetRawTextureData<byte>();
                if (_danceMultiRef == null || _danceMultiRef.Length != raw.Length) _danceMultiRef = new byte[raw.Length];
                raw.CopyTo(_danceMultiRef);
                int disagree = 0, maxBytes = 0, firstAt = -1;
                _danceMultiSeen.Clear();
                for (int i = 0; i < _danceMulti; i++)
                {
                    cam.targetTexture = target;
                    cam.backgroundColor = Color.black; cam.Render(); Graphics.Blit(target, _danceMultiRt);
                    RenderTexture.active = _danceMultiRt;
                    _danceMultiTex.ReadPixels(new Rect(0, 0, w, h), 0, 0, false);
                    var b = _danceMultiTex.GetRawTextureData<byte>();
                    int diff = 0, at = -1; uint hsh = 2166136261u;
                    for (int j = 0; j < b.Length; j++) { byte bj = b[j]; hsh = (hsh ^ bj) * 16777619u; if (bj != _danceMultiRef[j]) { diff++; if (at < 0) at = j; } }
                    if (diff > 0 && !_danceMultiSeen.Contains(hsh)) _danceMultiSeen.Add(hsh);
                    if (diff > 0) { disagree++; if (diff > maxBytes) maxBytes = diff; if (firstAt < 0) firstAt = at; }
                }
                _danceMultiFrames++;
                if (disagree > 0)
                {
                    _danceMultiDiffer++;
                    int px = firstAt / 4;
                    Plugin.Log.LogInfo("[DANCE-MULTI] tag=" + _danceMultiTag + " k=" + k + " disagree=" + disagree + "/" + _danceMulti
                                       + " bytes<=" + maxBytes + " first=(" + (px % w) + "," + (px / w) + ",bottom-up) ch=" + (firstAt % 4)
                                       + " distinct=" + _danceMultiSeen.Count + " jobs=" + Unity.Jobs.LowLevel.Unsafe.JobsUtility.JobWorkerCount);
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[DANCE-MULTI] tag=" + _danceMultiTag + " k=" + k + " threw " + ex.GetType().Name + ": " + ex.Message); }
            finally { RenderTexture.active = prev; cam.targetTexture = target; }
        }

        // S2F3 (round two), evidence lever `jobs=N`: the job system's worker
        // count held at N for the capture and put back at its end; jobs=0 runs
        // the engine jobs of the capture's renders on the main thread.
        private static int _danceJobsBefore = -1;
        private static string _danceJobsStat = "-";

        private static void DanceJobsHold(int n)
        {
            _danceJobsStat = "-"; _danceJobsBefore = -1;
            if (n < 0) return;
            try
            {
                int before = Unity.Jobs.LowLevel.Unsafe.JobsUtility.JobWorkerCount;
                Unity.Jobs.LowLevel.Unsafe.JobsUtility.JobWorkerCount = Mathf.Min(n, Unity.Jobs.LowLevel.Unsafe.JobsUtility.JobWorkerMaximumCount);
                _danceJobsBefore = before;
                _danceJobsStat = before + ">" + Unity.Jobs.LowLevel.Unsafe.JobsUtility.JobWorkerCount;
            }
            catch (Exception ex) { _danceJobsStat = "threw:" + ex.GetType().Name; }
        }

        private static void DanceJobsRestore()
        {
            if (_danceJobsBefore < 0) return;
            try { Unity.Jobs.LowLevel.Unsafe.JobsUtility.JobWorkerCount = _danceJobsBefore; _danceJobsStat += ">" + Unity.Jobs.LowLevel.Unsafe.JobsUtility.JobWorkerCount; }
            catch (Exception ex) { _danceJobsStat += "/restore-threw:" + ex.GetType().Name; }
            _danceJobsBefore = -1;
        }

        private static void DanceMultiRelease()
        {
            if (_danceMultiRt != null) { UnityEngine.Object.Destroy(_danceMultiRt); _danceMultiRt = null; }
            if (_danceMultiTex != null) { UnityEngine.Object.Destroy(_danceMultiTex); _danceMultiTex = null; }
            _danceMulti = 0;
        }

        /// <summary>T38/M1: a PhotonView added to every holdable the rig
        /// spawned, right after activation and before the sweep -- the case the
        /// clone-only sweep misses (the stock gun carries none).</summary>
        private static void DanceDevInjectPv(StringBuilder rep, GameObject clone)
        {
            int n = 0;
            foreach (var h in DanceHoldables(clone))
            {
                try { h.AddComponent<Photon.Pun.PhotonView>(); n++; }
                catch (Exception ex) { rep.Append("injectpv threw: ").Append(ex.Message).Append('\n'); }
            }
            rep.Append("injectpv: added ").Append(n).Append(" PhotonView(s) to the spawned holdable(s)\n");
            Plugin.Log.LogInfo("[DANCE] injectpv: added " + n + " PhotonView(s) to the spawned holdable(s)");
        }

        /// <summary>DanceMotionCore.Matte on the readback pair against
        /// MatteOfPasses on the ReadPixels pair of the same targets, pixel for
        /// pixel in the measured row order. `flip` changes one byte of the
        /// readback copy first: the comparison must then fail.</summary>
        private static void DanceMatteq(StringBuilder rep, byte[] rbB, byte[] rbW, Color32[] refB, Color32[] refW, bool flip)
        {
            try
            {
                int edge = DANCE_EDGE;
                byte[] b = (byte[])rbB.Clone();
                if (flip)
                {
                    int p = ((edge / 2) * edge + edge / 2) * 4;
                    b[p] = (byte)(b[p] == 255 ? 254 : b[p] + 1);
                }
                var o = new byte[b.Length];
                int lit, partial, covered;
                DanceMotionCore.Matte(b, rbW, o, out lit, out partial, out covered);
                float litR, partialR;
                var m = MatteOfPasses(refB, refW, out litR, out partialR);
                bool top = _danceOrientation == 2;
                int diff = 0, pixels = edge * edge;
                for (int y = 0; y < edge; y++)
                {
                    int ry = top ? edge - 1 - y : y;
                    for (int x = 0; x < edge; x++)
                    {
                        int p = (y * edge + x) * 4;
                        var c = m[ry * edge + x];
                        if (o[p] != c.r || o[p + 1] != c.g || o[p + 2] != c.b || o[p + 3] != c.a) diff++;
                    }
                }
                string line = "result=" + (diff == 0 ? "PASS" : "FAIL") + " arm=" + (flip ? "flip" : "control") + " diff=" + diff + " pixels=" + pixels
                            + " covered=" + covered + " lit=" + lit + " order=" + _danceOrientation;
                rep.Append("matteq: ").Append(line).Append('\n');
                Plugin.Log.LogInfo("[DANCE-MATTEQ] " + line);
            }
            catch (Exception ex) { Plugin.Log.LogInfo("[DANCE-MATTEQ] result=FAIL threw " + ex.GetType().Name + ": " + ex.Message); }
        }

        /// <summary>The lever's report and sentinel, and a root census two
        /// frames after the teardown (T37: "root counts at baseline").</summary>
        private static void DanceDevReport(DanceOpts opt, string sku, StringBuilder rep, string fail, DanceMotionCore.FrameOut still,
                                           DanceMotionCore.FrameOut[] frames, int n, int ms, DanceClock clock, GameObject[] rootsBefore, bool remember,
                                           string teardown)
        {
            try
            {
                var digest = new StringBuilder();
                int have = 0;
                if (frames != null) foreach (var f in frames) if (f != null && f.Png != null) { digest.Append(DanceMotionCore.Sha256Hex(f.Png)); have++; }
                string dig = have > 0 ? DanceMotionCore.Sha256Hex(Encoding.ASCII.GetBytes(digest.ToString())).Substring(0, 16) : "-";
                double p95, max; int fr;
                clock.Max("frames", out p95, out max, out fr);
                double ap95, amax; int afr;
                clock.Max(null, out ap95, out amax, out afr);
                string line = "tag=" + opt.tag + " sku=" + sku + " result=" + (fail == null ? "ok" : "fail") + " remembered=" + (remember && fail != null ? 1 : 0)
                            + " frames=" + have + "/" + n + " ms=" + ms + " digest=" + dig
                            + " still=" + (still != null && still.Png != null ? DanceMotionCore.Sha256Hex(still.Png).Substring(0, 16) : "-")
                            + " loop_p95=" + p95.ToString("F2") + " loop_max=" + max.ToString("F2") + " loop_frames=" + fr
                            + " all_p95=" + ap95.ToString("F2") + " all_max=" + amax.ToString("F2") + " all_frames=" + afr
                            + " hold=" + opt.holdFrames + " fps=" + opt.fps + " fdt=" + opt.fixedDt.ToString("R") + " tclock=" + (opt.tclock ? 1 : 0)
                            + " faultat=" + opt.faultAt + " gatestartonly=" + (opt.gateStartOnly ? 1 : 0) + " injectpv=" + (opt.injectPv ? 1 : 0)
                            + " m1=" + (opt.m1CloneOnly ? "cloneonly" : "full") + " selffail=" + (opt.selfFail ? 1 : 0)
                            + (opt.faultFrame >= 0 ? " faultframe=" + opt.faultFrame + (teardown ?? "") : "")
                            + " aa=" + (opt.msaa4 ? "msaa4" : "ss2x2")
                            + (opt.multi > 0 ? " multi=" + opt.multi + "/frames=" + _danceMultiFrames + "/disagree=" + _danceMultiDiffer : "")
                            + (opt.jobs >= 0 ? " jobs=" + _danceJobsStat : "")
                            + (fail != null ? " reason=\"" + fail.Replace('"', '\'') + "\"" : "");
                Plugin.Log.LogInfo("[DANCE-CAPTURE] " + line);
                rep.Append("capture: ").Append(line).Append('\n');
                rep.Append("slices all: ").Append(clock.Summary(null)).Append('\n');
                foreach (var ph in new[] { "start", "setup", "prepass", "alloc", "still", "frames", "drain" })
                    rep.Append("slices ").Append(ph).Append(": ").Append(clock.Summary(ph)).Append('\n');
                rep.Append("slices top: ").Append(clock.Top(8)).Append(" gc=").Append(clock.Collections).Append('\n');
                File.WriteAllText(Path.Combine(DanceCorpusDir(), opt.tag + "_" + sku + "_report.txt"), rep.ToString());
                if (Plugin.Instance != null) Plugin.Instance.StartCoroutine(DanceDevRoots(opt.tag, sku, rootsBefore));
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[DANCE-CAPTURE] report threw: " + ex.Message); }
        }

        private static IEnumerator DanceDevRoots(string tag, string sku, GameObject[] before)
        {
            yield return null;
            yield return null;
            var sb = new StringBuilder();
            CompareRoots(sb, before);
            Plugin.Log.LogInfo("[DANCE-ROOTS] tag=" + tag + " sku=" + sku + " " + (before == null ? "no census (the job ended before the rig)" : sb.ToString().Trim()));
        }

        /// <summary>The corpus files of one finished lever capture: the still,
        /// the container (bound, for the offline tools only, to the still's own
        /// SHA-256 -- the server binds to its canonical re-encode), and one line
        /// per frame (the T36 comparison reads these).</summary>
        private static void DanceDevCorpus(DanceOpts opt, string sku, DanceMotionCore.FrameOut still, DanceMotionCore.FrameOut[] frames, int ms)
        {
            try
            {
                string dir = DanceCorpusDir();
                string stem = Path.Combine(dir, opt.tag + "_" + sku);
                File.WriteAllBytes(stem + "_still.png", still.Png);
                var pngs = new List<byte[]>();
                var sb = new StringBuilder();
                for (int k = 0; k < frames.Length; k++)
                {
                    var f = frames[k];
                    pngs.Add(f.Png);
                    sb.Append(k).Append(' ').Append(DanceMotionCore.Sha256Hex(f.Png)).Append(' ').Append(f.Png.Length)
                      .Append(' ').Append(f.Coverage.ToString("F5", System.Globalization.CultureInfo.InvariantCulture))
                      .Append(' ').Append(f.EdgeClear ? 1 : 0).Append('\n');
                }
                string header = DanceMotionCore.HeaderText(sku, DanceEmotes.MOTION_RECIPE, frames.Length, ms, DanceMotionCore.Sha256Hex(still.Png));
                byte[] c = DanceMotionCore.BuildContainer(header, pngs);
                File.WriteAllBytes(stem + ".scrmotion", c);
                sb.Append("still ").Append(DanceMotionCore.Sha256Hex(still.Png)).Append(' ').Append(still.Png.Length).Append('\n');
                sb.Append("container ").Append(DanceMotionCore.Sha256Hex(c)).Append(' ').Append(c.Length).Append('\n');
                File.WriteAllText(stem + "_frames.txt", sb.ToString());
                Plugin.Log.LogInfo("[DANCE-CAPTURE] tag=" + opt.tag + " sku=" + sku + " corpus=" + opt.tag + "_" + sku + ".scrmotion bytes=" + c.Length
                                   + " container=" + DanceMotionCore.Sha256Hex(c).Substring(0, 16));
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[DANCE-CAPTURE] corpus write threw: " + ex.Message); }
        }

        /// <summary>T38 (design S8, extended per M1 in the capture's own sweep):
        /// two offline components, a rig root and a same-named root outside it,
        /// each with a same-named child. With PortraitPose set on the rig,
        /// TryGetPose for the outside child must return exactly its
        /// PortraitPose-null result; for the rig's child the portrait pose; after
        /// the rig root is destroyed, no portrait pose. `mutant` sets the
        /// name-match arm for this call only.</summary>
        private static void DanceDevT38(bool mutant)
        {
            GameObject rigA = null, rigB = null;
            try
            {
                rigA = new GameObject("CR_PortraitRig"); rigA.hideFlags = HideFlags.HideAndDontSave;
                var childA = new GameObject("ArmTarget"); childA.hideFlags = HideFlags.HideAndDontSave; childA.transform.SetParent(rigA.transform, false);
                rigB = new GameObject("CR_PortraitRig"); rigB.hideFlags = HideFlags.HideAndDontSave;
                var childB = new GameObject("ArmTarget"); childB.hideFlags = HideFlags.HideAndDontSave; childB.transform.SetParent(rigB.transform, false);
                rigA.transform.position = PARK + new Vector3(0f, 40f, 0f);
                rigB.transform.position = PARK + new Vector3(0f, 60f, 0f);
                const int idx = 0; const float t = 0.5f;

                DanceEmotes.PortraitPose = null;
                Vector2 b0, l0, r0; float a0;
                bool g0 = DanceEmotes.DevTryGetPose(childB.transform, out b0, out a0, out l0, out r0);

                DanceEmotes.DevT38MatchByName = mutant;
                DanceEmotes.PortraitPose = new DanceEmotes.PortraitPoseSpec(rigA.transform, idx, t);
                Vector2 b1, l1, r1; float a1;
                bool g1 = DanceEmotes.DevTryGetPose(childB.transform, out b1, out a1, out l1, out r1);
                bool outside = g1 == g0 && b1 == b0 && a1 == a0 && l1 == l0 && r1 == r0;

                Vector2 bA, lA, rA; float aA;
                bool gA = DanceEmotes.DevTryGetPose(childA.transform, out bA, out aA, out lA, out rA);
                Vector2 eb, el, er; float ea;
                bool ge = DanceEmotes.EvaluateClamped(idx, t, out eb, out ea, out el, out er);
                bool rig = gA && ge && lA == el && rA == er && (DanceEmotes.PORTRAIT_BODY_CHANNEL || (bA == Vector2.zero && aA == 0f));

                UnityEngine.Object.DestroyImmediate(rigA); rigA = null;
                Vector2 b2, l2, r2; float a2;
                bool g2 = DanceEmotes.DevTryGetPose(childB.transform, out b2, out a2, out l2, out r2);
                bool destroyed = g2 == g0 && b2 == b0 && a2 == a0 && l2 == l0 && r2 == r0;

                Plugin.Log.LogInfo("[DANCE-T38] arm=" + (mutant ? "mutant(name-match)" : "control") + " outside=" + (outside ? "PASS" : "FAIL")
                                   + " rig=" + (rig ? "PASS" : "FAIL") + " destroyed=" + (destroyed ? "PASS" : "FAIL")
                                   + " null-result=" + g0 + " outside-result=" + g1 + " rig-result=" + gA);
            }
            catch (Exception ex) { Plugin.Log.LogInfo("[DANCE-T38] FAIL threw " + ex.GetType().Name + ": " + ex.Message); }
            finally
            {
                DanceEmotes.DevT38MatchByName = false;
                DanceEmotes.PortraitPose = null;
                if (rigA != null) UnityEngine.Object.DestroyImmediate(rigA);
                if (rigB != null) UnityEngine.Object.DestroyImmediate(rigB);
            }
        }

        /// <summary>T48's decision probe: DanceMotionCore.Decide over the real
        /// remembered set and this seat's own descriptor, with the server state
        /// given by `stored` (none: no picture; base: the base still stored;
        /// dance: the dance still stored, no motion). `recolor` changes the base
        /// descriptor's colour field (a colour change); `nomemory` is the mutant
        /// arm. Prints the route the visit check would take.</summary>
        private static void DanceDevDecide(string sku, bool nomemory, bool recolor, string stored)
        {
            try
            {
                string steam = MatchTracker.LocalSteamId;
                string baseDesc = BuildDescriptor(CurrentPreset());
                if (baseDesc == null) { Plugin.Log.LogInfo("[DANCE-T48] no descriptor: " + LastResult); return; }
                string storedBase = baseDesc, storedDance = DanceDescriptor(baseDesc, sku);
                if (recolor)
                {
                    int a = baseDesc.IndexOf("|color=", StringComparison.Ordinal);
                    int b = a >= 0 ? baseDesc.IndexOf('|', a + 1) : -1;
                    if (a >= 0 && b > a) baseDesc = baseDesc.Substring(0, a) + "|color=dev_probe:123456" + baseDesc.Substring(b);
                }
                string danceDesc = DanceDescriptor(baseDesc, sku);
                string hash = stored == "none" ? "" : new string('a', 64);
                string desc = stored == "base" ? storedBase : stored == "dance" ? storedDance : "";
                bool remembered = danceDesc != null && !nomemory && _danceRemembered.Contains(DanceMotionCore.RememberKey(steam, danceDesc));
                var need = DanceMotionCore.Decide(true, sku, true, "", hash, desc, danceDesc, DanceEmotes.MOTION_RECIPE, DanceSeatCan(), remembered);
                string route = need == DanceMotionCore.Need.Needed ? "dance-job"
                             : need == DanceMotionCore.Need.Current ? "current"
                             : need == DanceMotionCore.Need.Fallback
                                 ? (DanceMotionCore.StillCurrent(hash, desc, baseDesc, danceDesc) ? "still-current" : "still-only-run")
                                 : "product-path";
                Plugin.Log.LogInfo("[DANCE-T48] sku=" + sku + " arm=" + (nomemory ? "mutant(no-memory)" : "control") + " recolor=" + (recolor ? 1 : 0)
                                   + " stored=" + stored + " remembered=" + (remembered ? 1 : 0) + " remembered-keys=" + _danceRemembered.Count
                                   + " seat-can=" + (DanceSeatCan() ? 1 : 0) + " need=" + need + " route=" + route);
            }
            catch (Exception ex) { Plugin.Log.LogInfo("[DANCE-T48] threw " + ex.GetType().Name + ": " + ex.Message); }
        }
    }
}
