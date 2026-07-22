using Steamworks;
using System;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// July 21 item 4 — Steam ownership proof. The HMAC shared secret ships in
    /// the DLL and is extractable, so on its own it only proves "a copy of the
    /// mod sent this", not "the owner of this Steam ID sent this". This class
    /// mints a Steam WEB-API auth ticket (SteamUser.GetAuthTicketForWebApi —
    /// present in the game's bundled Steamworks.NET, verified by decompile),
    /// posts it to the server, and holds the opaque session token the server
    /// returns after verifying the ticket with ISteamUserAuth/AuthenticateUserTicket.
    /// The token rides every API call as X-Session-Token. Failure is always
    /// soft on the client: no ticket -> no header -> the server's enforcement
    /// mode decides (log-only until the web key + version floor are live).
    /// The game's own SteamManager pumps SteamAPI.RunCallbacks every frame, so
    /// the ticket callback fires without any pumping here. The Callback object
    /// MUST stay referenced in a static or it gets GC'd and never fires.
    /// </summary>
    internal static class SteamAuth
    {
        public static string SessionToken { get; private set; }
        private static float _sessionExpiresAt = -1f;    // Time.realtimeSinceStartup
        private static Callback<GetTicketForWebApiResponse_t> _webTicketCb;
        private static bool _requestInFlight;
        private static float _requestStartedAt = -999f;
        private static float _lastAttemptAt = -999f;
        private static bool _loggedUnavailable;

        public static bool HasFreshToken =>
            !string.IsNullOrEmpty(SessionToken)
            && Time.realtimeSinceStartup < _sessionExpiresAt - 3600f;   // refresh 1h before expiry

        /// <summary>Ticked from ApiClient's heartbeat loop (~20s). Mints a new
        /// ticket whenever no fresh session is held, with a 60s retry backoff.</summary>
        public static void MaybeRefresh()
        {
            try
            {
                // Un-latch a lost ticket callback (Steam hiccup): a request in
                // flight >30s is presumed dead, allow a fresh mint.
                if (_requestInFlight && Time.realtimeSinceStartup - _requestStartedAt > 30f)
                    _requestInFlight = false;
                if (HasFreshToken || _requestInFlight) return;
                // Hammer until the FIRST session lands (enforced actions 401
                // without one, so the startup window must be short); relax to
                // a 60s pre-expiry refresh cadence once established.
                float backoff = string.IsNullOrEmpty(SessionToken) ? 4f : 60f;
                if (Time.realtimeSinceStartup - _lastAttemptAt < backoff) return;
                string sid = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(sid) || sid == "unknown" || sid.StartsWith("photon_")) return;
                _lastAttemptAt = Time.realtimeSinceStartup;
                if (_webTicketCb == null)
                    _webTicketCb = Callback<GetTicketForWebApiResponse_t>.Create(OnWebTicket);
                SteamUser.GetAuthTicketForWebApi("competitive-rounds");
                _requestInFlight = true;
                _requestStartedAt = Time.realtimeSinceStartup;
            }
            catch (Exception ex)
            {
                if (!_loggedUnavailable)
                {
                    _loggedUnavailable = true;
                    Plugin.Log.LogWarning($"[STEAM-AUTH] ticket request unavailable: {ex.Message} — running without session auth");
                }
            }
        }

        private static void OnWebTicket(GetTicketForWebApiResponse_t cb)
        {
            _requestInFlight = false;
            try
            {
                if (cb.m_eResult != EResult.k_EResultOK || cb.m_cubTicket <= 0 || cb.m_rgubTicket == null)
                {
                    Plugin.Log.LogWarning($"[STEAM-AUTH] ticket callback failed: {cb.m_eResult}");
                    return;
                }
                string hex = BitConverter.ToString(cb.m_rgubTicket, 0, cb.m_cubTicket).Replace("-", "");
                Plugin.Log.LogInfo($"[STEAM-AUTH] web ticket minted ({cb.m_cubTicket} bytes) — exchanging for session");
                ApiClient.PostSteamAuth(hex);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[STEAM-AUTH] ticket handling error: {ex.Message}");
            }
        }

        public static void SetSession(string token, int expiresInSeconds)
        {
            if (string.IsNullOrEmpty(token)) return;
            SessionToken = token;
            _sessionExpiresAt = Time.realtimeSinceStartup + Mathf.Max(600, expiresInSeconds);
            Plugin.Log.LogInfo($"[STEAM-AUTH] session established (expires in {expiresInSeconds}s)");
        }

        /// <summary>Server rejected our session (hard-enforce mode) — drop it so
        /// the next MaybeRefresh mints a fresh ticket immediately.</summary>
        public static void InvalidateSession()
        {
            SessionToken = null;
            _sessionExpiresAt = -1f;
            _lastAttemptAt = -999f;
        }

        /// <summary>Invalidate only if the rejected token is STILL the current
        /// one — guards the race where a slow request's 401 lands after a
        /// newer session was already minted.</summary>
        public static void InvalidateSessionIf(string token)
        {
            if (!string.IsNullOrEmpty(token) && token == SessionToken) InvalidateSession();
        }
    }
}
