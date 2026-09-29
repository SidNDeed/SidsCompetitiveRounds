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
        private static float _lastAttemptAt = -999f;
        private static bool _loggedUnavailable;

        // One Steam web-API ticket at a time (board row 27 round 2, the
        // no-token residual). A ticket is HELD from the request until its
        // exchange ends, and every end cancels it with Steam: the answer
        // (a session or a refusal), a transport failure or timeout, a refusal
        // before the post, a failed ticket callback, or abandonment. Before
        // this the latch cleared at the ticket CALLBACK, so while exchanges
        // timed out (20 s) a new ticket was requested every 4 s and none was
        // ever cancelled; the 2026-09-28 note in MaybeRefresh records twenty
        // such tickets followed by no further ticket for the rest of the
        // session, and the round-2 witness S4 repeated it (20 tickets, then
        // none after the restore).
        //
        // Round 3 (Codex round 2 LOW 5): the latch is SecureRouteRules.TicketLatch
        // and is released only after the cancel returns. A cancel that throws
        // keeps the handle held-but-failed; the next refresh tick retries it
        // once and then retires the handle with a log line; no successor ticket
        // is requested while a handle is unretired (harness MT6-MT8).
        private static readonly SecureRouteRules.TicketLatch _latch = new SecureRouteRules.TicketLatch();
        private static HAuthTicket _ticket;

        /// <summary>The one-ticket latch, read (never driven) by the portal's
        /// session waits: whether a sign-in they depend on is still running.</summary>
        internal static SecureRouteRules.TicketLatch Latch => _latch;

        public static bool HasFreshToken =>
            !string.IsNullOrEmpty(SessionToken)
            && Time.realtimeSinceStartup < _sessionExpiresAt - 3600f;   // refresh 1h before expiry

        /// <summary>Ticked from ApiClient's loops (SteamAuthLoop every 3 s, the
        /// presence loop, the portal's session wait). Requests a ticket whenever
        /// no fresh session is held and the api would exchange it: 4 s apart
        /// while no session is held, 60 s apart while one nears expiry.</summary>
        public static void MaybeRefresh()
        {
            try
            {
                // A held ticket whose end never arrived (a lost callback, a
                // coroutine that died with its host) is abandoned and
                // cancelled here, and a cancel that failed is retried once and
                // then retired, so the next ticket supersedes the old one and
                // never stacks on it.
                string note = _latch.Tick(Time.realtimeSinceStartup, CancelHeldTicket, out bool tickFailed);
                if (note != null)
                {
                    if (tickFailed) Plugin.Log.LogWarning(note);
                    else Plugin.Log.LogInfo(note);
                }
                string sid = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(sid) || sid == "unknown" || sid.StartsWith("photon_")) return;
                // No ticket while the api would refuse to exchange it (the
                // plaintext backup; PostSteamAuth asks the same question). On
                // the broadcast seat (2026-09-28) twenty unexchanged tickets
                // were followed by no further ticket for the rest of that
                // session, so a session back on the secure route (board row
                // 27) could not sign in again. Asked before the session
                // checks, so the refusal notice also reaches a player who
                // holds a session (the backup withholds its token, so
                // signed-in features are off either way); no attempt is spent
                // here, so the first tick after the route returns can request
                // one.
                if (!ApiClient.TicketExchangeAllowed())
                {
                    ApiClient.NoteTicketExchangeRefused();
                    return;
                }
                if (HasFreshToken || !_latch.MayRequest) return;
                // Hammer until the FIRST session lands (enforced actions 401
                // without one, so the startup window must be short); relax to
                // a 60s pre-expiry refresh cadence once established.
                float backoff = string.IsNullOrEmpty(SessionToken) ? 4f : 60f;
                if (Time.realtimeSinceStartup - _lastAttemptAt < backoff) return;
                _lastAttemptAt = Time.realtimeSinceStartup;
                if (_webTicketCb == null)
                    _webTicketCb = Callback<GetTicketForWebApiResponse_t>.Create(OnWebTicket);
                _ticket = SteamUser.GetAuthTicketForWebApi("competitive-rounds");
                _latch.Took(Time.realtimeSinceStartup);
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
            // Only the held ticket's callback counts. A late callback for a
            // ticket already ended (abandoned, so already cancelled) is dropped:
            // exchanging it would put a second exchange beside the held one.
            if (!_latch.IsHeld || cb.m_hAuthTicket.m_HAuthTicket != _ticket.m_HAuthTicket) return;
            int serial = _latch.Serial;
            // The exchange's own timeout starts here, not at the request: a
            // portal wait keeps waiting for it (SecureRouteRules.KeepWaitingForSession).
            _latch.CallbackArrived(serial, Time.realtimeSinceStartup);
            try
            {
                if (cb.m_eResult != EResult.k_EResultOK || cb.m_cubTicket <= 0 || cb.m_rgubTicket == null)
                {
                    Plugin.Log.LogWarning($"[STEAM-AUTH] ticket callback failed: {cb.m_eResult}");
                    EndTicket(serial, "callback failed");
                    return;
                }
                string hex = BitConverter.ToString(cb.m_rgubTicket, 0, cb.m_cubTicket).Replace("-", "");
                Plugin.Log.LogInfo($"[STEAM-AUTH] web ticket minted ({cb.m_cubTicket} bytes) — exchanging for session");
                ApiClient.PostSteamAuth(hex, outcome => EndTicket(serial, outcome));
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[STEAM-AUTH] ticket handling error: {ex.Message}");
                EndTicket(serial, "handling error");
            }
        }

        /// <summary>The held ticket's exchange has ended (`outcome` names how):
        /// cancel the ticket with Steam, and only then release the one-ticket
        /// latch (a failed cancel keeps it; SecureRouteRules.TicketLatch). A
        /// serial that is no longer the held ticket's (already ended, or
        /// superseded) changes nothing, so an end reported twice, or late,
        /// can never release a newer ticket.</summary>
        internal static void EndTicket(int serial, string outcome)
        {
            string line = _latch.End(serial, outcome, CancelHeldTicket, out bool failed);
            if (line == null) return;
            if (failed) Plugin.Log.LogWarning(line);
            else Plugin.Log.LogInfo(line);
        }

        /// <summary>Cancel the held handle with Steam: false when there is no
        /// handle, and a failure THROWS, so the latch sees it and keeps the
        /// handle.</summary>
        private static bool CancelHeldTicket()
        {
            if (_ticket.m_HAuthTicket == 0) return false;
            SteamUser.CancelAuthTicket(_ticket);
            return true;
        }

        public static void SetSession(string token, int expiresInSeconds)
        {
            if (string.IsNullOrEmpty(token)) return;
            SessionToken = token;
            _sessionExpiresAt = Time.realtimeSinceStartup + Mathf.Max(600, expiresInSeconds);
            Plugin.Log.LogInfo($"[STEAM-AUTH] session established (expires in {expiresInSeconds}s)");
        }

        /// <summary>Witness lever only (board row 27 round 2, [Broadcast]
        /// TestStaleToken, broadcast identity): replace the held token with one
        /// the server has never issued, keeping the local expiry, so the seat
        /// holds exactly what a server-dropped session looks like from here: a
        /// nonempty, locally fresh token the server refuses. No-op without a
        /// session.</summary>
        internal static bool ReplaceTokenForWitness(string token)
        {
            if (string.IsNullOrEmpty(SessionToken) || string.IsNullOrEmpty(token)) return false;
            SessionToken = token;
            return true;
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
