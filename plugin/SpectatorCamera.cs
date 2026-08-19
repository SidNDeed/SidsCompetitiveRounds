using System;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 18 (Sid): the broadcast/spectator view "only has left-right
    /// capture, not up and down." Vanilla's camera is a fixed-center
    /// orthographic view: CameraZoomHandler lerps every rig camera's
    /// orthographicSize toward Map.size (default 15-20) while the OOB kill
    /// band reaches ±20 world units (#230) — so a fighter flying above (or
    /// knocked below) the frame is alive but invisible, while the wide 16:9
    /// aspect usually keeps the same escape covered horizontally.
    ///
    /// Spectator seats only: replace CameraZoomHandler.Update with a lerp
    /// toward a fighter-CONTAINING target size. Never below the map's own
    /// size, so framing is vanilla-identical whenever everyone is inside
    /// the frame; the horizontal term divides by the camera aspect so a
    /// wide escape zooms out too.
    ///
    /// SMOOTHING, third model (Aug 18 late stream feedback: the border
    /// dance still pumped). Model 1 followed the raw containment target
    /// both ways at vanilla speed — pumping. Model 2 grew instantly and
    /// shrank after a 2.5s calm hold — but a fighter FLIRTING with the
    /// border cycles approach/retreat every 3-8s, so the camera still ran
    /// fast-out / pause / slow-in / fast-out nearly 1:1 with the dance.
    /// Model 3 (this one) deletes the commit/hold state machine: the zoom
    /// target IS the rolling MAXIMUM need over a trailing bucket-ring
    /// window (20 x 0.5s; guaranteed coverage >= 9.5s — see the BUCKETS
    /// comment). Growth is still effectively immediate (a new spike raises
    /// the window max the same frame), but repeated approaches inside the
    /// window hold the target STEADY at the widest recent need — zero
    /// oscillation by construction — and the view only eases back in,
    /// slowly, after a full window of genuine calm. A small shrink-side
    /// deadband stops the asymptotic lerp tail from reading as drift
    /// (screen-shake rides the same rig transform this reads).
    ///
    /// Zoom-only by design: the camera rig transform is never moved — SFSS
    /// lighting, parallax and screen-shake all hang off it (#117/#119) —
    /// and zooming is the mechanism vanilla itself uses on every map load.
    /// Purely local presentation: nothing is replicated, fighter seats keep
    /// vanilla exactly (the prefix returns true for them on one static
    /// check). Any surprise inside falls back to vanilla for the frame.
    /// </summary>
    [HarmonyPatch(typeof(CameraZoomHandler), "Update")]
    internal static class SpectatorCameraZoomPatch
    {
        private const float MARGIN_Y = 3f;    // world units of headroom above/below a body
        private const float MARGIN_X = 4f;    // world units of headroom left/right
        private const float MAX_SIZE = 26f;   // ±20 kill band + margin; bounds a stray body
        private const float GROW_RATE = 5f;   // vanilla's easing constant
        private const float SHRINK_RATE = 0.8f;
        private const float SHRINK_DEADBAND = 0.5f;   // stop the asymptotic ease-in tail
        // Guaranteed trailing coverage is (BUCKETS-1) x BUCKET_SECONDS — the
        // current bucket is partial — so 20 buckets guarantee >= 9.5s
        // (review F3: 16 guaranteed only 7.5s, and a border dance with a
        // ~7.9s period could still age its spike out and pump ~0.4 units
        // before the next approach). Any finite window has a beat period;
        // 9.5s covers the observed 3-8s dance cycles with margin, and the
        // slow shrink + deadband bound what a marginal age-out can move.
        private const int BUCKETS = 20;
        private const float BUCKET_SECONDS = 0.5f;

        // Rolling-max window state (one spectator camera per process).
        private static readonly float[] _ring = new float[BUCKETS];
        private static int _ringIdx = -1;             // -1 = unseeded
        private static float _ringBucketStart;

        /// <summary>Also called from SpectatorSession.EndSession — the one
        /// teardown that runs in EVERY path — so a finished session's
        /// window can never leak into the next one (review r-hud finding 4:
        /// the in-prefix reset only runs if a camera Update happens to fire
        /// between the role clearing and the next session, which room
        /// teardown ordering does not guarantee).</summary>
        internal static void ResetState()
        {
            _ringIdx = -1;
        }

        static bool Prefix(CameraZoomHandler __instance)
        {
            try
            {
                if (!RoomActors.LocalIsSpectator)
                {
                    if (_ringIdx >= 0) ResetState();      // stale across sessions
                    return true;                          // vanilla everywhere else
                }
                var cams = __instance.cameras;            // publicized private; Start() filled it
                if (cams == null || cams.Length == 0) return true;

                // Vanilla's base target: the current map's size (20 when none).
                float baseSize = 20f;
                try
                {
                    var current = MapManager.instance != null ? MapManager.instance.currentMap : null;
                    if (current != null) baseSize = current.Map.size;
                }
                catch { }

                // Containment need over live fighter bodies. players carries
                // fake-null corpses after leaves (#222) — skip them.
                float needed = baseSize;
                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (players != null)
                {
                    var refCam = cams[0];
                    Vector3 center = refCam != null ? refCam.transform.position : Vector3.zero;
                    float aspect = refCam != null && refCam.aspect > 0.1f ? refCam.aspect : (16f / 9f);
                    for (int i = 0; i < players.Count; i++)
                    {
                        var p = players[i];
                        if (p == null) continue;
                        try
                        {
                            if (!p.gameObject.activeInHierarchy) continue;
                            if (p.data == null || p.data.dead) continue;
                            Vector3 pos = p.transform.position;
                            float needY = Mathf.Abs(pos.y - center.y) + MARGIN_Y;
                            float needX = (Mathf.Abs(pos.x - center.x) + MARGIN_X) / aspect;
                            if (needY > needed) needed = needY;
                            if (needX > needed) needed = needX;
                        }
                        catch { }
                    }
                }
                if (needed > MAX_SIZE) needed = MAX_SIZE;
                if (needed < baseSize) needed = baseSize;

                // Rolling-max window: seed the whole ring on first use (or
                // after ResetState), advance one 0.5s bucket at a time, and
                // record this frame's need into the current bucket. The
                // target is the max over all buckets, so any spike inside
                // the trailing window (>= 9.5s) pins the view wide and border
                // approaches cannot oscillate it.
                float now = Time.unscaledTime;
                if (_ringIdx < 0)
                {
                    _ringIdx = 0;
                    _ringBucketStart = now;
                    for (int i = 0; i < BUCKETS; i++) _ring[i] = needed;
                }
                while (now - _ringBucketStart >= BUCKET_SECONDS)
                {
                    _ringIdx = (_ringIdx + 1) % BUCKETS;
                    _ring[_ringIdx] = needed;
                    _ringBucketStart += BUCKET_SECONDS;
                    if (now - _ringBucketStart >= BUCKETS * BUCKET_SECONDS)
                    {
                        // Long stall (loading hitch): the whole window is
                        // stale — reseed at the current need rather than
                        // spinning the ring hundreds of steps.
                        for (int i = 0; i < BUCKETS; i++) _ring[i] = needed;
                        _ringBucketStart = now;
                        break;
                    }
                }
                if (needed > _ring[_ringIdx]) _ring[_ringIdx] = needed;

                float target = baseSize;
                for (int i = 0; i < BUCKETS; i++)
                    if (_ring[i] > target) target = _ring[i];

                float cur = cams[0] != null ? cams[0].orthographicSize : target;
                if (target > cur)
                {
                    float t = Time.unscaledDeltaTime * GROW_RATE;
                    for (int i = 0; i < cams.Length; i++)
                    {
                        var cam = cams[i];
                        if (cam != null) cam.orthographicSize = Mathf.Lerp(cam.orthographicSize, target, t);
                    }
                }
                else if (target < cur - SHRINK_DEADBAND)
                {
                    float t = Time.unscaledDeltaTime * SHRINK_RATE;
                    for (int i = 0; i < cams.Length; i++)
                    {
                        var cam = cams[i];
                        if (cam != null) cam.orthographicSize = Mathf.Lerp(cam.orthographicSize, target, t);
                    }
                }
                // Inside the shrink deadband: hold exactly — no motion.
                return false;
            }
            catch { return true; }
        }
    }
}
