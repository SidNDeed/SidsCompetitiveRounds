using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.Rendering;

namespace CompetitiveRounds
{
    /// <summary>
    /// Dance cards: the capture on the owning client (design S1.1-S1.9), the
    /// job that replaces the static product run whenever the per-visit picture
    /// check finds a motion needed (S1.2). One camera serves both products: the
    /// dancer's still at 1180 px and the frames at 590 px, the rig posed only by
    /// DanceEmotes.PortraitPose (S1.3), which moves the arm channel through the
    /// live IKArmMove patch path (step 0: arms-only, PORTRAIT_BODY_CHANNEL
    /// false).
    ///
    /// Main thread per Unity frame (S1.8): a pose write, or two renders, two
    /// blits and two AsyncGPUReadback requests; the readback callbacks copy
    /// the bytes out of Unity's buffer. The matte, then the grade, then the PNG
    /// encode, the edge band and the luma run on a worker thread
    /// (DanceMotionCore.ProcessPair), a frame pair at a time through a ring of
    /// four pairs. The still takes the same route at 1180 px, so the still's
    /// matte, grade and lit gate are the static path's arithmetic
    /// (DanceMotionCore.Matte and Grade, the matteq lever proves the matte
    /// equal to MattePixels) with no synchronous ReadPixels on the product
    /// path.
    ///
    /// Findings carried here (build brief section 12): M1 -- right after the
    /// rig activates, in the same frame and before AfterActivate, any
    /// PortraitPose, Start/Update or yield, every PhotonView on the clone and
    /// on every holdable it spawned is destroyed and zero must remain, else the
    /// job ends (DanceSweepPhotonViews). L1 -- every baseline restore and every
    /// clear of PortraitPose is preceded by DanceEmotes.RestorePortraitRig, and
    /// Tick's empty-active branch does not run while PortraitPose is set
    /// (DanceEmotes.Tick). L2 -- the frames leave this job checked but
    /// unassembled; DanceUploadJob builds the header and the container only
    /// from the still writer's returned portrait_hash.
    ///
    /// Build deviations recorded in the lane notes: D2 -- every pose is held
    /// DANCE_HOLD_FRAMES frames before a render or a bounds read (step 0
    /// measured the rig's arms reaching a render fixed point after three held
    /// frames, never after one), where the design's steps 4 and 7 say one; the
    /// readbacks are waited for BEFORE the rig teardown rather than after it
    /// (the pose is cleared first either way, so the frames are the same).
    /// </summary>
    internal static partial class PortraitRender
    {
        private const int DANCE_HOLD_FRAMES = 3;                   // D2 (step 0: hold 1 left 20 of 24 lag checks moving, hold 3 none)
        private const float DANCE_CEILING_S = 90f;                 // S1.6: rig build to container
        private const int DANCE_RING_PAIRS = 4;                    // S1.4 step 7
        private const float DANCE_SHOP_WAIT_S = 10f;               // the ownership read's wait before the conservative route
        private const int DANCE_EDGE = DanceMotionCore.FRAME_EDGE; // 590

        // Process-lifetime memory (S1.2, S2.11): a key whose dance job failed a
        // capture check, or whose still or motion upload drew a 422 or a 413, is
        // not captured again until the key changes or the process restarts. The
        // key is RememberKey(steam, dance descriptor): the dance descriptor names
        // every pixel input, the dance and MOTION_RECIPE, and none of the visit
        // or UI generations, which change on every tab visit (a key holding them
        // would forget at the next visit).
        private static readonly HashSet<string> _danceRemembered = new HashSet<string>(StringComparer.Ordinal);
        // The readback row order on this seat, measured once per process at the
        // first dance job's rest pose: 0 not measured, 1 bottom-up (a Texture2D's
        // order), 2 top-down, -1 neither matched (this seat cannot dance).
        private static int _danceOrientation;
        private static float _danceHoldUntil = -1f;                // a HoldOff answer (day cap, rate limit, unconfigured)
        private static bool _danceSessionStop;                     // a SessionStop answer (no route, capacity)
        private static int _danceShopVisit = -1;
        private static float _danceShopUntil = -1f;
        private static int _danceGen;
        private static readonly List<RenderTexture> _danceTargets = new List<RenderTexture>();

        /// <summary>The dance job's own last outcome, for the log and the dev
        /// probes; LastResult carries the player-facing note.</summary>
        internal static string DanceLastResult { get; private set; } = "";

        /// <summary>This seat can run the dance job at all (S1.1's static
        /// terms): AsyncGPUReadback, a baked grade table, a readback order that
        /// was not refused, and no hold or session stop from an answer.</summary>
        private static bool DanceSeatCan()
        {
            try
            {
                return SystemInfo.supportsAsyncGPUReadback && GradeBaked && _danceOrientation >= 0
                    && !_danceSessionStop && Time.realtimeSinceStartup >= _danceHoldUntil;
            }
            catch { return false; }
        }

        private static int DanceIndex(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return -1;
            for (int i = 0; i < DanceEmotes.Defs.Length; i++)
                if (string.Equals(DanceEmotes.Defs[i].Sku, sku, StringComparison.Ordinal)) return i;
            return -1;
        }

        /// <summary>The ownership read may still be waited for this visit: the
        /// first ask opens a DANCE_SHOP_WAIT_S window and asks for the shop list.</summary>
        private static bool DanceMayDefer()
        {
            float now = Time.realtimeSinceStartup;
            if (_danceShopVisit != _visitId)
            {
                _danceShopVisit = _visitId;
                _danceShopUntil = now + DANCE_SHOP_WAIT_S;
                try { ApiClient.FetchShopItems(MatchTracker.LocalSteamId); } catch { }
                return true;
            }
            return now < _danceShopUntil;
        }

        /// <summary>S1.2 on this seat: DanceMotionCore.Decide over the /pc/me
        /// answer, the owned list and the seat's facts. `defer`: the owned list
        /// is not here yet and may still arrive this visit -- the check is asked
        /// again. When it cannot be read in time, or the selection names a dance
        /// this client does not know, the route is the conservative one: never a
        /// motion capture, never a base still over a still that is current
        /// (ownedHere true, canDance false: Current or Fallback). The server
        /// names a selection only while the player holds it (S2.9).</summary>
        private static DanceMotionCore.Need DanceDecision(ApiClient.PcMe me, string baseDescriptor, out string sku, out int idx,
                                                          out string danceDesc, out bool defer)
        {
            sku = ""; idx = -1; danceDesc = null; defer = false;
            bool supported = me != null && me.dance_supported;
            if (supported) sku = me.pc_dance_sku ?? "";
            if (!supported || sku.Length == 0)
                return DanceMotionCore.Decide(supported, sku, false, null, null, null, null, DanceEmotes.MOTION_RECIPE, false, false);
            idx = DanceIndex(sku);
            danceDesc = DanceDescriptor(baseDescriptor, sku);
            bool remembered = danceDesc != null
                              && _danceRemembered.Contains(DanceMotionCore.RememberKey(MatchTracker.LocalSteamId, danceDesc));
            bool owned, can;
            if (idx < 0) { owned = true; can = false; }
            else
            {
                var list = DanceEmotes.OwnedDanceIndexes();
                if (list == null)
                {
                    if (DanceMayDefer()) { defer = true; return DanceMotionCore.Need.None; }
                    owned = true; can = false;
                }
                else { owned = list.Contains(idx); can = DanceSeatCan(); }
            }
            return DanceMotionCore.Decide(true, sku, owned, me.pc_motion, me.portrait_hash, me.portrait_descriptor, danceDesc,
                                          DanceEmotes.MOTION_RECIPE, can, remembered);
        }

        /// <summary>The visit check's dance half (Tick). True when the visit is
        /// settled here -- a dance job started or was re-armed, the dance picture
        /// is current, a Fallback's still is current, or the check is deferred;
        /// false when the product path decides as before (no dance selected, an
        /// older server, or a Fallback whose still is behind).</summary>
        private static bool DanceVisit(ApiClient.PcMe me, string want)
        {
            string sku, danceDesc; int idx; bool defer;
            var need = DanceDecision(me, want, out sku, out idx, out danceDesc, out defer);
            if (defer) { _pendingCheck = true; _checkedVisit = -1; return true; }
            switch (need)
            {
                case DanceMotionCore.Need.Needed:
                    if (!StartDance("visit", sku, idx, null)) { _refreshAt = Time.realtimeSinceStartup + 5f; _refreshWhy = "visit"; }
                    return true;
                case DanceMotionCore.Need.Current:
                    LastResult = "picture current (dancing)";
                    if (PreviewTex == null) Start("preview", false);
                    return true;
                case DanceMotionCore.Need.Fallback:
                    if (!DanceMotionCore.StillCurrent(me.portrait_hash, me.portrait_descriptor, want, danceDesc)) return false;
                    LastResult = "picture current";
                    if (PreviewTex == null) Start("preview", false);
                    return true;
                default:
                    return false;
            }
        }

        /// <summary>A matured refresh (Tick): the dance job when a motion is
        /// needed, nothing when the dance picture is current, else the product
        /// path as before (a Fallback re-renders the base still, as a refresh
        /// always did). False keeps the refresh armed (busy, refused, deferred).</summary>
        private static bool RefreshStart(string why)
        {
            var me = ApiClient.CachedPcMe;
            if (me != null && me.dance_supported && !string.IsNullOrEmpty(me.pc_dance_sku))
            {
                string want = BuildDescriptor(CurrentPreset());
                if (want != null)
                {
                    string sku, danceDesc; int idx; bool defer;
                    var need = DanceDecision(me, want, out sku, out idx, out danceDesc, out defer);
                    if (defer) return false;
                    if (need == DanceMotionCore.Need.Needed) return StartDance(why, sku, idx, null);
                    if (need == DanceMotionCore.Need.Current) { LastResult = "picture current (dancing)"; return true; }
                }
            }
            return Start(why, true);
        }

        /// <summary>The state key extended with the selected dance and
        /// MOTION_RECIPE (S1.1), the pixel inputs still its last segment so
        /// Abandon can cut them off.</summary>
        private static string DanceStateKey()
        {
            var me = ApiClient.CachedPcMe;
            string sel = me == null || !me.dance_supported ? "-" : (me.pc_dance_sku ?? "");
            return (MatchTracker.LocalSteamId ?? "")
                 + "|" + PlayerCardsUI.Epoch
                 + "|" + _visitId
                 + "|" + CurrentPreset()
                 + "|" + (GameStateWatcher.IsInMatch ? 1 : 0)
                 + "|" + sel.Replace('|', '_') + ":" + DanceEmotes.MOTION_RECIPE
                 + "|" + LiveInputsKey();
        }

        /// <summary>Dev knobs of the capture (PortraitRenderDanceDev.cs); the
        /// product path always runs a fresh default instance.</summary>
        private sealed class DanceOpts
        {
            internal bool local;          // no upload: the still, the container and the frame hashes go to BepInEx/dance_corpus
            internal string tag = "product";
            internal bool tclock;         // T36's mutant arm: the pose time from the clock
            internal int faultAt = -1;    // T37: the gate reports an online room from this yield on
            internal bool gateStartOnly;  // T37's mutant arm: no gate after a yield
            internal bool injectPv;       // T38/M1: a PhotonView added to the spawned holdable right after activation
            internal bool m1CloneOnly;    // M1's mutant arm: the sweep covers the clone only
            internal bool selfFail;       // T48: the self-check fails
            internal bool matteq;         // DanceMotionCore.Matte against MatteOfPasses on one pass pair at rest
            internal bool matteqFlip;     // matteq's negative arm: one byte of the readback copy changed first
            internal int holdFrames = DANCE_HOLD_FRAMES;
            internal float fixedDt = -1f; // T36: Time.fixedDeltaTime for the job, restored after
            internal int fps = -1;        // T36: Application.targetFrameRate for the job (vSync off), restored after
        }

        /// <summary>Starts the dance job; false when it cannot start now (the
        /// caller keeps its request armed). The product path's own refusals, the
        /// lock, DevLeverBlocked's room and client-state terms and the seat's
        /// static terms (S1.1) are asked here and again after every yield.</summary>
        private static bool StartDance(string why, string sku, int idx, DanceOpts opt)
        {
            EnsureSceneHook();
            Reclaim();
            if (Rendering || UploadInFlight || Plugin.Instance == null) return false;
            if (GameStateWatcher.IsInMatch) { LastResult = "skipped: in a match"; return false; }
            if (PlayerAssigner.instance == null || PlayerAssigner.instance.playerPrefab == null) { LastResult = "skipped: no player prefab yet"; return false; }
            if (string.IsNullOrEmpty(MatchTracker.LocalSteamId) || MatchTracker.LocalSteamId == "unknown") { LastResult = "skipped: no identity"; return false; }
            if (idx < 0 || idx >= DanceEmotes.Defs.Length || !string.Equals(DanceEmotes.Defs[idx].Sku, sku, StringComparison.Ordinal)) return false;
            var me = ApiClient.CachedPcMe;
            if ((opt == null || !opt.local) && me != null && !string.IsNullOrEmpty(me.portrait_locked_until)) { LastResult = "picture locked"; return false; }
            string blocked = DevLeverBlocked(0);
            if (blocked != null) { DanceLastResult = "not started: " + blocked; return false; }
            if (!DanceSeatCan()) { DanceLastResult = "not started: this seat cannot capture a dance now"; return false; }
            int gen = _renderClaim.Take(Plugin.Instance, RENDER_BUDGET);
            var o = opt ?? new DanceOpts();
            var clock = new DanceClock();
            Plugin.Instance.StartCoroutine(DanceTimed(DanceRun(why, sku, idx, gen, o, clock), clock));
            return true;
        }

        // -- the job's main-thread slices (S1.8, T37) ---------------------------

        /// <summary>Main-thread milliseconds the job spent, per Unity frame:
        /// every resume of the coroutine and every readback callback, summed by
        /// Time.frameCount. Phases name the S1.4 step a frame belongs to (the
        /// phase current at the frame's first sample). A garbage collection
        /// that completes inside a timed resume is counted against that frame,
        /// so Top tells a collection's pause apart from the job's own work
        /// (finding S2F4).</summary>
        private sealed class DanceClock
        {
            private readonly System.Diagnostics.Stopwatch _sw = new System.Diagnostics.Stopwatch();
            private readonly Dictionary<int, double> _ms = new Dictionary<int, double>();
            private readonly Dictionary<int, string> _phaseOf = new Dictionary<int, string>();
            private readonly Dictionary<int, int> _gcOf = new Dictionary<int, int>();
            private int _gc0;
            internal string Phase = "start";

            internal void Begin() { _gc0 = GC.CollectionCount(0); _sw.Reset(); _sw.Start(); }
            internal void End()
            {
                if (!_sw.IsRunning) return;
                _sw.Stop();
                Add(_sw.Elapsed.TotalMilliseconds);
                int gc = GC.CollectionCount(0) - _gc0;
                if (gc > 0) { int f = Time.frameCount, v; _gcOf.TryGetValue(f, out v); _gcOf[f] = v + gc; }
            }

            /// <summary>Collections that completed inside timed resumes.</summary>
            internal int Collections { get { int n = 0; foreach (var v in _gcOf.Values) n += v; return n; } }

            /// <summary>The `count` costliest frames, costliest first, as
            /// "frame:phase:ms", with ":gcN" when N collections completed inside
            /// its timed resumes; frames are numbered from the job's first.</summary>
            internal string Top(int count)
            {
                if (_ms.Count == 0) return "-";
                int first = int.MaxValue;
                foreach (var f in _ms.Keys) if (f < first) first = f;
                var list = new List<KeyValuePair<int, double>>(_ms);
                list.Sort((a, b) => b.Value.CompareTo(a.Value));
                var sb = new StringBuilder();
                for (int i = 0; i < list.Count && i < count; i++)
                {
                    int f = list[i].Key, gc; string p;
                    _phaseOf.TryGetValue(f, out p);
                    _gcOf.TryGetValue(f, out gc);
                    if (sb.Length > 0) sb.Append(' ');
                    sb.Append(f - first).Append(':').Append(p ?? "-").Append(':')
                      .Append(list[i].Value.ToString("F2", System.Globalization.CultureInfo.InvariantCulture));
                    if (gc > 0) sb.Append(":gc").Append(gc);
                }
                return sb.ToString();
            }

            internal void Add(double ms)
            {
                int f = Time.frameCount;
                double v;
                _ms.TryGetValue(f, out v);
                _ms[f] = v + ms;
                if (!_phaseOf.ContainsKey(f)) _phaseOf[f] = Phase;
            }

            /// <summary>"frames=N p95=X max=Y" over the frames of `phase`, or of
            /// every phase when null.</summary>
            internal string Summary(string phase)
            {
                var list = new List<double>();
                foreach (var kv in _ms)
                {
                    string p;
                    if (phase != null && (!_phaseOf.TryGetValue(kv.Key, out p) || p != phase)) continue;
                    list.Add(kv.Value);
                }
                if (list.Count == 0) return "frames=0";
                list.Sort();
                double p95 = list[Math.Min(list.Count - 1, (int)Math.Ceiling(0.95 * list.Count) - 1)];
                double max = list[list.Count - 1];
                return "frames=" + list.Count + " p95=" + p95.ToString("F2", System.Globalization.CultureInfo.InvariantCulture)
                     + " max=" + max.ToString("F2", System.Globalization.CultureInfo.InvariantCulture);
            }

            internal void Max(string phase, out double p95, out double max, out int n)
            {
                var list = new List<double>();
                foreach (var kv in _ms)
                {
                    string p;
                    if (phase != null && (!_phaseOf.TryGetValue(kv.Key, out p) || p != phase)) continue;
                    list.Add(kv.Value);
                }
                n = list.Count;
                if (n == 0) { p95 = 0; max = 0; return; }
                list.Sort();
                p95 = list[Math.Min(n - 1, (int)Math.Ceiling(0.95 * n) - 1)];
                max = list[n - 1];
            }
        }

        /// <summary>Drives `inner`, timing every MoveNext as main-thread work.
        /// An exception in `inner` runs its finally blocks inside MoveNext, as
        /// Unity's own driver would.</summary>
        private static IEnumerator DanceTimed(IEnumerator inner, DanceClock clock)
        {
            while (true)
            {
                bool more;
                clock.Begin();
                try { more = inner.MoveNext(); }
                finally { clock.End(); }
                if (!more) yield break;
                yield return inner.Current;
            }
        }

        // -- the ring (S1.4 step 7) ----------------------------------------------

        /// <summary>One pass pair in flight: the two non-MSAA targets the camera's
        /// resolve is copied into, the readback copies, the worker's scratch.</summary>
        private sealed class DanceSlot
        {
            internal RenderTexture B, W;
            internal byte[] BufB, BufW, Work;
            internal int Edge;
            internal int State;        // 0 free, 1 waiting for its readbacks, 2 on the worker
            internal int Arrived;      // 1 black, 2 white
            internal int K;            // frame index, -1 the still, -2 a calibration pair
        }

        /// <summary>The frames and the still in flight and done. Every
        /// completion carries the generation it was requested under, and a
        /// closed ring or another generation drops it (S1.4 step 7).</summary>
        private sealed class DanceRing
        {
            internal readonly object Sync = new object();
            internal readonly int Gen;
            internal readonly List<DanceSlot> Slots = new List<DanceSlot>();
            internal readonly DanceMotionCore.FrameOut[] Frames;
            internal DanceMotionCore.FrameOut Still;
            internal string Error;
            internal int InFlight;
            internal bool Closed;
            internal byte[] Table;
            internal bool BottomUp;
            internal DanceClock Clock;
            // calibration: the raw copies of one pass pair, kept for the caller
            internal byte[] CalB, CalW;
            internal bool CalDone;
            // S2F4: the slots' byte buffers, made off the main thread
            internal bool BuffersDone;

            internal DanceRing(int gen, int frames) { Gen = gen; Frames = new DanceMotionCore.FrameOut[frames]; }

            internal DanceSlot Free()
            {
                lock (Sync) { foreach (var s in Slots) if (s.State == 0 && s.Edge == DANCE_EDGE) return s; }
                return null;
            }

            internal int Done()
            {
                int n = 0;
                lock (Sync) { foreach (var f in Frames) if (f != null) n++; }
                return n;
            }

            internal void Close() { lock (Sync) { Closed = true; } }
        }

        private static RenderTexture DanceTarget(int edge, int depth, int aa)
        {
            var rt = new RenderTexture(edge, edge, depth);
            _danceTargets.Add(rt);
            // Registered as it is made (finding S2F12), so nothing that runs
            // below can leave a target DanceReleaseTargets does not know.
            if (aa > 1) rt.antiAliasing = aa;
            rt.Create();
            return rt;
        }

        /// <summary>Every target the dance job made, released. Teardown is its
        /// one caller, so ForceAbort's teardown of a job that never unwound
        /// releases them too.</summary>
        private static void DanceReleaseTargets()
        {
            foreach (var rt in _danceTargets)
                try { if (rt != null) { rt.Release(); UnityEngine.Object.Destroy(rt); } } catch { }
            _danceTargets.Clear();
        }

        /// <summary>Finding S2F4: every slot's three byte buffers (the two
        /// readback copies and the worker's scratch, edge * edge * 4 each),
        /// made on a pool thread so their page faults are not the main
        /// thread's. Each slot's land together under the ring's lock, then
        /// BuffersDone; a failure is the ring's Error. The render targets stay
        /// on the main thread (Unity objects).</summary>
        private static void DanceQueueBuffers(DanceRing ring)
        {
            var slots = new List<DanceSlot>(ring.Slots);
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    foreach (var slot in slots)
                    {
                        int size = slot.Edge * slot.Edge * 4;
                        byte[] b = new byte[size], w = new byte[size], work = new byte[size];
                        lock (ring.Sync) { slot.BufB = b; slot.BufW = w; slot.Work = work; }
                    }
                    lock (ring.Sync) ring.BuffersDone = true;
                }
                catch (Exception ex)
                {
                    lock (ring.Sync) { if (ring.Error == null) ring.Error = "the ring's buffers failed: " + ex.GetType().Name + ": " + ex.Message; }
                }
            });
        }

        /// <summary>The black and the white pass of the current pose into the
        /// slot's two targets, back to back with no yield between them (S1.4
        /// step 7), and both readbacks requested.</summary>
        private static void DanceRenderPair(DanceRing ring, Camera cam, RenderTexture msaa, DanceSlot slot, int k)
        {
            lock (ring.Sync) { slot.State = 1; slot.Arrived = 0; slot.K = k; ring.InFlight++; }
            cam.targetTexture = msaa;
            cam.backgroundColor = Color.black; cam.Render(); Graphics.Blit(msaa, slot.B);
            cam.backgroundColor = Color.white; cam.Render(); Graphics.Blit(msaa, slot.W);
            AsyncGPUReadback.Request(slot.B, 0, TextureFormat.RGBA32, req => DanceOnReadback(ring, slot, 1, req));
            AsyncGPUReadback.Request(slot.W, 0, TextureFormat.RGBA32, req => DanceOnReadback(ring, slot, 2, req));
        }

        /// <summary>A readback landed (main thread). Accepted only while the
        /// ring is open and of the job's generation; hasError fails the job
        /// (S1.6). When both passes are in, the pair goes to the worker.</summary>
        private static void DanceOnReadback(DanceRing ring, DanceSlot slot, int which, AsyncGPUReadbackRequest req)
        {
            var sw = System.Diagnostics.Stopwatch.StartNew();
            try
            {
                lock (ring.Sync)
                {
                    if (ring.Closed || ring.Gen != _danceGen) return;
                    if (req.hasError) { if (ring.Error == null) ring.Error = "a readback reported an error (pair " + slot.K + ")"; return; }
                    var data = req.GetData<byte>();
                    var buf = which == 1 ? slot.BufB : slot.BufW;
                    if (data.Length != buf.Length) { if (ring.Error == null) ring.Error = "a readback was " + data.Length + " bytes, not " + buf.Length; return; }
                    data.CopyTo(buf);
                    slot.Arrived |= which;
                    if (slot.Arrived != 3) return;
                    if (slot.K == -2)
                    {
                        ring.CalB = (byte[])slot.BufB.Clone();
                        ring.CalW = (byte[])slot.BufW.Clone();
                        ring.CalDone = true;
                        slot.State = 0;
                        ring.InFlight--;
                        return;
                    }
                    slot.State = 2;
                }
                DanceQueueWorker(ring, slot);
            }
            catch (Exception ex) { lock (ring.Sync) { if (ring.Error == null) ring.Error = "readback callback threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 80); } }
            finally
            {
                sw.Stop();
                try { if (ring.Clock != null) ring.Clock.Add(sw.Elapsed.TotalMilliseconds); } catch { }
            }
        }

        /// <summary>Matte, then grade, then the PNG, the edge band and the luma
        /// (or the still's preview), off the main thread (S1.4 step 7).</summary>
        private static void DanceQueueWorker(DanceRing ring, DanceSlot slot)
        {
            byte[] table = ring.Table;
            bool bottomUp = ring.BottomUp;
            int k = slot.K;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                DanceMotionCore.FrameOut f = null;
                string err = null;
                try
                {
                    DanceMotionCore.RgbMap map = (int r, int g, int b, out byte ro, out byte go, out byte bo) => LutSample(table, r, g, b, out ro, out go, out bo);
                    f = DanceMotionCore.ProcessPair(slot.BufB, slot.BufW, slot.Edge, map, bottomUp, slot.Work, k >= 0);
                }
                catch (Exception ex) { err = ex.GetType().Name + ": " + ex.Message; }
                lock (ring.Sync)
                {
                    if (err != null) { if (ring.Error == null) ring.Error = (k >= 0 ? "frame " + k : "the still") + " failed on the worker: " + err; }
                    else if (!ring.Closed)
                    {
                        if (k >= 0 && k < ring.Frames.Length) ring.Frames[k] = f;
                        else if (k == -1) ring.Still = f;
                    }
                    slot.State = 0;
                    ring.InFlight--;
                }
            });
        }

        // -- M1: the synchronous PhotonView sweep -------------------------------

        /// <summary>Finding M1: called in the frame the rig activated, before
        /// AfterActivate, any PortraitPose, any Start/Update and any yield.
        /// Destroys every PhotonView under the clone and under every holdable a
        /// Holding on the clone spawned (the gun is its own scene root, which
        /// BuildRig's pre-activation sweep of the clone cannot reach), then
        /// counts both again. Returns the number that remain; the job refuses
        /// on anything but zero. `cloneOnly` is M1's mutant arm (dev lever).</summary>
        private static int DanceSweepPhotonViews(StringBuilder rep, GameObject clone, bool cloneOnly)
        {
            int destroyed = 0;
            var holdables = DanceHoldables(clone);
            var roots = new List<GameObject> { clone };
            if (!cloneOnly) roots.AddRange(holdables);
            foreach (var root in roots)
            {
                if (root == null) continue;
                foreach (var pv in root.GetComponentsInChildren<Photon.Pun.PhotonView>(true))
                {
                    try { UnityEngine.Object.DestroyImmediate(pv); destroyed++; }
                    catch (Exception ex) { rep.Append("M1 pv destroy: ").Append(ex.Message).Append('\n'); }
                }
            }
            int remain = clone.GetComponentsInChildren<Photon.Pun.PhotonView>(true).Length;
            foreach (var h in holdables) if (h != null) remain += h.GetComponentsInChildren<Photon.Pun.PhotonView>(true).Length;
            string line = "M1 sweep: holdables=" + holdables.Count + " destroyed=" + destroyed + " remain=" + remain + (cloneOnly ? " (mutant: clone only)" : "");
            rep.Append(line).Append('\n');
            Plugin.Log.LogInfo("[DANCE] " + line);
            return remain;
        }

        /// <summary>Every scene instance a Holding on the clone holds (a
        /// holdable that is still the prefab asset is never touched).</summary>
        private static List<GameObject> DanceHoldables(GameObject clone)
        {
            var list = new List<GameObject>();
            foreach (var hold in clone.GetComponentsInChildren<Holding>(true))
            {
                var h = hold != null ? hold.holdable : null;
                if (h == null || !h.gameObject.scene.IsValid() || list.Contains(h.gameObject)) continue;
                list.Add(h.gameObject);
            }
            return list;
        }

        // -- the arms, the baseline, the pose ------------------------------------

        private sealed class DanceArms
        {
            internal IKArmMove L, R;
            internal Vector3 BaseL, BaseR;

            /// <summary>Finding L1 then the baseline: the rig's remembered deltas
            /// undone once, the targets written back to the frozen baseline with
            /// their spring velocity zeroed.</summary>
            internal void Rest(Transform rigRoot)
            {
                DanceEmotes.RestorePortraitRig(rigRoot);
                L.target.position = BaseL; R.target.position = BaseR;
                L.velolcity = Vector3.zero; R.velolcity = Vector3.zero;
            }
        }

        private static DanceArms DanceFindArms(GameObject clone)
        {
            IKArmMove l = null, r = null;
            foreach (var a in clone.GetComponentsInChildren<IKArmMove>(true))
            {
                if (a == null || a.target == null) continue;
                if (a.target.name.IndexOf("Left", StringComparison.OrdinalIgnoreCase) >= 0) l = a; else r = a;
            }
            if (l == null || r == null) return null;
            return new DanceArms { L = l, R = r, BaseL = l.target.position, BaseR = r.target.position };
        }

        /// <summary>The gun root where the pin left it and Holding still off: the
        /// rig is pinned at a pose (S1.4 steps 4 and 7).</summary>
        private static bool DanceRigStill(Vector3 gunPos, Quaternion gunRot)
        {
            if (_holdable == null || _hold == null) return false;
            if (_hold.enabled) return false;
            var t = _holdable.transform;
            float e2 = GUN_STILL_EPS * GUN_STILL_EPS;
            return (t.position - gunPos).sqrMagnitude <= e2
                && (t.rotation * Vector3.up - gunRot * Vector3.up).sqrMagnitude <= e2
                && (t.rotation * Vector3.right - gunRot * Vector3.right).sqrMagnitude <= e2;
        }

        /// <summary>A frame's pose time: k / fps exactly, never a clock (S1.7).
        /// `tclock` is T36's mutant arm (dev lever): seconds since the loop began.</summary>
        private static float DanceT(int k, int ms, DanceOpts opt, float loopStart)
        {
            if (opt.tclock) return Time.time - loopStart;
            return k * ms / 1000f;
        }

        // -- the job ----------------------------------------------------------------

        private static IEnumerator DanceRun(string why, string sku, int idx, int gen, DanceOpts opt, DanceClock clock)
        {
            var rep = new StringBuilder();
            _errCount = 0; _errs.Clear();
            _cleanupOwed = true;
            Application.logMessageReceived -= OnLog;
            Application.logMessageReceived += OnLog;
            float t0 = Time.realtimeSinceStartup, tRig = -1f;
            _legSummary = ""; _gunSummary = ""; _particleSummary = "";
            string steam = MatchTracker.LocalSteamId;
            string key = DanceStateKey();
            var inp = Capture(CurrentPreset());
            string baseDesc = inp.descriptor;
            string danceDesc = DanceDescriptor(baseDesc, sku);
            int ms = DanceEmotes.CaptureMs[idx], n = DanceEmotes.CaptureFrames(idx);
            string rkey = DanceMotionCore.RememberKey(steam, danceDesc);
            string fail = null;
            bool remember = false, stale = false;
            int yields = 0;
            GameObject[] rootsBefore = null;
            Transform rigRoot = null;
            DanceRing ring = null;
            DanceMotionCore.FrameOut still = null;
            DanceMotionCore.FrameOut[] frames = null;
            string checkFail = null;
            int prevFps = Application.targetFrameRate, prevVsync = QualitySettings.vSyncCount;
            float prevFixed = Time.fixedDeltaTime;
            bool timing = false;
            int headerLength = 0;
            string rootsLine = "";
            try
            {
                if (inp.refusal != null) { fail = "no picture: " + inp.refusal; yield break; }
                if (danceDesc == null) { fail = "the dance descriptor could not be built"; yield break; }
                if (n <= 0 || n > DanceMotionCore.FRAMES_MAX) { fail = "the table gives " + n + " frames"; yield break; }
                string probeHeader = DanceMotionCore.HeaderText(sku, DanceEmotes.MOTION_RECIPE, n, ms, new string('0', 64));
                if (probeHeader == null) { fail = "the header cannot be written for " + sku; yield break; }
                headerLength = Encoding.UTF8.GetByteCount(probeHeader);
                if (opt.fps > 0 || opt.fixedDt > 0f)
                {
                    timing = true;
                    if (opt.fps > 0) { QualitySettings.vSyncCount = 0; Application.targetFrameRate = opt.fps; }
                    if (opt.fixedDt > 0f) Time.fixedDeltaTime = opt.fixedDt;
                }
                clock.Phase = "start";
                yield return new WaitForEndOfFrame(); yields++;
                if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;

                // S1.4 step 2: the rig, exactly as the static path builds it
                clock.Phase = "setup";
                rootsBefore = SafeRoots();
                tRig = Time.realtimeSinceStartup;
                GameObject clone; CharacterData data;
                string err = BuildRig(rep, out clone, out data);
                if (err != null) { fail = "rig: " + Trunc(err, 160); remember = true; yield break; }
                clone.transform.SetParent(null, true);          // activation: every kept Awake runs now
                _clone = clone;
                rigRoot = clone.transform;
                UnityEngine.Object.Destroy(_root); _root = null;
                if (opt.injectPv) DanceDevInjectPv(rep, clone);
                int pvLeft = DanceSweepPhotonViews(rep, clone, opt.m1CloneOnly);   // M1: same frame, nothing between activation and here
                if (pvLeft != 0) { fail = "M1: " + pvLeft + " PhotonView(s) remain on the rig or its holdable after the sweep"; remember = true; yield break; }
                if (!AfterActivate(rep, clone, data, inp.face, null)) { fail = "the captured face could not be equipped"; remember = true; yield break; }
                MakeGround(rep, clone);
                yield return null; yields++;
                if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                int colour = ApplyColorExact(rep, clone, inp.colorSku, inp.colorHex);
                var aura = ApplyEffectExact(rep, clone, inp.effectSku);
                PinRig(rep, true);
                float ts = Time.realtimeSinceStartup; int settle = 0, gunStill = 0;
                var watch = new ParticleWatch();
                while (Time.realtimeSinceStartup - ts < DEFAULT_SETTLE || settle < 10)
                {
                    settle++;
                    yield return null; yields++;
                    if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                    gunStill = HoldGun() ? gunStill + 1 : 0;
                    watch.Read();
                }
                Stamp(clone); if (_holdable != null) Stamp(_holdable);
                var rig = PinRig(rep, true);
                _gunSummary = rig.Summary(gunStill);
                watch.Read();
                var particles = PinParticles(rep, PlanParticles(false), PARTICLE_SIM_SECS, 0, false);
                _particleSummary = particles.Summary() + " watch " + watch.Summary();
                if (!watch.Steady) { fail = "particles changed during the settle " + watch.Summary(); remember = true; yield break; }
                if (!particles.Ok) { fail = "particles not pinned " + _particleSummary; remember = true; yield break; }
                if (!ColourReady(inp.colorHex, colour)) { fail = "colour not applied as captured"; remember = true; yield break; }
                if (!EffectReady(inp.effectSku, aura, clone)) { fail = "effect not applied as captured"; remember = true; yield break; }
                if (!LegsPlanted(out _legSummary)) { fail = "legs not planted " + _legSummary; remember = true; yield break; }
                if (!rig.Pinned(gunStill)) { fail = "rig not pinned " + _gunSummary; remember = true; yield break; }

                // S1.4 step 3: the frozen baseline
                var arms = DanceFindArms(clone);
                if (arms == null) { fail = "the rig's two arm targets were not found"; remember = true; yield break; }
                Vector3 gunPos = _holdable.transform.position;
                Quaternion gunRot = _holdable.transform.rotation;
                rep.Append("dance baseline: armL=").Append(V(arms.BaseL - PARK)).Append(" armR=").Append(V(arms.BaseR - PARK))
                   .Append(" gun=").Append(V(gunPos - PARK)).Append(" hold=").Append(opt.holdFrames).Append('\n');

                // S1.4 step 4: the union pre-pass -- the rest pose, then every k at k / fps
                clock.Phase = "prepass";
                var scratch = new StringBuilder();
                Bounds union = new Bounds(PARK, Vector3.one); bool any = false;
                float loopStart = Time.time;
                for (int k = -1; k < n; k++)
                {
                    arms.Rest(rigRoot);
                    DanceEmotes.PortraitPose = k < 0 ? (DanceEmotes.PortraitPoseSpec?)null
                                                     : new DanceEmotes.PortraitPoseSpec(rigRoot, idx, DanceT(k, ms, opt, loopStart));
                    for (int h = 0; h < opt.holdFrames; h++)
                    {
                        yield return new WaitForEndOfFrame(); yields++;
                        if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                    }
                    if (!LegsPlanted(out _legSummary)) { fail = "legs not planted at pose " + k + " " + _legSummary; remember = true; yield break; }
                    if (!DanceRigStill(gunPos, gunRot)) { fail = "the rig moved at pose " + k; remember = true; yield break; }
                    scratch.Length = 0;
                    Bounds b;
                    if (!SolidBounds(scratch, clone, out b)) { fail = "no bounds at pose " + k; remember = true; yield break; }
                    if (!any) { union = b; any = true; } else union.Encapsulate(b);
                }
                arms.Rest(rigRoot);
                DanceEmotes.PortraitPose = null;
                Bounds fit = SquareFit(union, 1.3f);
                rep.Append("dance union: ").Append(V(union.min - PARK)).Append("..").Append(V(union.max - PARK))
                   .Append(" fit side=").Append(fit.size.x.ToString("F2")).Append('\n');

                // S1.4 step 5: one camera for both products. Finding S2F4: made
                // all in one frame, the targets and buffers measured 21-61 ms of
                // main thread on the verification seat, over S1.8's 33 ms
                // maximum. Now `_rt` is created with the camera (not on the
                // still's first Render), every other target in a Unity frame of
                // its own behind the after-yield gate, and the fifteen byte
                // buffers on a pool thread (a fresh 5.6 MB array alone measured
                // up to 26 ms there, its page faults paid by the allocating
                // thread). The loop ends only when every target is made and the
                // buffers are in; nothing reads a slot before that.
                clock.Phase = "alloc";
                var cam = MakeCamera(fit, DEFAULT_SIZE);          // the still's 1180 MSAA target is _rt
                _rt.Create();
                RenderTexture msaa = null;                        // the frames' 590 MSAA target
                ring = new DanceRing(++_danceGen, n) { Table = GradeTable, Clock = clock };
                for (int s = 0; s <= DANCE_RING_PAIRS; s++)
                    ring.Slots.Add(new DanceSlot { Edge = s < DANCE_RING_PAIRS ? DANCE_EDGE : DEFAULT_SIZE });
                DanceQueueBuffers(ring);
                int targets = 1 + 2 * ring.Slots.Count;
                for (int step = 0; ; step++)
                {
                    yield return null; yields++;
                    if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                    string e; bool done;
                    lock (ring.Sync) { e = ring.Error; done = ring.BuffersDone; }
                    if (e != null) { fail = e; remember = true; yield break; }
                    if (step == 0) msaa = DanceTarget(DANCE_EDGE, 24, 4);
                    else if (step < targets)
                    {
                        var slot = ring.Slots[(step - 1) / 2];
                        if ((step - 1) % 2 == 0) slot.B = DanceTarget(slot.Edge, 0, 1);
                        else slot.W = DanceTarget(slot.Edge, 0, 1);
                    }
                    else if (done) break;
                }
                var stillSlot = ring.Slots[DANCE_RING_PAIRS];     // the still's pair, made last

                // S1.4 step 6: the still, at rest
                clock.Phase = "still";
                for (int h = 0; h < opt.holdFrames; h++)
                {
                    yield return new WaitForEndOfFrame(); yields++;
                    if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                }
                if (_danceOrientation == 0 || opt.matteq)
                {
                    // The readback's row order on this seat, against ReadPixels (a
                    // Texture2D's order is bottom-up), once per process; with
                    // `matteq` also DanceMotionCore.Matte against MatteOfPasses on
                    // the same pass pair.
                    var cal = ring.Slots[0];
                    Color32[] refB, refW;
                    // One synchronous ReadPixels per Unity frame (S2F4): the pair's
                    // two renders, then each reference a frame later. Nothing
                    // renders into `cal` again before the frames' loop.
                    DanceRenderPair(ring, cam, msaa, cal, -2);
                    yield return null; yields++;
                    if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                    refB = DanceReadPixels(cal.B);
                    yield return null; yields++;
                    if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                    refW = DanceReadPixels(cal.W);
                    while (!ring.CalDone)
                    {
                        yield return null; yields++;
                        if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                        string e; lock (ring.Sync) e = ring.Error;
                        if (e != null) { fail = e; remember = true; yield break; }
                    }
                    int order = DanceOrder(ring.CalB, refB, DANCE_EDGE);
                    rep.Append("dance readback order: ").Append(order == 1 ? "bottom-up" : order == 2 ? "top-down" : order == 3 ? "ambiguous" : "neither").Append('\n');
                    if (order == 1 || order == 2) _danceOrientation = order;
                    else if (order == 0) { _danceOrientation = -1; fail = "the readback matches ReadPixels in neither row order (this seat cannot dance)"; yield break; }
                    else { fail = "the calibration pair cannot tell the row order apart"; yield break; }
                    if (opt.matteq) DanceMatteq(rep, ring.CalB, ring.CalW, refB, refW, opt.matteqFlip);
                }
                ring.BottomUp = _danceOrientation == 1;
                cam.targetTexture = _rt;
                cam.backgroundColor = Color.black; cam.Render(); Graphics.Blit(_rt, stillSlot.B);
                cam.backgroundColor = Color.white; cam.Render(); Graphics.Blit(_rt, stillSlot.W);
                lock (ring.Sync) { stillSlot.State = 1; stillSlot.Arrived = 0; stillSlot.K = -1; ring.InFlight++; }
                AsyncGPUReadback.Request(stillSlot.B, 0, TextureFormat.RGBA32, req => DanceOnReadback(ring, stillSlot, 1, req));
                AsyncGPUReadback.Request(stillSlot.W, 0, TextureFormat.RGBA32, req => DanceOnReadback(ring, stillSlot, 2, req));

                // S1.4 step 7: the frames, through the ring
                clock.Phase = "frames";
                loopStart = Time.time;
                for (int k = 0; k < n; k++)
                {
                    DanceSlot slot;
                    while ((slot = ring.Free()) == null)
                    {
                        yield return null; yields++;
                        if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                        string e; lock (ring.Sync) e = ring.Error;
                        if (e != null) { fail = e; remember = true; yield break; }
                    }
                    arms.Rest(rigRoot);
                    DanceEmotes.PortraitPose = new DanceEmotes.PortraitPoseSpec(rigRoot, idx, DanceT(k, ms, opt, loopStart));
                    for (int h = 0; h < opt.holdFrames; h++)
                    {
                        yield return new WaitForEndOfFrame(); yields++;
                        if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                    }
                    if (!LegsPlanted(out _legSummary)) { fail = "legs not planted at frame " + k + " " + _legSummary; remember = true; yield break; }
                    if (!DanceRigStill(gunPos, gunRot)) { fail = "the rig moved at frame " + k; remember = true; yield break; }
                    string e2; lock (ring.Sync) e2 = ring.Error;
                    if (e2 != null) { fail = e2; remember = true; yield break; }
                    DanceRenderPair(ring, cam, msaa, slot, k);
                }

                // S1.4 step 8: the pose cleared (L1 first), every readback and
                // worker waited for, then the rig torn down
                clock.Phase = "drain";
                arms.Rest(rigRoot);
                DanceEmotes.PortraitPose = null;
                while (true)
                {
                    string e; int inFlight;
                    lock (ring.Sync) { e = ring.Error; inFlight = ring.InFlight; }
                    if (e != null) { fail = e; remember = true; yield break; }
                    if (inFlight == 0) break;
                    yield return null; yields++;
                    if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                }
                lock (ring.Sync) { still = ring.Still; frames = (DanceMotionCore.FrameOut[])ring.Frames.Clone(); }
                ring.Close();
                Teardown(rep);
                yield return null; yields++;                     // deferred Destroy lands
                if ((fail = DanceAfterYield(gen, key, tRig, opt, yields, ref stale, ref remember)) != null) yield break;
                var rootsNow = new StringBuilder();
                CompareRoots(rootsNow, rootsBefore);
                rootsLine = rootsNow.ToString().Trim();
                rep.Append(rootsLine).Append('\n');

                // S1.6: the client's copy of the server's checks, and the still's gate
                if (still == null || still.Png == null) { fail = "the still is missing"; remember = true; yield break; }
                if (still.LitFraction < 0.02 || still.LitFraction > 0.60) { fail = "still discarded: lit " + (100.0 * still.LitFraction).ToString("F1") + "%"; remember = true; yield break; }
                if (still.Png.Length > UPLOAD_MAX_BYTES) { fail = "the still is " + still.Png.Length + " bytes, over the cap"; remember = true; yield break; }
                checkFail = opt.selfFail ? "dev: selffail" : DanceMotionCore.SelfCheck(frames, n, headerLength);
                if (checkFail != null) { fail = "self-check: " + checkFail; remember = true; yield break; }
                if (tRig >= 0f && Time.realtimeSinceStartup - tRig > DANCE_CEILING_S) { fail = "over the " + DANCE_CEILING_S + " s ceiling"; remember = true; yield break; }
                DanceSetPreview(still);
            }
            finally
            {
                DanceEmotes.PortraitPose = null;                  // S1.3: cleared again in the job's finally
                try { if (rigRoot != null) DanceEmotes.RestorePortraitRig(rigRoot); } catch { }
                if (ring != null) ring.Close();
                if (timing)
                {
                    Application.targetFrameRate = prevFps; QualitySettings.vSyncCount = prevVsync;
                    Time.fixedDeltaTime = prevFixed;
                }
                if (!_renderClaim.HeldByOther(gen))
                {
                    _cleanupOwed = false;
                    Application.logMessageReceived -= OnLog;
                    Teardown(rep);
                }
                if (fail != null && remember && danceDesc != null) _danceRemembered.Add(rkey);
                DanceLastResult = fail == null ? "captured" : (stale ? "abandoned: " : remember ? "failed (remembered): " : "stopped: ") + fail;
                if (fail != null && !opt.local) LastResult = stale ? "aborted" : "dance capture failed";
                long bytes = 0; double covMin = 1, covMax = 0;
                if (frames != null) foreach (var f in frames) if (f != null && f.Png != null) { bytes += f.Png.Length; covMin = Math.Min(covMin, f.Coverage); covMax = Math.Max(covMax, f.Coverage); }
                Plugin.Log.LogInfo("[DANCE] " + why + ": capture " + (fail == null ? "ok" : "none") + " sku=" + sku + " frames=" + n + " ms=" + ms
                                   + " hold=" + opt.holdFrames + " still=" + (still != null && still.Png != null ? still.Png.Length : 0)
                                   + " lit=" + (still != null ? (100.0 * still.LitFraction).ToString("F1") : "-") + "% frames_bytes=" + bytes
                                   + " cover=" + (bytes > 0 ? covMin.ToString("F3") + ".." + covMax.ToString("F3") : "-")
                                   + " order=" + _danceOrientation + " yields=" + yields
                                   + " slices[all " + clock.Summary(null) + "; frames " + clock.Summary("frames") + "; setup " + clock.Summary("setup")
                                   + "; still " + clock.Summary("still") + "; prepass " + clock.Summary("prepass") + "; alloc " + clock.Summary("alloc")
                                   + "; drain " + clock.Summary("drain") + "] top[" + clock.Top(6) + "] gc=" + clock.Collections
                                   + " rig=" + _gunSummary + " legs=" + _legSummary + " errors=" + _errCount
                                   + " elapsed=" + (Time.realtimeSinceStartup - t0).ToString("F2") + "s"
                                   + (fail != null ? " result=" + DanceLastResult : ""));
                foreach (var e in _errs) Plugin.Log.LogWarning("[DANCE]   " + e);
                if (opt.local) DanceDevReport(opt, sku, rep, fail, still, frames, n, ms, clock, rootsBefore, remember);
                if (stale) Abandon(key);
                _renderClaim.Drop(gen);
                try { NativeUI.MarkDirty(); } catch { }
            }
            if (fail != null || still == null || frames == null) yield break;
            if (opt.local) { DanceDevCorpus(opt, sku, still, frames, ms); yield break; }
            if (DanceStateKey() != key) { Abandon(key); yield break; }
            var pngs = new List<byte[]>(frames.Length);
            foreach (var f in frames) pngs.Add(f.Png);
            DanceUpload(key, rkey, sku, danceDesc, still.Png, pngs, ms, why);
        }

        /// <summary>The gate after a yield (S1.1, "checked at start and again
        /// after every yield"), with the claim's heartbeat. `gateStartOnly` is
        /// T37's mutant arm (dev lever): the heartbeat alone.</summary>
        private static string DanceAfterYield(int gen, string key, float tRig, DanceOpts opt, int yields, ref bool stale, ref bool remember)
        {
            _renderClaim.Beat(gen, RENDER_BUDGET);
            if (opt.gateStartOnly) return null;
            return DanceGate(gen, key, tRig, opt, yields, ref stale, ref remember);
        }

        /// <summary>Every S1.1 term, read now: DevLeverBlocked (the claim, the
        /// rig, the online room and Photon client state, spectating, a match, a
        /// started game, spawned players), the product refusals (prefab,
        /// identity), the extended state key, AsyncGPUReadback, the grade table,
        /// and the S1.6 ceiling. A moved key is `stale` (Abandon asks for a fresh
        /// picture when the pixel inputs moved); the ceiling is remembered.</summary>
        private static string DanceGate(int gen, string key, float tRig, DanceOpts opt, int yields, ref bool stale, ref bool remember)
        {
            string b = DevLeverBlocked(gen);
            if (b != null) return b;
            if (opt.faultAt >= 0 && yields >= opt.faultAt) return "in an online room (dev fault from yield " + opt.faultAt + ")";
            if (PlayerAssigner.instance == null || PlayerAssigner.instance.playerPrefab == null) return "no player prefab";
            string id = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(id) || id == "unknown") return "no identity";
            if (key != DanceStateKey()) { stale = true; return "the state key moved"; }
            if (!SystemInfo.supportsAsyncGPUReadback) return "AsyncGPUReadback is not supported";
            if (!GradeBaked) return "no baked grade table";
            if (tRig >= 0f && Time.realtimeSinceStartup - tRig > DANCE_CEILING_S) { remember = true; return "over the " + DANCE_CEILING_S + " s ceiling"; }
            return null;
        }

        /// <summary>A target read with ReadPixels, as a Texture2D holds it
        /// (row 0 the bottom): the calibration's reference.</summary>
        private static Color32[] DanceReadPixels(RenderTexture rt)
        {
            var prev = RenderTexture.active;
            Texture2D tex = null;
            try
            {
                RenderTexture.active = rt;
                tex = new Texture2D(rt.width, rt.height, TextureFormat.RGBA32, false);
                tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                tex.Apply();
                return tex.GetPixels32();
            }
            finally
            {
                RenderTexture.active = prev;
                if (tex != null) UnityEngine.Object.Destroy(tex);
            }
        }

        /// <summary>1 when the readback equals the reference row for row, 2 when
        /// it equals it with the rows reversed, 3 when both (an image that cannot
        /// tell them apart), 0 when neither.</summary>
        private static int DanceOrder(byte[] rb, Color32[] reference, int edge)
        {
            if (rb == null || reference == null || rb.Length != reference.Length * 4) return 0;
            bool asIs = true, flipped = true;
            for (int y = 0; y < edge && (asIs || flipped); y++)
            {
                int ry = edge - 1 - y;
                for (int x = 0; x < edge; x++)
                {
                    int p = (y * edge + x) * 4;
                    var a = reference[y * edge + x];
                    var f = reference[ry * edge + x];
                    if (asIs && (rb[p] != a.r || rb[p + 1] != a.g || rb[p + 2] != a.b || rb[p + 3] != a.a)) asIs = false;
                    if (flipped && (rb[p] != f.r || rb[p + 1] != f.g || rb[p + 2] != f.b || rb[p + 3] != f.a)) flipped = false;
                    if (!asIs && !flipped) break;
                }
            }
            return asIs && flipped ? 3 : asIs ? 1 : flipped ? 2 : 0;
        }

        /// <summary>The Settings preview from the dancer's still (reduce(4),
        /// straight RGBA in the readback's row order).</summary>
        private static void DanceSetPreview(DanceMotionCore.FrameOut still)
        {
            if (still == null || still.Preview == null) return;
            int n = DEFAULT_SIZE / 4;
            if (still.Preview.Length != n * n * 4) return;
            byte[] px = still.Preview;
            if (_danceOrientation == 2)
            {
                px = new byte[still.Preview.Length];
                int stride = n * 4;
                for (int y = 0; y < n; y++) Buffer.BlockCopy(still.Preview, (n - 1 - y) * stride, px, y * stride, stride);
            }
            var t = new Texture2D(n, n, TextureFormat.RGBA32, false);
            t.LoadRawTextureData(px);
            t.Apply(false, true);
            t.filterMode = FilterMode.Bilinear;
            var prev = PreviewTex;
            PreviewTex = t; PreviewSerial++;
            if (prev != null) UnityEngine.Object.Destroy(prev);
        }

        // -- S1.4 step 9 / C3: the uploads -------------------------------------------

        /// <summary>The still first through the existing writer with the dance
        /// suffix, then the motion bound to the hash the writer returned (L2:
        /// DanceUploadJob assembles the header and container only then). The
        /// upload claim is held for the whole job.</summary>
        private static void DanceUpload(string key, string rkey, string sku, string danceDesc, byte[] still, List<byte[]> pngs, int ms, string why)
        {
            if (!GradeBaked) { LastResult = "not sent: this build has no baked colour grade table"; return; }
            if (Plugin.Instance == null) { LastResult = "not sent: no host"; return; }
            int ugen = _uploadClaim.Take(Plugin.Instance, UPLOAD_BUDGET);
            LastResult = "uploading";
            var port = new DanceApiPort(MatchTracker.LocalSteamId, key, ugen);
            var job = new DanceUploadJob(port, danceDesc, still, sku, DanceEmotes.MOTION_RECIPE, ms, pngs);
            job.Finished = j => DanceFinished(j, key, rkey, danceDesc, ugen, why);
            job.Start();
        }

        /// <summary>The job's world over ApiClient (IDanceUploadPort).</summary>
        private sealed class DanceApiPort : IDanceUploadPort
        {
            private readonly string _steam, _key;
            private readonly int _ugen, _epoch;

            internal DanceApiPort(string steam, string key, int ugen)
            {
                _steam = steam; _key = key; _ugen = ugen; _epoch = ApiClient.IdentityEpoch;
            }

            public void UploadStill(string descriptor, byte[] png, Action<DanceMotionCore.Answer> done)
            {
                _uploadClaim.Beat(_ugen, UPLOAD_BUDGET);
                ApiClient.PcPortraitUpload(_steam, Guid.NewGuid().ToString("N"), descriptor, png, (ok, resp) =>
                {
                    var a = DanceAnswer(ok, resp);
                    if (ok && a.Status == 200 && _epoch == ApiClient.IdentityEpoch)
                    {
                        var me = ApiClient.CachedPcMe;
                        string d = ApiClient.PcStr(ApiClient.PcTopLevel(resp, "portrait_descriptor"));
                        if (me != null)
                        {
                            if (DanceMotionCore.HexHashOk(a.PortraitHash)) me.portrait_hash = a.PortraitHash;
                            if (!string.IsNullOrEmpty(d)) me.portrait_descriptor = d;
                        }
                    }
                    done(a);
                });
            }

            public void UploadMotion(string descriptor, byte[] container, Action<DanceMotionCore.Answer> done)
            {
                _uploadClaim.Beat(_ugen, UPLOAD_BUDGET);
                ApiClient.PcMotionUpload(_steam, Guid.NewGuid().ToString("N"), descriptor, container, (ok, resp) => done(DanceAnswer(ok, resp)));
            }

            public void After(int seconds, Action then)
            {
                _uploadClaim.Beat(_ugen, UPLOAD_BUDGET);
                if (Plugin.Instance == null) return;
                Plugin.Instance.StartCoroutine(DanceAfter(seconds, then));
            }

            public bool Holds()
            {
                return _epoch == ApiClient.IdentityEpoch && _key == DanceStateKey() && !GameStateWatcher.IsInMatch;
            }

            public void Note(string line) { Plugin.Log.LogInfo("[DANCE] " + line); }
        }

        private static IEnumerator DanceAfter(int seconds, Action then)
        {
            yield return new WaitForSecondsRealtime(seconds);
            try { then(); } catch (Exception ex) { Plugin.Log.LogWarning("[DANCE] wait callback threw: " + ex.Message); }
        }

        /// <summary>An upload's (ok, resp) as the job reads it (S2.6, S2.11).</summary>
        internal static DanceMotionCore.Answer DanceAnswer(bool ok, string resp)
        {
            var a = new DanceMotionCore.Answer { RetryAfter = -1 };
            if (ok)
            {
                a.Status = 200;
                a.PortraitHash = ApiClient.PcStr(ApiClient.PcTopLevel(resp, "portrait_hash"));
                a.Applied = ApiClient.PcBool(ApiClient.PcTopLevel(resp, "applied"));
                return a;
            }
            a.Status = ApiClient.PcHttpCode(resp);
            a.Error = a.Status == 0 ? "transport" : (ApiClient.PcErrorCode(resp) ?? "http");
            a.Reason = ApiClient.PcErrorStr(resp, "reason");
            a.RetryAfter = ApiClient.PcRetryAfterRaw(resp);
            return a;
        }

        /// <summary>What the job's end leaves for the next check (S1.2, S2.11).</summary>
        private static void DanceFinished(DanceUploadJob job, string key, string rkey, string danceDesc, int ugen, string why)
        {
            _uploadClaim.Drop(ugen);
            var a = job.LastAnswer;
            var act = job.LastAct;
            string code = string.IsNullOrEmpty(a.Error) ? a.Status.ToString() : a.Status + " " + a.Error;
            switch (job.Result)
            {
                case DanceUploadResult.MotionApplied:
                    LastResult = "dance card updated";
                    break;
                case DanceUploadResult.MotionSame:
                    LastResult = "dance card current";
                    break;
                case DanceUploadResult.Abandoned:
                    Abandon(key);
                    break;
                case DanceUploadResult.Invalid:
                    _danceRemembered.Add(rkey);
                    LastResult = "dance card not sent";
                    break;
                default:
                    LastResult = (job.Result == DanceUploadResult.StillRefused ? "upload refused: " : "dance refused: ") + code;
                    if (act == DanceMotionCore.Act.Remember) _danceRemembered.Add(rkey);
                    else if (act == DanceMotionCore.Act.HoldOff) _danceHoldUntil = Time.realtimeSinceStartup + DanceMotionCore.HoldSeconds(a);
                    else if (act == DanceMotionCore.Act.SessionStop) _danceSessionStop = true;
                    break;
            }
            DanceLastResult = "upload " + job.Result + " (" + code + ")";
            Plugin.Log.LogInfo("[DANCE] " + why + ": upload " + job.Result + " act=" + act + " answer=" + code
                               + " bound=" + (job.BoundHash != null ? job.BoundHash.Substring(0, 12) : "-") + " trace=" + string.Join(",", job.Trace.ToArray()));
            // The server's selection and motion state after the job, whatever the
            // outcome: the next check decides from it (RefreshMe included).
            if (job.Result != DanceUploadResult.Abandoned)
                try { ApiClient.FetchPcMe(MatchTracker.LocalSteamId, true); } catch { }
            try { NativeUI.MarkDirty(); } catch { }
        }
    }
}
