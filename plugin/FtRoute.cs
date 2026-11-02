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
    /// no player data, no write), or a GET of a local file (a file: url that is not a UNC path: the music
    /// engine's own clips, read from disk, never a network route; build decision 23). Everything else, a
    /// route it cannot name included, is refused and counted per route; an allowed request is counted as sent.
    /// One choke point covers every UnityWebRequest transport in the process: a prefix on
    /// UnityWebRequest.SendWebRequest, which runs after the caller has built the request and before anything
    /// is sent. A refused request is never sent: the prefix skips the original, so no transport runs at all
    /// (round-1 MEDIUM, FtRoute.cs:97), SendWebRequest returns null, and the request's result stays InProgress,
    /// which every caller's `result == Success` test reads as a failure (ApiClient's one polling caller has a
    /// variant-only null test). A postfix counts every send the original actually made, by the request's own
    /// method and url and independently of Allow's answer (dispatched:route), so VR6 compares the two counts
    /// per route: a refused route dispatched, or a route sent and dispatched a different number of times, fails.
    /// The three System.Net downloads (CustomCosmetics, EmojiSprites, MusicAssets) and chat's websocket are
    /// closed at their own sites (gate_specs/routes.py, uploads.py).</summary>
    internal static class FtRoute
    {
        private const int NAME_CAP = 64;

        private static readonly string[][] Open =
        {
            T("/api/v1/health"), T("/api/v1/mod-version"), T("/api/v1/admin/maintenance/status"),
            T("/api/v1/alerts/active"), T("/api/v1/release-notes/{}"), T("/api/v1/release-notes/full/{}"),
            T("/api/v1/releases/recent"), T("/api/v1/i18n/pack/{}"), T("/translate"),
        };

        private static readonly HashSet<string> _names = new HashSet<string>(StringComparer.Ordinal);

        private static string[] T(string p) { return p.Split('/'); }

        /// <summary>The name a request is counted under, from its method and url alone (both counters use it).</summary>
        internal static string Classify(string method, string url)
        {
            Uri u;
            if (string.IsNullOrEmpty(url) || !Uri.TryCreate(url, UriKind.Absolute, out u)) return "unparsed";
            if (u.IsFile && !u.IsUnc) return (method ?? "?") + "_local";
            return Name(method, u);
        }

        /// <summary>True when the request may be sent. route is the name it is counted under.</summary>
        internal static bool Allow(string method, string url, out string route)
        {
            route = Classify(method, url);
            Uri u;
            if (string.IsNullOrEmpty(url) || !Uri.TryCreate(url, UriKind.Absolute, out u)) return false;
            if (!string.Equals(method, "GET", StringComparison.Ordinal)) return false;
            if (u.IsFile) return !u.IsUnc;
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
        /// <summary>False (the original skipped: nothing is sent, no transport runs) for every refused request.</summary>
        [HarmonyPrefix]
        private static bool Prefix(UnityWebRequest __instance)
        {
            string route = "unreadable";
            bool allowed = false;
            try { allowed = FtRoute.Allow(__instance.method, __instance.url, out route); }
            catch { allowed = false; }
            if (allowed) { FtUpload.Count("sent", route); return true; }
            FtUpload.RefuseQuiet("route", route);
            return false;
        }

        /// <summary>The dispatch counter: every send the original made, named from the request itself.</summary>
        [HarmonyPostfix]
        private static void Postfix(UnityWebRequest __instance, bool __runOriginal)
        {
            if (!__runOriginal) return;
            string route;
            try { route = FtRoute.Classify(__instance.method, __instance.url); }
            catch { route = "unreadable"; }
            FtUpload.Count("dispatched", route);
        }
    }
}
#endif
