namespace CompetitiveRounds
{
    /// <summary>
    /// Every sentence the secure-route checks show a player (board row 27),
    /// each at its own I18n.Tr / I18n.TrF literal so tools/i18n_extract.py
    /// harvests it; this file is in the extractor's FILES list (#464).
    ///
    /// Nothing here reads Unity: tools/client-rules-harness compiles this file
    /// against a pass-through stand-in for I18n, so the exact English a player
    /// sees on each outcome is EXECUTED there, not asserted about (#391). No
    /// sentence tells the player to restart the game: the button retries the
    /// secure connection itself and a timer keeps retrying it.
    /// </summary>
    internal static class SecureRouteText
    {
        internal static string Checking()
        {
            return I18n.Tr("Checking the secure connection...");
        }

        internal static string RestoredOpeningPortal()
        {
            return I18n.Tr("Secure connection restored - opening the portal.");
        }

        /// <summary>An explicit plaintext BaseUrl (a LAN address or the old
        /// plaintext endpoint set by hand): no check runs for it, so the gate
        /// names the address instead of promising a retry.</summary>
        internal static string PlaintextOverride(string baseUrl)
        {
            return I18n.TrF("Can't open the portal - it only opens over a secure connection, and this install's server address is {0}.", baseUrl);
        }

        /// <summary>What failed and where, for a check the player is waiting
        /// on. `hostPort` is the address the check probed.</summary>
        internal static string Failure(SecureRouteRules.Outcome outcome, string hostPort, int timeoutSeconds, long httpCode)
        {
            switch (outcome)
            {
                case SecureRouteRules.Outcome.TimedOut:
                    return I18n.TrF("The secure connection to {0} timed out after {1} s. The portal needs it; the game keeps working on the backup connection.", hostPort, timeoutSeconds);
                case SecureRouteRules.Outcome.Refused:
                    return I18n.TrF("The secure connection to {0} was refused. The portal needs it; the game keeps working on the backup connection.", hostPort);
                case SecureRouteRules.Outcome.NameNotFound:
                    return I18n.TrF("The secure connection to {0} failed: the address could not be looked up. The portal needs it; the game keeps working on the backup connection.", hostPort);
                case SecureRouteRules.Outcome.SecurityCheckFailed:
                    return I18n.TrF("The secure connection to {0} failed its security check. The portal needs it; the game keeps working on the backup connection.", hostPort);
                case SecureRouteRules.Outcome.ServerError:
                    return I18n.TrF("The secure connection to {0} answered with an error (HTTP {1}). The portal needs it; the game keeps working on the backup connection.", hostPort, httpCode);
                case SecureRouteRules.Outcome.NotTheServer:
                    return I18n.TrF("The secure connection to {0} answered, but not as the SCR server. The portal needs it; the game keeps working on the backup connection.", hostPort);
                default:
                    return I18n.TrF("The secure connection to {0} could not be opened. The portal needs it; the game keeps working on the backup connection.", hostPort);
            }
        }
    }
}
