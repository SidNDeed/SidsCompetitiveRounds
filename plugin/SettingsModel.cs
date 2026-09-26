using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 13 (v1.41.0, the settings page reorganisation): the part of the
    /// page model that needs no Unity, so tools/client-rules-harness can
    /// EXECUTE it rather than assert about it (#391). Four rules live here:
    /// how a row's painted string splits into its label and its value, which
    /// sub-tab each home id is, which rows a per-tab reset writes, and what
    /// each key does on the page (design 6.3).
    /// </summary>
    internal static class SettingsModel
    {
        /// <summary>The seven sub-tabs, in bar order. The home id is the
        /// descriptor's <c>home</c>; the body name is the GameObject the
        /// tab's rows are built under (the keyset manifest's sub_tab_body).</summary>
        internal static readonly string[] SubTabHomes =
            { "ingame", "chatmail", "sound", "visuals", "perf", "langmenus", "privacy" };
        internal static readonly string[] SubTabBodies =
            { "SubIngame", "SubChatMail", "SubSound", "SubVisuals", "SubPerf", "SubLangMenus", "SubPrivacy" };

        /// <summary>The home id or body name's index in bar order, or -1.</summary>
        internal static int SubTabIndex(string homeOrBody)
        {
            if (string.IsNullOrEmpty(homeOrBody)) return -1;
            for (int i = 0; i < SubTabHomes.Length; i++)
                if (string.Equals(SubTabHomes[i], homeOrBody, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(SubTabBodies[i], homeOrBody, StringComparison.OrdinalIgnoreCase))
                    return i;
            return -1;
        }

        /// <summary>The end of the rich-text tag that opens at
        /// <paramref name="i"/>, or -1 when the '&lt;' is plain text (no
        /// closing '&gt;' before the next '&lt;').</summary>
        private static int TagEnd(string s, int i)
        {
            for (int j = i + 1; j < s.Length; j++)
            {
                if (s[j] == '>') return j;
                if (s[j] == '<') return -1;
            }
            return -1;
        }

        /// <summary>
        /// Split a painted row string at its FIRST ':' outside a rich-text
        /// tag: "FPS counter: &lt;color=#88FF88&gt;ON&lt;/color&gt;" becomes the
        /// label "FPS counter" and the value "&lt;color=#88FF88&gt;ON&lt;/color&gt;".
        /// The first colon, not the last, because a value may carry one of its
        /// own (a time, a ratio) and the label never does. A string with no
        /// such colon returns false, an empty label and the whole string as the
        /// value: the control shows everything, nothing is lost.
        /// </summary>
        internal static bool SplitSettingLabel(string s, out string label, out string value)
        {
            label = "";
            value = s ?? "";
            if (string.IsNullOrEmpty(s)) return false;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '<')
                {
                    int end = TagEnd(s, i);
                    if (end > i) { i = end; continue; }
                }
                else if (c == ':')
                {
                    label = s.Substring(0, i).Trim();
                    value = s.Substring(i + 1).Trim();
                    return true;
                }
            }
            return false;
        }

        /// <summary>The string with every rich-text tag removed (the same tag
        /// rule as the split), trimmed.</summary>
        internal static string StripTags(string s)
        {
            if (string.IsNullOrEmpty(s)) return s ?? "";
            var sb = new StringBuilder(s.Length);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '<')
                {
                    int end = TagEnd(s, i);
                    if (end > i) { i = end; continue; }
                }
                sb.Append(c);
            }
            return sb.ToString().Trim();
        }

        /// <summary>
        /// The rows a per-tab reset writes: every descriptor whose home is the
        /// active sub-tab AND whose bulk_reset is set, in descriptor order.
        /// Both clauses are load-bearing (design section 6.4): without the home
        /// clause a reset on Sound rewrites every tab; without the bulk clause
        /// it writes server rows, the language (a page rebuild) and the
        /// player's own consent decisions. Privacy's set is empty by rule.
        /// </summary>
        internal static List<string> ResetSet(string home)
        {
            var keys = new List<string>();
            foreach (var d in SettingsDescriptors.All)
                if (d.Home == home && d.BulkReset)
                    keys.Add(d.Key);
            return keys;
        }

        /// <summary>A key the settings page acts on, already read from the
        /// device (design section 6.3). The page reads the keyboard into one
        /// of these each frame and hands it to <see cref="DispatchKey"/>; the
        /// driven-input harness hands it the same values with no keyboard, so
        /// a scripted key takes exactly the path a pressed one does.</summary>
        internal enum SettingsKey { None, Tab, ShiftTab, Up, Down, Left, Right, Enter, Space, Pin }

        /// <summary>Where a row activation came from. The source is kept to
        /// the end because the rule differs by source (design 6.3).</summary>
        internal enum SettingsActivation { Enter, Space }

        /// <summary>
        /// Whether a focused row of this kind (the descriptor's kind word, for
        /// example "DESTRUCTIVE") takes an activation from this source. Design
        /// 6.3's input table: Enter or Space activate an ACTION row or open a
        /// DROPDOWN; a DESTRUCTIVE row takes Enter only, at the arm and at the
        /// confirm, so Space - which the page otherwise treats like Enter -
        /// can never arm or confirm a deletion. Every other kind is stepped
        /// or toggled with Left and Right, never activated.
        /// </summary>
        internal static bool ActivationAccepts(string kind, SettingsActivation source)
        {
            switch (kind)
            {
                case "ACTION":
                case "DROPDOWN":
                case "DISCLOSURE":
                    return true;
                case "DESTRUCTIVE":
                    return source == SettingsActivation.Enter;
                default:
                    return false;
            }
        }

        /// <summary>
        /// Route one key to the page's action for it: Tab and Shift+Tab move
        /// between the sub-tabs (wrapping), Up and Down move the row focus,
        /// Left and Right step the focused row, Enter and Space activate it -
        /// each keeping its own source, never merged - and Pin pins the help
        /// pane. The page passes its own methods; the harness passes
        /// recorders.
        /// </summary>
        internal static void DispatchKey(SettingsKey key, int subTab, int tabs,
                                         Action<int> switchSubTab, Action<int> moveFocus, Action<int> step,
                                         Action<SettingsActivation> activate, Action togglePin)
        {
            if (tabs <= 0) return;
            switch (key)
            {
                case SettingsKey.Tab: switchSubTab((subTab + 1) % tabs); break;
                case SettingsKey.ShiftTab: switchSubTab((subTab + tabs - 1) % tabs); break;
                case SettingsKey.Up: moveFocus(-1); break;
                case SettingsKey.Down: moveFocus(1); break;
                case SettingsKey.Left: step(-1); break;
                case SettingsKey.Right: step(1); break;
                case SettingsKey.Enter: activate(SettingsActivation.Enter); break;
                case SettingsKey.Space: activate(SettingsActivation.Space); break;
                case SettingsKey.Pin: togglePin(); break;
            }
        }
    }
}
