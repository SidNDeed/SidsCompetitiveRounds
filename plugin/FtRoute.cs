#if SCR_FRAMETIME
using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine.Networking;

namespace CompetitiveRounds
{
    /// <summary>FrameTime part b item 5 (FORMAT-M-PLAN.md V2 section 3, F02), the route classifier: a request
    /// is allowed only when it is a GET, to the mod's own backend (ApiClient.BaseUrl's authority), on a route
    /// in read_gate.py's OPEN set (backend/api/read_gate.py:143-158 at 1c77f580: readable with no credential,
    /// no player data, no write). Everything else, a route it cannot name included, is refused as a transport
    /// failure and counted per route; an allowed request is counted as sent, so a refused route's send count
    /// is zero by construction (VR6).
    /// One choke point covers every UnityWebRequest transport in the process: a prefix on
    /// UnityWebRequest.SendWebRequest, which runs after the caller has built the request and before anything
    /// is sent. A refused request has its url replaced by Sink (loopback, port 1, where nothing listens), so it
    /// fails as a connection error through the caller's own failure path and its body never leaves the seat.
    /// The three System.Net downloads (CustomCosmetics, EmojiSprites, MusicAssets) and chat's websocket are
    /// closed at their own sites (gate_specs/routes.py, uploads.py).</summary>
    internal static class FtRoute
    {
        internal const string Sink = "http://127.0.0.1:1/ft-refused";
        private const int NAME_CAP = 64;

        private static readonly string[][] Open =
        {
            T("/api/v1/health"), T("/api/v1/mod-version"), T("/api/v1/admin/maintenance/status"),
            T("/api/v1/alerts/active"), T("/api/v1/release-notes/{}"), T("/api/v1/release-notes/full/{}"),
            T("/api/v1/releases/recent"), T("/api/v1/i18n/pack/{}"), T("/translate"),
        };

        private static readonly HashSet<string> _names = new HashSet<string>(StringComparer.Ordinal);

        private static string[] T(string p) { return p.Split('/'); }

        /// <summary>True when the request may be sent. route is the name it is counted under.</summary>
        internal static bool Allow(string method, string url, out string route)
        {
            route = "unparsed";
            Uri u;
            if (string.IsNullOrEmpty(url) || !Uri.TryCreate(url, UriKind.Absolute, out u)) return false;
            route = Name(method, u);
            if (!string.Equals(method, "GET", StringComparison.Ordinal)) return false;
            Uri b;
            string baseUrl = ApiClient.BaseUrl;
            if (string.IsNullOrEmpty(baseUrl) || !Uri.TryCreate(baseUrl, UriKind.Absolute, out b)) return false;
            if (!string.Equals(u.Scheme, b.Scheme, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(u.Authority, b.Authority, StringComparison.OrdinalIgnoreCase)) return false;
            string[] seg = u.AbsolutePath.Split('/');
            foreach (var t in Open)
                if (Match(t, seg)) return true;
            return false;
        }

        private static bool Match(string[] t, string[] seg)
        {
            if (t.Length != seg.Length) return false;
            for (int i = 0; i < t.Length; i++)
            {
                if (t[i] == "{}") { if (seg[i].Length == 0) return false; continue; }
                if (!string.Equals(t[i], seg[i], StringComparison.Ordinal)) return false;
            }
            return true;
        }

        /// <summary>method, host and path with every segment holding a digit replaced by {n}; at most NAME_CAP
        /// distinct names, then "other", so the count table stays bounded.</summary>
        internal static string Name(string method, Uri u)
        {
            string[] seg = u.AbsolutePath.Split('/');
            for (int i = 0; i < seg.Length; i++)
                foreach (char ch in seg[i])
                    if (ch >= '0' && ch <= '9') { seg[i] = "{n}"; break; }
            string n = (method ?? "?") + "_" + u.Host + string.Join("/", seg);
            lock (_names)
            {
                if (_names.Contains(n)) return n;
                if (_names.Count >= NAME_CAP) return (method ?? "?") + "_other";
                _names.Add(n);
                return n;
            }
        }
    }

    [HarmonyPatch(typeof(UnityWebRequest), nameof(UnityWebRequest.SendWebRequest))]
    internal static class FtRoute_SendPatch
    {
        /// <summary>False (the original skipped, nothing sent) only when a refused request cannot be redirected.</summary>
        [HarmonyPrefix]
        private static bool Prefix(UnityWebRequest __instance)
        {
            string route = "unreadable";
            bool allowed = false;
            try { allowed = FtRoute.Allow(__instance.method, __instance.url, out route); }
            catch { allowed = false; }
            if (allowed) { FtUpload.Count("sent", route); return true; }
            FtUpload.RefuseQuiet("route", route);
            try { __instance.url = FtRoute.Sink; return true; }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FRAME-TIME] route refusal could not redirect " + route + ", send skipped: " + ex.Message);
                return false;
            }
        }
    }
}
#endif
