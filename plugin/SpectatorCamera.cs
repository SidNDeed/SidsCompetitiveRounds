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
    /// SMOOTHING (Aug 18 stream feedback: "keeps zooming in/out" — the raw
    /// containment target moves every few seconds as fighters die, respawn
    /// and teleport, and the first cut followed it both ways at vanilla
    /// speed, reading as pumping): broadcast-camera asymmetry. Growing is
    /// adopted immediately (a fighter must never sit off-frame), at
    /// vanilla's own easing rate. Shrinking only commits after the needed
    /// size has stayed below the committed target CONTINUOUSLY for
    /// SHRINK_HOLD_SECONDS — committed to the MAX need seen over that hold,
    /// so the view never tightens onto a momentary dip — and eases at a
    /// third of the grow rate. A deadband absorbs sub-unit target wiggle
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
        private const float DEADBAND = 1.25f; // ignore sub-unit need wiggle (shake, idle drift)
        private const float SHRINK_HOLD_SECONDS = 2.5f;
        private const float GROW_RATE = 5f;   // vanilla's easing constant
        private const float SHRINK_RATE = 1.5f;

        // Committed-target state (one spectator camera per process).
        private static float _committed = -1f;
        private static float _holdStart = -1f;
        private static float _holdMaxNeed;

        private static void ResetState()
        {
            _committed = -1f;
            _holdStart = -1f;
            _holdMaxNeed = 0f;
        }

        static bool Prefix(CameraZoomHandler __instance)
        {
            try
            {
                if (!RoomActors.LocalIsSpectator)
                {
                    if (_committed >= 0f) ResetState();   // stale across sessions
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

                float now = Time.unscaledTime;
                if (_committed < 0f) _committed = needed;

                if (needed > _committed)
                {
                    // Grow immediately — someone is leaving the frame.
                    _committed = needed;
                    _holdStart = -1f;
                }
                else if (needed < _committed - DEADBAND)
                {
                    // Candidate shrink: commit only to the MAX need seen over
                    // a full continuous hold, so a momentary dip (a death, a
                    // teleport frame) never tightens the view.
                    if (_holdStart < 0f)
                    {
                        _holdStart = now;
                        _holdMaxNeed = needed;
                    }
                    else
                    {
                        if (needed > _holdMaxNeed) _holdMaxNeed = needed;
                        if (now - _holdStart >= SHRINK_HOLD_SECONDS)
                        {
                            _committed = _holdMaxNeed;
                            _holdStart = now;        // re-arm: continued calm keeps easing in
                            _holdMaxNeed = needed;
                        }
                    }
                }
                else
                {
                    // Inside the deadband of the committed size: steady.
                    _holdStart = -1f;
                }

                float cur = cams[0] != null ? cams[0].orthographicSize : _committed;
                float rate = _committed > cur ? GROW_RATE : SHRINK_RATE;
                float t = Time.unscaledDeltaTime * rate;
                for (int i = 0; i < cams.Length; i++)
                {
                    var cam = cams[i];
                    if (cam == null) continue;
                    cam.orthographicSize = Mathf.Lerp(cam.orthographicSize, _committed, t);
                }
                return false;
            }
            catch { return true; }
        }
    }
}
