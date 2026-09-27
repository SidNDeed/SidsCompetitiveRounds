using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
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
