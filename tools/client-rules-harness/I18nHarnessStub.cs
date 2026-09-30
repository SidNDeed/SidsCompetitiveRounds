using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>
    /// HARNESS-ONLY stand-in for plugin/I18n.cs, which reads Unity and cannot
    /// compile here. It carries exactly what plugin/SecureRouteText.cs and
    /// plugin/I18nCatalogues.cs call: Tr, TrF and RegisterCatalogue.
    ///
    /// Tr is the identity while HarnessLocale is "en", and otherwise looks the
    /// English up in the catalogue I18nCatalogues.Install registered for that
    /// locale, falling back to the English as the real Tr does. TrF formats
    /// the way the real one does: InvariantCulture over Tr(template), and the
    /// template itself when formatting throws. Nothing under plugin/ compiles
    /// this file; the plugin build has the real I18n.
    /// </summary>
    internal static class I18n
    {
        internal static string HarnessLocale = "en";

        private static readonly Dictionary<string, Dictionary<string, string>> _catalogues =
            new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);

        internal static void RegisterCatalogue(string locale, Dictionary<string, string> entries)
        {
            if (string.IsNullOrEmpty(locale) || entries == null) return;
            _catalogues[locale] = entries;
        }

        internal static bool HasCatalogue(string locale)
        {
            return locale != null && _catalogues.ContainsKey(locale);
        }

        internal static string Tr(string english)
        {
            if (english == null || HarnessLocale == "en") return english;
            Dictionary<string, string> cat;
            string v;
            if (_catalogues.TryGetValue(HarnessLocale, out cat) && cat.TryGetValue(english, out v)
                && !string.IsNullOrEmpty(v))
                return v;
            return english;
        }

        internal static string TrF(string template, params object[] args)
        {
            try { return string.Format(CultureInfo.InvariantCulture, Tr(template), args); }
            catch { return template; }
        }
    }
}
