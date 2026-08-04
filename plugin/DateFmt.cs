using System;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>Central date-ORDER formatting (Sid Aug-3 item 9). Every plain
    /// user-visible date in the mod routes through here so one Settings picker
    /// (Plugin.UiDateFormat: MDY default / DMY / YMD) reorders them all.
    /// Digits-only + InvariantCulture (#47: locale month names render as
    /// squares in the Gravity SDF font). Deliberately NOT used by: wire/ISO
    /// timestamps (server contracts), report-room ids (#174 durable identity),
    /// filenames, and the Tournaments tab's richer ISO/US/EU slot-time
    /// setting, which keeps its own knob.</summary>
    internal static class DateFmt
    {
        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        private static string Order()
        {
            try
            {
                string v = Plugin.UiDateFormat?.Value;
                return (v == "DMY" || v == "YMD") ? v : "MDY";
            }
            catch { return "MDY"; }
        }

        /// <summary>Full date, 4-digit year: 8/23/2026 | 23/8/2026 | 2026-08-23.</summary>
        public static string Full(DateTime d)
        {
            switch (Order())
            {
                case "DMY": return d.ToString("d/M/yyyy", Inv);
                case "YMD": return d.ToString("yyyy-MM-dd", Inv);
                default:    return d.ToString("M/d/yyyy", Inv);
            }
        }

        /// <summary>Full date, 2-digit year: 8/23/26 | 23/8/26 | 26-08-23.
        /// (YMD keeps a 2-digit year for width parity with the sites that
        /// chose yy deliberately — those cells are narrow.)</summary>
        public static string FullShortYear(DateTime d)
        {
            switch (Order())
            {
                case "DMY": return d.ToString("d/M/yy", Inv);
                case "YMD": return d.ToString("yy-MM-dd", Inv);
                default:    return d.ToString("M/d/yy", Inv);
            }
        }

        /// <summary>Short month/day form: 8/23 | 23/8 | 08-23 (YMD's
        /// month-first order preserved with its dash style).</summary>
        public static string Short(DateTime d)
        {
            switch (Order())
            {
                case "DMY": return d.ToString("d/M", Inv);
                case "YMD": return d.ToString("MM-dd", Inv);
                default:    return d.ToString("M/d", Inv);
            }
        }
    }
}
