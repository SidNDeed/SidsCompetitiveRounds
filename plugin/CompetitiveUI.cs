using System;
using System.Collections.Generic;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    public static class CompetitiveUI
    {
        public static int LastKnownLevel = -1;

        // FPS
        private static float fpsTimer = 0f;
        private static int fpsCnt = 0;
        private static float fpsVal = 0f;
        private static GUIStyle fpsStyle;

        // Notification (IMGUI)
        private static string notifText = "";
        private static Color notifColor = Color.white;
        private static float notifTimer = 0f;
        private static List<QueuedNotif> notifQueue = new List<QueuedNotif>();
        private struct QueuedNotif { public string text; public Color color; public float dur; }
        private static GUIStyle notifStyle;

        // Match status
        private static GUIStyle statusStyle;

        public static void ToggleOverlay() => NativeUI.Toggle();

        public static void ShowNotification(string text, Color color, float duration = 3f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            notifText = text;
            notifColor = color;
            notifTimer = duration;
        }

        public static void QueueNotification(string text, Color color, float duration = 3f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            notifQueue.Add(new QueuedNotif { text = text, color = color, dur = duration });
        }

        public static void ResetStyles() { }

        public static void CacheRaycasters() { }

        public static void MarkDirty() => NativeUI.MarkDirty();

        /// <summary>Called from Update. Ticks the native UI.</summary>
        public static void Tick() => NativeUI.Tick();

        /// <summary>Called from OnGUI. FPS + notifications + match status.</summary>
        public static void DrawUI()
        {
            DrawFPS();
            DrawNotification();
            DrawMatchStatus();
        }

        private static void DrawFPS()
        {
            fpsCnt++;
            fpsTimer += Time.deltaTime;
            if (fpsTimer >= 0.5f) { fpsVal = fpsCnt / fpsTimer; fpsCnt = 0; fpsTimer = 0f; }
            if (fpsStyle == null) { fpsStyle = new GUIStyle(GUI.skin.label); fpsStyle.fontSize = 11; fpsStyle.normal.textColor = new Color(0.5f, 0.5f, 0.5f, 0.7f); }

            string label = $"{fpsVal:F0} FPS";
            float width = 60;

            // Show ping + region when connected to Photon
            try
            {
                if (PhotonNetwork.IsConnected && PhotonNetwork.InRoom)
                {
                    int ping = PhotonNetwork.GetPing();
                    string region = PhotonNetwork.CloudRegion ?? "";
                    if (!string.IsNullOrEmpty(region))
                    {
                        // Clean region string (e.g. "us/*" -> "us")
                        int slash = region.IndexOf('/');
                        if (slash > 0) region = region.Substring(0, slash);
                        region = region.ToUpper();
                    }
                    Color pingColor = ping < 60 ? new Color(0.4f, 0.7f, 0.4f, 0.7f) :
                                      ping < 120 ? new Color(0.7f, 0.7f, 0.3f, 0.7f) :
                                                    new Color(0.7f, 0.4f, 0.4f, 0.7f);
                    label += $"  |  {ping}ms  {region}";
                    width = 200;

                    // Draw with ping color for the ping portion
                    GUI.Label(new Rect(6, 4, width, 18), label, fpsStyle);
                    return;
                }
            }
            catch { }

            GUI.Label(new Rect(6, 4, width, 18), label, fpsStyle);
        }

        private static void DrawNotification()
        {
            if (notifTimer <= 0f && notifQueue.Count > 0)
            {
                var n = notifQueue[0]; notifQueue.RemoveAt(0);
                notifText = n.text; notifColor = n.color; notifTimer = n.dur;
            }
            if (notifTimer <= 0f) return;
            notifTimer -= Time.deltaTime;
            float alpha = Mathf.Clamp01(notifTimer);

            if (notifStyle == null)
            {
                notifStyle = new GUIStyle(GUI.skin.label);
                notifStyle.fontSize = 16;
                notifStyle.fontStyle = FontStyle.Bold;
                notifStyle.alignment = TextAnchor.MiddleCenter;
            }

            var color = new Color(notifColor.r, notifColor.g, notifColor.b, alpha);
            var origColor = GUI.contentColor;
            GUI.contentColor = color;

            float width = 500;
            float x = (Screen.width - width) / 2f;
            float y = Screen.height - 80;

            var bgTex = Texture2D.whiteTexture;
            GUI.DrawTexture(new Rect(x, y - 2, width, 28), bgTex, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, alpha * 0.5f), 0, 0);
            GUI.Label(new Rect(x, y, width, 24), notifText, notifStyle);
            GUI.contentColor = origColor;
        }

        private static void DrawMatchStatus()
        {
            if (!MatchTracker.IsInMatch || !GameStateWatcher.MatchIsRanked) return;
            if (statusStyle == null)
            {
                statusStyle = new GUIStyle(GUI.skin.label);
                statusStyle.fontSize = 11;
                statusStyle.fontStyle = FontStyle.Bold;
                statusStyle.alignment = TextAnchor.MiddleCenter;
            }
            var oc = GUI.contentColor;
            GUI.contentColor = Color.green;
            GUI.Label(new Rect((Screen.width - 140) / 2f, 8, 140, 18), "RANKED - Recording", statusStyle);
            GUI.contentColor = oc;
        }
    }
}
