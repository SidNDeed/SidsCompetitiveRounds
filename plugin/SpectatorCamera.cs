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
    /// band reaches ±20 world units vertically (#230) — so a fighter flying
    /// above (or knocked below) the frame is alive but invisible, while the
    /// wide 16:9 aspect usually keeps the same escape covered horizontally.
    ///
    /// Spectator seats only: replace CameraZoomHandler.Update with the same
    /// lerp toward a fighter-CONTAINING target size. Never below the map's
    /// own size, so framing is vanilla-identical whenever everyone is inside
    /// the frame; the horizontal term divides by the camera aspect so a wide
    /// escape (small maps: half-width at size 15 is ~26.7 vs the ±35.56
    /// band) zooms out too.
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

        static bool Prefix(CameraZoomHandler __instance)
        {
            try
            {
                if (!RoomActors.LocalIsSpectator) return true;   // vanilla everywhere else
                var cams = __instance.cameras;                    // publicized private; Start() filled it
                if (cams == null || cams.Length == 0) return true;

                // Vanilla's base target: the current map's size (20 when none).
                float baseSize = 20f;
                try
                {
                    var current = MapManager.instance != null ? MapManager.instance.currentMap : null;
                    if (current != null) baseSize = current.Map.size;
                }
                catch { }
                float target = baseSize;

                // Containment pass over live fighter bodies. players carries
                // fake-null corpses after leaves (#222) — skip them.
                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (players != null)
                {
                    // All rig cameras share one transform family; the first
                    // stands for the frame's center and aspect.
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
                            if (needY > target) target = needY;
                            if (needX > target) target = needX;
                        }
                        catch { }
                    }
                }
                if (target > MAX_SIZE) target = MAX_SIZE;
                if (target < baseSize) target = baseSize;

                // Vanilla's own easing constant, toward the containing target.
                float t = Time.unscaledDeltaTime * 5f;
                for (int i = 0; i < cams.Length; i++)
                {
                    var cam = cams[i];
                    if (cam == null) continue;
                    cam.orthographicSize = Mathf.Lerp(cam.orthographicSize, target, t);
                }
                return false;
            }
            catch { return true; }
        }
    }
}
