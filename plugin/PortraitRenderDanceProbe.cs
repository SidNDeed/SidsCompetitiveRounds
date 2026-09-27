using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Dance cards build step 0 (design S11.1) and VM test T45
    /// (`body_channel_probe`), on the portrait rig. A dev option of the
    /// `portrait:run,...` lever (Run): after the still, every dance of the
    /// capture table is posed through DanceEmotes.PortraitPose frame by frame
    /// (t = k * ms / 1000, never a clock), the rig is rendered after each pose
    /// and compared with the rest render.
    ///
    /// Options (after `dances`): `dancemode=pose` (T45: PortraitPose set for
    /// every frame), `dancemode=nopose` (T45's mutant: PortraitPose never
    /// set), `dancemode=still` (T45's control: a still-only run, asserting
    /// zero motion); `l1=guarded` (the frame's Tick is the product one) or
    /// `l1=unguarded` (L1's mutant: Tick's pre-L1 hard restore instead);
    /// `only=I:J:..` a subset of dance indexes; `lag=N` re-renders N frames
    /// per dance one frame later (does one frame settle a pose?).
    ///
    /// Per frame, in the capture's own order (design S1.4 steps 4 and 7):
    /// the rig's remembered deltas undone once (RestorePortraitRig, L1), the
    /// frozen arm baseline written back, the pose set; one full frame
    /// (Update, the Arm Postfix, LateUpdate) passes; the frame's Tick; the
    /// targets read (L1: each must equal its baseline plus the clamped
    /// Evaluate offset) and the rig rendered. None of it is reachable from
    /// the product path.</summary>
    internal static partial class PortraitRender
    {
        private const float DANCE_PROBE_MIN_OFFSET = 0.05f;   // world units: a pose this far off rest must show
        // World units, the L1 equality. The rig stands at PARK (4000, 4000), where
        // one float ulp is 2^-11 (about 4.9e-4) units, so a target written there
        // cannot land nearer its exact value than that; 1e-3 is two ulps. The L1
        // defects it must catch move a target by a whole offset (0.05 and up).
        private const float DANCE_PROBE_EPS = 1e-3f;

        private static Transform FindDeepNamed(Transform root, string name)
        {
            if (root == null) return null;
            foreach (var t in root.GetComponentsInChildren<Transform>(true))
                if (t != null && t.name == name) return t;
            return null;
        }

        private static void PixelDiff(Color32[] a, Color32[] b, out int exact, out int over8)
        {
            exact = 0; over8 = 0;
            int n = Math.Min(a.Length, b.Length);
            for (int i = 0; i < n; i++)
            {
                var x = a[i]; var y = b[i];
                if (x.r == y.r && x.g == y.g && x.b == y.b && x.a == y.a) continue;
                exact++;
                if (Math.Abs(x.r - y.r) > PROBE_FLOOR || Math.Abs(x.g - y.g) > PROBE_FLOOR || Math.Abs(x.b - y.b) > PROBE_FLOOR) over8++;
            }
        }

        private static IEnumerator DanceProbeFrames(StringBuilder rep, GameObject clone, Camera cam, int size, string tag,
                                                    string mode, string l1, List<int> only, int lagN, int hold, int gen)
        {
            bool setPose = mode == "pose";
            bool unguarded = l1 == "unguarded";
            Transform rigRoot = clone != null ? clone.transform : null;
            IKArmMove armL = null, armR = null;
            if (clone != null)
                foreach (var a in clone.GetComponentsInChildren<IKArmMove>(true))
                {
                    if (a == null || a.target == null) continue;
                    if (a.target.name.IndexOf("Left", StringComparison.OrdinalIgnoreCase) >= 0) armL = a; else armR = a;
                }
            if (hold < 1) hold = 1;
            rep.Append("dance probe: mode=").Append(mode).Append(" l1=").Append(l1).Append(" lag=").Append(lagN).Append(" hold=").Append(hold)
               .Append(" body-channel=").Append(DanceEmotes.PORTRAIT_BODY_CHANNEL)
               .Append(" armL=").Append(armL != null ? armL.target.name : "none").Append(" armR=").Append(armR != null ? armR.target.name : "none").Append('\n');
            if (rigRoot == null || armL == null || armR == null)
            {
                rep.Append("dance probe: FAIL rig or arm targets not found\n");
                Plugin.Log.LogInfo("[DANCE-T45] FAIL tag=" + tag + " reason=no-arm-targets");
                yield break;
            }
            Vector3 baseL = armL.target.position, baseR = armR.target.position;
            Transform handL = FindDeepNamed(armL.transform, "Hand"), handR = FindDeepNamed(armR.transform, "Hand");
            Color32[] rest;
            {
                var restTex = Grab(cam, Color.black, size);
                rest = restTex.GetPixels32();
                UnityEngine.Object.Destroy(restTex);
            }
            rep.Append("dance probe: baseL=").Append(V(baseL - PARK)).Append(" baseR=").Append(V(baseR - PARK))
               .Append(" handL=").Append(handL != null ? V(handL.position - PARK) : "none")
               .Append(" handR=").Append(handR != null ? V(handR.position - PARK) : "none").Append('\n');

            var tsv = new StringBuilder("dance\tk\tt\talx\taly\tarx\tary\tdLx\tdLy\tdRx\tdRy\tl1_ok\tapplied\tchanged_exact\tchanged_over8\thandLx\thandLy\thandRx\thandRy\n");
            var lagTsv = new StringBuilder("dance\tk\tlag_changed_exact\tlag_changed_over8\n");
            int total = 0, nonzeroFrames = 0, unmovedNonzero = 0, zeroFrames = 0, zeroChanged = 0, anyChanged = 0;
            int l1Checked = 0, l1Fail = 0, l1Pairs = 0, appliedFrames = 0, appliedMissing = 0, lagChecks = 0, lagMoved = 0;
            double minMoving = 1.0, maxChanged = 0.0;
            int dancesNoMotion = 0;
            var perDance = new StringBuilder();
            float t0 = Time.realtimeSinceStartup;
            string blocked;

            var set = new List<int>();
            for (int i = 0; i < DanceEmotes.Defs.Length; i++) if (only == null || only.Contains(i)) set.Add(i);

            yield return new WaitForEndOfFrame();
            try
            {
                foreach (int idx in set)
                {
                    int ms = DanceEmotes.CaptureMs[idx];
                    int n = DanceEmotes.CaptureFrames(idx);
                    int dMoving = 0, dUnmoved = 0; double dMax = 0.0; bool prevNonzeroOk = false;
                    for (int k = 0; k < n; k++)
                    {
                        float t = k * ms / 1000f;
                        // L1: undo the rig's remembered deltas once, then the baseline
                        DanceEmotes.RestorePortraitRig(rigRoot);
                        armL.target.position = baseL; armR.target.position = baseR;
                        armL.velolcity = Vector3.zero; armR.velolcity = Vector3.zero;
                        Vector2 body, al, ar; float rot;
                        DanceEmotes.EvaluateClamped(idx, t, out body, out rot, out al, out ar);
                        if (setPose) DanceEmotes.PortraitPose = new DanceEmotes.PortraitPoseSpec(rigRoot, idx, t);
                        int applied0 = DanceEmotes.PortraitArmApplied;
                        int applied = 0;
                        for (int h = 0; h < hold; h++)
                        {
                            // hold the pose `hold` whole frames; the arm delta counted in the first
                            yield return new WaitForEndOfFrame();
                            _renderClaim.Beat(gen, DEV_BUDGET);
                            if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("dance probe aborted: ").Append(blocked).Append('\n'); yield break; }
                            if (h == 0) applied = DanceEmotes.PortraitArmApplied - applied0;
                        }
                        // the frame's Tick: the product one, or (L1 mutant) its pre-L1 hard restore
                        if (unguarded) DanceEmotes.DevUnguardedRestoreAll(); else DanceEmotes.Tick();
                        Vector3 dL = armL.target.position - baseL, dR = armR.target.position - baseR;
                        Vector2 expL = setPose ? al : Vector2.zero, expR = setPose ? ar : Vector2.zero;
                        bool l1ok = Mathf.Abs(dL.x - expL.x) < DANCE_PROBE_EPS && Mathf.Abs(dL.y - expL.y) < DANCE_PROBE_EPS && Mathf.Abs(dL.z) < DANCE_PROBE_EPS
                                 && Mathf.Abs(dR.x - expR.x) < DANCE_PROBE_EPS && Mathf.Abs(dR.y - expR.y) < DANCE_PROBE_EPS && Mathf.Abs(dR.z) < DANCE_PROBE_EPS;
                        bool nonzero = Mathf.Max(al.magnitude, ar.magnitude) >= DANCE_PROBE_MIN_OFFSET;
                        int expectApplied = setPose ? ((al != Vector2.zero ? 1 : 0) + (ar != Vector2.zero ? 1 : 0)) : 0;
                        if (setPose && nonzero) { if (applied == expectApplied) appliedFrames++; else appliedMissing++; }
                        if (nonzero && setPose)
                        {
                            l1Checked++;
                            if (!l1ok) l1Fail++;
                            if (l1ok && prevNonzeroOk) l1Pairs++;
                            prevNonzeroOk = l1ok;
                        }
                        else if (!l1ok) l1Fail++;
                        var tex = Grab(cam, Color.black, size);
                        var px = tex.GetPixels32();
                        UnityEngine.Object.Destroy(tex);
                        int ce, c8; PixelDiff(rest, px, out ce, out c8);
                        double frac = (double)ce / Math.Max(1, px.Length);
                        total++;
                        if (ce > 0) anyChanged++;
                        if (frac > maxChanged) maxChanged = frac;
                        if (frac > dMax) dMax = frac;
                        if (nonzero)
                        {
                            nonzeroFrames++;
                            if (ce > 0) { dMoving++; if (frac < minMoving) minMoving = frac; }
                            else { dUnmoved++; unmovedNonzero++; }
                        }
                        else { zeroFrames++; if (ce > 0) zeroChanged++; }
                        tsv.Append(DanceEmotes.Defs[idx].Sku).Append('\t').Append(k).Append('\t').Append(t.ToString("F3"))
                           .Append('\t').Append(al.x.ToString("F4")).Append('\t').Append(al.y.ToString("F4"))
                           .Append('\t').Append(ar.x.ToString("F4")).Append('\t').Append(ar.y.ToString("F4"))
                           .Append('\t').Append(dL.x.ToString("F4")).Append('\t').Append(dL.y.ToString("F4"))
                           .Append('\t').Append(dR.x.ToString("F4")).Append('\t').Append(dR.y.ToString("F4"))
                           .Append('\t').Append(l1ok ? 1 : 0).Append('\t').Append(applied)
                           .Append('\t').Append(frac.ToString("F5")).Append('\t').Append(((double)c8 / Math.Max(1, px.Length)).ToString("F5"))
                           .Append('\t').Append(handL != null ? (handL.position.x - PARK.x).ToString("F4") : "-")
                           .Append('\t').Append(handL != null ? (handL.position.y - PARK.y).ToString("F4") : "-")
                           .Append('\t').Append(handR != null ? (handR.position.x - PARK.x).ToString("F4") : "-")
                           .Append('\t').Append(handR != null ? (handR.position.y - PARK.y).ToString("F4") : "-").Append('\n');
                        if (lagN > 0 && (k == 1 || k == n / 3 || k == (2 * n) / 3))
                        {
                            // the same pose one more frame: does the render move again?
                            yield return new WaitForEndOfFrame();
                            _renderClaim.Beat(gen, DEV_BUDGET);
                            if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("dance probe aborted: ").Append(blocked).Append('\n'); yield break; }
                            if (unguarded) DanceEmotes.DevUnguardedRestoreAll(); else DanceEmotes.Tick();
                            var tex2 = Grab(cam, Color.black, size);
                            var px2 = tex2.GetPixels32();
                            UnityEngine.Object.Destroy(tex2);
                            int le, l8; PixelDiff(px, px2, out le, out l8);
                            lagChecks++;
                            if (le > 0) lagMoved++;
                            lagTsv.Append(DanceEmotes.Defs[idx].Sku).Append('\t').Append(k).Append('\t')
                                  .Append(((double)le / Math.Max(1, px.Length)).ToString("F5")).Append('\t')
                                  .Append(((double)l8 / Math.Max(1, px.Length)).ToString("F5")).Append('\n');
                        }
                    }
                    if (dMax <= 0.0) dancesNoMotion++;
                    perDance.Append("dance ").Append(DanceEmotes.Defs[idx].Sku).Append(" frames=").Append(n).Append(" ms=").Append(ms)
                            .Append(" moving=").Append(dMoving).Append(" unmoved-nonzero=").Append(dUnmoved)
                            .Append(" max-changed=").Append(dMax.ToString("F5")).Append('\n');
                }
            }
            finally
            {
                DanceEmotes.PortraitPose = null;
                DanceEmotes.RestorePortraitRig(rigRoot);
            }
            rep.Append(perDance);
            bool motionPass = set.Count > 0 && dancesNoMotion == 0 && unmovedNonzero == 0 && nonzeroFrames > 0;
            bool stillPass = anyChanged == 0 && total > 0;
            bool l1Pass = setPose && l1Fail == 0 && l1Pairs >= 1;
            bool armRan = setPose && appliedMissing == 0 && appliedFrames > 0;
            string line = "tag=" + tag + " mode=" + mode + " l1=" + l1 + " hold=" + hold + " dances=" + set.Count + " frames=" + total
                        + " nonzero-frames=" + nonzeroFrames + " unmoved-nonzero=" + unmovedNonzero + " dances-without-motion=" + dancesNoMotion
                        + " zero-frames=" + zeroFrames + " zero-frames-changed=" + zeroChanged
                        + " min-moving-changed=" + (nonzeroFrames > 0 && minMoving < 1.0 ? minMoving.ToString("F5") : "-")
                        + " max-changed=" + maxChanged.ToString("F5")
                        + " l1-checked=" + l1Checked + " l1-fail=" + l1Fail + " l1-pairs=" + l1Pairs
                        + " arm-update-frames=" + appliedFrames + " arm-update-missing=" + appliedMissing
                        + " lag-checks=" + lagChecks + " lag-moved=" + lagMoved
                        + " secs=" + (Time.realtimeSinceStartup - t0).ToString("F1");
            rep.Append("dance probe: ").Append(line).Append('\n');
            rep.Append("T45 motion assertion (every dance's rig frames change): ").Append(motionPass ? "PASS" : "FAIL").Append('\n');
            rep.Append("T45 still-only assertion (zero motion): ").Append(stillPass ? "PASS" : "FAIL").Append('\n');
            rep.Append("L1 assertion (successive nonzero targets equal Evaluate): ").Append(setPose ? (l1Pass ? "PASS" : "FAIL") : "n/a (no pose)").Append('\n');
            rep.Append("IKArmMove.Update runs on the pinned rig (Arm Postfix applied every nonzero pose): ").Append(setPose ? (armRan ? "YES" : "NO") : "n/a (no pose)").Append('\n');
            Plugin.Log.LogInfo("[DANCE-T45] motion=" + (motionPass ? "PASS" : "FAIL") + " still-only=" + (stillPass ? "PASS" : "FAIL")
                               + " l1=" + (setPose ? (l1Pass ? "PASS" : "FAIL") : "n/a") + " arm-update=" + (setPose ? (armRan ? "YES" : "NO") : "n/a") + " " + line);
            try
            {
                File.WriteAllText(Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_portrait_dance_" + tag + ".tsv"), tsv.ToString());
                File.WriteAllText(Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_portrait_dance_" + tag + "_lag.tsv"), lagTsv.ToString());
            }
            catch (Exception ex) { rep.Append("dance probe tsv write threw: ").Append(ex.Message).Append('\n'); }
        }
    }

    /// <summary>Build step 0's live half (design S11.1): on a fully started
    /// live player (the offline sandbox's local body) performing Floss, the
    /// rig-relevant transforms sampled every 100 ms, the whole window
    /// captured in-engine at rest and at the body channel's extrema (#622:
    /// this seat cannot be captured from outside), and the changed-pixel
    /// fraction inside the body's screen box against the rest frame. The
    /// wobble subtree's own renderers (healthbar, name, crown, chat) are
    /// hidden for the captures and restored after, so a changed pixel is
    /// the body's or the arms'. Settles PORTRAIT_BODY_CHANNEL: the body
    /// channel moves visible body pixels only if a body transform (Art,
    /// Particles, Limbs/LegStuff, Limbs/ArmStuff) moves while the wobble
    /// transform the channel writes does. OFFLINE ONLY (TestDance lever).</summary>
    internal static class DanceStep0Probe
    {
        private const int FLOSS = 7;
        private static bool _running;

        private static string P(Vector3 v) => v.x.ToString("F4") + "," + v.y.ToString("F4") + "," + v.z.ToString("F4");

        private static Player LocalBody()
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm != null && pm.players != null)
                    foreach (var p in pm.players)
                        if (p != null && p.data != null && p.data.view != null && p.data.view.IsMine) return p;
            }
            catch { }
            return null;
        }

        private static string PathOf(Transform t)
        {
            if (t == null) return "none";
            var parts = new List<string>();
            for (var c = t; c != null; c = c.parent) parts.Add(c.name);
            parts.Reverse();
            return string.Join("/", parts.ToArray());
        }

        private static Color32[] ScreenPixels(string file, out int w, out int h)
        {
            w = Screen.width; h = Screen.height;
            Texture2D tex = null;
            try
            {
                tex = new Texture2D(w, h, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                tex.Apply();
                if (file != null) File.WriteAllBytes(Path.Combine(BepInEx.Paths.BepInExRootPath, file), tex.EncodeToPNG());
                return tex.GetPixels32();
            }
            finally { if (tex != null) UnityEngine.Object.Destroy(tex); }
        }

        private static void RectDiff(Color32[] a, Color32[] b, int w, RectInt r, out double exact, out double over8)
        {
            int n = 0, e = 0, o = 0;
            for (int y = r.yMin; y < r.yMax; y++)
                for (int x = r.xMin; x < r.xMax; x++)
                {
                    int i = y * w + x;
                    if (i < 0 || i >= a.Length || i >= b.Length) continue;
                    n++;
                    var p = a[i]; var q = b[i];
                    if (p.r == q.r && p.g == q.g && p.b == q.b) continue;
                    e++;
                    if (Math.Abs(p.r - q.r) > 8 || Math.Abs(p.g - q.g) > 8 || Math.Abs(p.b - q.b) > 8) o++;
                }
            exact = (double)e / Math.Max(1, n); over8 = (double)o / Math.Max(1, n);
        }

        internal static IEnumerator BodyProbe(string tag)
        {
            if (_running) { Plugin.Log.LogInfo("[DANCE-STEP0] busy"); yield break; }
            _running = true;
            var rep = new StringBuilder();
            var hiddenR = new List<Renderer>();
            var hiddenB = new List<Behaviour>();
            string outcome = "inconclusive";
            try
            {
                rep.Append("step0 body probe ").Append(DateTime.UtcNow.ToString("u")).Append(" tag=").Append(tag).Append('\n');
                if (!PhotonNetwork.OfflineMode) { rep.Append("refused: not offline\n"); yield break; }
                Player me = LocalBody();
                if (me == null)
                {
                    // The sandbox waits for a join key (Space: PlayerAssigner.LateUpdate
                    // calls CreatePlayer(null)); synthetic input never reaches this seat
                    // (#420), so the probe asks for that same keyboard player itself.
                    // Offline only (checked above), and only while nobody has joined.
                    var pa = PlayerAssigner.instance;
                    bool canJoin = false;
                    try { canJoin = pa != null && pa.playersCanJoin && (pa.players == null || pa.players.Count == 0); } catch { }
                    rep.Append("no local player; sandbox join open=").Append(canJoin).Append('\n');
                    if (canJoin)
                    {
                        try { pa.CreatePlayer(null); rep.Append("spawned the keyboard player (the sandbox's Space join)\n"); }
                        catch (Exception ex) { rep.Append("spawn threw: ").Append(ex.Message).Append('\n'); }
                    }
                    for (int i = 0; i < 50 && me == null; i++) { yield return new WaitForSecondsRealtime(0.1f); me = LocalBody(); }
                    if (me != null) yield return new WaitForSecondsRealtime(2.5f);   // fully started: landed and settled
                }
                if (me == null) { rep.Append("refused: no local player\n"); yield break; }
                bool gmPlaying = false, battle = false;
                try { gmPlaying = GameManager.instance != null && GameManager.instance.isPlaying; battle = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
                rep.Append("player: active=").Append(me.gameObject.activeInHierarchy).Append(" dead=").Append(me.data.dead)
                   .Append(" data.isPlaying=").Append(me.data.isPlaying).Append(" grounded=").Append(me.data.isGrounded)
                   .Append(" gm.isPlaying=").Append(gmPlaying).Append(" battleOngoing=").Append(battle)
                   .Append(" health=").Append(me.data.health.ToString("F1")).Append('\n');
                if (!me.gameObject.activeInHierarchy || me.data.dead) { rep.Append("refused: player not live\n"); yield break; }

                Transform root = me.transform;
                Transform art = root.Find("Art"), parts = root.Find("Particles"), legs = root.Find("Limbs/LegStuff"), arms = root.Find("Limbs/ArmStuff");
                PlayerWobblePosition wob = null;
                foreach (var w in UnityEngine.Object.FindObjectsOfType<PlayerWobblePosition>())
                    if (w != null && w.player == me) { wob = w; break; }
                Transform wt = wob != null ? wob.transform : null;
                rep.Append("paths: art=").Append(PathOf(art)).Append(" particles=").Append(PathOf(parts))
                   .Append(" legs=").Append(PathOf(legs)).Append(" arms=").Append(PathOf(arms)).Append(" wobble=").Append(PathOf(wt)).Append('\n');
                if (wt != null)
                {
                    rep.Append("under wobble: art=").Append(art != null && art.IsChildOf(wt)).Append(" particles=").Append(parts != null && parts.IsChildOf(wt))
                       .Append(" legs=").Append(legs != null && legs.IsChildOf(wt)).Append(" arms=").Append(arms != null && arms.IsChildOf(wt))
                       .Append(" wobble-under-player=").Append(wt.IsChildOf(root)).Append('\n');
                    foreach (var r in wt.GetComponentsInChildren<Renderer>(true))
                        if (r != null) rep.Append("  wobble renderer ").Append(r.GetType().Name).Append(' ').Append(PathOf(r.transform)).Append(" enabled=").Append(r.enabled).Append('\n');
                    // Canvas lives in UnityEngine.UIModule, which this plugin never references (UI by reflection)
                    foreach (var c in wt.GetComponentsInChildren<Behaviour>(true))
                        if (c != null && c.GetType().Name == "Canvas") rep.Append("  wobble canvas ").Append(PathOf(c.transform)).Append(" enabled=").Append(c.enabled).Append('\n');
                }
                int artR = art != null ? art.GetComponentsInChildren<Renderer>(true).Length : 0;
                int limbR = 0; foreach (var lt in new[] { legs, arms }) if (lt != null) limbR += lt.GetComponentsInChildren<Renderer>(true).Length;
                rep.Append("renderers: art=").Append(artR).Append(" limbs=").Append(limbR).Append('\n');

                IKArmMove aL = null, aR = null;
                foreach (var a in root.GetComponentsInChildren<IKArmMove>(true))
                {
                    if (a == null || a.target == null) continue;
                    if (a.target.name.IndexOf("Left", StringComparison.OrdinalIgnoreCase) >= 0) aL = a; else aR = a;
                }
                Transform hL = null, hR = null;
                if (aL != null) foreach (var t in aL.GetComponentsInChildren<Transform>(true)) if (t.name == "Hand") { hL = t; break; }
                if (aR != null) foreach (var t in aR.GetComponentsInChildren<Transform>(true)) if (t.name == "Hand") { hR = t; break; }

                // the body's screen box at rest (solid renderers of Art and Limbs), 1 unit of margin
                var cam = MainCam.instance != null ? MainCam.instance.cam : Camera.main;
                RectInt box = new RectInt(0, 0, Screen.width, Screen.height);
                try
                {
                    bool any = false; Bounds b = new Bounds();
                    foreach (var tr in new[] { art, legs, arms })
                    {
                        if (tr == null) continue;
                        foreach (var r in tr.GetComponentsInChildren<Renderer>(true))
                        {
                            if (r == null || !r.enabled || !r.gameObject.activeInHierarchy || r is ParticleSystemRenderer) continue;
                            if (!any) { b = r.bounds; any = true; } else b.Encapsulate(r.bounds);
                        }
                    }
                    if (any && cam != null)
                    {
                        b.Expand(new Vector3(2f, 2f, 0f));
                        Vector3 s0 = cam.WorldToScreenPoint(b.min), s1 = cam.WorldToScreenPoint(b.max);
                        int x0 = Mathf.Clamp(Mathf.FloorToInt(Mathf.Min(s0.x, s1.x)), 0, Screen.width - 1);
                        int x1 = Mathf.Clamp(Mathf.CeilToInt(Mathf.Max(s0.x, s1.x)), x0 + 1, Screen.width);
                        int y0 = Mathf.Clamp(Mathf.FloorToInt(Mathf.Min(s0.y, s1.y)), 0, Screen.height - 1);
                        int y1 = Mathf.Clamp(Mathf.CeilToInt(Mathf.Max(s0.y, s1.y)), y0 + 1, Screen.height);
                        box = new RectInt(x0, y0, x1 - x0, y1 - y0);
                    }
                    rep.Append("body box: world=").Append(any ? (P(b.min) + ".." + P(b.max)) : "none").Append(" screen=")
                       .Append(box.xMin).Append(',').Append(box.yMin).Append(' ').Append(box.width).Append('x').Append(box.height)
                       .Append(" of ").Append(Screen.width).Append('x').Append(Screen.height).Append('\n');
                }
                catch (Exception ex) { rep.Append("body box threw: ").Append(ex.Message).Append('\n'); }

                // hide the wobble subtree's own renderers and canvases (restored in finally)
                if (wt != null)
                {
                    foreach (var r in wt.GetComponentsInChildren<Renderer>(true)) if (r != null && r.enabled) { r.enabled = false; hiddenR.Add(r); }
                    foreach (var c in wt.GetComponentsInChildren<Behaviour>(true)) if (c != null && c.GetType().Name == "Canvas" && c.enabled) { c.enabled = false; hiddenB.Add(c); }
                }
                rep.Append("hidden for the captures: renderers=").Append(hiddenR.Count).Append(" canvases=").Append(hiddenB.Count).Append('\n');

                Transform[] probe = { art, parts, legs, arms, aL != null ? aL.target : null, aR != null ? aR.target : null, hL, hR, wt };
                string[] names = { "art", "particles", "legs", "arms", "targetL", "targetR", "handL", "handR", "wobble" };
                var restPos = new Vector3[probe.Length];
                var maxDisp = new float[probe.Length];
                var sb = new StringBuilder("phase\tt\tbody_x\tbody_y\ttilt");
                foreach (var nm in names) sb.Append('\t').Append(nm);
                sb.Append('\n');

                // rest: 10 samples at 100 ms, then two captures 0.5 s apart (the noise floor)
                yield return new WaitForSecondsRealtime(0.5f);
                var restAcc = new Vector3[probe.Length];
                for (int i = 0; i < 10; i++)
                {
                    sb.Append("rest\t").Append((i * 0.1f).ToString("F1")).Append("\t0\t0\t0");
                    for (int j = 0; j < probe.Length; j++)
                    {
                        Vector3 v = probe[j] != null ? root.InverseTransformPoint(probe[j].position) : Vector3.zero;
                        restAcc[j] += v;
                        sb.Append('\t').Append(P(v));
                    }
                    sb.Append('\n');
                    yield return new WaitForSecondsRealtime(0.1f);
                }
                for (int j = 0; j < probe.Length; j++) restPos[j] = restAcc[j] / 10f;
                yield return new WaitForEndOfFrame();
                int sw, sh;
                var restA = ScreenPixels("pc_step0_" + tag + "_restA.png", out sw, out sh);
                yield return new WaitForSecondsRealtime(0.5f);
                yield return new WaitForEndOfFrame();
                var restB = ScreenPixels("pc_step0_" + tag + "_restB.png", out sw, out sh);
                double nE, n8; RectDiff(restA, restB, sw, box, out nE, out n8);
                rep.Append("noise floor (rest A vs rest B, body box): exact=").Append(nE.ToString("F5")).Append(" over8=").Append(n8.ToString("F5")).Append('\n');

                // Floss on the local body, 100 ms samples for its whole duration
                bool ok = DanceEmotes.DevInstallLocal(FLOSS);
                int ts0 = PhotonNetwork.ServerTimestamp;
                rep.Append("floss installed=").Append(ok).Append('\n');
                if (!ok) yield break;
                float dur = DanceEmotes.Defs[FLOSS].Duration;
                float lastSample = -1f;
                int posShots = 0, negShots = 0;
                var shots = new StringBuilder();
                while (true)
                {
                    yield return null;
                    float t = unchecked(PhotonNetwork.ServerTimestamp - ts0) / 1000f;
                    if (t > dur) break;
                    Vector2 body, al, ar; float tilt;
                    DanceEmotes.EvaluateClamped(FLOSS, t, out body, out tilt, out al, out ar);
                    for (int j = 0; j < probe.Length; j++)
                    {
                        if (probe[j] == null) continue;
                        float d = (root.InverseTransformPoint(probe[j].position) - restPos[j]).magnitude;
                        if (d > maxDisp[j]) maxDisp[j] = d;
                    }
                    if (t - lastSample >= 0.1f)
                    {
                        lastSample = t;
                        sb.Append("floss\t").Append(t.ToString("F3")).Append('\t').Append(body.x.ToString("F4")).Append('\t').Append(body.y.ToString("F4")).Append('\t').Append(tilt.ToString("F2"));
                        for (int j = 0; j < probe.Length; j++)
                            sb.Append('\t').Append(probe[j] != null ? P(root.InverseTransformPoint(probe[j].position)) : "-");
                        sb.Append('\n');
                    }
                    bool pos = body.x >= 0.9f * 0.48f, neg = body.x <= -0.9f * 0.48f;
                    if ((pos && posShots < 2) || (neg && negShots < 2))
                    {
                        string nm = "pc_step0_" + tag + "_" + (pos ? "pos" : "neg") + (pos ? posShots : negShots) + ".png";
                        yield return new WaitForEndOfFrame();
                        var ext = ScreenPixels(nm, out sw, out sh);
                        double eE, e8; RectDiff(restA, ext, sw, box, out eE, out e8);
                        shots.Append("extremum ").Append(pos ? "+" : "-").Append(" t=").Append(t.ToString("F3")).Append(" body.x=").Append(body.x.ToString("F3"))
                             .Append(" changed(body box) exact=").Append(eE.ToString("F5")).Append(" over8=").Append(e8.ToString("F5"))
                             .Append(" -> ").Append(nm).Append('\n');
                        if (pos) posShots++; else negShots++;
                    }
                }
                rep.Append(shots);
                for (int j = 0; j < probe.Length; j++)
                    rep.Append("max displacement ").Append(names[j]).Append('=').Append(probe[j] != null ? maxDisp[j].ToString("F4") : "-").Append('\n');
                float bodyMax = Mathf.Max(Mathf.Max(maxDisp[0], maxDisp[1]), Mathf.Max(maxDisp[2], maxDisp[3]));
                float wobbleMax = maxDisp[8];
                bool channelLive = wt != null && wobbleMax > 0.3f;
                if (!channelLive) outcome = "inconclusive (the body channel did not move the wobble transform)";
                else outcome = bodyMax > 0.01f ? "arms-plus-body" : "arms-only";
                rep.Append("outcome=").Append(outcome).Append(" body-transform-max=").Append(bodyMax.ToString("F4"))
                   .Append(" wobble-max=").Append(wobbleMax.ToString("F4")).Append(" dance-wobble-dead=").Append(DanceEmotes.WobbleChannelDead)
                   .Append(" arm-dead=").Append(DanceEmotes.ArmChannelDead).Append('\n');
                try { File.WriteAllText(Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_step0_" + tag + "_samples.tsv"), sb.ToString()); }
                catch (Exception ex) { rep.Append("samples write threw: ").Append(ex.Message).Append('\n'); }
                Plugin.Log.LogInfo("[DANCE-STEP0] outcome=" + outcome + " body-transform-max=" + bodyMax.ToString("F4") + " wobble-max=" + wobbleMax.ToString("F4")
                                   + " noise=" + nE.ToString("F5") + " extrema=" + (posShots + negShots) + " tag=" + tag);
            }
            finally
            {
                foreach (var r in hiddenR) if (r != null) r.enabled = true;
                foreach (var c in hiddenB) if (c != null) c.enabled = true;
                _running = false;
                try { File.WriteAllText(Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_step0_" + tag + "_report.txt"), rep.ToString()); }
                catch { }
                Plugin.Log.LogInfo("[DANCE-STEP0] done tag=" + tag + " outcome=" + outcome);
            }
        }
    }
}
