using System;
using HarmonyLib;

namespace CompetitiveRounds
{
    /// <summary>
    /// Keeps the Steam login ticket out of LogOutput.log and Player.log.
    ///
    /// ROUNDS' own Steam runtime (FriendlyFoe.Steam.SteamRuntimeManager.
    /// OnAuthCallback, in SteamPlatformRuntime.dll) writes the first web-API
    /// ticket delivered to its callback with
    /// <c>Debug.Log("Steam Login success. Session Ticket: " + hex)</c>. The
    /// plugin requests its own ticket (SteamAuth), so that hex can be the
    /// credential /api/v1/auth/steam exchanges, and both files ride every bug
    /// report and automatic upload. This rewrites the line to
    /// "Steam Login success. Session Ticket: [redacted len=N sha256=XXXXXXXX]"
    /// (LogScrub.TryRedactSteamTicketLine) before either file sees it.
    ///
    /// WHERE IT HOOKS. Debug.Log(object) calls
    /// <c>Debug.unityLogger.Log(LogType.Log, message)</c> through the ILogger
    /// interface, so the call reaches Logger.Log(LogType, object) on the
    /// Logger instance and cannot be inlined past it. The prefix runs before
    /// the log handler receives the message, and the handler is where Unity
    /// writes Player.log and raises the log-message event BepInEx copies into
    /// LogOutput.log: one rewrite, both files.
    ///
    /// WHEN. Applied by the per-class loop in Plugin.Awake with every other
    /// [HarmonyPatch] class, ahead of SteamAuth's first ticket request. A line
    /// the game wrote before this was applied stays in the local file; the
    /// second layer, LogScrub's pass 0 at the bundle's single scrub site,
    /// rewrites it before a bundle leaves the process.
    ///
    /// NEVER LOGS AND NEVER THROWS. It runs inside the logger, so a log call
    /// from here would re-enter it. A failure while building the redacted line
    /// still replaces the message, with the prefix and a bare "[redacted]",
    /// because passing the original through is the one outcome this class
    /// exists to prevent.
    /// </summary>
    [HarmonyPatch(typeof(UnityEngine.Logger), nameof(UnityEngine.Logger.Log),
                  new Type[] { typeof(UnityEngine.LogType), typeof(object) })]
    internal static class SteamTicketLogRedaction
    {
        // The parameter keeps the target's own name ("message") so Harmony
        // binds it.
        private static void Prefix(ref object message)
        {
            string s = message as string;
            if (s == null || !s.StartsWith(LogScrub.SteamTicketLinePrefix, StringComparison.Ordinal)) return;
            try
            {
                string redacted;
                if (LogScrub.TryRedactSteamTicketLine(s, out redacted)) message = redacted;
            }
            catch
            {
                message = LogScrub.SteamTicketLinePrefix + "[redacted]";
            }
        }
    }
}
