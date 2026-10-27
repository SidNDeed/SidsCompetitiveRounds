using System;
using System.Globalization;
using System.Text;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace CompetitiveRounds
{
    /// <summary>
    /// Letterbox ghost fix: a mod-owned camera that clears the WHOLE window to
    /// opaque black before anything else draws.
    ///
    /// ROUNDS draws its cameras into a 16:9 viewport. On a window of any other
    /// aspect (16:10 measured: 90 px strips top and bottom at 2880x1800) nothing
    /// clears the window outside that viewport, while the mod draws across the
    /// full window (the F5 page's overlay canvas, the chat canvas, IMGUI toasts
    /// and tooltips). The strips therefore keep the last frame anything drew
    /// there, indefinitely. No ROUNDS camera can be assumed to clear colour:
    /// MainCamera clears depth only and the background is LightCamera's clear,
    /// confined to the viewport rect (learnings #116, #117, #395).
    ///
    /// The camera renders nothing (cullingMask 0); it only clears. Its depth is
    /// ADAPTIVE: the minimum depth over every other enabled camera, minus one,
    /// re-read on every scene change and every AdaptPeriodSeconds. A camera
    /// enabled mid-scene below that depth draws under the clear until the next
    /// periodic pass (at most one period). Inside the viewport ROUNDS' own
    /// cameras draw over the black (LightCamera clears its rect); outside it
    /// the strips stay black. Whether the viewport is pixel-unchanged is the
    /// laptop seat's acceptance probe, not a claim made here. Visual and local
    /// only, so it is not gated.
    ///
    /// Lifetime: a child of the persistent host, created from
    /// Plugin.AttachPersistentCompanions (initial spawn AND the OnDestroy
    /// respawn), so it lives exactly as long as the host does; Upkeep
    /// re-creates it if it is ever destroyed on its own. (Named Upkeep, not
    /// Tick, and CreateClearCamera, not Attach: tools/keybind_surfaces.py
    /// resolves call references by member name, and a shared name would add
    /// false chain hops to every other member of that name.)
    /// </summary>
    internal static class LetterboxClear
    {
        internal const string ObjectName = "CR_LetterboxClear";
        internal const string LogTag = "[LETTERBOX]";
        // Depth re-adaptation period (seconds, unscaled time).
        internal const float AdaptPeriodSeconds = 2f;

        private static Camera _cam;
        private static float _nextAdaptAt;
        private static int _sceneHandle = int.MinValue;
        private static bool _logPending = true;

        /// <summary>True for the clearing camera. Every pass that walks all
        /// cameras and rewrites them (the map-colour clear pass) skips it.</summary>
        internal static bool IsOurs(Camera c)
        {
            return c != null && _cam != null && c == _cam;
        }

        /// <summary>Creates the clearing camera as a child of the persistent host.
        /// Called from Plugin.AttachPersistentCompanions only.</summary>
        internal static void CreateClearCamera(GameObject host)
        {
            try
            {
                if (host == null) return;
                var go = new GameObject(ObjectName);
                go.hideFlags = HideFlags.HideAndDontSave;
                go.transform.SetParent(host.transform, false);
                var cam = go.AddComponent<Camera>();
                ApplyClearConfig(cam);
                _cam = cam;
                _logPending = true;
                AdaptClearDepth(false);
                Plugin.Log.LogInfo($"{LogTag} clear camera created on '{host.name}', depth {cam.depth:F0}");
            }
            catch (Exception ex)
            {
                try { Plugin.Log.LogWarning($"{LogTag} create failed: {ex.Message}"); } catch { }
            }
        }

        /// <summary>Called every frame from the persistent host's Update. Cheap per
        /// frame (one scene-handle compare); the camera walk runs on a scene change
        /// and then every AdaptPeriodSeconds.</summary>
        internal static void Upkeep(GameObject host)
        {
            try
            {
                if (_cam == null)
                {
                    // Destroyed without its host (the host's own destruction
                    // goes through the respawn, which calls CreateClearCamera).
                    if (host != null) CreateClearCamera(host);
                    return;
                }
                float now = Time.unscaledTime;
                int handle = SceneManager.GetActiveScene().handle;
                if (handle != _sceneHandle)
                {
                    _sceneHandle = handle;
                    // Re-adapt at once rather than up to a period later, so the
                    // cameras the new scene loaded with are not drawn under the
                    // clear for that period; the measurement line is written by the
                    // periodic pass one period later, once the scene's camera
                    // rects have settled.
                    _logPending = true;
                    AdaptClearDepth(false);
                    _nextAdaptAt = now + AdaptPeriodSeconds;
                    return;
                }
                if (now < _nextAdaptAt) return;
                _nextAdaptAt = now + AdaptPeriodSeconds;
                ApplyClearConfig(_cam);
                AdaptClearDepth(true);
            }
            catch { }
        }

        private static void ApplyClearConfig(Camera cam)
        {
            if (cam.clearFlags != CameraClearFlags.SolidColor) cam.clearFlags = CameraClearFlags.SolidColor;
            var black = new Color(0f, 0f, 0f, 1f);
            if (cam.backgroundColor != black) cam.backgroundColor = black;
            if (cam.cullingMask != 0) cam.cullingMask = 0;
            var full = new Rect(0f, 0f, 1f, 1f);
            if (cam.rect != full) cam.rect = full;
            if (cam.targetTexture != null) cam.targetTexture = null;
            if (!cam.orthographic) cam.orthographic = true;
            if (cam.allowHDR) cam.allowHDR = false;
            if (cam.allowMSAA) cam.allowMSAA = false;
            if (cam.useOcclusionCulling) cam.useOcclusionCulling = false;
            if (!cam.enabled) cam.enabled = true;
            if (!cam.gameObject.activeSelf) cam.gameObject.SetActive(true);
        }

        /// <summary>Sets the clear camera's depth to (minimum depth over every other
        /// enabled camera) - 1. With no other camera enabled the depth is left as
        /// it is. With allowLog, writes the measured camera set once per scene.</summary>
        private static void AdaptClearDepth(bool allowLog)
        {
            if (_cam == null) return;
            var cams = Camera.allCameras;
            float min = float.MaxValue;
            bool any = false;
            StringBuilder sb = (allowLog && _logPending) ? new StringBuilder(LogTag + " cameras:") : null;
            foreach (var c in cams)
            {
                if (c == null || c == _cam) continue;
                any = true;
                if (c.depth < min) min = c.depth;
                if (sb != null)
                {
                    var r = c.rect;
                    var inv = CultureInfo.InvariantCulture;   // a comma-decimal locale would make the rect unreadable
                    sb.Append(' ').Append(c.name).Append(':').Append(c.depth.ToString("F0", inv))
                      .Append(":(").Append(r.x.ToString("F3", inv)).Append(',').Append(r.y.ToString("F3", inv))
                      .Append(',').Append(r.width.ToString("F3", inv)).Append(',').Append(r.height.ToString("F3", inv))
                      .Append("):").Append(c.clearFlags);
                    if (c.targetTexture != null) sb.Append(":rt");
                }
            }
            float before = _cam.depth;
            if (any)
            {
                float want = min - 1f;
                if (_cam.depth != want) _cam.depth = want;
            }
            if (sb != null && any)
            {
                _logPending = false;
                sb.Append(" clear-camera depth ").Append(_cam.depth.ToString("F0"))
                  .Append(" (scene '").Append(SceneManager.GetActiveScene().name)
                  .Append("', screen ").Append(Screen.width).Append('x').Append(Screen.height).Append(')');
                Plugin.Log.LogInfo(sb.ToString());
            }
            else if (_cam.depth != before)
            {
                Plugin.Log.LogInfo($"{LogTag} clear-camera depth {before:F0} -> {_cam.depth:F0}");
            }
        }
    }
}
